/// Synapse DB — SQLite v15 스키마 (Dart 포팅).
///
/// Python engine/db.py v15와 동기화:
/// - posts 테이블 (v12): 마크다운 게시물 원본 보관
/// - sentences: post_id, position 컬럼 포함, retention 없음 (v13 폐기)
/// - node_mentions: 노드↔문장 역참조 (v12)
/// - node_categories: origin 컬럼 포함 (v14)
/// - aliases: origin 컬럼 포함 (v14)
/// - unresolved_tokens: 승인 대기 지시어 (v12)
/// - edges 테이블 없음 (v15 폐기)

import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;

const _schema = '''
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    markdown   TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sentences (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    text       TEXT    NOT NULL,
    role       TEXT    NOT NULL DEFAULT 'user' CHECK(role IN ('user', 'assistant')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS nodes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS node_mentions (
    node_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, sentence_id)
);

CREATE TABLE IF NOT EXISTS node_categories (
    node_id    INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    category   TEXT    NOT NULL,
    origin     TEXT    NOT NULL DEFAULT 'user' CHECK(origin IN ('user', 'ai', 'rule')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, category)
);

CREATE TABLE IF NOT EXISTS aliases (
    alias      TEXT    PRIMARY KEY,
    node_id    INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    origin     TEXT    NOT NULL DEFAULT 'user' CHECK(origin IN ('user', 'ai', 'rule')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS unresolved_tokens (
    sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    token       TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (sentence_id, token)
);

CREATE INDEX IF NOT EXISTS idx_sentences_role       ON sentences(role);
CREATE INDEX IF NOT EXISTS idx_sentences_post       ON sentences(post_id, position);
CREATE INDEX IF NOT EXISTS idx_nodes_name           ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_status         ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_mentions_node        ON node_mentions(node_id);
CREATE INDEX IF NOT EXISTS idx_mentions_sentence    ON node_mentions(sentence_id);
CREATE INDEX IF NOT EXISTS idx_nc_category          ON node_categories(category);
CREATE INDEX IF NOT EXISTS idx_nc_node              ON node_categories(node_id);
CREATE INDEX IF NOT EXISTS idx_aliases              ON aliases(alias);
CREATE INDEX IF NOT EXISTS idx_unresolved_sentence  ON unresolved_tokens(sentence_id);
''';

/// Open or create the Synapse database. v15 스키마.
Future<Database> openSynapseDb(String dataDir) async {
  final dbPath = p.join(dataDir, 'synapse.db');
  return openDatabase(
    dbPath,
    version: 15,
    onConfigure: (db) async {
      await db.execute('PRAGMA journal_mode = WAL');
      await db.execute('PRAGMA foreign_keys = ON');
    },
    onCreate: (db, version) async {
      final statements = _schema
          .split(';')
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty);
      for (final stmt in statements) {
        await db.execute(stmt);
      }
    },
    onOpen: (db) async {
      // 구 스키마 감지 시 삭제 후 재생성. (실사용자 데이터 있으면 백업 권고)
      if (!await _isCurrentSchema(db)) {
        await db.close();
        await deleteDatabase(dbPath);
        throw StateError(
          'Old schema detected (pre-v15). DB deleted. Please reopen to recreate.',
        );
      }
    },
  );
}

Future<bool> _isCurrentSchema(Database db) async {
  final tables = (await db.rawQuery(
    "SELECT name FROM sqlite_master WHERE type='table'",
  ))
      .map((r) => r['name'] as String)
      .toSet();

  if (tables.contains('sessions')) return false;
  if (tables.contains('edges')) return false; // v15: 폐기
  for (final required in const [
    'posts',
    'sentences',
    'nodes',
    'node_mentions',
    'node_categories',
    'aliases',
    'unresolved_tokens',
  ]) {
    if (!tables.contains(required)) return false;
  }

  Future<Set<String>> colsOf(String t) async =>
      (await db.rawQuery('PRAGMA table_info($t)'))
          .map((r) => r['name'] as String)
          .toSet();

  final sent = await colsOf('sentences');
  if (!sent.contains('role') || !sent.contains('post_id') || !sent.contains('position')) {
    return false;
  }
  if (sent.contains('retention')) return false; // v13 폐기

  final nodes = await colsOf('nodes');
  if (nodes.contains('category')) return false; // 구 스키마

  final nc = await colsOf('node_categories');
  if (!nc.contains('origin')) return false; // v14 설계

  final al = await colsOf('aliases');
  if (!al.contains('origin')) return false;

  return true;
}

/// Engine statistics.
class EngineStats {
  final int postsTotal;
  final int nodesTotal;
  final int nodesActive;
  final int mentionsTotal;
  final int categoriesTotal;
  final int aliasesTotal;
  final int sentencesTotal;
  final int sentencesUser;
  final int sentencesAssistant;
  final int unresolvedTotal;

  const EngineStats({
    required this.postsTotal,
    required this.nodesTotal,
    required this.nodesActive,
    required this.mentionsTotal,
    required this.categoriesTotal,
    required this.aliasesTotal,
    required this.sentencesTotal,
    required this.sentencesUser,
    required this.sentencesAssistant,
    required this.unresolvedTotal,
  });
}

Future<EngineStats> getStats(Database db) async {
  int count(List<Map<String, Object?>> r) => Sqflite.firstIntValue(r) ?? 0;

  return EngineStats(
    postsTotal: count(await db.rawQuery('SELECT COUNT(*) FROM posts')),
    nodesTotal: count(await db.rawQuery('SELECT COUNT(*) FROM nodes')),
    nodesActive: count(await db.rawQuery(
        "SELECT COUNT(*) FROM nodes WHERE status='active'")),
    mentionsTotal:
        count(await db.rawQuery('SELECT COUNT(*) FROM node_mentions')),
    categoriesTotal:
        count(await db.rawQuery('SELECT COUNT(*) FROM node_categories')),
    aliasesTotal: count(await db.rawQuery('SELECT COUNT(*) FROM aliases')),
    sentencesTotal:
        count(await db.rawQuery('SELECT COUNT(*) FROM sentences')),
    sentencesUser: count(await db.rawQuery(
        "SELECT COUNT(*) FROM sentences WHERE role='user'")),
    sentencesAssistant: count(await db.rawQuery(
        "SELECT COUNT(*) FROM sentences WHERE role='assistant'")),
    unresolvedTotal:
        count(await db.rawQuery('SELECT COUNT(*) FROM unresolved_tokens')),
  );
}

// ── CRUD helpers ─────────────────────────────────────────

/// 마크다운 게시물 저장 후 id 반환.
Future<int> insertPost(Database db, String markdown) async {
  return db.insert('posts', {'markdown': markdown});
}

/// 문장 저장. v15: post_id, position 지원, retention 없음.
Future<int> insertSentence(
  Database db,
  String text, {
  String role = 'user',
  int? postId,
  int position = 0,
}) async {
  return db.insert('sentences', {
    'text': text,
    'role': role,
    'post_id': postId,
    'position': position,
  });
}

/// Upsert a node: if same name exists, return existing id. Returns (id, isNew).
Future<(int, bool)> upsertNode(Database db, String name) async {
  final existing = await db.query(
    'nodes',
    where: "LOWER(name) = LOWER(?) AND status = 'active'",
    whereArgs: [name],
    orderBy: 'updated_at DESC',
    limit: 1,
  );

  if (existing.isNotEmpty) {
    final id = existing.first['id'] as int;
    return (id, false);
  }

  final id = await db.insert('nodes', {
    'name': name,
    'status': 'active',
  });
  return (id, true);
}

/// 노드↔문장 역참조 (문장 바구니 멤버십) INSERT. 중복 안전.
Future<bool> addNodeMention(Database db, int nodeId, int sentenceId) async {
  final rows = await db.rawInsert(
    'INSERT OR IGNORE INTO node_mentions (node_id, sentence_id) VALUES (?,?)',
    [nodeId, sentenceId],
  );
  return rows > 0;
}

/// 카테고리 INSERT. origin: user(사용자 명시) / ai(LLM 추론) / rule(결정론적 규칙).
Future<void> addNodeCategory(
  Database db,
  int nodeId,
  String? category, {
  String origin = 'user',
}) async {
  if (category == null || category.isEmpty) return;
  await db.insert(
    'node_categories',
    {'node_id': nodeId, 'category': category, 'origin': origin},
    conflictAlgorithm: ConflictAlgorithm.ignore,
  );
}

/// 별칭 INSERT.
Future<void> addAlias(
  Database db,
  String alias,
  int nodeId, {
  String origin = 'user',
}) async {
  await db.insert(
    'aliases',
    {'alias': alias.toLowerCase(), 'node_id': nodeId, 'origin': origin},
    conflictAlgorithm: ConflictAlgorithm.replace,
  );
}

Future<void> removeAlias(Database db, String alias) async {
  await db.delete('aliases', where: 'alias = ?', whereArgs: [alias.toLowerCase()]);
}

/// 치환 실패 지시어 기록 (유일한 승인 대기 테이블).
Future<bool> addUnresolved(Database db, int sentenceId, String token) async {
  final rows = await db.rawInsert(
    'INSERT OR IGNORE INTO unresolved_tokens (sentence_id, token) VALUES (?,?)',
    [sentenceId, token],
  );
  return rows > 0;
}

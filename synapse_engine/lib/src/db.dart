/// Synapse DB — SQLite v10 sessionless schema + node_categories many-to-many + connection management.
///
/// Direct port of engine/db.py.

import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;

const _schema = '''
CREATE TABLE IF NOT EXISTS sentences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    text            TEXT    NOT NULL,
    role            TEXT    NOT NULL DEFAULT 'user' CHECK(role IN ('user', 'assistant')),
    retention       TEXT    NOT NULL DEFAULT 'memory' CHECK(retention IN ('memory', 'daily')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS nodes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS node_categories (
    node_id    INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    category   TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, category)
);

CREATE TABLE IF NOT EXISTS edges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    label          TEXT,
    sentence_id    INTEGER REFERENCES sentences(id) ON DELETE SET NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_used      TEXT
);

CREATE TABLE IF NOT EXISTS aliases (
    alias   TEXT    PRIMARY KEY,
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sentences_role  ON sentences(role);
CREATE INDEX IF NOT EXISTS idx_nodes_name      ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_status    ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_nc_category     ON node_categories(category);
CREATE INDEX IF NOT EXISTS idx_nc_node         ON node_categories(node_id);
CREATE INDEX IF NOT EXISTS idx_edges_src       ON edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_tgt       ON edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_sentence  ON edges(sentence_id);
CREATE INDEX IF NOT EXISTS idx_aliases         ON aliases(alias);
''';

/// Open or create the Synapse database.
Future<Database> openSynapseDb(String dataDir) async {
  final dbPath = p.join(dataDir, 'synapse.db');
  return openDatabase(
    dbPath,
    version: 10,
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
      // Verify current schema; if outdated, recreate.
      if (!await _isCurrentSchema(db)) {
        await db.close();
        await deleteDatabase(dbPath);
        // Reopen will trigger onCreate.
        // Caller should call openSynapseDb again.
        throw StateError('Old schema detected. DB deleted. Please reopen.');
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

  if (!tables.contains('sentences')) return false;
  if (tables.contains('sessions')) return false;
  if (!tables.contains('node_categories')) return false;

  final sentCols = (await db.rawQuery('PRAGMA table_info(sentences)'))
      .map((r) => r['name'] as String)
      .toList();
  if (!sentCols.contains('role') || !sentCols.contains('retention')) {
    return false;
  }

  final edgeCols = (await db.rawQuery('PRAGMA table_info(edges)'))
      .map((r) => r['name'] as String)
      .toList();
  if (!edgeCols.contains('sentence_id')) return false;

  final nodeCols = (await db.rawQuery('PRAGMA table_info(nodes)'))
      .map((r) => r['name'] as String)
      .toList();
  if (nodeCols.contains('category')) return false; // old schema with category column
  return true;
}

/// Engine statistics.
class EngineStats {
  final int nodesTotal;
  final int nodesActive;
  final int edgesTotal;
  final int categoriesTotal;
  final int aliasesTotal;
  final int sentencesTotal;
  final int sentencesUser;
  final int sentencesAssistant;

  const EngineStats({
    required this.nodesTotal,
    required this.nodesActive,
    required this.edgesTotal,
    required this.categoriesTotal,
    required this.aliasesTotal,
    required this.sentencesTotal,
    required this.sentencesUser,
    required this.sentencesAssistant,
  });
}

Future<EngineStats> getStats(Database db) async {
  int _count(List<Map<String, Object?>> r) => Sqflite.firstIntValue(r) ?? 0;

  return EngineStats(
    nodesTotal: _count(await db.rawQuery('SELECT COUNT(*) FROM nodes')),
    nodesActive: _count(await db.rawQuery(
        "SELECT COUNT(*) FROM nodes WHERE status='active'")),
    edgesTotal: _count(await db.rawQuery('SELECT COUNT(*) FROM edges')),
    categoriesTotal:
        _count(await db.rawQuery('SELECT COUNT(*) FROM node_categories')),
    aliasesTotal: _count(await db.rawQuery('SELECT COUNT(*) FROM aliases')),
    sentencesTotal:
        _count(await db.rawQuery('SELECT COUNT(*) FROM sentences')),
    sentencesUser: _count(await db.rawQuery(
        "SELECT COUNT(*) FROM sentences WHERE role='user'")),
    sentencesAssistant: _count(await db.rawQuery(
        "SELECT COUNT(*) FROM sentences WHERE role='assistant'")),
  );
}

// ── CRUD helpers ─────────────────────────────────────────

Future<int> insertSentence(
  Database db,
  String text, {
  String role = 'user',
  String retention = 'memory',
}) async {
  return db.insert('sentences', {
    'text': text,
    'role': role,
    'retention': retention,
  });
}

/// Upsert a node: if same name exists, return existing id.
/// Returns (id, isNew).
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

/// Add a category to a node (duplicate-safe).
Future<void> addNodeCategory(Database db, int nodeId, String? category) async {
  if (category == null || category.isEmpty) return;
  await db.insert(
    'node_categories',
    {'node_id': nodeId, 'category': category},
    conflictAlgorithm: ConflictAlgorithm.ignore,
  );
}

Future<int> insertEdge(
  Database db, {
  required int sourceNodeId,
  required int targetNodeId,
  String? label,
  int? sentenceId,
}) async {
  return db.insert('edges', {
    'source_node_id': sourceNodeId,
    'target_node_id': targetNodeId,
    'label': label,
    'sentence_id': sentenceId,
  });
}

Future<void> addAlias(Database db, String alias, int nodeId) async {
  await db.insert(
    'aliases',
    {'alias': alias.toLowerCase(), 'node_id': nodeId},
    conflictAlgorithm: ConflictAlgorithm.replace,
  );
}

Future<void> removeAlias(Database db, String alias) async {
  await db.delete('aliases', where: 'alias = ?', whereArgs: [alias.toLowerCase()]);
}

// 9-table hypergraph schema, v22 2nd plan.
// Single source: docs/DESIGN_HYPERGRAPH.md §스키마.

const int schemaVersion = 1;

/// origin column CHECK clause shared by node_sentence_mentions,
/// node_category_mentions, sentence_categories, aliases.
const String _originCheck =
    "CHECK(origin IN ('user','ai','system','external'))";

/// Builds posts DDL with dynamic kind CHECK from EngineConfig.allowedKinds.
/// See docs/DESIGN_ENGINE.md §3.3.
String buildPostsDdl(List<String> allowedKinds) {
  if (allowedKinds.isEmpty) {
    throw ArgumentError('allowedKinds must contain at least one kind');
  }
  for (final kind in allowedKinds) {
    if (kind.contains("'") || kind.isEmpty) {
      throw ArgumentError('invalid kind: "$kind"');
    }
  }
  final inList = allowedKinds.map((k) => "'$k'").join(',');
  final defaultKind = allowedKinds.first;
  return '''
    CREATE TABLE posts (
      id          INTEGER PRIMARY KEY,
      kind        TEXT NOT NULL DEFAULT '$defaultKind'
                       CHECK(kind IN ($inList)),
      title       TEXT,
      source      TEXT,
      created_at  TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
  ''';
}

/// Static DDL for the other 8 tables. Order matters for FK resolution.
const List<String> staticDdl = [
  // sentences ─ post 에 반드시 속함. ON DELETE CASCADE 로 미아 방지.
  '''
  CREATE TABLE sentences (
    id          INTEGER PRIMARY KEY,
    post_id     INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL DEFAULT 0,
    text        TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'user'
                     CHECK(role IN ('user','assistant')),
    origin      TEXT
                     CHECK(origin IS NULL OR origin IN ('user','insight')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
  )
  ''',

  // nodes ─ name UNIQUE 아님 (동명이인 허용)
  '''
  CREATE TABLE nodes (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
  )
  ''',

  // node_sentence_mentions ─ 문장 하이퍼엣지 멤버십
  '''
  CREATE TABLE node_sentence_mentions (
    node_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    origin      TEXT NOT NULL DEFAULT 'system' $_originCheck,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, sentence_id)
  )
  ''',

  // categories ─ adjacency list, 19 대분류 시드 + 사용자 heading 공존
  '''
  CREATE TABLE categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    parent_id   INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (parent_id, name)
  )
  ''',

  // sentence_categories ─ 사용자 heading 말단 카테고리 ↔ 문장
  '''
  CREATE TABLE sentence_categories (
    sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    origin      TEXT NOT NULL DEFAULT 'user' $_originCheck,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (sentence_id, category_id)
  )
  ''',

  // node_category_mentions ─ 노드 ↔ 카테고리 단일 매핑
  '''
  CREATE TABLE node_category_mentions (
    node_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    origin      TEXT NOT NULL DEFAULT 'system' $_originCheck,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, category_id)
  )
  ''',

  // aliases ─ 별칭 하이퍼엣지. ai origin 미사용 (DESIGN_HYPERGRAPH §하이퍼엣지 ③).
  '''
  CREATE TABLE aliases (
    alias       TEXT PRIMARY KEY,
    node_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    origin      TEXT NOT NULL
                     CHECK(origin IN ('user','system','external')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
  )
  ''',

  // unresolved_tokens ─ 유일한 승인 대기 (origin 컬럼 없음)
  '''
  CREATE TABLE unresolved_tokens (
    sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    token       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (sentence_id, token)
  )
  ''',
];

/// Indexes called out in DESIGN_HYPERGRAPH inline comments.
const List<String> indexDdl = [
  'CREATE INDEX idx_categories_parent ON categories(parent_id)',
  'CREATE INDEX idx_sentence_categories_cat ON sentence_categories(category_id)',
  'CREATE INDEX idx_node_sentence_mentions_sentence ON node_sentence_mentions(sentence_id)',
  'CREATE INDEX idx_node_category_mentions_category ON node_category_mentions(category_id)',
];

/// Names of the 9 hypergraph tables (used by tests + introspection).
const List<String> tableNames = [
  'posts',
  'sentences',
  'nodes',
  'node_sentence_mentions',
  'categories',
  'sentence_categories',
  'node_category_mentions',
  'aliases',
  'unresolved_tokens',
];

import 'package:sqflite/sqflite.dart';

import '../models/graph_models.dart';

/// Direct lookup helpers for the redesigned retrieval pipeline (DESIGN_PIPELINE
/// §인출 파이프라인 — 2026-04-29 재설계).
///
/// These functions replace the old BFS layer expansion with deterministic
/// joins: keyword → node/category id → sentence rows in one shot. The orchestrator
/// in `flow/retrieve.dart` composes them.

/// Match keywords against `categories.name`. Exact match first, then a
/// substring fallback (LIKE %kw%) so a question like "건강" can pull every
/// sub-category whose name contains the keyword.
Future<Set<int>> matchStartCategories(
  Database db, {
  required Iterable<String> keywords,
  int substringLimit = 5,
}) async {
  final out = <int>{};
  final seen = <String>{};
  for (final kwRaw in keywords) {
    final kw = kwRaw.trim();
    if (kw.isEmpty || !seen.add(kw)) continue;

    final exact = await db.rawQuery(
      'SELECT id FROM categories WHERE name = ?',
      [kw],
    );
    if (exact.isNotEmpty) {
      for (final r in exact) {
        out.add(r['id'] as int);
      }
      continue;
    }
    final like = await db.rawQuery(
      'SELECT id FROM categories WHERE name LIKE ? LIMIT ?',
      ['%$kw%', substringLimit],
    );
    for (final r in like) {
      out.add(r['id'] as int);
    }
  }
  return out;
}

/// Path ① — sentences directly mentioning any of the start nodes. Each
/// returned [Mention] keeps `nodeId` so callers can fold the matched node
/// id back into the retrieved-set without an extra query.
Future<List<Mention>> collectMentionsForNodes(
  Database db, {
  required Set<int> nodeIds,
  Set<int> excludeSentenceIds = const {},
  int? limit,
}) async {
  if (nodeIds.isEmpty) return const [];
  final nodePh = List.filled(nodeIds.length, '?').join(',');
  final exclude = excludeSentenceIds.isEmpty
      ? ''
      : 'AND m.sentence_id NOT IN '
          '(${List.filled(excludeSentenceIds.length, '?').join(',')})';
  final cap = limit == null ? '' : 'LIMIT $limit';
  final rows = await db.rawQuery(
    '''
    SELECT m.node_id, m.sentence_id, m.origin,
           n.name AS node_name,
           s.text AS sentence_text,
           s.created_at AS sentence_created_at
    FROM node_sentence_mentions m
    JOIN nodes n     ON n.id = m.node_id
    JOIN sentences s ON s.id = m.sentence_id
    WHERE m.node_id IN ($nodePh)
      $exclude
    ORDER BY s.created_at ASC, s.id ASC
    $cap
    ''',
    [...nodeIds, ...excludeSentenceIds],
  );
  return rows
      .map((r) => Mention(
            nodeId: r['node_id'] as int,
            sentenceId: r['sentence_id'] as int,
            origin: r['origin'] as String? ?? 'system',
            nodeName: r['node_name'] as String?,
            sentenceText: r['sentence_text'] as String?,
            sentenceCreatedAt: r['sentence_created_at'] as String?,
          ))
      .toList(growable: false);
}

/// Path ② — sentences from sibling nodes that share at least one category
/// with the start nodes via `node_category_mentions`. The query stays a
/// single SQL round-trip so the retrieval pipeline avoids a per-node loop.
Future<List<Mention>> collectMentionsByCategorySharing(
  Database db, {
  required Set<int> nodeIds,
  Set<int> excludeSentenceIds = const {},
  int siblingLimit = 200,
  int? mentionLimit,
}) async {
  if (nodeIds.isEmpty) return const [];
  final startPh = List.filled(nodeIds.length, '?').join(',');
  // (1) sibling node ids: same category, not in start set.
  final siblingRows = await db.rawQuery(
    '''
    SELECT DISTINCT ncm2.node_id AS id
    FROM node_category_mentions ncm1
    JOIN node_category_mentions ncm2
         ON ncm1.category_id = ncm2.category_id
    WHERE ncm1.node_id IN ($startPh)
      AND ncm2.node_id NOT IN ($startPh)
    LIMIT ?
    ''',
    [...nodeIds, ...nodeIds, siblingLimit],
  );
  final siblingIds = {for (final r in siblingRows) r['id'] as int};
  if (siblingIds.isEmpty) return const [];
  return collectMentionsForNodes(
    db,
    nodeIds: siblingIds,
    excludeSentenceIds: excludeSentenceIds,
    limit: mentionLimit,
  );
}

/// Path ③ — sentences attached (via `sentence_categories`) to the recursive
/// subtree rooted at any of [categoryIds]. Co-mentioned nodes are folded
/// in so the orchestrator can also fold their ids into `retrievedNodeIds`.
/// Heading-only sentences (no node mention) come back with `nodeId == -1`.
Future<List<Mention>> collectMentionsByHeadingSubtree(
  Database db, {
  required Set<int> categoryIds,
  Set<int> excludeSentenceIds = const {},
}) async {
  if (categoryIds.isEmpty) return const [];

  // (1) recursive subtree expansion — single CTE seeded with every root.
  final rootPh = List.filled(categoryIds.length, '?').join(',');
  final subtreeRows = await db.rawQuery(
    '''
    WITH RECURSIVE sub(id) AS (
        SELECT id FROM categories WHERE id IN ($rootPh)
        UNION ALL
        SELECT c.id FROM categories c JOIN sub ON c.parent_id = sub.id
    )
    SELECT DISTINCT id FROM sub
    ''',
    categoryIds.toList(),
  );
  final allCatIds = {for (final r in subtreeRows) r['id'] as int};
  if (allCatIds.isEmpty) return const [];

  // (2) sentences attached to the subtree.
  final catPh = List.filled(allCatIds.length, '?').join(',');
  final excludeClause = excludeSentenceIds.isEmpty
      ? ''
      : 'AND s.id NOT IN '
          '(${List.filled(excludeSentenceIds.length, '?').join(',')})';
  final sentRows = await db.rawQuery(
    '''
    SELECT DISTINCT s.id AS sentence_id,
                    s.text AS sentence_text,
                    s.created_at AS sentence_created_at
    FROM sentence_categories sc
    JOIN sentences s ON s.id = sc.sentence_id
    WHERE sc.category_id IN ($catPh)
      $excludeClause
    ORDER BY s.created_at ASC, s.id ASC
    ''',
    [...allCatIds, ...excludeSentenceIds],
  );
  if (sentRows.isEmpty) return const [];

  final sentIds = <int>{};
  final sentenceText = <int, String>{};
  final sentenceCreated = <int, String?>{};
  for (final r in sentRows) {
    final sid = r['sentence_id'] as int;
    sentIds.add(sid);
    sentenceText[sid] = r['sentence_text'] as String;
    sentenceCreated[sid] = r['sentence_created_at'] as String?;
  }

  // (3) co-mentioned nodes per sentence.
  final sidPh = List.filled(sentIds.length, '?').join(',');
  final mentionRows = await db.rawQuery(
    '''
    SELECT m.sentence_id, m.node_id, n.name AS node_name
    FROM node_sentence_mentions m
    JOIN nodes n ON n.id = m.node_id
    WHERE m.sentence_id IN ($sidPh)
    ''',
    sentIds.toList(),
  );
  final byS = <int, List<({int nodeId, String nodeName})>>{};
  for (final r in mentionRows) {
    final sid = r['sentence_id'] as int;
    byS.putIfAbsent(sid, () => []).add(
          (nodeId: r['node_id'] as int, nodeName: r['node_name'] as String),
        );
  }

  final out = <Mention>[];
  for (final sid in sentIds) {
    final text = sentenceText[sid]!;
    final created = sentenceCreated[sid];
    final nodes = byS[sid] ?? const [];
    if (nodes.isEmpty) {
      out.add(Mention(
        nodeId: -1,
        nodeName: '',
        sentenceId: sid,
        sentenceText: text,
        sentenceCreatedAt: created,
      ));
    } else {
      for (final n in nodes) {
        out.add(Mention(
          nodeId: n.nodeId,
          nodeName: n.nodeName,
          sentenceId: sid,
          sentenceText: text,
          sentenceCreatedAt: created,
        ));
      }
    }
  }
  return out;
}

/// All `category_id`s that the given nodes are mentioned in. Used to feed
/// path ③ when the user's keyword matched a node first (and the node sits
/// inside a heading subtree).
Future<Set<int>> categoriesForNodes(
  Database db,
  Set<int> nodeIds,
) async {
  if (nodeIds.isEmpty) return const <int>{};
  final ph = List.filled(nodeIds.length, '?').join(',');
  final rows = await db.rawQuery(
    'SELECT DISTINCT category_id FROM node_category_mentions '
    'WHERE node_id IN ($ph)',
    nodeIds.toList(),
  );
  return {for (final r in rows) r['category_id'] as int};
}

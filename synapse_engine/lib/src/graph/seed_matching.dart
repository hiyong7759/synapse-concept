import 'package:sqflite/sqflite.dart';

import '../models/graph_models.dart';

/// Resolve question keywords to start node ids. Mirrors Python
/// `engine/retrieve.py::_match_start_nodes`: alias substring inside the raw
/// question first, then alias exact, then `nodes.name` exact, then `name LIKE`.
///
/// Returns `{nodeId: name}` — id is unique per node (the same node can match
/// multiple keywords but only appears once in the result).
Future<Map<int, String>> matchStartNodes(
  Database db, {
  required List<String> keywords,
  required String question,
}) async {
  final result = <int, String>{};
  final resolvedNames = <String>{};

  // (a) Alias substring scan against the raw question — catches aliases that
  // never made it into the tokenised keyword list (e.g. punctuation-glued).
  if (question.isNotEmpty) {
    final rows = await db.rawQuery(
      'SELECT a.alias, n.id, n.name FROM aliases a '
      'JOIN nodes n ON n.id = a.node_id',
    );
    for (final r in rows) {
      final alias = r['alias'] as String;
      if (question.contains(alias)) {
        final id = r['id'] as int;
        final name = r['name'] as String;
        result[id] = name;
        resolvedNames.add(name);
      }
    }
  }

  for (final kw in keywords) {
    if (kw.isEmpty || resolvedNames.contains(kw)) continue;

    // (b) Exact alias match.
    final aliasRow = await db.rawQuery(
      'SELECT n.id, n.name FROM aliases a '
      'JOIN nodes n ON n.id = a.node_id '
      'WHERE a.alias = ? LIMIT 1',
      [kw],
    );
    if (aliasRow.isNotEmpty) {
      final id = aliasRow.first['id'] as int;
      final name = aliasRow.first['name'] as String;
      result[id] = name;
      resolvedNames.add(name);
      continue;
    }

    // (c) Exact node name.
    final exactRows = await db.rawQuery(
      'SELECT id, name FROM nodes WHERE name = ?',
      [kw],
    );
    if (exactRows.isNotEmpty) {
      for (final r in exactRows) {
        final id = r['id'] as int;
        result[id] = r['name'] as String;
      }
      continue;
    }

    // (d) Fuzzy substring (LIKE), capped to keep noise down.
    final likeRows = await db.rawQuery(
      "SELECT id, name FROM nodes WHERE name LIKE ? LIMIT 5",
      ['%$kw%'],
    );
    for (final r in likeRows) {
      final id = r['id'] as int;
      final name = r['name'] as String;
      if (resolvedNames.contains(name)) continue;
      result[id] = name;
    }
  }

  return result;
}

/// Path-3 (heading subtree) seeds. Mirrors Python
/// `_match_start_categories` + `_get_sentences_by_category_ids`.
///
/// Walks every category subtree rooted at a category that mentions any
/// start node, then collects the sentences attached via `sentence_categories`
/// along with their co-mentioned nodes. Heading-only sentences (no node
/// mention at all) still surface as `Mention(nodeId: -1, nodeName: '')` so
/// the BFS caller can present them in the final context.
Future<HeadingSubtreeSeeds> headingSubtreeSeeds(
  Database db, {
  required Set<int> startNodeIds,
}) async {
  if (startNodeIds.isEmpty) {
    return const HeadingSubtreeSeeds(categoryIds: <int>{}, mentions: <Mention>[]);
  }

  final categoryIds = <int>{};
  for (final nodeId in startNodeIds) {
    final rows = await db.rawQuery(
      '''
      WITH RECURSIVE sub(id) AS (
          SELECT category_id FROM node_category_mentions WHERE node_id = ?
          UNION ALL
          SELECT c.id FROM categories c JOIN sub ON c.parent_id = sub.id
      )
      SELECT DISTINCT id FROM sub
      ''',
      [nodeId],
    );
    for (final r in rows) {
      categoryIds.add(r['id'] as int);
    }
  }
  if (categoryIds.isEmpty) {
    return const HeadingSubtreeSeeds(categoryIds: <int>{}, mentions: <Mention>[]);
  }

  // (1) Sentences attached to the subtree.
  final catPlaceholders = List.filled(categoryIds.length, '?').join(',');
  final sentRows = await db.rawQuery(
    '''
    SELECT DISTINCT s.id AS sentence_id,
                    s.text AS sentence_text,
                    s.created_at AS sentence_created_at
    FROM sentence_categories sc
    JOIN sentences s ON s.id = sc.sentence_id
    WHERE sc.category_id IN ($catPlaceholders)
    ''',
    categoryIds.toList(),
  );
  if (sentRows.isEmpty) {
    return HeadingSubtreeSeeds(categoryIds: categoryIds, mentions: const []);
  }

  final sentenceIds = <int>{};
  final sentenceText = <int, String>{};
  final sentenceCreated = <int, String?>{};
  for (final r in sentRows) {
    final sid = r['sentence_id'] as int;
    sentenceIds.add(sid);
    sentenceText[sid] = r['sentence_text'] as String;
    sentenceCreated[sid] = r['sentence_created_at'] as String?;
  }

  // (2) Co-mentioned nodes per sentence.
  final sidPlaceholders = List.filled(sentenceIds.length, '?').join(',');
  final mentionRows = await db.rawQuery(
    '''
    SELECT m.sentence_id, m.node_id, n.name AS node_name
    FROM node_sentence_mentions m
    JOIN nodes n ON n.id = m.node_id
    WHERE m.sentence_id IN ($sidPlaceholders)
    ''',
    sentenceIds.toList(),
  );
  final mentionsBySid = <int, List<({int nodeId, String nodeName})>>{};
  for (final r in mentionRows) {
    final sid = r['sentence_id'] as int;
    mentionsBySid
        .putIfAbsent(sid, () => [])
        .add((nodeId: r['node_id'] as int, nodeName: r['node_name'] as String));
  }

  final out = <Mention>[];
  for (final sid in sentenceIds) {
    final text = sentenceText[sid]!;
    final created = sentenceCreated[sid];
    final nodes = mentionsBySid[sid] ?? const [];
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
  return HeadingSubtreeSeeds(categoryIds: categoryIds, mentions: out);
}

/// Path-2 (axis-B) supplement. Mirrors Python `_get_category_supplement_nodes`.
///
/// "Same-category sibling" expansion: for every node id in [startNodeIds],
/// surface other node ids that share at least one category via
/// `node_category_mentions`. Already-visited ids are excluded.
Future<Set<int>> sameCategoryNodes(
  Database db, {
  required Set<int> startNodeIds,
  required Set<int> visitedNodeIds,
  int limit = 50,
}) async {
  if (startNodeIds.isEmpty) return const <int>{};
  final placeholders = List.filled(startNodeIds.length, '?').join(',');
  final rows = await db.rawQuery(
    '''
    SELECT DISTINCT ncm2.node_id
    FROM node_category_mentions ncm1
    JOIN node_category_mentions ncm2
         ON ncm1.category_id = ncm2.category_id
    WHERE ncm1.node_id IN ($placeholders)
      AND ncm2.node_id NOT IN ($placeholders)
    LIMIT ?
    ''',
    [...startNodeIds, ...startNodeIds, limit],
  );
  final result = <int>{};
  for (final r in rows) {
    final id = r['node_id'] as int;
    if (!visitedNodeIds.contains(id)) result.add(id);
  }
  return result;
}

/// Bundle returned by [headingSubtreeSeeds] — the category-id set drives
/// BFS's optional category-overlap filter, while [mentions] are folded
/// into the BFS pre-seed.
class HeadingSubtreeSeeds {
  const HeadingSubtreeSeeds({
    required this.categoryIds,
    required this.mentions,
  });
  final Set<int> categoryIds;
  final List<Mention> mentions;
}

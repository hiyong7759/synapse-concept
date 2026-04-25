import 'package:sqflite/sqflite.dart';

import '../models/graph_models.dart';

/// Path-1 BFS over `node_sentence_mentions`. Higher-level retrieval
/// (category-based seeds, heading subtree, retrieve-filter LLM) belongs
/// in `SynapseFlow` (F5+); this helper stays purely graph-level so the
/// reuse path (gabjil-style apps) can call it directly.
///
/// Mirrors the inner BFS loop in Python `engine/retrieve.py:503-536`.
/// Same input → same output (verified by the BFS scenario test).
Future<List<Mention>> bfsRetrieve(
  Database db, {
  required Set<int> startNodes,
  int maxLayers = 5,
}) async {
  if (startNodes.isEmpty) return const [];

  final visitedNodes = Set<int>.from(startNodes);
  final visitedSentences = <int>{};
  final mentions = <Mention>[];
  Set<int> current = Set<int>.from(startNodes);

  for (var layer = 0; layer < maxLayers; layer++) {
    final layerMentions = await _mentionsForNodes(
      db,
      current,
      visitedSentences,
    );
    if (layerMentions.isEmpty) break;

    mentions.addAll(layerMentions);
    for (final m in layerMentions) {
      visitedSentences.add(m.sentenceId);
    }

    final nextSentenceIds = layerMentions.map((m) => m.sentenceId).toSet();
    final coNodeIds = await _coMentionedNodeIds(db, nextSentenceIds);
    final newIds = coNodeIds.difference(visitedNodes);
    if (newIds.isEmpty) break;
    visitedNodes.addAll(newIds);
    current = newIds;
  }
  return mentions;
}

Future<List<Mention>> _mentionsForNodes(
  Database db,
  Set<int> nodeIds,
  Set<int> excludeSentenceIds,
) async {
  if (nodeIds.isEmpty) return const [];
  final nodePlaceholders = List.filled(nodeIds.length, '?').join(',');
  final excludeClause = excludeSentenceIds.isEmpty
      ? ''
      : 'AND m.sentence_id NOT IN '
          '(${List.filled(excludeSentenceIds.length, '?').join(',')})';
  final rows = await db.rawQuery(
    '''
    SELECT m.node_id, m.sentence_id, m.origin,
           n.name AS node_name, s.text AS sentence_text
    FROM node_sentence_mentions m
    JOIN nodes n      ON n.id = m.node_id
    JOIN sentences s  ON s.id = m.sentence_id
    WHERE m.node_id IN ($nodePlaceholders)
      $excludeClause
    ''',
    [...nodeIds, ...excludeSentenceIds],
  );
  return rows.map((r) => Mention(
        nodeId: r['node_id'] as int,
        sentenceId: r['sentence_id'] as int,
        origin: r['origin'] as String? ?? 'system',
        nodeName: r['node_name'] as String?,
        sentenceText: r['sentence_text'] as String?,
      ))
      .toList(growable: false);
}

Future<Set<int>> _coMentionedNodeIds(
  Database db,
  Set<int> sentenceIds,
) async {
  if (sentenceIds.isEmpty) return const <int>{};
  final placeholders = List.filled(sentenceIds.length, '?').join(',');
  final rows = await db.rawQuery(
    'SELECT DISTINCT node_id FROM node_sentence_mentions '
    'WHERE sentence_id IN ($placeholders)',
    sentenceIds.toList(),
  );
  return rows.map((r) => r['node_id'] as int).toSet();
}

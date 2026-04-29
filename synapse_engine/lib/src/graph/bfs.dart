import 'package:sqflite/sqflite.dart';

import '../models/graph_models.dart';

/// Optional sentence-level batch filter. Injected by callers that want
/// LLM-driven relevance pruning (synapse app passes a closure that calls
/// `LlmTasks.retrieveFilter`); reuse apps that don't have an LLM simply
/// don't pass it. Returns one bool per input — `false` drops the
/// matching candidate sentence from the next layer.
///
/// Batch shape (instead of one-call-per-sentence) lets the LLM compare
/// sentences against each other in a single round trip — cuts call
/// count by an order of magnitude and improves cross-sentence
/// consistency. The BFS chunks candidates so prompt size stays bounded.
///
/// Keeping this as a callback — rather than an `LlmTasks` import — is what
/// lets `bfs.dart` honour the dependency-injection split spelled out in
/// DESIGN_PRINCIPLES §1 원칙 11.
typedef MentionFilter = Future<List<bool>> Function(List<String> sentenceTexts);

/// BFS over the hypergraph, mirroring `engine/retrieve.py`.
///
/// **Path 1 (built-in)** — `node_sentence_mentions`: each layer expands to
/// nodes that co-mention a sentence with the current layer.
///
/// **Path 2 (axis-A pre-seed)** — heading subtree mentions resolved by
/// `seed_matching.dart::headingSubtreeSeeds`. Pass them as [seedMentions];
/// the BFS will treat their sentences as already-visited and seed layer 0
/// with their co-mentioned nodes.
///
/// **Path 3 (axis-B post-supplement)** — same-category sibling nodes
/// resolved by `seed_matching.dart::sameCategoryNodes`. Pass them as
/// [supplementNodes]; BFS runs one extra hop after the main loop ends.
///
/// **Stop condition** — collected sentence count ≥ [maxSentences] *or* no
/// new nodes to visit. We stop on sentence count rather than layer depth
/// because layer depth conveys nothing predictable about how saturated
/// the LLM context already is (DESIGN_PIPELINE §인출).
///
/// **Node-explosion suppression** — every layer's candidates pass through
/// two filters before becoming the next [current] set:
///   (1) Frequency stopwords — nodes with `mention_count >= [stopwordThreshold]`
///       (computed once at the start) are dropped from expansion.
///   (2) Category overlap — if [startCategoryIds] is non-empty, only
///       candidate nodes that share at least one category with the start
///       set survive. Empty start categories means the filter is skipped
///       (heading-less corpora aren't penalised).
Future<List<Mention>> bfsRetrieve(
  Database db, {
  required Set<int> startNodes,
  List<Mention> seedMentions = const [],
  Set<int> supplementNodes = const {},
  Set<int> startCategoryIds = const {},
  MentionFilter? filter,
  int maxSentences = 50,
  int stopwordThreshold = 50,
}) async {
  if (startNodes.isEmpty && seedMentions.isEmpty) return const [];

  final stopwordIds = await _computeStopwords(db, stopwordThreshold);
  final allowedByCategory = startCategoryIds.isEmpty
      ? null // category filter disabled
      : await _nodesInCategories(db, startCategoryIds);

  final visitedNodes = Set<int>.from(startNodes);
  final visitedSentences = <int>{};
  final mentions = <Mention>[];

  // Pre-seed (axis-A) — fold heading-subtree mentions in before layer 0.
  for (final m in seedMentions) {
    if (visitedSentences.add(m.sentenceId)) {
      mentions.add(m);
    }
    if (m.nodeId > 0) visitedNodes.add(m.nodeId);
  }

  Set<int> current = {
    ...startNodes,
    ...seedMentions.where((m) => m.nodeId > 0).map((m) => m.nodeId),
  };

  while (current.isNotEmpty && mentions.length < maxSentences) {
    final layerCandidates = await _mentionsForNodes(
      db,
      current,
      visitedSentences,
    );
    if (layerCandidates.isEmpty) break;

    final accepted = await _applyFilter(layerCandidates, filter);
    if (accepted.isEmpty) break;

    for (final m in accepted) {
      if (mentions.length >= maxSentences) break;
      if (visitedSentences.add(m.sentenceId)) {
        mentions.add(m);
      }
    }
    if (mentions.length >= maxSentences) break;

    final nextSentenceIds = accepted.map((m) => m.sentenceId).toSet();
    final coNodeIds = await _coMentionedNodeIds(db, nextSentenceIds);
    final newIds = <int>{
      for (final id in coNodeIds.difference(visitedNodes))
        if (!stopwordIds.contains(id) &&
            (allowedByCategory == null || allowedByCategory.contains(id)))
          id,
    };
    if (newIds.isEmpty) break;
    visitedNodes.addAll(newIds);
    current = newIds;
  }

  // Post-supplement (axis-B) — same-category siblings get one extra hop.
  if (supplementNodes.isNotEmpty && mentions.length < maxSentences) {
    final supplement = supplementNodes.difference(visitedNodes);
    if (supplement.isNotEmpty) {
      final extra = await _mentionsForNodes(
        db,
        supplement,
        visitedSentences,
      );
      final accepted = await _applyFilter(extra, filter);
      for (final m in accepted) {
        if (mentions.length >= maxSentences) break;
        if (visitedSentences.add(m.sentenceId)) {
          mentions.add(m);
        }
      }
      visitedNodes.addAll(supplement);
    }
  }

  return mentions;
}

/// Chunk size when passing candidate sentences to the batch filter.
/// Smaller batches let small Korean LLMs (Gemma 4 E2B) keep the
/// per-sentence `o`/`x` marks consistent — earlier 10-batch runs drifted
/// into prose / mismatched mark counts on cluttered prompts and the
/// filter ended up keeping everything via the fallback. 5 still cuts
/// LLM calls 10× from the per-sentence baseline (50 → ≤10) while staying
/// well inside the model's response-quality envelope.
const int _filterBatchSize = 5;

Future<List<Mention>> _applyFilter(
  List<Mention> candidates,
  MentionFilter? filter,
) async {
  if (filter == null) return candidates;
  // Sentence-level dedup — the same sentence can surface through multiple
  // co-mention paths and we don't want the LLM seeing it twice.
  final seenSentence = <int>{};
  final mentionsToFilter = <Mention>[];
  final passthrough = <Mention>[];
  for (final m in candidates) {
    if (m.sentenceText == null) {
      passthrough.add(m);
      continue;
    }
    if (!seenSentence.add(m.sentenceId)) continue;
    mentionsToFilter.add(m);
  }

  final chunks = <List<Mention>>[];
  for (var i = 0; i < mentionsToFilter.length; i += _filterBatchSize) {
    chunks.add(
      mentionsToFilter.skip(i).take(_filterBatchSize).toList(growable: false),
    );
  }

  // Chunk-level parallelism. The synapse app's filter callback ultimately
  // funnels into a single llamadart instance (which serialises generate
  // calls to keep its KV cache consistent), so wall-clock gain here is
  // modest — but Future.wait still removes the await-loop overhead and
  // lets reuse apps that wire a thread-safe backend reap real concurrency.
  final results = await Future.wait(chunks.map((chunk) async {
    final texts = chunk.map((m) => m.sentenceText!).toList(growable: false);
    final keeps = await filter(texts);
    final kept = <Mention>[];
    for (var j = 0; j < chunk.length; j++) {
      // Defensive: if the filter returned a shorter list than asked (parser
      // tolerance + LLM cutoff), treat missing slots as keep.
      final keep = j < keeps.length ? keeps[j] : true;
      if (keep) kept.add(chunk[j]);
    }
    return kept;
  }));

  final out = <Mention>[...passthrough];
  for (final kept in results) {
    out.addAll(kept);
  }
  return out;
}

Future<Set<int>> _computeStopwords(Database db, int threshold) async {
  if (threshold <= 0) return const <int>{};
  final rows = await db.rawQuery(
    'SELECT node_id FROM node_sentence_mentions '
    'GROUP BY node_id HAVING COUNT(*) >= ?',
    [threshold],
  );
  return rows.map((r) => r['node_id'] as int).toSet();
}

Future<Set<int>> _nodesInCategories(
  Database db,
  Set<int> categoryIds,
) async {
  if (categoryIds.isEmpty) return const <int>{};
  final placeholders = List.filled(categoryIds.length, '?').join(',');
  final rows = await db.rawQuery(
    'SELECT DISTINCT node_id FROM node_category_mentions '
    'WHERE category_id IN ($placeholders)',
    categoryIds.toList(),
  );
  return rows.map((r) => r['node_id'] as int).toSet();
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
           n.name AS node_name,
           s.text AS sentence_text,
           s.created_at AS sentence_created_at
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
        sentenceCreatedAt: r['sentence_created_at'] as String?,
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

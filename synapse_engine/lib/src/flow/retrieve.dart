import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:sqflite/sqflite.dart';

import '../graph/lookup.dart';
import '../graph/seed_matching.dart' show matchStartNodes;
import '../kiwi/kiwi_wasm.dart';
import '../llm/tasks.dart';
import '../models/graph_models.dart';

/// Result bundle for [retrieveForQuestion]. `contextSentenceIds` is parallel
/// to `contexts` so the caller can persist the retrieve cache for later
/// `[⬆ 통찰로 승격]` actions without an extra query.
class RetrieveResult {
  const RetrieveResult({
    required this.contexts,
    required this.contextSentenceIds,
    required this.retrievedNodeIds,
    required this.timings,
  });

  final List<ContextSentence> contexts;
  final List<int> contextSentenceIds;
  final Set<int> retrievedNodeIds;
  final RetrieveTimings timings;
}

/// Per-stage millisecond timings exposed for the synapse-app debug overlay.
class RetrieveTimings {
  const RetrieveTimings({
    required this.expandMs,
    required this.matchMs,
    required this.collectMs,
    required this.filterMs,
  });
  final int expandMs;
  final int matchMs;
  final int collectMs;
  final int filterMs;
}

/// Run the redesigned retrieval pipeline (DESIGN_PIPELINE §인출):
///
/// 1. Expand the question into keywords (Kiwi + retrieve-expand LLM).
/// 2. Direct lookup → start node ids + start category ids.
/// 3. Collect sentences via the three paths (① mentions, ② category
///    sharing, ③ heading subtree). Order is fixed; later paths skip
///    sentences already collected.
/// 4. Optional retrieve-filter LLM batch removes off-topic sentences.
///
/// LLM is best-effort: missing or failing tasks degrade to "skip filter"
/// rather than empty results, matching DESIGN_PRINCIPLES §1 원칙 11.
Future<RetrieveResult> retrieveForQuestion(
  Database db, {
  required String question,
  required KiwiBackend kiwi,
  LlmTasks? llm,
  int maxSentences = 500,
}) async {
  final stage = Stopwatch()..start();

  // ── 1. expand + filter keywords ──────────────────────────
  final candidates = await _expandKeywords(question, kiwi: kiwi, llm: llm);
  final expandMs = stage.elapsedMilliseconds;

  stage..reset()..start();
  final keywords = await _filterKeywords(candidates, llm, question);
  final filterMs = stage.elapsedMilliseconds;

  // ── 2. lookup ─────────────────────────────────────────────
  // matchStartNodes and matchStartCategories are independent — run in
  // parallel. categoriesForNodes depends on startNodeIds so it stays
  // sequential.
  stage..reset()..start();
  final matched = await Future.wait([
    matchStartNodes(db, keywords: keywords, question: question),
    matchStartCategories(db, keywords: keywords),
  ]);
  final startNodeMap = matched[0] as Map<int, String>;
  final startNodeIds = startNodeMap.keys.toSet();
  final keywordCategoryIds = matched[1] as Set<int>;
  final nodeCategoryIds = await categoriesForNodes(db, startNodeIds);
  final startCategoryIds = <int>{...keywordCategoryIds, ...nodeCategoryIds};
  final matchMs = stage.elapsedMilliseconds;

  // ── 3. collect ────────────────────────────────────────────
  stage..reset()..start();
  final mentions = <Mention>[];
  final seenSids = <int>{};

  void absorb(Iterable<Mention> chunk) {
    for (final m in chunk) {
      if (mentions.length >= maxSentences) break;
      if (seenSids.add(m.sentenceId)) mentions.add(m);
    }
  }

  // Path ①
  if (startNodeIds.isNotEmpty) {
    absorb(await collectMentionsForNodes(
      db,
      nodeIds: startNodeIds,
      limit: maxSentences,
    ));
  }
  // Path ②
  if (mentions.length < maxSentences && startNodeIds.isNotEmpty) {
    absorb(await collectMentionsByCategorySharing(
      db,
      nodeIds: startNodeIds,
      excludeSentenceIds: seenSids,
      mentionLimit: maxSentences - mentions.length,
    ));
  }
  // Path ③
  if (mentions.length < maxSentences && startCategoryIds.isNotEmpty) {
    absorb(await collectMentionsByHeadingSubtree(
      db,
      categoryIds: startCategoryIds,
      excludeSentenceIds: seenSids,
    ));
  }
  final collectMs = stage.elapsedMilliseconds;

  // ── compose result ────────────────────────────────────────
  final contexts = <ContextSentence>[];
  final contextSentenceIds = <int>[];
  final retrievedNodeIds = <int>{...startNodeIds};
  final dedup = <int>{};
  for (final m in mentions) {
    if (m.nodeId > 0) retrievedNodeIds.add(m.nodeId);
    if (!dedup.add(m.sentenceId)) continue;
    final text = m.sentenceText;
    if (text == null) continue;
    contexts.add(ContextSentence(
      text: text,
      role: 'user',
      createdAt: m.sentenceCreatedAt,
    ));
    contextSentenceIds.add(m.sentenceId);
  }

  if (kDebugMode) {
    // ignore: avoid_print
    print('[retrieve] kw_in=${candidates.length} kw_out=${keywords.length} '
        'startNodes=${startNodeIds.length} '
        'startCats=${startCategoryIds.length} '
        'kept=${contexts.length} '
        'expand=${expandMs}ms filter=${filterMs}ms '
        'match=${matchMs}ms collect=${collectMs}ms');
  }

  return RetrieveResult(
    contexts: contexts,
    contextSentenceIds: contextSentenceIds,
    retrievedNodeIds: retrievedNodeIds,
    timings: RetrieveTimings(
      expandMs: expandMs,
      matchMs: matchMs,
      collectMs: collectMs,
      filterMs: filterMs,
    ),
  );
}

Future<List<String>> _expandKeywords(
  String question, {
  required KiwiBackend kiwi,
  LlmTasks? llm,
}) async {
  final out = <String>[];
  final seen = <String>{};
  void add(String s) {
    final t = s.trim();
    if (t.isEmpty || !seen.add(t)) return;
    out.add(t);
  }

  if (llm != null) {
    try {
      for (final kw in await llm.retrieveExpand(question)) {
        add(kw);
      }
    } catch (_) {
      // LLM failure → fall through to deterministic only.
    }
  }
  for (final piece in question.split(RegExp(r'\s+'))) {
    add(piece);
  }
  try {
    for (final n in await kiwi.nouns(question)) {
      add(n);
    }
  } catch (_) {
    // Kiwi failure non-fatal — whitespace tokens are already in.
  }
  return out;
}

Future<List<String>> _filterKeywords(
  List<String> candidates,
  LlmTasks? llm,
  String question,
) async {
  if (llm == null || candidates.isEmpty) return candidates;
  try {
    final keeps = await llm.filterKeywords(question, candidates);
    final out = <String>[];
    for (var i = 0; i < candidates.length; i++) {
      final keep = i < keeps.length ? keeps[i] : true;
      if (keep) out.add(candidates[i]);
    }
    // Defensive: if the model dropped everything, fall back to the raw
    // list rather than yielding zero matches.
    return out.isEmpty ? candidates : out;
  } catch (e) {
    if (kDebugMode) {
      // ignore: avoid_print
      print('[filterKeywords ERROR] $e');
    }
    return candidates;
  }
}

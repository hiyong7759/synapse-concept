import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:sqflite/sqflite.dart';

import '../db/category_seed.dart';
import '../graph/bfs.dart' as bfs_impl;
import '../graph/ops.dart';
import '../graph/seed_matching.dart';
import '../kiwi/kiwi_wasm.dart';
import '../llm/tasks.dart';
import '../markdown/parser.dart';
import '../models/graph_models.dart';
import 'note_pipeline.dart';
import 'results.dart';

/// SynapseFlow — full F5 surface.
///
/// `noteAutosave` / `noteProcess` come from F5a; F5b adds `synapseTurn`
/// (retrieve-and-answer) and `promoteToInsight` (Hebbian hub creation).
///
/// Activation: only attached when `EngineConfig.reservedKinds` includes
/// both `'synapse'` and `'insight'` (DESIGN_ENGINE §3 — kind 유연성).
class SynapseFlow {
  SynapseFlow({
    required this.db,
    required this.graph,
    required KiwiBackend kiwi,
    LlmTasks? llm,
    int retrieveMaxSentences = 50,
    int retrieveStopwordThreshold = 50,
  })  : _kiwi = kiwi,
        _llm = llm,
        _maxSentences = retrieveMaxSentences,
        _stopwordThreshold = retrieveStopwordThreshold,
        _pipeline = NotePipeline(
          db: db,
          graph: graph,
          kiwi: kiwi,
          llm: llm,
        );

  final Database db;
  final GraphOps graph;
  final NotePipeline _pipeline;
  final KiwiBackend _kiwi;
  final LlmTasks? _llm;
  final int _maxSentences;
  final int _stopwordThreshold;

  // ── /note 4 paths ────────────────────────────────────────

  /// LLM-free debounced save. See [NotePipeline.autosave].
  Future<void> noteAutosave({
    required int postId,
    required String source,
    String? title,
  }) =>
      _pipeline.autosave(postId: postId, source: source, title: title);

  /// Full meaning-processing pass. See [NotePipeline.process].
  Future<NoteProcessResult> noteProcess({
    required int postId,
    required String source,
  }) =>
      _pipeline.process(postId: postId, source: source);

  // ── /synapse turn ───────────────────────────────────────

  /// One synapse Q/A turn — keyword expansion → seed matching → BFS over
  /// three paths → optional LLM filter → time-sorted answer composition →
  /// Q/A persistence. The returned `retrievedNodeIds` is the cache the UI
  /// passes back to [promoteToInsight] when the user keeps the answer.
  ///
  /// LLM tasks are best-effort: if `engine.llm` is null or any call fails
  /// gracefully, the turn falls back to Kiwi-only keyword matching and the
  /// answer becomes the time-ordered context dump (DESIGN_PRINCIPLES §1
  /// 원칙 11 — LLM is core but injected, not required).
  Future<SynapseTurnResult> synapseTurn({
    required String question,
    int? postId,
  }) async {
    // Per-stage timing (debug builds only). Decides which stage to
    // optimise next — see PLAN-20260429-SYN-synapse-perf.
    final total = Stopwatch()..start();
    final persist = Stopwatch();
    final stage = Stopwatch();

    persist.start();
    final pid = postId ?? await db.insert('posts', {'kind': 'synapse'});

    final qPosition = await _nextPosition(pid);
    final questionSentenceId = await db.insert('sentences', {
      'post_id': pid,
      'text': question,
      'role': 'user',
      'position': qPosition,
    });
    persist.stop();

    stage..reset()..start();
    final keywords = await _expandKeywords(question);
    final tExpand = stage.elapsedMilliseconds;

    stage..reset()..start();
    final startNodeMap = await matchStartNodes(
      db,
      keywords: keywords,
      question: question,
    );
    final startNodeIds = startNodeMap.keys.toSet();
    final subtree = await headingSubtreeSeeds(db, startNodeIds: startNodeIds);
    final supplement = await sameCategoryNodes(
      db,
      startNodeIds: startNodeIds,
      visitedNodeIds: startNodeIds,
    );
    final tMatch = stage.elapsedMilliseconds;

    stage..reset()..start();
    final llm = _llm;
    final filter = llm == null
        ? null
        : (List<String> sentences) async {
            try {
              return await llm.retrieveFilter(question, sentences);
            } catch (_) {
              // Filter failures must not silently drop content — keep all.
              return List<bool>.filled(sentences.length, true);
            }
          };
    final mentions = await bfs_impl.bfsRetrieve(
      db,
      startNodes: startNodeIds,
      seedMentions: subtree.mentions,
      supplementNodes: supplement,
      startCategoryIds: subtree.categoryIds,
      filter: filter,
      maxSentences: _maxSentences,
      stopwordThreshold: _stopwordThreshold,
    );
    final tBfs = stage.elapsedMilliseconds;

    final seenSids = <int>{};
    final contexts = <ContextSentence>[];
    final contextSentenceIds = <int>[];
    final retrievedNodeIds = <int>{...startNodeIds};
    for (final m in mentions) {
      if (m.nodeId > 0) retrievedNodeIds.add(m.nodeId);
      if (!seenSids.add(m.sentenceId)) continue;
      final text = m.sentenceText;
      if (text == null) continue;
      contexts.add(ContextSentence(
        text: text,
        role: 'user',
        createdAt: m.sentenceCreatedAt,
      ));
      contextSentenceIds.add(m.sentenceId);
    }

    stage..reset()..start();
    String answer;
    if (llm != null) {
      try {
        answer = await llm.synapseAnswer(
          question: question,
          contexts: contexts,
        );
      } catch (_) {
        answer = _fallbackAnswer(contexts);
      }
    } else {
      answer = _fallbackAnswer(contexts);
    }
    final tAnswer = stage.elapsedMilliseconds;

    persist.start();
    final aPosition = qPosition + 1;
    final answerSentenceId = await db.insert('sentences', {
      'post_id': pid,
      'text': answer,
      'role': 'assistant',
      'position': aPosition,
    });
    persist.stop();

    if (kDebugMode) {
      // ignore: avoid_print
      print('[synapseTurn] expand=${tExpand}ms match=${tMatch}ms '
          'bfs=${tBfs}ms answer=${tAnswer}ms '
          'persist=${persist.elapsedMilliseconds}ms '
          'total=${total.elapsedMilliseconds}ms '
          '(ctx=${contexts.length})');
    }

    return SynapseTurnResult(
      postId: pid,
      questionSentenceId: questionSentenceId,
      answerSentenceId: answerSentenceId,
      answer: answer,
      retrievedNodeIds: retrievedNodeIds.toList()..sort(),
      contextSentenceIds: contextSentenceIds,
    );
  }

  // ── /promote ────────────────────────────────────────────

  /// Wraps [body] in a brand-new `kind='insight'` post and Hebbian-links
  /// every node in [snapshotNodeIds] to every sentence the markdown
  /// parser produces. Body-derived Kiwi nouns are also folded in (UNIQUE
  /// conflict on `(node_id, sentence_id)` simply skips dupes).
  ///
  /// Title falls back to the first non-blank line of the body.
  Future<InsightResult> promoteToInsight({
    required String body,
    required List<int> snapshotNodeIds,
    String? title,
  }) async {
    if (body.trim().isEmpty) {
      throw ArgumentError('promoteToInsight requires non-empty body');
    }
    final resolvedTitle = title ?? _firstLine(body);
    final lines = parseMarkdown(body);

    final newPostId = await db.insert('posts', {
      'kind': 'insight',
      'title': resolvedTitle,
      'source': body,
    });

    var position = 0;
    final sentenceIds = <int>[];
    var connectedRows = 0;

    for (final line in lines) {
      if (line.kind == ParsedKind.heading) continue;
      final sid = await db.insert('sentences', {
        'post_id': newPostId,
        'text': line.text,
        'role': 'user',
        'origin': 'insight',
        'position': position++,
      });
      sentenceIds.add(sid);

      // (a) Snapshot nodes — bulk Hebbian links.
      for (final nodeId in snapshotNodeIds) {
        final added = await graph.addMention(
          nodeId: nodeId,
          sentenceId: sid,
          origin: 'system',
        );
        if (added) connectedRows++;
      }

      // (b) Kiwi-extracted nodes from the body.
      final nouns = await _kiwi.nouns(line.text);
      for (final name in nouns) {
        if (name.isEmpty) continue;
        final newNodeId = await graph.upsertNode(name);
        final added = await graph.addMention(
          nodeId: newNodeId,
          sentenceId: sid,
          origin: 'system',
        );
        if (added) connectedRows++;
      }
    }

    if (sentenceIds.isEmpty) {
      // Body had only headings (or was structurally empty after parsing).
      // Fall back to a single sentence so the insight isn't silently void.
      final sid = await db.insert('sentences', {
        'post_id': newPostId,
        'text': body.trim(),
        'role': 'user',
        'origin': 'insight',
        'position': 0,
      });
      sentenceIds.add(sid);
      for (final nodeId in snapshotNodeIds) {
        final added = await graph.addMention(
          nodeId: nodeId,
          sentenceId: sid,
          origin: 'system',
        );
        if (added) connectedRows++;
      }
    }

    return InsightResult(
      postId: newPostId,
      sentenceIds: sentenceIds,
      connectedNodeCount: connectedRows,
    );
  }

  // ── post management ─────────────────────────────────────

  /// Inserts an empty post of the given [kind] and returns the new id.
  /// `title` and `source` start NULL — UI fills them through the editor +
  /// autosave path. Reuse apps (synapse session, future kinds) share this
  /// method instead of each writing their own `db.insert`.
  Future<int> createPost({required String kind}) async {
    return db.insert('posts', {'kind': kind});
  }

  /// Newest first. [kind] filter is optional; null returns every post.
  Future<List<PostMeta>> listPosts({
    String? kind,
    int limit = 50,
    int offset = 0,
  }) async {
    final rows = await db.query(
      'posts',
      columns: ['id', 'kind', 'title', 'created_at', 'updated_at'],
      where: kind == null ? null : 'kind = ?',
      whereArgs: kind == null ? null : [kind],
      orderBy: 'updated_at DESC',
      limit: limit,
      offset: offset,
    );
    return rows
        .map((r) => PostMeta(
              id: r['id']! as int,
              kind: r['kind']! as String,
              title: r['title'] as String?,
              createdAt: r['created_at']! as String,
              updatedAt: r['updated_at']! as String,
            ))
        .toList(growable: false);
  }

  /// Single-post fetch hydrated with sentences for re-entry.
  Future<PostDetail> getPost(int postId) async {
    final postRows = await db.query(
      'posts',
      where: 'id = ?',
      whereArgs: [postId],
      limit: 1,
    );
    if (postRows.isEmpty) {
      throw StateError('post $postId does not exist');
    }
    final p = postRows.single;
    final sentenceRows = await db.query(
      'sentences',
      where: 'post_id = ?',
      whereArgs: [postId],
      orderBy: 'position ASC, id ASC',
    );
    return PostDetail(
      meta: PostMeta(
        id: p['id']! as int,
        kind: p['kind']! as String,
        title: p['title'] as String?,
        createdAt: p['created_at']! as String,
        updatedAt: p['updated_at']! as String,
      ),
      source: p['source'] as String?,
      sentences: sentenceRows
          .map((r) => SentenceRow(
                id: r['id']! as int,
                position: r['position']! as int,
                text: r['text']! as String,
                role: r['role']! as String,
                origin: r['origin'] as String?,
              ))
          .toList(growable: false),
    );
  }

  Future<void> updatePostTitle(int postId, String title) async {
    await db.update(
      'posts',
      {'title': title},
      where: 'id = ?',
      whereArgs: [postId],
    );
  }

  Future<void> deletePost(int postId) async {
    await db.delete('posts', where: 'id = ?', whereArgs: [postId]);
  }

  // ── graph view ──────────────────────────────────────────

  /// Snapshot of the hypergraph for the visualization layer
  /// (`/hypergraph` + F7d `/note` panel + F9 `/synapse` panel).
  ///
  /// Filter mutually exclusive — caller picks one shape:
  /// - **all**: no filter → entire hypergraph
  /// - **postId**: only sentences in that post + the nodes they mention
  /// - **nodeIds**: only those nodes + every sentence they appear in
  ///
  /// `degree`, `isInsight`, and `primaryCategoryCode` are pre-computed in
  /// SQL so vis-network can skip a second pass — node radius / glow / fill
  /// drop straight in. See `docs/DESIGN_UI.md §/hypergraph 동작 사양`.
  Future<GraphData> getGraph({int? postId, List<int>? nodeIds}) async {
    if (postId != null && nodeIds != null) {
      throw ArgumentError(
        'getGraph: pass postId OR nodeIds, not both',
      );
    }

    // Resolve the working sentence set first; everything else hangs off it.
    final List<Map<String, Object?>> sentenceRows;
    if (postId != null) {
      sentenceRows = await db.query(
        'sentences',
        where: 'post_id = ?',
        whereArgs: [postId],
        orderBy: 'post_id, position, id',
      );
    } else if (nodeIds != null) {
      if (nodeIds.isEmpty) return _emptyGraph;
      final placeholders = List.filled(nodeIds.length, '?').join(',');
      sentenceRows = await db.rawQuery(
        'SELECT s.* FROM sentences s '
        'WHERE s.id IN ('
        '  SELECT DISTINCT m.sentence_id FROM node_sentence_mentions m '
        '  WHERE m.node_id IN ($placeholders)'
        ') '
        'ORDER BY s.post_id, s.position, s.id',
        nodeIds,
      );
    } else {
      sentenceRows = await db.query(
        'sentences',
        orderBy: 'post_id, position, id',
      );
    }

    final sentences = sentenceRows
        .map((r) => GraphSentence(
              id: r['id']! as int,
              postId: r['post_id']! as int,
              text: r['text']! as String,
              role: r['role']! as String,
              origin: r['origin'] as String?,
            ))
        .toList(growable: false);

    if (sentences.isEmpty) return _emptyGraph;
    final sentenceIds = sentences.map((s) => s.id).toList(growable: false);
    final sentencePh = List.filled(sentenceIds.length, '?').join(',');

    // Mentions: every row whose sentence_id sits in the working set. When
    // the caller filtered by nodeIds, also constrain on node_id so the
    // mentions list doesn't bleed in unrelated nodes that share a sentence.
    final List<Map<String, Object?>> mentionRows;
    if (nodeIds != null) {
      final nodePh = List.filled(nodeIds.length, '?').join(',');
      mentionRows = await db.rawQuery(
        'SELECT node_id, sentence_id FROM node_sentence_mentions '
        'WHERE sentence_id IN ($sentencePh) AND node_id IN ($nodePh)',
        [...sentenceIds, ...nodeIds],
      );
    } else {
      mentionRows = await db.rawQuery(
        'SELECT node_id, sentence_id FROM node_sentence_mentions '
        'WHERE sentence_id IN ($sentencePh)',
        sentenceIds,
      );
    }
    final mentions = mentionRows
        .map((r) => GraphMention(
              nodeId: r['node_id']! as int,
              sentenceId: r['sentence_id']! as int,
            ))
        .toList(growable: false);

    if (mentions.isEmpty) {
      // Sentences exist but no node mentions — return sentences alone so
      // an empty post still renders in F7d (header + carrying sentence count).
      return GraphData(
        nodes: const [],
        sentences: sentences,
        mentions: const [],
        categories: const [],
        nodeCategories: const [],
      );
    }

    // Node ids appearing in the working mention set.
    final workingNodeIds = mentions.map((m) => m.nodeId).toSet().toList()
      ..sort();
    final nodePh = List.filled(workingNodeIds.length, '?').join(',');

    // Nodes — degree is the count of working mentions per node, isInsight
    // joins back to sentences.origin = 'insight' over the same working set.
    final nodeRows = await db.rawQuery(
      '''
      SELECT n.id, n.name,
        (SELECT COUNT(*) FROM node_sentence_mentions m
          WHERE m.node_id = n.id AND m.sentence_id IN ($sentencePh)) AS degree,
        EXISTS(
          SELECT 1 FROM node_sentence_mentions m
          JOIN sentences s ON s.id = m.sentence_id
          WHERE m.node_id = n.id
            AND m.sentence_id IN ($sentencePh)
            AND s.origin = 'insight'
        ) AS is_insight
      FROM nodes n
      WHERE n.id IN ($nodePh)
      ORDER BY n.id
      ''',
      [...sentenceIds, ...sentenceIds, ...workingNodeIds],
    );

    // node_category_mentions — one row per (node, category). Pick the
    // lowest category_id among seed roots as primaryCategoryCode.
    final ncRows = await db.rawQuery(
      'SELECT nc.node_id, nc.category_id, nc.origin '
      'FROM node_category_mentions nc '
      'WHERE nc.node_id IN ($nodePh)',
      workingNodeIds,
    );
    final nodeCategories = ncRows
        .map((r) => GraphNodeCategory(
              nodeId: r['node_id']! as int,
              categoryId: r['category_id']! as int,
              origin: r['origin']! as String,
            ))
        .toList(growable: false);

    // sentence_categories — fetch the full mapping (not just distinct
    // category_id) so the visualization layer can color sentence baskets
    // by their user-heading root.
    final scFullRows = await db.rawQuery(
      'SELECT sentence_id, category_id, origin FROM sentence_categories '
      'WHERE sentence_id IN ($sentencePh)',
      sentenceIds,
    );
    final sentenceCategories = scFullRows
        .map((r) => GraphSentenceCategory(
              sentenceId: r['sentence_id']! as int,
              categoryId: r['category_id']! as int,
              origin: r['origin']! as String,
            ))
        .toList(growable: false);

    // Categories — fetch every category referenced by working nodes plus
    // every category that appears as a sentence_categories row in the
    // working set (so user-heading hierarchy shows up too). Then walk
    // every category to its root via parent_id so the root rows are
    // also fetched for color attribution.
    final touchedCategoryIds = <int>{};
    for (final nc in nodeCategories) {
      touchedCategoryIds.add(nc.categoryId);
    }
    for (final sc in sentenceCategories) {
      touchedCategoryIds.add(sc.categoryId);
    }

    final List<GraphCategory> categories;
    if (touchedCategoryIds.isEmpty) {
      categories = const [];
    } else {
      // Walk parent_id chain so every ancestor (root included) is also
      // fetched. Visualization needs the root to attribute color
      // (seed-19 vs user-heading).
      final allCatIds = <int>{...touchedCategoryIds};
      var frontier = touchedCategoryIds.toList();
      while (frontier.isNotEmpty) {
        final ph = List.filled(frontier.length, '?').join(',');
        final rows = await db.rawQuery(
          'SELECT DISTINCT parent_id FROM categories '
          'WHERE id IN ($ph) AND parent_id IS NOT NULL',
          frontier,
        );
        final next = <int>[];
        for (final r in rows) {
          final pid = r['parent_id'] as int;
          if (allCatIds.add(pid)) next.add(pid);
        }
        frontier = next;
      }
      final catPh = List.filled(allCatIds.length, '?').join(',');
      final catRows = await db.rawQuery(
        'SELECT id, name, parent_id FROM categories '
        'WHERE id IN ($catPh) ORDER BY id',
        allCatIds.toList(),
      );
      categories = catRows
          .map((r) => GraphCategory(
                id: r['id']! as int,
                name: r['name']! as String,
                parentId: r['parent_id'] as int?,
                code: _seedRootCode(
                  name: r['name']! as String,
                  parentId: r['parent_id'] as int?,
                ),
              ))
          .toList(growable: false);
    }

    // primaryCategoryCode per node — first seed-root code among that
    // node's categories, ordered by category_id ascending so the result
    // is deterministic.
    //
    // LLM categorize attaches to a leaf (`BOD.disease` → disease row),
    // not to the seed root, so we walk parent_id up to the root before
    // reading `cat.code` — leaves have `code == null`. The category
    // ancestor chain was already fetched above into [categories].
    final categoryById = {for (final c in categories) c.id: c};
    final primaryByNode = <int, String>{};
    for (final nc in nodeCategories) {
      var cat = categoryById[nc.categoryId];
      while (cat != null && cat.code == null && cat.parentId != null) {
        cat = categoryById[cat.parentId!];
      }
      final code = cat?.code;
      if (code == null) continue;
      primaryByNode.putIfAbsent(nc.nodeId, () => code);
    }

    final nodes = nodeRows.map((r) {
      final id = r['id']! as int;
      return GraphNode(
        id: id,
        name: r['name']! as String,
        degree: (r['degree'] as int?) ?? 0,
        isInsight: ((r['is_insight'] as int?) ?? 0) == 1,
        primaryCategoryCode: primaryByNode[id],
      );
    }).toList(growable: false);

    return GraphData(
      nodes: nodes,
      sentences: sentences,
      mentions: mentions,
      categories: categories,
      nodeCategories: nodeCategories,
      sentenceCategories: sentenceCategories,
    );
  }

  static const GraphData _emptyGraph = GraphData(
    nodes: [],
    sentences: [],
    mentions: [],
    categories: [],
    nodeCategories: [],
  );

  // ── suggestion data ─────────────────────────────────────

  /// Top nodes mentioned in sentences from the last [daysBack] days,
  /// ordered by mention count (desc) then most-recent appearance. Used
  /// by `/synapse` empty-state suggestion chips to seed question
  /// templates from the user's own recent activity. Returns an empty
  /// list when the window holds no mentions — UI falls back to a
  /// guidance card.
  Future<List<RecentNode>> recentTopNodes({
    int limit = 5,
    int daysBack = 7,
  }) async {
    if (limit <= 0) return const [];
    final rows = await db.rawQuery(
      '''
      SELECT n.id AS id, n.name AS name, COUNT(*) AS cnt
      FROM node_sentence_mentions m
      JOIN nodes n ON n.id = m.node_id
      JOIN sentences s ON s.id = m.sentence_id
      WHERE s.created_at > datetime('now', ?)
      GROUP BY n.id
      ORDER BY cnt DESC, MAX(s.created_at) DESC
      LIMIT ?
      ''',
      ['-$daysBack days', limit],
    );
    return rows
        .map((r) => RecentNode(
              id: r['id']! as int,
              name: r['name']! as String,
              mentionCount: r['cnt']! as int,
            ))
        .toList(growable: false);
  }

  /// Returns the seed-root code for a category row when it's a top-level
  /// seed (parent_id IS NULL AND name is one of the 19 known codes).
  String? _seedRootCode({required String name, int? parentId}) {
    if (parentId != null) return null;
    for (final root in seedRoots19) {
      if (root.code == name) return name;
    }
    return null;
  }

  // ── helpers ─────────────────────────────────────────────

  Future<int> _nextPosition(int postId) async {
    final rows = await db.rawQuery(
      'SELECT COALESCE(MAX(position), -1) + 1 AS next '
      'FROM sentences WHERE post_id = ?',
      [postId],
    );
    return (rows.first['next'] as int?) ?? 0;
  }

  Future<List<String>> _expandKeywords(String question) async {
    final out = <String>[];
    final seen = <String>{};
    void add(String s) {
      final trimmed = s.trim();
      if (trimmed.isEmpty || !seen.add(trimmed)) return;
      out.add(trimmed);
    }

    final llm = _llm;
    if (llm != null) {
      try {
        final expanded = await llm.retrieveExpand(question);
        for (final kw in expanded) {
          add(kw);
        }
      } catch (_) {
        // LLM expand failure → fall back to deterministic sources only.
      }
    }
    for (final piece in question.split(RegExp(r'\s+'))) {
      add(piece);
    }
    try {
      final nouns = await _kiwi.nouns(question);
      for (final n in nouns) {
        add(n);
      }
    } catch (_) {
      // Kiwi miss is non-fatal — `out` already has whitespace-split tokens.
    }
    return out;
  }

  String _fallbackAnswer(List<ContextSentence> contexts) {
    if (contexts.isEmpty) return '관련 정보를 찾을 수 없습니다.';
    final sorted = [...contexts]
      ..sort((a, b) => (a.createdAt ?? '').compareTo(b.createdAt ?? ''));
    final lines = sorted.map((c) {
      final hint = c.dateHint;
      return hint == null ? c.text : '[$hint] ${c.text}';
    });
    return lines.join('\n');
  }

  String _firstLine(String body) {
    for (final raw in body.split('\n')) {
      final line = raw.trim();
      if (line.isEmpty) continue;
      // Strip leading markdown noise (#, -, etc.) so the title reads cleanly.
      return line.replaceFirst(RegExp(r'^#+\s*'), '').replaceFirst(
            RegExp(r'^[-*]\s+'),
            '',
          );
    }
    return body.trim();
  }
}

/// Lightweight summary used in `/note` sidebar listings.
class PostMeta {
  const PostMeta({
    required this.id,
    required this.kind,
    required this.title,
    required this.createdAt,
    required this.updatedAt,
  });
  final int id;
  final String kind;
  final String? title;
  final String createdAt;
  final String updatedAt;
}

/// Hydrated post + sentences, used for re-entry into `/note`.
class PostDetail {
  const PostDetail({
    required this.meta,
    required this.source,
    required this.sentences,
  });
  final PostMeta meta;
  final String? source;
  final List<SentenceRow> sentences;
}

class SentenceRow {
  const SentenceRow({
    required this.id,
    required this.position,
    required this.text,
    required this.role,
    required this.origin,
  });
  final int id;
  final int position;
  final String text;
  final String role;
  final String? origin;
}

/// Single row of [SynapseFlow.recentTopNodes]. The mention count
/// scopes the recency window the caller asked for, not the all-time
/// degree.
class RecentNode {
  const RecentNode({
    required this.id,
    required this.name,
    required this.mentionCount,
  });
  final int id;
  final String name;
  final int mentionCount;
}

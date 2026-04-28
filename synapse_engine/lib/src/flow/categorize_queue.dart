import 'package:sqflite/sqflite.dart';

import '../graph/ops.dart';
import '../llm/tasks.dart';

/// Background queue that classifies nodes into seed-19 categories without
/// blocking the autosave / ⌘S path.
///
/// Two enqueue surfaces:
///   - [enqueuePost] — autosave hook. Picks every node mentioned in the
///     post that has no `origin='ai'` category mention yet.
///   - [enqueueAll]  — boot-time backfill. Same SELECT, scoped to the
///     whole DB.
///
/// Internally a single async loop drains [_queued] one node at a time,
/// keeping `LlmTasks.categorize` calls serial so llamadart's KV-cache
/// prefix reuse stays warm (the system prompt is identical across calls).
/// Dedup via [_queued] + [_processing] sets so repeated autosave
/// triggers and a concurrent boot backfill don't double-classify a node.
///
/// Failures (LLM throw, unknown sub-code) leave the node uncategorized;
/// the next [enqueuePost] / [enqueueAll] re-picks it because the SELECT
/// filters on `origin='ai'` mentions, not attempts.
class CategorizeQueue {
  CategorizeQueue({
    required this.db,
    required this.graph,
    required this.llm,
  });

  final Database db;
  final GraphOps graph;
  final LlmTasks llm;

  final Set<int> _queued = <int>{};
  final Set<int> _processing = <int>{};
  Future<void>? _worker;
  bool _stopped = false;

  /// Pending + in-flight count. Drives the autosave-chip progress label.
  int get pendingCount => _queued.length + _processing.length;

  /// Adds a single node. Already-queued or in-flight nodes are ignored.
  void enqueueNode(int nodeId) {
    if (_stopped) return;
    if (_queued.contains(nodeId) || _processing.contains(nodeId)) return;
    _queued.add(nodeId);
    _ensureWorker();
  }

  /// Enqueues every node mentioned in [postId] that lacks an `origin='ai'`
  /// category mention. Call from the autosave path.
  Future<void> enqueuePost(int postId) async {
    final rows = await db.rawQuery(
      '''
      SELECT DISTINCT n.id
      FROM nodes n
      JOIN node_sentence_mentions m ON m.node_id = n.id
      JOIN sentences s ON s.id = m.sentence_id
      WHERE s.post_id = ?
        AND n.id NOT IN (
          SELECT node_id FROM node_category_mentions WHERE origin = 'ai'
        )
      ''',
      [postId],
    );
    for (final r in rows) {
      enqueueNode(r['id']! as int);
    }
  }

  /// Enqueues every node lacking an `origin='ai'` category mention.
  /// Idempotent — dedup keeps repeats out.
  Future<void> enqueueAll() async {
    final rows = await db.rawQuery(
      '''
      SELECT id FROM nodes
      WHERE id NOT IN (
        SELECT node_id FROM node_category_mentions WHERE origin = 'ai'
      )
      ''',
    );
    for (final r in rows) {
      enqueueNode(r['id']! as int);
    }
  }

  /// Stops accepting new work. The worker drains its current node and exits.
  void stop() {
    _stopped = true;
  }

  /// Waits until the queue is empty and the worker is idle. Tests use this
  /// to assert post-conditions; production callers don't await.
  Future<void> drain() async {
    while (_worker != null) {
      await _worker;
    }
  }

  void _ensureWorker() {
    if (_worker != null) return;
    _worker = _run().whenComplete(() {
      _worker = null;
    });
  }

  Future<void> _run() async {
    while (_queued.isNotEmpty && !_stopped) {
      final nodeId = _queued.first;
      _queued.remove(nodeId);
      _processing.add(nodeId);
      try {
        await _processNode(nodeId);
      } catch (_) {
        // Swallow — node stays uncategorized, next backfill re-picks it.
      } finally {
        _processing.remove(nodeId);
      }
    }
  }

  Future<void> _processNode(int nodeId) async {
    final nodeRows = await db.query(
      'nodes',
      columns: ['name'],
      where: 'id = ?',
      whereArgs: [nodeId],
      limit: 1,
    );
    if (nodeRows.isEmpty) return;
    final name = nodeRows.first['name']! as String;

    // Up to 3 sentences mentioning this node, oldest first. The categorize
    // prompt only needs a thin disambiguation window (LlmTasks.categorize
    // doc).
    final ctxRows = await db.rawQuery(
      '''
      SELECT s.text FROM sentences s
      JOIN node_sentence_mentions m ON m.sentence_id = s.id
      WHERE m.node_id = ?
      ORDER BY s.created_at
      LIMIT 3
      ''',
      [nodeId],
    );
    final contexts =
        ctxRows.map((r) => r['text']! as String).toList(growable: false);

    final codes = await llm.categorize(
      nodeName: name,
      contextSentences: contexts,
    );

    for (final code in codes) {
      final leafId = await _resolveSubCategoryId(code);
      if (leafId == null) continue;
      await graph.addCategoryMention(
        nodeId: nodeId,
        categoryId: leafId,
        origin: 'ai',
      );
    }
  }

  /// Resolves a `BOD.disease` style code to its `categories.id`. Returns
  /// null when the root or leaf is missing.
  Future<int?> _resolveSubCategoryId(String code) async {
    final dot = code.indexOf('.');
    if (dot <= 0 || dot == code.length - 1) return null;
    final rootName = code.substring(0, dot);
    final leafName = code.substring(dot + 1);

    final rootRows = await db.query(
      'categories',
      columns: ['id'],
      where: 'name = ? AND parent_id IS NULL',
      whereArgs: [rootName],
      limit: 1,
    );
    if (rootRows.isEmpty) return null;
    final rootId = rootRows.first['id']! as int;

    final leafRows = await db.query(
      'categories',
      columns: ['id'],
      where: 'name = ? AND parent_id = ?',
      whereArgs: [leafName, rootId],
      limit: 1,
    );
    return leafRows.isEmpty ? null : leafRows.first['id']! as int;
  }
}

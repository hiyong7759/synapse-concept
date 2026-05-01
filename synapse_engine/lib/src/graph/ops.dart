import 'package:sqflite/sqflite.dart';

import '../kiwi/kiwi_wasm.dart';
import '../kiwi/tokens.dart';
import '../models/graph_models.dart';
import 'lookup.dart' as lookup;
import 'typo.dart' as typo_impl;

/// Atomic graph operations. The lower half of the two-layer API
/// (DESIGN_ENGINE §2.3) — works without an LLM (원칙 11) and is callable
/// from any consumer (synapse app, gabjil, …).
///
/// 17 methods are implemented at F4. `splitNode` is a stub: node merging
/// is a `/review` approval path and needs the merge-history / undo design
/// from a separate milestone.
class GraphOps {
  GraphOps({required this.db, required KiwiBackend kiwi}) : _kiwi = kiwi;

  final Database db;
  final KiwiBackend _kiwi;

  // ── 노드 ──────────────────────────────────────────────

  /// Returns the id of an existing node matching [name] (alias hit first,
  /// then exact name match), or inserts a new row. `nodes.name` is NOT
  /// UNIQUE (동명이인 허용 — DESIGN_HYPERGRAPH §스키마), so the first match
  /// is reused.
  Future<int> upsertNode(String name) async {
    final aliasHits = await findNodesByAlias(name);
    if (aliasHits.isNotEmpty) return aliasHits.first.id;

    final byName = await db.query(
      'nodes',
      columns: ['id'],
      where: 'name = ?',
      whereArgs: [name],
      limit: 1,
    );
    if (byName.isNotEmpty) return byName.first['id'] as int;

    return db.insert('nodes', {'name': name});
  }

  Future<List<Node>> findNodesByAlias(String alias) async {
    final rows = await db.rawQuery(
      'SELECT n.id, n.name FROM nodes n '
      'JOIN aliases a ON a.node_id = n.id '
      'WHERE a.alias = ?',
      [alias],
    );
    return rows
        .map((r) => Node(id: r['id'] as int, name: r['name'] as String))
        .toList(growable: false);
  }

  Future<void> deleteNode(int nodeId) async {
    // ON DELETE CASCADE on mentions, aliases, node_category_mentions
    // takes care of the rest (PRAGMA foreign_keys=ON in engine.dart).
    await db.delete('nodes', where: 'id = ?', whereArgs: [nodeId]);
  }

  /// Stub. Splitting a previously-merged node back into two requires
  /// merge-history tracking which v22 schema does not yet model. Lands
  /// in a follow-up milestone alongside the /review undo design.
  Future<void> splitNode(int nodeId, Object spec) {
    throw UnimplementedError(
      'splitNode requires merge-history schema (follow-up milestone).',
    );
  }

  // ── 문장 바구니 ────────────────────────────────────────

  Future<int> addSentence({
    required int postId,
    required String text,
    String role = 'user',
    String? origin,
  }) async {
    return db.insert('sentences', {
      'post_id': postId,
      'text': text,
      'role': role,
      if (origin != null) 'origin': origin,
    });
  }

  /// Inserts a `node_sentence_mentions` row. Returns true if a new row
  /// was created, false if the (node_id, sentence_id) pair already
  /// existed (ConflictAlgorithm.ignore).
  Future<bool> addMention({
    required int nodeId,
    required int sentenceId,
    String origin = 'system',
  }) async {
    final rowId = await db.insert(
      'node_sentence_mentions',
      {
        'node_id': nodeId,
        'sentence_id': sentenceId,
        'origin': origin,
      },
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
    return rowId > 0;
  }

  /// Replaces the body of a sentence. Refuses if the sentence is a
  /// promoted insight (origin='insight') — DESIGN_HYPERGRAPH §하이퍼엣지 ④
  /// requires going through `/review` for those.
  Future<void> updateSentence(int sentenceId, String newText) async {
    final rows = await db.query(
      'sentences',
      columns: ['origin'],
      where: 'id = ?',
      whereArgs: [sentenceId],
      limit: 1,
    );
    if (rows.isEmpty) {
      throw StateError('sentence $sentenceId does not exist');
    }
    if (rows.first['origin'] == 'insight') {
      throw StateError(
        'cannot update insight sentence $sentenceId — '
        'use /review approval path',
      );
    }
    await db.update(
      'sentences',
      {'text': newText, 'updated_at': _now()},
      where: 'id = ?',
      whereArgs: [sentenceId],
    );
  }

  Future<void> deleteSentence(int sentenceId) async {
    await db.delete(
      'sentences',
      where: 'id = ?',
      whereArgs: [sentenceId],
    );
  }

  // ── 카테고리 바구니 ────────────────────────────────────

  /// Walks [segments] (each one a single category name, in root→leaf order)
  /// and ensures every segment is present in `categories`, creating missing
  /// rows as children of the previous segment. Returns the leaf id, or null
  /// when [segments] is null/empty.
  ///
  /// Takes `List<String>` so the parser can pass `headingPath` directly —
  /// no string join/split round-trip, no separator collision risk.
  Future<int?> upsertCategoryPath(List<String>? segments) async {
    if (segments == null) return null;
    final cleaned = segments
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList(growable: false);
    if (cleaned.isEmpty) return null;

    int? parentId;
    for (final segment in cleaned) {
      final whereClause = parentId == null
          ? 'name = ? AND parent_id IS NULL'
          : 'name = ? AND parent_id = ?';
      final whereArgs = parentId == null ? [segment] : [segment, parentId];
      final existing = await db.query(
        'categories',
        columns: ['id'],
        where: whereClause,
        whereArgs: whereArgs,
        limit: 1,
      );
      if (existing.isNotEmpty) {
        parentId = existing.first['id'] as int;
      } else {
        parentId = await db.insert('categories', {
          'name': segment,
          'parent_id': parentId,
        });
      }
    }
    return parentId;
  }

  Future<void> addSentenceCategory({
    required int sentenceId,
    required int categoryId,
    String origin = 'user',
  }) async {
    await db.insert(
      'sentence_categories',
      {
        'sentence_id': sentenceId,
        'category_id': categoryId,
        'origin': origin,
      },
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
  }

  Future<void> addCategoryMention({
    required int nodeId,
    required int categoryId,
    String origin = 'system',
  }) async {
    await db.insert(
      'node_category_mentions',
      {
        'node_id': nodeId,
        'category_id': categoryId,
        'origin': origin,
      },
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
  }

  // ── 별칭 바구니 ────────────────────────────────────────

  Future<void> addAlias({
    required String alias,
    required int nodeId,
    String origin = 'user',
  }) async {
    await db.insert(
      'aliases',
      {'alias': alias, 'node_id': nodeId, 'origin': origin},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> removeAlias(String alias) async {
    await db.delete('aliases', where: 'alias = ?', whereArgs: [alias]);
  }

  // ── 인출 ──────────────────────────────────────────────

  /// Thin pass-through for path ① — sentences directly mentioning any of
  /// the start nodes. Reuse apps that don't need the orchestrated retrieve
  /// flow (no LLM filter, no category-share expansion) call this for a
  /// pure node→sentence lookup. The full pipeline lives in
  /// [SynapseFlow.synapseTurn] / `flow/retrieve.dart`.
  Future<List<Mention>> mentionsForNodes({
    required Set<int> nodeIds,
    Set<int> excludeSentenceIds = const {},
    int? limit,
  }) =>
      lookup.collectMentionsForNodes(
        db,
        nodeIds: nodeIds,
        excludeSentenceIds: excludeSentenceIds,
        limit: limit,
      );

  Future<List<TypoCandidate>> findSuspectedTypos({
    int maxDist = 1,
    int minJamoLen = 6,
  }) =>
      typo_impl.findSuspectedTypos(
        db,
        maxDist: maxDist,
        minJamoLen: minJamoLen,
      );

  // ── 통계·디버깅 ────────────────────────────────────────

  Future<EngineStats> getStats() async {
    Future<int> count(String table) async => Sqflite.firstIntValue(
          await db.rawQuery('SELECT COUNT(*) FROM $table'),
        ) ??
        0;
    return EngineStats(
      postCount: await count('posts'),
      sentenceCount: await count('sentences'),
      nodeCount: await count('nodes'),
      mentionCount: await count('node_sentence_mentions'),
      aliasCount: await count('aliases'),
      categoryCount: await count('categories'),
      unresolvedTokenCount: await count('unresolved_tokens'),
    );
  }

  // ── Kiwi 노출 ─────────────────────────────────────────

  Future<List<KiwiToken>> kiwiTokenize(String text) => _kiwi.tokenize(text);
  Future<List<String>> kiwiNouns(String text) => _kiwi.nouns(text);
}

String _now() => DateTime.now().toUtc().toIso8601String().replaceFirst('T', ' ');

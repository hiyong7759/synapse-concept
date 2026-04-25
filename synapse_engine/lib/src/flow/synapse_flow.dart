import 'package:sqflite/sqflite.dart';

import '../graph/ops.dart';
import '../kiwi/kiwi_wasm.dart';
import '../llm/tasks.dart';
import 'note_pipeline.dart';
import 'results.dart';

/// SynapseFlow — F5a portion (note autosave/process + post management).
/// `synapseTurn` and `promoteToInsight` land in F5b.
///
/// Activation: only attached when `EngineConfig.reservedKinds` includes
/// both `'synapse'` and `'insight'` (DESIGN_ENGINE §3 — kind 유연성).
class SynapseFlow {
  SynapseFlow({
    required this.db,
    required this.graph,
    required KiwiBackend kiwi,
    LlmTasks? llm,
  }) : _pipeline = NotePipeline(
          db: db,
          graph: graph,
          kiwi: kiwi,
          llm: llm,
        );

  final Database db;
  final GraphOps graph;
  final NotePipeline _pipeline;

  // ── /note 4 paths ────────────────────────────────────────

  /// LLM-free debounced save. See [NotePipeline.autosave].
  Future<void> noteAutosave({
    required int postId,
    required String source,
  }) =>
      _pipeline.autosave(postId: postId, source: source);

  /// Full meaning-processing pass. See [NotePipeline.process].
  Future<NoteProcessResult> noteProcess({
    required int postId,
    required String source,
  }) =>
      _pipeline.process(postId: postId, source: source);

  // ── post management ─────────────────────────────────────

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

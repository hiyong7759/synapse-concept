import 'package:sqflite/sqflite.dart';

import '../graph/ops.dart';
import '../internal/date_normalize.dart';
import '../internal/regex.dart' as unresolved;
import '../kiwi/kiwi_wasm.dart';
import '../llm/tasks.dart';
import '../markdown/parser.dart';
import '../models/graph_models.dart';
import 'results.dart';

/// Atomic save pipeline for `kind='note'` posts.
///
/// Two entry points (DESIGN_PIPELINE.md §자동저장 vs 의미 처리):
///   - [autosave] — `posts.source` UPDATE only. No LLM, no Kiwi.
///   - [process]  — Full 6-stage pipeline: DateNormalizer → unresolved →
///                  sentence INSERT → Kiwi node extraction → date splits →
///                  categories / mentions / aliases.
///
/// [process] requires [graph] (GraphOps + KiwiBackend). [llm] is optional —
/// when null, the meta filter passes everything through (DESIGN_PIPELINE
/// `--no-llm` mode).
class NotePipeline {
  NotePipeline({
    required this.db,
    required this.graph,
    required this.kiwi,
    this.llm,
    DateTime Function()? clock,
  })  : _now = clock ?? DateTime.now,
        _normalizer = const DateNormalizer();

  final Database db;
  final GraphOps graph;
  final KiwiBackend kiwi;
  final LlmTasks? llm;
  final DateTime Function() _now;
  final DateNormalizer _normalizer;

  // ── autosave ─────────────────────────────────────────────

  /// Updates `posts.source` (and `updated_at`). No LLM, no Kiwi. Single
  /// SQL UPDATE — meant for the 1.5 s debounce + page-leave path.
  ///
  /// When [title] is supplied (the user is editing the title field) it
  /// goes into the same UPDATE. When it is null and `posts.title` is
  /// also null we seed it with [source]'s first non-blank line so the
  /// sidebar has something to show. Once a title exists it is left alone
  /// unless the caller passes a new value.
  Future<void> autosave({
    required int postId,
    required String source,
    String? title,
  }) async {
    final updates = <String, Object?>{
      'source': source,
      'updated_at': _isoNow(),
    };

    if (title != null) {
      updates['title'] = title.isEmpty ? null : title;
    } else {
      final row = await db.query(
        'posts',
        columns: ['title'],
        where: 'id = ?',
        whereArgs: [postId],
        limit: 1,
      );
      if (row.isNotEmpty && row.first['title'] == null) {
        final firstLine = _firstNonBlankLine(source);
        if (firstLine != null) updates['title'] = firstLine;
      }
    }

    await db.update(
      'posts',
      updates,
      where: 'id = ?',
      whereArgs: [postId],
    );
  }

  String? _firstNonBlankLine(String source) {
    for (final raw in source.split('\n')) {
      final line = raw.trim();
      if (line.isEmpty) continue;
      // Strip leading markdown noise so the title reads cleanly.
      return line
          .replaceFirst(RegExp(r'^#+\s*'), '')
          .replaceFirst(RegExp(r'^[-*]\s+'), '');
    }
    return null;
  }

  // ── process ──────────────────────────────────────────────

  /// Full meaning-processing pass for [postId]. Replaces every existing
  /// sentence on that post with re-derived rows.
  Future<NoteProcessResult> process({
    required int postId,
    required String source,
  }) async {
    // 1. flush autosave + tear down derived rows.
    await db.update(
      'posts',
      {'source': source, 'updated_at': _isoNow()},
      where: 'id = ?',
      whereArgs: [postId],
    );
    // CASCADE cleans node_sentence_mentions / sentence_categories /
    // unresolved_tokens automatically (PRAGMA foreign_keys=ON).
    await db.delete('sentences', where: 'post_id = ?', whereArgs: [postId]);

    // 2. parse markdown → ParsedLine list.
    final lines = parseMarkdown(source);

    // 3. meta filter (게시물 단위 1회). Skip heading/keyValue.
    final filterables = <int>[];
    for (var i = 0; i < lines.length; i++) {
      final l = lines[i];
      if (l.kind == ParsedKind.list || l.kind == ParsedKind.free) {
        filterables.add(i);
      }
    }
    final metaIndices = <int>{};
    if (filterables.isNotEmpty && llm != null) {
      // Rule pre-filter: empty Kiwi nouns + '?' ending → very likely meta.
      // Otherwise route through the LLM batch.
      final llmIdx = <int>[];
      final llmTexts = <String>[];
      for (final i in filterables) {
        final text = lines[i].text;
        final nouns = await kiwi.nouns(text);
        if (nouns.isEmpty && text.endsWith('?')) {
          metaIndices.add(i);
        } else {
          llmIdx.add(i);
          llmTexts.add(text);
        }
      }
      if (llmTexts.isNotEmpty) {
        try {
          final flags = await llm!.metaFilter(llmTexts);
          for (var k = 0; k < flags.length && k < llmIdx.length; k++) {
            if (flags[k]) metaIndices.add(llmIdx[k]);
          }
        } on Object {
          // LLM failure → treat as no-llm: nothing additional flagged.
        }
      }
    }

    // 4. per-sentence loop.
    final reference = _now();
    final added = <Sentence>[];
    final unresolvedRecords = <({int sentenceId, String token})>[];
    var position = 0;
    String? firstSentenceText;

    for (var i = 0; i < lines.length; i++) {
      final line = lines[i];

      // Headings produce no sentence row, but their path is registered.
      if (line.kind == ParsedKind.heading) {
        await graph.upsertCategoryPath(line.headingPath.join('/'));
        continue;
      }

      if (metaIndices.contains(i)) continue;

      // 4a. DateNormalizer (자연어 날짜 + ISO + 반복 표현 보존).
      final norm = await _normalizer.normalize(
        line.text,
        kiwi: kiwi,
        reference: reference,
      );
      final normalizedText = norm.text;
      final dateNodes = norm.splitNodes;

      // 4b. unresolved detection (rule-based; LLM unresolved gone with save-pronoun).
      final unresolvedTokens =
          unresolved.detectUnresolvedTokens(normalizedText);

      // 4c. sentence INSERT.
      final sid = await graph.addSentence(
        postId: postId,
        text: normalizedText,
      );
      // position UPDATE — sqflite addSentence schema defaults position=0,
      // so set it explicitly for stable ordering.
      await db.update(
        'sentences',
        {'position': position},
        where: 'id = ?',
        whereArgs: [sid],
      );
      added.add(Sentence(
        id: sid,
        postId: postId,
        text: normalizedText,
        position: position,
      ));
      firstSentenceText ??= normalizedText;
      position++;

      // 4d. Kiwi nouns + 4e. date split nodes (combined upsert + mention).
      final kiwiNouns = await kiwi.nouns(normalizedText);
      final allNames = <String>[
        ...kiwiNouns,
        ...dateNodes,
      ];
      for (final name in allNames) {
        if (name.isEmpty) continue;
        final nodeId = await graph.upsertNode(name);
        await graph.addMention(nodeId: nodeId, sentenceId: sid);
      }

      // 4f. heading path → sentence_categories.
      if (line.headingPath.isNotEmpty) {
        final catId =
            await graph.upsertCategoryPath(line.headingPath.join('/'));
        if (catId != null) {
          await graph.addSentenceCategory(
            sentenceId: sid,
            categoryId: catId,
            origin: 'user',
          );
        }
      }

      // 4g. unresolved_tokens.
      for (final token in unresolvedTokens) {
        await db.insert(
          'unresolved_tokens',
          {'sentence_id': sid, 'token': token},
          conflictAlgorithm: ConflictAlgorithm.ignore,
        );
        unresolvedRecords.add((sentenceId: sid, token: token));
      }
    }

    // 4h. categorize fresh nodes (LLM, best-effort).
    if (llm != null) {
      await _categorizePostNodes(postId);
    }

    // 5. auto-fill posts.title with the first sentence's first line, if
    //    title is still null.
    if (firstSentenceText != null) {
      final row = await db.query(
        'posts',
        columns: ['title'],
        where: 'id = ?',
        whereArgs: [postId],
        limit: 1,
      );
      if (row.isNotEmpty && row.first['title'] == null) {
        final firstLine = firstSentenceText.split('\n').first.trim();
        await db.update(
          'posts',
          {'title': firstLine},
          where: 'id = ?',
          whereArgs: [postId],
        );
      }
    }

    return NoteProcessResult(
      postId: postId,
      sentencesAdded: added,
      unresolvedTokens: unresolvedRecords,
    );
  }

  /// Categorizes every node mentioned in [postId] that doesn't yet have an
  /// `origin='ai'` mapping in `node_category_mentions`. One LLM call per
  /// node (deduped). Failures are swallowed — categorization is best-effort
  /// and the rest of the pipeline (sentence INSERTs, mentions, headings)
  /// stays committed regardless.
  ///
  /// Sub codes (`BOD.disease`) are resolved to leaf category rows under
  /// the seed root (`BOD`). Unknown roots / leaves are skipped — the
  /// system prompt enumerates the closed set, so unknown codes are
  /// hallucinations rather than legitimate user-headings.
  Future<void> _categorizePostNodes(int postId) async {
    final llmRef = llm;
    if (llmRef == null) return;
    final rows = await db.rawQuery(
      '''
      SELECT DISTINCT n.id, n.name
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
    if (rows.isEmpty) return;
    final total = rows.length;
    if (total >= 20) {
      // ignore: avoid_print
      print('[categorize] post=$postId — $total nodes pending');
    }
    var done = 0;
    for (final row in rows) {
      final nodeId = row['id']! as int;
      final nodeName = row['name']! as String;

      final ctxRows = await db.rawQuery(
        '''
        SELECT s.text FROM sentences s
        JOIN node_sentence_mentions m ON m.sentence_id = s.id
        WHERE m.node_id = ? AND s.post_id = ?
        ORDER BY s.position
        LIMIT 3
        ''',
        [nodeId, postId],
      );
      final contexts =
          ctxRows.map((r) => r['text']! as String).toList(growable: false);

      List<String> codes;
      try {
        codes = await llmRef.categorize(
          nodeName: nodeName,
          contextSentences: contexts,
        );
      } on Object {
        continue;
      }

      for (final code in codes) {
        final leafId = await _resolveSubCategoryId(code);
        if (leafId == null) continue;
        await graph.addCategoryMention(
          nodeId: nodeId,
          categoryId: leafId,
          origin: 'ai',
        );
      }
      done++;
      if (total >= 20 && (done % 50 == 0 || done == total)) {
        // ignore: avoid_print
        print('[categorize] $done/$total');
      }
    }
  }

  /// Resolves a `BOD.disease` style code to its `categories.id`. Returns
  /// null when the root or leaf is missing — caller skips the mention.
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

  String _isoNow() => _now()
      .toUtc()
      .toIso8601String()
      .replaceFirst('T', ' ')
      .substring(0, 19);
}

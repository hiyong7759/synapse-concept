import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/flow/note_pipeline.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';
import 'package:synapse_engine/src/llm/stub_backend.dart';

KiwiToken _nng(String form, int start) =>
    KiwiToken(surface: form, tag: 'NNG', lemma: form, start: start, length: form.length);

void main() {
  // 2026-04-26 — Sunday. "어제" → "2026년 4월 25일".
  final reference = DateTime(2026, 4, 26);

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  Future<({SynapseEngine engine, NotePipeline pipeline, int postId})>
      setup({
    StubInferenceBackend? stub,
    Map<String, List<KiwiToken>> kiwiFixtures = const {},
  }) async {
    final kiwi = InMemoryKiwiBackend(fixtures: Map.of(kiwiFixtures));
    final engine = await SynapseEngine.create(
      EngineConfig(
        appName: 'note_pipeline_test',
        allowedKinds: const ['note', 'synapse', 'insight'],
        reservedKinds: const ['synapse', 'insight'],
        dbPath: inMemoryDatabasePath,
        categorySeed: CategorySeed.synapse19(),
        // PromptLoader otherwise hits rootBundle — these stubs let
        // metaFilter/etc resolve without an asset manifest.
        promptOverrides: const {
          'category': '<sys:category>',
          'metaFilter': '<sys:metaFilter>',
          'retrieveExpand': '<sys:retrieveExpand>',
          'retrieveFilter': '<sys:retrieveFilter>',
          'synapseAnswer': '<sys:synapseAnswer>',
        },
      ),
      kiwiOverride: kiwi,
      backendOverride: stub,
    );
    final postId =
        await engine.db.insert('posts', {'kind': 'note'});
    final pipeline = NotePipeline(
      db: engine.db,
      graph: engine.graph!,
      kiwi: kiwi,
      llm: engine.llm,
      clock: () => reference,
    );
    return (engine: engine, pipeline: pipeline, postId: postId);
  }

  group('autosave', () {
    test('only updates posts.source / updated_at', () async {
      final s = await setup();
      try {
        await s.pipeline.autosave(postId: s.postId, source: 'draft 1');
        final row = (await s.engine.db.query(
          'posts',
          where: 'id = ?',
          whereArgs: [s.postId],
        )).single;
        expect(row['source'], 'draft 1');
        // No sentence rows produced.
        final c = Sqflite.firstIntValue(
          await s.engine.db.rawQuery(
            'SELECT COUNT(*) FROM sentences WHERE post_id = ?',
            [s.postId],
          ),
        );
        expect(c, 0);
      } finally {
        await s.engine.dispose();
      }
    });
  });

  group('process — simple paths', () {
    test('single free line: DateNormalizer + Kiwi + date split', () async {
      const text = '어제 강남세브란스 갔다';
      final s = await setup(kiwiFixtures: {
        // After DateNormalizer rewrites "어제" → "2026년 4월 25일", the
        // pipeline calls kiwi.nouns on the rewritten text.
        '2026년 4월 25일 강남세브란스 갔다': [
          _nng('강남세브란스', 9),
        ],
      });
      try {
        final r = await s.pipeline.process(
          postId: s.postId,
          source: text,
        );
        expect(r.sentencesAdded.length, 1);
        expect(r.sentencesAdded.first.text, '2026년 4월 25일 강남세브란스 갔다');

        // Nodes: 강남세브란스 + 2026년 + 4월 + 25일 + 2026년 4월 25일
        final names = await s.engine.db.rawQuery(
          'SELECT n.name FROM nodes n '
          'JOIN node_sentence_mentions m ON m.node_id = n.id '
          'WHERE m.sentence_id = ?',
          [r.sentencesAdded.first.id],
        );
        final set = names.map((r) => r['name'] as String).toSet();
        expect(set, containsAll(
          ['강남세브란스', '2026년', '4월', '25일', '2026년 4월 25일'],
        ));
      } finally {
        await s.engine.dispose();
      }
    });

    test('heading registers a sentence_categories row', () async {
      const text = '# 더나은\n## 개발팀\n- 팀장:: 박지수';
      final s = await setup(kiwiFixtures: {
        '팀장:: 박지수': [_nng('팀장', 0), _nng('박지수', 5)],
      });
      try {
        final r = await s.pipeline.process(
          postId: s.postId,
          source: text,
        );
        expect(r.sentencesAdded.length, 1);
        // sentence_categories row exists with origin='user'.
        final scRows = await s.engine.db.query(
          'sentence_categories',
          where: 'sentence_id = ?',
          whereArgs: [r.sentencesAdded.first.id],
        );
        expect(scRows.length, 1);
        expect(scRows.first['origin'], 'user');
      } finally {
        await s.engine.dispose();
      }
    });

    test('rerun replaces existing sentences (CASCADE)', () async {
      final s = await setup(kiwiFixtures: {
        '첫 번째 문장': const [],
        '두 번째 문장': const [],
      });
      try {
        await s.pipeline.process(
          postId: s.postId,
          source: '첫 번째 문장',
        );
        await s.pipeline.process(
          postId: s.postId,
          source: '두 번째 문장',
        );
        final rows = await s.engine.db.query(
          'sentences',
          where: 'post_id = ?',
          whereArgs: [s.postId],
        );
        expect(rows.length, 1);
        expect(rows.first['text'], '두 번째 문장');
      } finally {
        await s.engine.dispose();
      }
    });

    test('auto-fills posts.title with the first sentence', () async {
      final s = await setup(kiwiFixtures: {
        '회의 잘 끝남': const [],
      });
      try {
        await s.pipeline.process(
          postId: s.postId,
          source: '회의 잘 끝남',
        );
        final row = (await s.engine.db.query(
          'posts',
          where: 'id = ?',
          whereArgs: [s.postId],
        )).single;
        expect(row['title'], '회의 잘 끝남');
      } finally {
        await s.engine.dispose();
      }
    });

    test('detects demonstrative tokens into unresolved_tokens', () async {
      const text = '거기 가서 만났다';
      final s = await setup(kiwiFixtures: {
        '거기 가서 만났다': const [],
      });
      try {
        final r = await s.pipeline.process(
          postId: s.postId,
          source: text,
        );
        expect(r.unresolvedTokens, isNotEmpty);
        expect(r.unresolvedTokens.first.token, '거기');
        final stored = await s.engine.db.query(
          'unresolved_tokens',
          where: 'sentence_id = ?',
          whereArgs: [r.sentencesAdded.first.id],
        );
        expect(stored.length, 1);
      } finally {
        await s.engine.dispose();
      }
    });
  });

  group('meta filter', () {
    test('llm = null → all lines pass through', () async {
      const text = '방금 그거 다시?\n어제 회의 결과';
      final s = await setup(kiwiFixtures: {
        // First line: no nouns + ends with '?' → rule pre-filter would
        // catch it, but only when an LLM is wired. Without an LLM all lines
        // pass.
        '방금 그거 다시?': const [],
        '2026년 4월 25일 회의 결과': const [],
      });
      try {
        final r = await s.pipeline.process(
          postId: s.postId,
          source: text,
        );
        expect(r.sentencesAdded.length, 2);
      } finally {
        await s.engine.dispose();
      }
    });

    test('llm marks meta — those lines are dropped', () async {
      const text = '방금 그거 다시\n어제 회의 결과';
      final stub = StubInferenceBackend(
        canned: {
          '::방금 그거 다시': 'meta',
          '::2026년 4월 25일 회의 결과': 'no',
        },
      );
      final s = await setup(
        stub: stub,
        kiwiFixtures: {
          '방금 그거 다시': [_nng('회의', 0)], // pretend it has at least one noun
          '2026년 4월 25일 회의 결과': [_nng('회의', 11)],
        },
      );
      try {
        final r = await s.pipeline.process(
          postId: s.postId,
          source: text,
        );
        expect(r.sentencesAdded.length, 1);
        expect(r.sentencesAdded.first.text, '2026년 4월 25일 회의 결과');
      } finally {
        await s.engine.dispose();
      }
    });
  });

  group('first-person alias seed', () {
    test('seeded "나" node + 11 aliases land in DB at engine.create', () async {
      final s = await setup();
      try {
        final naRows = await s.engine.db.query(
          'nodes',
          where: 'name = ?',
          whereArgs: ['나'],
        );
        expect(naRows.length, 1);
        final aliasCount = Sqflite.firstIntValue(
          await s.engine.db.rawQuery(
            'SELECT COUNT(*) FROM aliases WHERE origin = ?',
            ['system'],
          ),
        );
        expect(aliasCount, 11);
        // Looking up via "내가" returns the same "나" node.
        final hits = await s.engine.graph!.findNodesByAlias('내가');
        expect(hits.length, 1);
        expect(hits.first.name, '나');
      } finally {
        await s.engine.dispose();
      }
    });
  });
}

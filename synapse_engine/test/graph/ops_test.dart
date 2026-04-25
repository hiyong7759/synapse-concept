import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';

Future<SynapseEngine> _engine() => SynapseEngine.create(
      EngineConfig(
        appName: 'test_graph',
        allowedKinds: const ['note', 'synapse', 'insight'],
        reservedKinds: const ['synapse', 'insight'],
        dbPath: inMemoryDatabasePath,
        categorySeed: CategorySeed.synapse19(),
      ),
      kiwiOverride: InMemoryKiwiBackend(),
    );

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('GraphOps CRUD', () {
    late SynapseEngine engine;
    late GraphOps ops;
    late int postId;

    setUp(() async {
      engine = await _engine();
      ops = engine.graph!;
      postId = await engine.db.insert('posts', {'kind': 'note'});
    });

    tearDown(() async {
      await engine.dispose();
    });

    test('upsertNode reuses an existing name match', () async {
      final id1 = await ops.upsertNode('스타벅스');
      final id2 = await ops.upsertNode('스타벅스');
      expect(id1, id2);
    });

    test('upsertNode reuses via alias when alias matches', () async {
      final id = await ops.upsertNode('스타벅스');
      await ops.addAlias(alias: '스벅', nodeId: id);
      final id2 = await ops.upsertNode('스벅');
      expect(id2, id);
    });

    test('addSentence + addMention + bfsRetrieve hydrate names', () async {
      final node = await ops.upsertNode('허리디스크');
      final sid = await ops.addSentence(
        postId: postId,
        text: '허리디스크 진단받았어',
      );
      final added = await ops.addMention(nodeId: node, sentenceId: sid);
      expect(added, isTrue);
      // Duplicate insert is a no-op.
      expect(await ops.addMention(nodeId: node, sentenceId: sid), isFalse);

      final mentions = await ops.bfsRetrieve(startNodes: {node});
      expect(mentions, hasLength(1));
      expect(mentions.first.nodeName, '허리디스크');
      expect(mentions.first.sentenceText, '허리디스크 진단받았어');
    });

    test('updateSentence rewrites bodies but refuses insight rows', () async {
      final sid1 = await ops.addSentence(postId: postId, text: '원래');
      await ops.updateSentence(sid1, '바뀐');
      final row = (await engine.db.query(
        'sentences',
        where: 'id = ?',
        whereArgs: [sid1],
      )).single;
      expect(row['text'], '바뀐');

      final insightSid = await ops.addSentence(
        postId: postId,
        text: '통찰 본문',
        origin: 'insight',
      );
      expect(
        () => ops.updateSentence(insightSid, '함부로 수정'),
        throwsA(isA<StateError>()),
      );
    });

    test('upsertCategoryPath builds the chain incrementally', () async {
      final firstId = await ops.upsertCategoryPath('더나은/개발팀');
      expect(firstId, isNotNull);
      // Re-upserting the same path returns the same leaf.
      final secondId = await ops.upsertCategoryPath('더나은/개발팀');
      expect(secondId, firstId);
      // Extending the path adds one row but keeps the parent.
      final deeperId = await ops.upsertCategoryPath('더나은/개발팀/민지');
      expect(deeperId, isNot(firstId));
      // Whitespace and empty segments are ignored.
      expect(await ops.upsertCategoryPath('  '), isNull);
      expect(await ops.upsertCategoryPath(null), isNull);
    });

    test('addAlias / removeAlias / findNodesByAlias round-trip', () async {
      final node = await ops.upsertNode('스타벅스');
      await ops.addAlias(alias: '스벅', nodeId: node);
      expect((await ops.findNodesByAlias('스벅')).map((n) => n.id), [node]);
      await ops.removeAlias('스벅');
      expect(await ops.findNodesByAlias('스벅'), isEmpty);
    });

    test('addSentenceCategory + addCategoryMention insert idempotently',
        () async {
      final node = await ops.upsertNode('민지');
      final sid = await ops.addSentence(postId: postId, text: '민지가 맡음');
      final catId = await ops.upsertCategoryPath('더나은/개발팀');
      await ops.addSentenceCategory(sentenceId: sid, categoryId: catId!);
      await ops.addSentenceCategory(sentenceId: sid, categoryId: catId);
      await ops.addCategoryMention(nodeId: node, categoryId: catId);
      await ops.addCategoryMention(nodeId: node, categoryId: catId);

      final scCount = Sqflite.firstIntValue(
        await engine.db.rawQuery('SELECT COUNT(*) FROM sentence_categories'),
      );
      final ncCount = Sqflite.firstIntValue(
        await engine.db.rawQuery('SELECT COUNT(*) FROM node_category_mentions'),
      );
      expect(scCount, 1);
      expect(ncCount, 1);
    });

    test('deleteSentence cascades to mentions', () async {
      final node = await ops.upsertNode('허리');
      final sid = await ops.addSentence(postId: postId, text: '허리 아파');
      await ops.addMention(nodeId: node, sentenceId: sid);
      await ops.deleteSentence(sid);
      final after = Sqflite.firstIntValue(
        await engine.db.rawQuery(
          'SELECT COUNT(*) FROM node_sentence_mentions WHERE sentence_id = ?',
          [sid],
        ),
      );
      expect(after, 0);
    });

    test('getStats counts each table', () async {
      await ops.upsertNode('a');
      await ops.upsertNode('b');
      await ops.addSentence(postId: postId, text: 's1');
      final stats = await ops.getStats();
      expect(stats.postCount, 1);
      expect(stats.sentenceCount, 1);
      expect(stats.nodeCount, 2);
      expect(stats.categoryCount, 133);
    });

    test('splitNode is a stub in F4', () async {
      expect(
        () => ops.splitNode(1, const Object()),
        throwsA(isA<UnimplementedError>()),
      );
    });
  });

  group('GraphOps Kiwi delegation', () {
    test('kiwiTokenize / kiwiNouns delegate to the supplied backend',
        () async {
      final kiwi = InMemoryKiwiBackend()
        ..seed('나는 학교에 간다', const [
          KiwiToken(
              surface: '나', tag: 'NP', lemma: '나', start: 0, length: 1),
          KiwiToken(
              surface: '학교', tag: 'NNG', lemma: '학교', start: 3, length: 2),
          KiwiToken(
              surface: '가다', tag: 'VV', lemma: '가다', start: 8, length: 2),
        ]);
      final engine = await SynapseEngine.create(
        EngineConfig(
          appName: 'kiwi_test',
          allowedKinds: const ['note'],
          reservedKinds: const [],
          dbPath: inMemoryDatabasePath,
          categorySeed: CategorySeed.empty(),
        ),
        kiwiOverride: kiwi,
      );
      try {
        final tokens = await engine.graph!.kiwiTokenize('나는 학교에 간다');
        expect(tokens, hasLength(3));
        final nouns = await engine.graph!.kiwiNouns('나는 학교에 간다');
        // NP is excluded, NNG + VV included.
        expect(nouns, ['학교', '가다']);
      } finally {
        await engine.dispose();
      }
    });
  });
}

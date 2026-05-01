import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';

Future<SynapseEngine> _engine() => SynapseEngine.create(
      EngineConfig(
        appName: 'lookup_test',
        allowedKinds: const ['note'],
        reservedKinds: const [],
        dbPath: inMemoryDatabasePath,
        categorySeed: CategorySeed.empty(),
      ),
      kiwiOverride: InMemoryKiwiBackend(),
    );

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('matchStartCategories', () {
    late SynapseEngine engine;
    late GraphOps ops;

    setUp(() async {
      engine = await _engine();
      ops = engine.graph!;
    });
    tearDown(() async {
      await engine.dispose();
    });

    test('exact name match wins over substring', () async {
      final exact = await ops.upsertCategoryPath(['만화 라이트노벨']);
      await ops.upsertCategoryPath(['만화 라이트노벨', '슬램덩크']);
      final result = await matchStartCategories(
        engine.db,
        keywords: const ['만화 라이트노벨'],
      );
      expect(result, contains(exact));
    });

    test('substring fallback hits child categories', () async {
      await ops.upsertCategoryPath(['건강', '허리']);
      await ops.upsertCategoryPath(['건강', '심혈관']);
      final result = await matchStartCategories(
        engine.db,
        keywords: const ['건강'],
      );
      expect(result, isNotEmpty);
    });

    test('empty keywords yield empty result', () async {
      final result = await matchStartCategories(
        engine.db,
        keywords: const [],
      );
      expect(result, isEmpty);
    });
  });

  group('collectMentionsByHeadingSubtree', () {
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

    test('walks subtree and surfaces co-mentioned nodes', () async {
      final rootId = await ops.upsertCategoryPath(['건강']);
      final leafId = await ops.upsertCategoryPath(['건강', '허리']);
      final hsk = await ops.upsertNode('허리디스크');
      final exer = await ops.upsertNode('운동');
      final yoga = await ops.upsertNode('요가');

      final s1 = await ops.addSentence(postId: postId, text: '허리디스크와 운동');
      final s2 = await ops.addSentence(postId: postId, text: '요가 추천');
      await ops.addSentenceCategory(sentenceId: s1, categoryId: leafId!);
      await ops.addSentenceCategory(sentenceId: s2, categoryId: rootId!);
      await ops.addMention(nodeId: hsk, sentenceId: s1);
      await ops.addMention(nodeId: exer, sentenceId: s1);
      await ops.addMention(nodeId: yoga, sentenceId: s2);

      final mentions = await collectMentionsByHeadingSubtree(
        engine.db,
        categoryIds: {rootId},
      );
      // Both sentences (root + leaf via subtree) come back.
      expect(mentions.map((m) => m.sentenceId).toSet(), {s1, s2});
      // 허리디스크, 운동, 요가 — every co-mentioned node is surfaced.
      expect(mentions.map((m) => m.nodeName).toSet(),
          containsAll(<String>['허리디스크', '운동', '요가']));
    });

    test('heading-only sentences come back with nodeId=-1', () async {
      final leafId = await ops.upsertCategoryPath(['회사', '공지']);
      final s = await ops.addSentence(postId: postId, text: '회사 공지 본문');
      await ops.addSentenceCategory(sentenceId: s, categoryId: leafId!);

      final mentions = await collectMentionsByHeadingSubtree(
        engine.db,
        categoryIds: {leafId},
      );
      expect(mentions, hasLength(1));
      expect(mentions.first.nodeId, -1);
      expect(mentions.first.sentenceText, '회사 공지 본문');
    });

    test('empty input returns empty list', () async {
      final mentions = await collectMentionsByHeadingSubtree(
        engine.db,
        categoryIds: const <int>{},
      );
      expect(mentions, isEmpty);
    });
  });

  group('collectMentionsByCategorySharing', () {
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

    test('finds sibling-category nodes and pulls their mentions', () async {
      final catId = await ops.upsertCategoryPath(['건강', '허리']);
      final hsk = await ops.upsertNode('허리디스크');
      final yoga = await ops.upsertNode('요가');
      for (final id in [hsk, yoga]) {
        await ops.addCategoryMention(nodeId: id, categoryId: catId!);
      }
      final s = await ops.addSentence(postId: postId, text: '요가 추천');
      await ops.addMention(nodeId: yoga, sentenceId: s);

      final mentions = await collectMentionsByCategorySharing(
        engine.db,
        nodeIds: {hsk},
      );
      expect(mentions.map((m) => m.sentenceId).toSet(), {s});
      expect(mentions.first.nodeName, '요가');
    });

    test('empty start yields empty', () async {
      final mentions = await collectMentionsByCategorySharing(
        engine.db,
        nodeIds: const <int>{},
      );
      expect(mentions, isEmpty);
    });
  });
}

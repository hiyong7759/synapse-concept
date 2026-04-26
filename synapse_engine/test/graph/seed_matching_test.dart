import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/graph/seed_matching.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';

Future<SynapseEngine> _engine() => SynapseEngine.create(
      EngineConfig(
        appName: 'seed_test',
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

  group('matchStartNodes', () {
    late SynapseEngine engine;
    late GraphOps ops;

    setUp(() async {
      engine = await _engine();
      ops = engine.graph!;
    });

    tearDown(() async {
      await engine.dispose();
    });

    test('alias substring inside the raw question wins over keyword scan',
        () async {
      final id = await ops.upsertNode('스타벅스');
      await ops.addAlias(alias: '스벅', nodeId: id);
      // The keyword list has nothing useful — only the substring scan
      // against the raw question can rescue 스벅.
      final result = await matchStartNodes(
        engine.db,
        keywords: const ['아메리카노'],
        question: '스벅 갔어',
      );
      expect(result, {id: '스타벅스'});
    });

    test('exact alias match', () async {
      final id = await ops.upsertNode('강남세브란스');
      await ops.addAlias(alias: '세브란스', nodeId: id);
      final result = await matchStartNodes(
        engine.db,
        keywords: const ['세브란스'],
        question: '',
      );
      expect(result, {id: '강남세브란스'});
    });

    test('exact name match (no alias)', () async {
      final id = await ops.upsertNode('허리디스크');
      final result = await matchStartNodes(
        engine.db,
        keywords: const ['허리디스크'],
        question: '',
      );
      expect(result, {id: '허리디스크'});
    });

    test('LIKE substring fallback when nothing else matches', () async {
      final id = await ops.upsertNode('허리디스크');
      final result = await matchStartNodes(
        engine.db,
        keywords: const ['허리'],
        question: '',
      );
      expect(result.containsKey(id), isTrue);
    });

    test('returns empty when no keywords match anything', () async {
      await ops.upsertNode('허리디스크');
      final result = await matchStartNodes(
        engine.db,
        keywords: const ['xyz'],
        question: '',
      );
      expect(result, isEmpty);
    });
  });

  group('headingSubtreeSeeds', () {
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

    test('walks the recursive subtree and surfaces co-mentioned nodes',
        () async {
      // Build: 건강 / 허리 (leaf 'A'); 'B' under 건강 directly.
      final rootId = await ops.upsertCategoryPath('건강');
      final leafId = await ops.upsertCategoryPath('건강/허리');

      final hsk = await ops.upsertNode('허리디스크');
      final exer = await ops.upsertNode('운동');
      final yoga = await ops.upsertNode('요가');

      // Map 허리디스크 to the leaf, so it becomes the seed entry.
      await ops.addCategoryMention(nodeId: hsk, categoryId: leafId!);

      // Sentences: one on the leaf (with hsk + 운동 co-mention),
      // one on the parent root (with 요가 alone).
      final s1 = await ops.addSentence(postId: postId, text: '허리디스크와 운동');
      final s2 = await ops.addSentence(postId: postId, text: '요가 추천');
      await ops.addSentenceCategory(sentenceId: s1, categoryId: leafId);
      await ops.addSentenceCategory(sentenceId: s2, categoryId: rootId!);
      await ops.addMention(nodeId: hsk, sentenceId: s1);
      await ops.addMention(nodeId: exer, sentenceId: s1);
      await ops.addMention(nodeId: yoga, sentenceId: s2);

      final result = await headingSubtreeSeeds(
        engine.db,
        startNodeIds: {hsk},
      );
      expect(result.categoryIds, isNotEmpty);
      // Both sentences (leaf + parent root) come back.
      expect(result.mentions.map((m) => m.sentenceId).toSet(), isNot(isEmpty));
      // 운동 (co-mentioned in s1) and 허리디스크 itself are present.
      final names = result.mentions.map((m) => m.nodeName).toSet();
      expect(names, containsAll(<String>['허리디스크', '운동']));
    });

    test('heading-only sentences come back with nodeId=-1', () async {
      final leafId = await ops.upsertCategoryPath('회사/공지');
      final hsk = await ops.upsertNode('허리디스크');
      // Map hsk to a sibling category so the subtree triggers, but the
      // sentence under '회사/공지' has zero node mentions.
      await ops.addCategoryMention(nodeId: hsk, categoryId: leafId!);
      final s = await ops.addSentence(postId: postId, text: '회사 공지 본문');
      await ops.addSentenceCategory(sentenceId: s, categoryId: leafId);

      final result = await headingSubtreeSeeds(
        engine.db,
        startNodeIds: {hsk},
      );
      final headingOnly =
          result.mentions.where((m) => m.nodeId == -1).toList();
      expect(headingOnly, hasLength(1));
      expect(headingOnly.single.sentenceText, '회사 공지 본문');
    });

    test('empty input returns an empty bundle', () async {
      final result = await headingSubtreeSeeds(
        engine.db,
        startNodeIds: const <int>{},
      );
      expect(result.categoryIds, isEmpty);
      expect(result.mentions, isEmpty);
    });
  });

  group('sameCategoryNodes', () {
    late SynapseEngine engine;
    late GraphOps ops;

    setUp(() async {
      engine = await _engine();
      ops = engine.graph!;
    });

    tearDown(() async {
      await engine.dispose();
    });

    test('surfaces other nodes sharing a category and skips visited', () async {
      final catId = await ops.upsertCategoryPath('건강/허리');
      final hsk = await ops.upsertNode('허리디스크');
      final exer = await ops.upsertNode('운동');
      final yoga = await ops.upsertNode('요가');
      for (final id in [hsk, exer, yoga]) {
        await ops.addCategoryMention(nodeId: id, categoryId: catId!);
      }
      final result = await sameCategoryNodes(
        engine.db,
        startNodeIds: {hsk},
        visitedNodeIds: {hsk, exer},
      );
      expect(result, {yoga});
    });

    test('returns empty when start has no category mentions', () async {
      final hsk = await ops.upsertNode('허리디스크');
      final result = await sameCategoryNodes(
        engine.db,
        startNodeIds: {hsk},
        visitedNodeIds: const <int>{},
      );
      expect(result, isEmpty);
    });
  });
}

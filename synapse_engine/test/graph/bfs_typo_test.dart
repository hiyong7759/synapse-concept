import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';

Future<SynapseEngine> _engine() => SynapseEngine.create(
      EngineConfig(
        appName: 'test_bfs',
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

  group('bfsRetrieve', () {
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

    test('returns empty when start set is empty', () async {
      expect(await ops.bfsRetrieve(startNodes: const {}), isEmpty);
    });

    test('reaches a co-mentioned node via a follow-up sentence (Python parity)',
        () async {
      // Match Python `engine/retrieve.py` BFS semantics: a mention is
      // emitted only when the layer's current node is the *origin* of
      // the edge. Sharing a sentence is what surfaces the neighbour as
      // the next layer's `current` set; the neighbour's own mention
      // becomes visible only when it has another sentence to point to.
      final hsk = await ops.upsertNode('허리디스크');
      final sev = await ops.upsertNode('강남세브란스');
      final shared = await ops.addSentence(
        postId: postId,
        text: '허리디스크 진단 받고 강남세브란스 다님',
      );
      final sevOnly = await ops.addSentence(
        postId: postId,
        text: '강남세브란스에서 또 진료',
      );
      await ops.addMention(nodeId: hsk, sentenceId: shared);
      await ops.addMention(nodeId: sev, sentenceId: shared);
      await ops.addMention(nodeId: sev, sentenceId: sevOnly);

      final mentions = await ops.bfsRetrieve(startNodes: {hsk});
      expect(mentions.map((m) => m.nodeId).toSet(), {hsk, sev});
      expect(mentions.map((m) => m.sentenceId).toSet(), {shared, sevOnly});
    });

    test('multi-layer expansion records a mention per visited node', () async {
      // Three nodes chained by shared sentences plus one extra sentence
      // so each node has somewhere to point to.
      //   A — s1 — B
      //   B — s2 — C
      //   C — s3       (terminal sentence so C also produces a mention)
      final a = await ops.upsertNode('A');
      final b = await ops.upsertNode('B');
      final c = await ops.upsertNode('C');
      final s1 = await ops.addSentence(postId: postId, text: 'A and B');
      final s2 = await ops.addSentence(postId: postId, text: 'B and C');
      final s3 = await ops.addSentence(postId: postId, text: 'C alone');
      await ops.addMention(nodeId: a, sentenceId: s1);
      await ops.addMention(nodeId: b, sentenceId: s1);
      await ops.addMention(nodeId: b, sentenceId: s2);
      await ops.addMention(nodeId: c, sentenceId: s2);
      await ops.addMention(nodeId: c, sentenceId: s3);

      final mentions = await ops.bfsRetrieve(startNodes: {a});
      expect(mentions.map((m) => m.nodeId).toSet(), {a, b, c});
      expect(mentions.map((m) => m.sentenceId).toSet(), {s1, s2, s3});
    });

    test('seedMentions are folded in before layer 0 (axis-A pre-seed)',
        () async {
      final hsk = await ops.upsertNode('허리디스크');
      final cof = await ops.upsertNode('커피');
      final s1 =
          await ops.addSentence(postId: postId, text: '커피와 허리디스크 같이');
      final s2 =
          await ops.addSentence(postId: postId, text: '허리디스크 다른 문장');
      await ops.addMention(nodeId: hsk, sentenceId: s1);
      await ops.addMention(nodeId: cof, sentenceId: s1);
      await ops.addMention(nodeId: hsk, sentenceId: s2);

      // s1 is a pre-seed (caller resolved it from a heading subtree). BFS
      // must include it in the result and treat hsk/cof as already known.
      final mentions = await ops.bfsRetrieve(
        startNodes: const {},
        seedMentions: [
          Mention(
            nodeId: hsk,
            sentenceId: s1,
            nodeName: '허리디스크',
            sentenceText: '커피와 허리디스크 같이',
          ),
          Mention(
            nodeId: cof,
            sentenceId: s1,
            nodeName: '커피',
            sentenceText: '커피와 허리디스크 같이',
          ),
        ],
      );
      // s1 is reported (from the seed) and BFS expands hsk → s2.
      expect(mentions.map((m) => m.sentenceId).toSet(), {s1, s2});
    });

    test('supplementNodes add a one-hop axis-B layer after BFS terminates',
        () async {
      final hsk = await ops.upsertNode('허리디스크');
      final exer = await ops.upsertNode('운동');
      final s1 = await ops.addSentence(postId: postId, text: '허리디스크 진단');
      final s2 = await ops.addSentence(postId: postId, text: '운동 시작');
      await ops.addMention(nodeId: hsk, sentenceId: s1);
      await ops.addMention(nodeId: exer, sentenceId: s2);

      final mentions = await ops.bfsRetrieve(
        startNodes: {hsk},
        supplementNodes: {exer},
      );
      expect(mentions.map((m) => m.sentenceId).toSet(), {s1, s2});
    });

    test('filter callback gets to drop sentences', () async {
      final hsk = await ops.upsertNode('허리디스크');
      final s1 = await ops.addSentence(postId: postId, text: 'keep this');
      final s2 = await ops.addSentence(postId: postId, text: 'drop this');
      await ops.addMention(nodeId: hsk, sentenceId: s1);
      await ops.addMention(nodeId: hsk, sentenceId: s2);

      final mentions = await ops.bfsRetrieve(
        startNodes: {hsk},
        filter: (text) async => !text.startsWith('drop'),
      );
      expect(mentions.map((m) => m.sentenceText).toSet(), {'keep this'});
    });

    test('stopwordThreshold prunes hyper-connected nodes from expansion',
        () async {
      // "받음" appears in 3 sentences — with threshold=2 it becomes a
      // stopword and BFS must NOT expand into it from another start node.
      final receive = await ops.upsertNode('받음');
      final coffee = await ops.upsertNode('커피');
      final pkg = await ops.upsertNode('택배');
      final s1 = await ops.addSentence(postId: postId, text: '커피 받음');
      final s2 = await ops.addSentence(postId: postId, text: '택배 받음');
      final s3 = await ops.addSentence(postId: postId, text: '메시지 받음');
      await ops.addMention(nodeId: coffee, sentenceId: s1);
      await ops.addMention(nodeId: receive, sentenceId: s1);
      await ops.addMention(nodeId: pkg, sentenceId: s2);
      await ops.addMention(nodeId: receive, sentenceId: s2);
      await ops.addMention(nodeId: receive, sentenceId: s3);

      final mentions = await ops.bfsRetrieve(
        startNodes: {coffee},
        stopwordThreshold: 2,
      );
      // BFS must surface the start node's own sentence but stop there:
      // 받음 is a stopword, so neither 택배 nor s2/s3 should appear.
      expect(mentions.map((m) => m.sentenceId).toSet(), {s1});
    });

    test('respects maxSentences (cuts off once collection reaches the cap)',
        () async {
      // 5-hop chain. With maxSentences=1 the BFS records only the first
      // layer's mention (ids[0] @ edge0) and breaks immediately. With
      // maxSentences=2 we also pick up (ids[1] @ edge1).
      final ids = <int>[];
      for (var i = 0; i < 6; i++) {
        ids.add(await ops.upsertNode('N$i'));
      }
      for (var i = 0; i < 5; i++) {
        final sid = await ops.addSentence(postId: postId, text: 'edge$i');
        await ops.addMention(nodeId: ids[i], sentenceId: sid);
        await ops.addMention(nodeId: ids[i + 1], sentenceId: sid);
      }
      final m1 = await ops.bfsRetrieve(
        startNodes: {ids[0]},
        maxSentences: 1,
      );
      expect(m1.map((m) => m.nodeId).toSet(), {ids[0]});

      final m2 = await ops.bfsRetrieve(
        startNodes: {ids[0]},
        maxSentences: 2,
      );
      expect(m2.map((m) => m.nodeId).toSet(), {ids[0], ids[1]});
    });
  });

  group('findSuspectedTypos', () {
    late SynapseEngine engine;
    late GraphOps ops;

    setUp(() async {
      engine = await _engine();
      ops = engine.graph!;
    });

    tearDown(() async {
      await engine.dispose();
    });

    test('flags 스타벅스/스타벅시 and ignores unrelated nodes', () async {
      await ops.upsertNode('스타벅스');
      await ops.upsertNode('스타벅시');
      await ops.upsertNode('강남세브란스');
      await ops.upsertNode('허리디스크');

      final candidates = await ops.findSuspectedTypos();
      expect(candidates, hasLength(1));
      final pair = candidates.single;
      expect({pair.left.name, pair.right.name}, {'스타벅스', '스타벅시'});
      expect(pair.distance, 1);
    });

    test('skips short names below minJamoLen', () async {
      await ops.upsertNode('가');
      await ops.upsertNode('나');
      expect(await ops.findSuspectedTypos(), isEmpty);
    });
  });
}

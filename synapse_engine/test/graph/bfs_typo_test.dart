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

    test('respects maxLayers (truncates traversal after N layers)', () async {
      // 5-hop chain. With maxLayers=1 only the first layer fires —
      // emitting just (N0, edge0). N1 enters `current` for the next
      // layer but the loop exits before that layer runs.
      final ids = <int>[];
      for (var i = 0; i < 6; i++) {
        ids.add(await ops.upsertNode('N$i'));
      }
      for (var i = 0; i < 5; i++) {
        final sid = await ops.addSentence(postId: postId, text: 'edge$i');
        await ops.addMention(nodeId: ids[i], sentenceId: sid);
        await ops.addMention(nodeId: ids[i + 1], sentenceId: sid);
      }
      final m1 = await ops.bfsRetrieve(startNodes: {ids[0]}, maxLayers: 1);
      expect(m1.map((m) => m.nodeId).toSet(), {ids[0]});

      final m2 = await ops.bfsRetrieve(startNodes: {ids[0]}, maxLayers: 2);
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

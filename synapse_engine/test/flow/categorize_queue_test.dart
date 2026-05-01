import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/flow/categorize_queue.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';
import 'package:synapse_engine/src/llm/stub_backend.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  Future<({SynapseEngine engine, CategorizeQueue queue, StubInferenceBackend stub})>
      setup({Map<String, String>? canned}) async {
    final stub = StubInferenceBackend(canned: canned);
    final kiwi = InMemoryKiwiBackend(fixtures: const {});
    final engine = await SynapseEngine.create(
      EngineConfig(
        appName: 'categorize_queue_test',
        allowedKinds: const ['note'],
        reservedKinds: const [],
        dbPath: inMemoryDatabasePath,
        categorySeed: CategorySeed.synapse19(),
        promptOverrides: const {
          'category': '<sys:category>',
          'metaFilter': '<sys:metaFilter>',
          'retrieveExpand': '<sys:retrieveExpand>',
          'keywordFilter': '<sys:keywordFilter>',
          'synapseAnswer': '<sys:synapseAnswer>',
        },
      ),
      kiwiOverride: kiwi,
      backendOverride: stub,
    );
    final queue = CategorizeQueue(
      db: engine.db,
      graph: engine.graph!,
      llm: engine.llm!,
    );
    return (engine: engine, queue: queue, stub: stub);
  }

  Future<int> seedNode(
    SynapseEngine engine, {
    required String name,
    required String sentence,
    required int postId,
    int position = 0,
  }) async {
    final sentenceId = await engine.db.insert('sentences', {
      'post_id': postId,
      'text': sentence,
      'origin': 'user',
      'position': position,
    });
    final nodeId = await engine.db.insert('nodes', {'name': name});
    await engine.db.insert('node_sentence_mentions', {
      'node_id': nodeId,
      'sentence_id': sentenceId,
      'origin': 'user',
    });
    return nodeId;
  }

  Future<int> insertPost(SynapseEngine engine) =>
      engine.db.insert('posts', {'kind': 'note'});

  Future<int> mentionsCount(SynapseEngine engine, int nodeId) async {
    return Sqflite.firstIntValue(
          await engine.db.rawQuery(
            'SELECT COUNT(*) FROM node_category_mentions WHERE node_id = ?',
            [nodeId],
          ),
        ) ??
        0;
  }

  test('enqueueNode → categorize → addCategoryMention', () async {
    final s = await setup(canned: {
      '::노드: 허리\n맥락 문장:\n- 허리 아픔':
          '{"categories": ["BOD.disease"]}',
    });
    try {
      final postId = await insertPost(s.engine);
      final nodeId = await seedNode(
        s.engine,
        name: '허리',
        sentence: '허리 아픔',
        postId: postId,
      );

      s.queue.enqueueNode(nodeId);
      await s.queue.drain();

      final rows = await s.engine.db.rawQuery(
        '''
        SELECT c.name AS sub, p.name AS root, ncm.origin
        FROM node_category_mentions ncm
        JOIN categories c ON c.id = ncm.category_id
        JOIN categories p ON p.id = c.parent_id
        WHERE ncm.node_id = ?
        ''',
        [nodeId],
      );
      expect(rows, hasLength(1));
      expect(rows.first['root'], 'BOD');
      expect(rows.first['sub'], 'disease');
      expect(rows.first['origin'], 'ai');
      expect(s.stub.generateCalls, 1);
    } finally {
      await s.engine.dispose();
    }
  });

  test('dedup: same node enqueued twice → categorize called once',
      () async {
    final s = await setup(canned: {
      '::노드: 허리\n맥락 문장:\n- 허리 아픔':
          '{"categories": ["BOD.disease"]}',
    });
    try {
      final postId = await insertPost(s.engine);
      final nodeId = await seedNode(
        s.engine,
        name: '허리',
        sentence: '허리 아픔',
        postId: postId,
      );

      // Two enqueues before draining; second one must be ignored.
      s.queue.enqueueNode(nodeId);
      s.queue.enqueueNode(nodeId);
      await s.queue.drain();

      expect(s.stub.generateCalls, 1);
      expect(await mentionsCount(s.engine, nodeId), 1);
    } finally {
      await s.engine.dispose();
    }
  });

  test('enqueuePost picks only nodes without an ai-origin mention',
      () async {
    final s = await setup(canned: {
      '::노드: 허리\n맥락 문장:\n- 허리 아픔':
          '{"categories": ["BOD.disease"]}',
    });
    try {
      final postId = await insertPost(s.engine);

      // Pre-categorized node — autosave must not re-classify.
      final preNodeId = await seedNode(
        s.engine,
        name: '출장',
        sentence: '출장 일정',
        postId: postId,
        position: 0,
      );
      final wrkRoot = (await s.engine.db.query(
        'categories',
        where: 'name = ? AND parent_id IS NULL',
        whereArgs: ['WRK'],
      ))
          .first['id']! as int;
      await s.engine.graph!.addCategoryMention(
        nodeId: preNodeId,
        categoryId: wrkRoot,
        origin: 'ai',
      );

      // Pending node — should be classified.
      final pendingNodeId = await seedNode(
        s.engine,
        name: '허리',
        sentence: '허리 아픔',
        postId: postId,
        position: 1,
      );

      await s.queue.enqueuePost(postId);
      await s.queue.drain();

      // categorize ran exactly once — for the pending node.
      expect(s.stub.generateCalls, 1);
      // Pre-categorized stays at one mention; pending gets its first.
      expect(await mentionsCount(s.engine, preNodeId), 1);
      expect(await mentionsCount(s.engine, pendingNodeId), 1);
    } finally {
      await s.engine.dispose();
    }
  });

  test('processedNotifier increments per node finished', () async {
    final s = await setup(canned: {
      '::노드: 허리\n맥락 문장:\n- 허리 아픔':
          '{"categories": ["BOD.disease"]}',
      '::노드: 김밥\n맥락 문장:\n- 김밥 먹음':
          '{"categories": ["FOD.ingredient"]}',
    });
    try {
      final postId = await insertPost(s.engine);
      final huri = await seedNode(
        s.engine,
        name: '허리',
        sentence: '허리 아픔',
        postId: postId,
      );
      final gimbap = await seedNode(
        s.engine,
        name: '김밥',
        sentence: '김밥 먹음',
        postId: postId,
        position: 1,
      );

      expect(s.queue.processedNotifier.value, 0);
      s.queue.enqueueNode(huri);
      s.queue.enqueueNode(gimbap);
      await s.queue.drain();
      expect(s.queue.processedNotifier.value, 2);
    } finally {
      await s.engine.dispose();
    }
  });

  test('enqueueAll picks every uncategorized node across posts', () async {
    final s = await setup(canned: {
      '::노드: 허리\n맥락 문장:\n- 허리 아픔':
          '{"categories": ["BOD.disease"]}',
      '::노드: 김밥\n맥락 문장:\n- 김밥 먹음':
          '{"categories": ["FOD.ingredient"]}',
    });
    try {
      final postA = await insertPost(s.engine);
      final postB = await insertPost(s.engine);

      final huriId = await seedNode(
        s.engine,
        name: '허리',
        sentence: '허리 아픔',
        postId: postA,
      );
      final gimbapId = await seedNode(
        s.engine,
        name: '김밥',
        sentence: '김밥 먹음',
        postId: postB,
      );

      await s.queue.enqueueAll();
      await s.queue.drain();

      expect(s.stub.generateCalls, 2);
      expect(await mentionsCount(s.engine, huriId), 1);
      expect(await mentionsCount(s.engine, gimbapId), 1);
    } finally {
      await s.engine.dispose();
    }
  });
}

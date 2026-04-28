import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';

Future<SynapseEngine> _engine() => SynapseEngine.create(
      EngineConfig(
        appName: 'get_graph_test',
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

  group('SynapseFlow.getGraph', () {
    late SynapseEngine engine;
    late SynapseFlow flow;

    setUp(() async {
      engine = await _engine();
      flow = engine.flow!;
    });

    tearDown(() async {
      await engine.dispose();
    });

    test('empty DB → all empty lists', () async {
      final g = await flow.getGraph();
      expect(g.nodes, isEmpty);
      expect(g.sentences, isEmpty);
      expect(g.mentions, isEmpty);
      expect(g.categories, isEmpty);
      expect(g.nodeCategories, isEmpty);
      expect(g.isEmpty, isTrue);
    });

    test('postId filter → only that post\'s sentences + mentioned nodes',
        () async {
      // Post A (target): two sentences, three nodes, two mentions each.
      final pidA = await engine.db.insert('posts', {'kind': 'note'});
      final n1 = await engine.graph!.upsertNode('허리');
      final n2 = await engine.graph!.upsertNode('물리치료');
      final n3 = await engine.graph!.upsertNode('병원');
      final sA1 = await engine.graph!
          .addSentence(postId: pidA, text: '허리 아파서 병원');
      final sA2 = await engine.graph!
          .addSentence(postId: pidA, text: '물리치료 시작');
      await engine.graph!.addMention(nodeId: n1, sentenceId: sA1);
      await engine.graph!.addMention(nodeId: n3, sentenceId: sA1);
      await engine.graph!.addMention(nodeId: n2, sentenceId: sA2);

      // Post B (noise): different sentence + different node.
      final pidB = await engine.db.insert('posts', {'kind': 'note'});
      final n4 = await engine.graph!.upsertNode('회의');
      final sB1 = await engine.graph!
          .addSentence(postId: pidB, text: '회의 잡힘');
      await engine.graph!.addMention(nodeId: n4, sentenceId: sB1);

      final g = await flow.getGraph(postId: pidA);

      // Sentences: only post A's two.
      expect(g.sentences.map((s) => s.id).toSet(), {sA1, sA2});
      expect(g.sentences.every((s) => s.postId == pidA), isTrue);

      // Nodes: 허리·물리치료·병원, no 회의.
      final nodeNames = g.nodes.map((n) => n.name).toSet();
      expect(nodeNames, {'허리', '물리치료', '병원'});
      expect(nodeNames, isNot(contains('회의')));

      // Mentions: exactly the 3 we inserted in post A.
      expect(g.mentions, hasLength(3));

      // Degrees: 허리·물리치료·병원 each appear in 1 sentence within post A.
      final byName = {for (final n in g.nodes) n.name: n};
      expect(byName['허리']!.degree, 1);
      expect(byName['물리치료']!.degree, 1);
      expect(byName['병원']!.degree, 1);
    });

    test('nodeIds filter → those nodes + every sentence they appear in',
        () async {
      // Two posts, one shared node ('허리') and one unrelated ('회의').
      final pidA = await engine.db.insert('posts', {'kind': 'note'});
      final pidB = await engine.db.insert('posts', {'kind': 'note'});
      final huri = await engine.graph!.upsertNode('허리');
      final hoeui = await engine.graph!.upsertNode('회의');
      final byungwon = await engine.graph!.upsertNode('병원');

      final sA = await engine.graph!
          .addSentence(postId: pidA, text: '허리 진단');
      final sB = await engine.graph!
          .addSentence(postId: pidB, text: '허리 다시 아파');
      final sC = await engine.graph!
          .addSentence(postId: pidB, text: '회의 잡힘');
      await engine.graph!.addMention(nodeId: huri, sentenceId: sA);
      await engine.graph!.addMention(nodeId: byungwon, sentenceId: sA);
      await engine.graph!.addMention(nodeId: huri, sentenceId: sB);
      await engine.graph!.addMention(nodeId: hoeui, sentenceId: sC);

      final g = await flow.getGraph(nodeIds: [huri]);

      // Sentences = the 2 sentences that mention 허리, regardless of post.
      expect(g.sentences.map((s) => s.id).toSet(), {sA, sB});

      // Nodes = only 허리 (병원 + 회의 share posts but weren't requested).
      expect(g.nodes.map((n) => n.name).toList(), ['허리']);

      // Mentions filtered down to just (허리, sA) + (허리, sB) — the
      // (병원, sA) mention must NOT bleed in even though sA is in the
      // working sentence set.
      expect(g.mentions, hasLength(2));
      expect(g.mentions.every((m) => m.nodeId == huri), isTrue);

      // Degree of 허리 within this filtered view = 2.
      expect(g.nodes.single.degree, 2);
    });

    test('full snapshot (no filter) → every post + isInsight propagates',
        () async {
      // Note post with one mention.
      final notePid = await engine.db.insert('posts', {'kind': 'note'});
      final huri = await engine.graph!.upsertNode('허리');
      final noteSid = await engine.graph!
          .addSentence(postId: notePid, text: '허리 아파');
      await engine.graph!.addMention(nodeId: huri, sentenceId: noteSid);

      // Insight post: same 허리 node connected to an insight-origin sentence.
      final insightPid = await engine.db.insert('posts', {'kind': 'insight'});
      final insightSid = await engine.graph!.addSentence(
        postId: insightPid,
        text: '허리 치료 진행 정리',
        origin: 'insight',
      );
      await engine.graph!
          .addMention(nodeId: huri, sentenceId: insightSid);

      final g = await flow.getGraph();

      // Both posts contribute sentences.
      expect(g.sentences.map((s) => s.postId).toSet(),
          {notePid, insightPid});
      expect(g.sentences, hasLength(2));

      // 허리 has degree 2 + isInsight=true (connected to insight sentence).
      expect(g.nodes.single.name, '허리');
      expect(g.nodes.single.degree, 2);
      expect(g.nodes.single.isInsight, isTrue);
    });

    test('primaryCategoryCode picks first seed-root code by category_id',
        () async {
      // Set up: one node with two seed-root mappings + one user heading.
      final pid = await engine.db.insert('posts', {'kind': 'note'});
      final huri = await engine.graph!.upsertNode('허리');
      final sid = await engine.graph!
          .addSentence(postId: pid, text: '허리 진단');
      await engine.graph!.addMention(nodeId: huri, sentenceId: sid);

      // Seed roots are pre-inserted by category_seed migration. Pull two
      // codes and attach them deterministically to 허리.
      final bod = (await engine.db.query(
        'categories',
        columns: ['id'],
        where: 'name = ? AND parent_id IS NULL',
        whereArgs: ['BOD'],
      )).single['id']! as int;
      final wrk = (await engine.db.query(
        'categories',
        columns: ['id'],
        where: 'name = ? AND parent_id IS NULL',
        whereArgs: ['WRK'],
      )).single['id']! as int;

      await engine.graph!.addCategoryMention(nodeId: huri, categoryId: bod);
      await engine.graph!.addCategoryMention(nodeId: huri, categoryId: wrk);

      // User heading category — must NOT be chosen as primary code.
      final userCatId = await engine.graph!.upsertCategoryPath('건강');
      await engine.graph!
          .addCategoryMention(nodeId: huri, categoryId: userCatId!);

      final g = await flow.getGraph();
      // Lower category_id wins. BOD is the 2nd seed root in seedRoots19,
      // WRK is the 7th, so BOD's id is lower → primaryCategoryCode = BOD.
      final node = g.nodes.single;
      final lowerCode = bod < wrk ? 'BOD' : 'WRK';
      expect(node.primaryCategoryCode, lowerCode);

      // GraphCategory.code is filled only on seed roots, not user headings.
      final byId = {for (final c in g.categories) c.id: c};
      expect(byId[bod]!.code, 'BOD');
      expect(byId[userCatId]!.code, isNull);
    });

    test('primaryCategoryCode walks leaf → root for sub-category mentions',
        () async {
      // LLM categorize attaches to a leaf (BOD.disease), not the root.
      // Color attribution still needs the root code, so getGraph must
      // walk parent_id up before reading cat.code.
      final pid = await engine.db.insert('posts', {'kind': 'note'});
      final huri = await engine.graph!.upsertNode('허리');
      final sid = await engine.graph!
          .addSentence(postId: pid, text: '허리 아픔');
      await engine.graph!.addMention(nodeId: huri, sentenceId: sid);

      final bodRoot = (await engine.db.query(
        'categories',
        columns: ['id'],
        where: 'name = ? AND parent_id IS NULL',
        whereArgs: ['BOD'],
      )).single['id']! as int;
      final disease = (await engine.db.query(
        'categories',
        columns: ['id'],
        where: 'name = ? AND parent_id = ?',
        whereArgs: ['disease', bodRoot],
      )).single['id']! as int;
      await engine.graph!.addCategoryMention(
        nodeId: huri,
        categoryId: disease,
        origin: 'ai',
      );

      final g = await flow.getGraph();
      expect(g.nodes.single.primaryCategoryCode, 'BOD');
    });

    test('postId + nodeIds together → ArgumentError', () async {
      expect(
        () => flow.getGraph(postId: 1, nodeIds: const [1]),
        throwsArgumentError,
      );
    });
  });
}

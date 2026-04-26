import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';

Future<SynapseEngine> _engine() => SynapseEngine.create(
      EngineConfig(
        appName: 'flow_test',
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

  group('SynapseFlow', () {
    late SynapseEngine engine;
    late SynapseFlow flow;

    setUp(() async {
      engine = await _engine();
      flow = engine.flow!;
    });

    tearDown(() async {
      await engine.dispose();
    });

    test('attached only when reservedKinds enables synapse + insight',
        () async {
      // Reuse-app config — should NOT have a SynapseFlow.
      final reuse = await SynapseEngine.create(
        EngineConfig(
          appName: 'reuse',
          allowedKinds: const ['message'],
          reservedKinds: const [],
          dbPath: inMemoryDatabasePath,
          categorySeed: CategorySeed.empty(),
        ),
        kiwiOverride: InMemoryKiwiBackend(),
      );
      try {
        expect(reuse.flow, isNull);
      } finally {
        await reuse.dispose();
      }
    });

    test('listPosts returns rows newest-first and respects kind filter',
        () async {
      final n1 = await engine.db.insert('posts', {'kind': 'note'});
      final n2 = await engine.db.insert('posts', {'kind': 'note'});
      final s1 = await engine.db.insert('posts', {'kind': 'synapse'});
      // Bump n2 forward in time so it sorts first.
      await engine.db.update(
        'posts',
        {'updated_at': '9999-12-31 23:59:59'},
        where: 'id = ?',
        whereArgs: [n2],
      );

      final all = await flow.listPosts();
      expect(all.first.id, n2);
      expect(all.length, 3);

      final notesOnly = await flow.listPosts(kind: 'note');
      expect(notesOnly.map((p) => p.id), [n2, n1]);
      expect(notesOnly.every((p) => p.kind == 'note'), isTrue);
      expect(s1, isNonZero);
    });

    test('getPost hydrates sentences in position order', () async {
      final pid = await engine.db.insert('posts', {
        'kind': 'note',
        'title': 'demo',
        'source': 'raw text',
      });
      await engine.db.insert('sentences',
          {'post_id': pid, 'text': 'second', 'position': 1});
      await engine.db.insert('sentences',
          {'post_id': pid, 'text': 'first', 'position': 0});

      final detail = await flow.getPost(pid);
      expect(detail.meta.title, 'demo');
      expect(detail.source, 'raw text');
      expect(detail.sentences.map((s) => s.text), ['first', 'second']);
    });

    test('updatePostTitle persists the new title', () async {
      final pid = await engine.db.insert('posts', {'kind': 'note'});
      await flow.updatePostTitle(pid, 'renamed');
      final row = (await engine.db.query(
        'posts',
        where: 'id = ?',
        whereArgs: [pid],
      )).single;
      expect(row['title'], 'renamed');
    });

    test('deletePost cascades sentences', () async {
      final pid = await engine.db.insert('posts', {'kind': 'note'});
      await engine.db.insert('sentences', {
        'post_id': pid,
        'text': 'will be deleted',
      });
      await flow.deletePost(pid);
      final s = Sqflite.firstIntValue(
        await engine.db.rawQuery(
          'SELECT COUNT(*) FROM sentences WHERE post_id = ?',
          [pid],
        ),
      );
      expect(s, 0);
    });

    // ── synapseTurn ───────────────────────────────────────

    test('synapseTurn creates a synapse post and persists Q/A', () async {
      // Seed a tiny graph: '허리디스크' mentioned in one note sentence.
      final notePid = await engine.db.insert('posts', {'kind': 'note'});
      final hsk = await engine.graph!.upsertNode('허리디스크');
      final sid = await engine.graph!
          .addSentence(postId: notePid, text: '허리디스크 진단 받음');
      await engine.graph!.addMention(nodeId: hsk, sentenceId: sid);

      final result = await flow.synapseTurn(question: '허리디스크 어때?');

      expect(result.postId, isPositive);
      // The post exists and is kind='synapse'.
      final post = (await engine.db.query(
        'posts',
        where: 'id = ?',
        whereArgs: [result.postId],
      )).single;
      expect(post['kind'], 'synapse');

      // Two sentences (question + answer) were inserted.
      final sentences = await engine.db.query(
        'sentences',
        where: 'post_id = ?',
        whereArgs: [result.postId],
        orderBy: 'position ASC',
      );
      expect(sentences, hasLength(2));
      expect(sentences[0]['role'], 'user');
      expect(sentences[0]['text'], '허리디스크 어때?');
      expect(sentences[1]['role'], 'assistant');
      expect(result.answer, isNotEmpty);

      // BFS picked up the seed node.
      expect(result.retrievedNodeIds, contains(hsk));
    });

    test('synapseTurn ties follow-up turns to the same post when postId given',
        () async {
      final first = await flow.synapseTurn(question: 'first?');
      final second = await flow.synapseTurn(
        question: 'second?',
        postId: first.postId,
      );
      expect(second.postId, first.postId);
      final all = await engine.db.query(
        'sentences',
        where: 'post_id = ?',
        whereArgs: [first.postId],
        orderBy: 'position ASC',
      );
      expect(all, hasLength(4)); // q1, a1, q2, a2
    });

    // ── promoteToInsight ─────────────────────────────────

    test('promoteToInsight creates an insight post with Hebbian links',
        () async {
      final hsk = await engine.graph!.upsertNode('허리디스크');
      final exer = await engine.graph!.upsertNode('운동');

      final result = await flow.promoteToInsight(
        body: '허리에는 꾸준한 운동이 도움이 된다',
        snapshotNodeIds: [hsk, exer],
      );
      expect(result.postId, isPositive);
      expect(result.sentenceIds, isNotEmpty);
      expect(result.connectedNodeCount, greaterThanOrEqualTo(2));

      // Post is kind='insight' with the body's first line as title.
      final row = (await engine.db.query(
        'posts',
        where: 'id = ?',
        whereArgs: [result.postId],
      )).single;
      expect(row['kind'], 'insight');
      expect(row['title'], '허리에는 꾸준한 운동이 도움이 된다');
      expect(row['source'], '허리에는 꾸준한 운동이 도움이 된다');

      // Each sentence is origin='insight'.
      final sentences = await engine.db.query(
        'sentences',
        where: 'post_id = ?',
        whereArgs: [result.postId],
      );
      expect(sentences.every((s) => s['origin'] == 'insight'), isTrue);

      // Snapshot nodes are wired to every sentence via mentions.
      for (final sid in result.sentenceIds) {
        final mentions = await engine.db.query(
          'node_sentence_mentions',
          where: 'sentence_id = ?',
          whereArgs: [sid],
        );
        final ids = mentions.map((m) => m['node_id'] as int).toSet();
        expect(ids, containsAll([hsk, exer]));
      }
    });

    test('promoteToInsight with empty snapshot still inserts the body',
        () async {
      final result = await flow.promoteToInsight(
        body: '오늘 깨달은 것: 휴식도 운동이다',
        snapshotNodeIds: const [],
      );
      expect(result.sentenceIds, hasLength(1));
      // No snapshot nodes → connectedNodeCount only counts Kiwi nouns
      // (InMemoryKiwiBackend has no fixture for this text → 0).
      expect(result.connectedNodeCount, 0);
    });

    test('promoteToInsight rejects empty body', () async {
      expect(
        () => flow.promoteToInsight(body: '   ', snapshotNodeIds: const []),
        throwsArgumentError,
      );
    });

    test('insight sentences cannot be edited via updateSentence', () async {
      final result = await flow.promoteToInsight(
        body: '편집 금지 통찰',
        snapshotNodeIds: const [],
      );
      final sid = result.sentenceIds.single;
      expect(
        () => engine.graph!.updateSentence(sid, '바뀐 본문'),
        throwsStateError,
      );
    });
  });
}

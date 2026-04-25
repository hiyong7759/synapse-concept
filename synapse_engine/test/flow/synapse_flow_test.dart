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
  });
}

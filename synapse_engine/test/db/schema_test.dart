import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/src/db/category_seed.dart' show buildAdjacentMap;
import 'package:synapse_engine/synapse_engine.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('schema v1', () {
    late SynapseEngine engine;

    setUp(() async {
      engine = await SynapseEngine.create(
        EngineConfig(
          appName: 'test_synapse',
          allowedKinds: const ['note', 'synapse', 'insight'],
          reservedKinds: const ['synapse', 'insight'],
          dbPath: inMemoryDatabasePath,
          categorySeed: CategorySeed.synapse19(),
        ),
      );
    });

    tearDown(() async {
      await engine.dispose();
    });

    test('9 hypergraph tables exist', () async {
      final rows = await engine.db.rawQuery(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'android_%'",
      );
      final names = rows.map((r) => r['name'] as String).toSet();
      expect(names, containsAll([
        'posts',
        'sentences',
        'nodes',
        'node_sentence_mentions',
        'categories',
        'sentence_categories',
        'node_category_mentions',
        'aliases',
        'unresolved_tokens',
      ]));
    });

    test('category seed inserts 19 roots + 114 leaves = 133 rows', () async {
      final total = Sqflite.firstIntValue(
        await engine.db.rawQuery('SELECT COUNT(*) FROM categories'),
      );
      expect(total, 133);

      final rootCount = Sqflite.firstIntValue(
        await engine.db.rawQuery(
          'SELECT COUNT(*) FROM categories WHERE parent_id IS NULL',
        ),
      );
      expect(rootCount, 19);

      // Spot-check a few macro codes are present as roots.
      for (final code in ['PER', 'BOD', 'TIM', 'ACT']) {
        final hit = Sqflite.firstIntValue(
          await engine.db.rawQuery(
            'SELECT COUNT(*) FROM categories WHERE name = ? AND parent_id IS NULL',
            [code],
          ),
        );
        expect(hit, 1, reason: '$code root missing');
      }
    });

    test('posts.kind CHECK accepts allowed kinds', () async {
      for (final kind in ['note', 'synapse', 'insight']) {
        final id = await engine.db.insert('posts', {'kind': kind});
        expect(id, greaterThan(0));
      }
    });

    test('posts.kind CHECK rejects an unknown kind', () async {
      expect(
        () => engine.db.insert('posts', {'kind': 'message'}),
        throwsA(isA<DatabaseException>()),
      );
    });

    test('posts.kind defaults to allowedKinds.first', () async {
      final id = await engine.db.insert('posts', {'title': 'no kind given'});
      final row = (await engine.db.query(
        'posts',
        where: 'id = ?',
        whereArgs: [id],
      )).single;
      expect(row['kind'], 'note');
    });

    test('categories UNIQUE(parent_id, name) prevents duplicate children',
        () async {
      // PER's child 'individual' is already seeded.
      // Fetch PER's id and try to insert a duplicate child under it.
      final perId = Sqflite.firstIntValue(
        await engine.db.rawQuery(
          'SELECT id FROM categories WHERE name = ? AND parent_id IS NULL',
          ['PER'],
        ),
      );
      expect(perId, isNotNull);
      expect(
        () => engine.db.insert(
          'categories',
          {'name': 'individual', 'parent_id': perId},
        ),
        throwsA(isA<DatabaseException>()),
      );
      // Note: SQLite treats each NULL as distinct in UNIQUE indexes, so
      // duplicate roots (parent_id IS NULL) are NOT prevented by the schema.
      // Root-name uniqueness is enforced by application-level guard
      // (DESIGN_CATEGORY §계층 확장 규칙 — 루트 네이밍 충돌 방지).
    });

    test('FK CASCADE deletes sentences when their post is deleted', () async {
      final postId = await engine.db.insert('posts', {'kind': 'note'});
      await engine.db.insert('sentences', {
        'post_id': postId,
        'text': 'hello',
      });
      await engine.db.delete('posts', where: 'id = ?', whereArgs: [postId]);
      final remaining = Sqflite.firstIntValue(
        await engine.db.rawQuery(
          'SELECT COUNT(*) FROM sentences WHERE post_id = ?',
          [postId],
        ),
      );
      expect(remaining, 0);
    });

    test('sentences.origin CHECK rejects invalid value', () async {
      final postId = await engine.db.insert('posts', {'kind': 'note'});
      expect(
        () => engine.db.insert('sentences', {
          'post_id': postId,
          'text': 'x',
          'origin': 'system',
        }),
        throwsA(isA<DatabaseException>()),
      );
    });

    test('node_sentence_mentions.origin CHECK accepts the four values',
        () async {
      final postId = await engine.db.insert('posts', {'kind': 'note'});
      final sid = await engine.db.insert('sentences', {
        'post_id': postId,
        'text': 'hello',
      });
      final nid = await engine.db.insert('nodes', {'name': 'hello'});
      for (final origin in const ['user', 'ai', 'system', 'external']) {
        // Use a separate sentence row for each so PK doesn't conflict.
        final s = await engine.db.insert('sentences', {
          'post_id': postId,
          'text': 'origin=$origin',
        });
        final id = await engine.db.insert('node_sentence_mentions', {
          'node_id': nid,
          'sentence_id': s,
          'origin': origin,
        });
        expect(id, isNonZero);
      }
      // Avoid unused warning about sid.
      expect(sid, isNonZero);
    });
  });

  group('reuse-app config (gabjil-style)', () {
    test('custom allowedKinds CHECK is enforced', () async {
      final engine = await SynapseEngine.create(
        EngineConfig(
          appName: 'test_gabjil',
          allowedKinds: const ['message', 'thread', 'friend'],
          reservedKinds: const [],
          dbPath: inMemoryDatabasePath,
          categorySeed: CategorySeed.empty(),
        ),
      );
      try {
        // Allowed kind goes through.
        await engine.db.insert('posts', {'kind': 'message'});
        // Synapse-app kind is rejected.
        expect(
          () => engine.db.insert('posts', {'kind': 'note'}),
          throwsA(isA<DatabaseException>()),
        );
        // Empty seed → 0 categories.
        final count = Sqflite.firstIntValue(
          await engine.db.rawQuery('SELECT COUNT(*) FROM categories'),
        );
        expect(count, 0);
        expect(engine.config.isSynapseFlowEnabled, isFalse);
      } finally {
        await engine.dispose();
      }
    });
  });

  group('adjacency map', () {
    test('expands single-direction pairs into bidirectional map', () {
      final map = buildAdjacentMap(const [
        ('A.x', 'B.y'),
        ('A.x', 'C.z'),
      ]);
      expect(map['A.x'], containsAll(['B.y', 'C.z']));
      expect(map['B.y'], ['A.x']);
      expect(map['C.z'], ['A.x']);
    });
  });
}

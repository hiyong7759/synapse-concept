import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';

Future<SynapseEngine> _engine() => SynapseEngine.create(
      EngineConfig(
        appName: 'recent_test',
        allowedKinds: const ['note', 'synapse', 'insight'],
        reservedKinds: const ['synapse', 'insight'],
        dbPath: inMemoryDatabasePath,
        categorySeed: CategorySeed.synapse19(),
      ),
      kiwiOverride: InMemoryKiwiBackend(),
    );

/// Inserts a `post → sentence → node → mention` chain and lets the
/// caller backdate the sentence so the recency window can be exercised.
Future<int> _seedMention(
  SynapseEngine engine, {
  required String nodeName,
  String? createdAt,
  int? reuseNodeId,
}) async {
  final pid = await engine.db.insert('posts', {'kind': 'note'});
  final sid = await engine.db.insert('sentences', {
    'post_id': pid,
    'text': 'about $nodeName',
    'position': 0,
  });
  final nid = reuseNodeId ??
      await engine.db.insert('nodes', {'name': nodeName});
  await engine.db.insert('node_sentence_mentions', {
    'node_id': nid,
    'sentence_id': sid,
    'origin': 'system',
  });
  if (createdAt != null) {
    await engine.db.update(
      'sentences',
      {'created_at': createdAt},
      where: 'id = ?',
      whereArgs: [sid],
    );
  }
  return nid;
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('SynapseFlow.recentTopNodes', () {
    late SynapseEngine engine;
    late SynapseFlow flow;

    setUp(() async {
      engine = await _engine();
      flow = engine.flow!;
    });

    tearDown(() async {
      await engine.dispose();
    });

    test('empty DB returns an empty list', () async {
      final result = await flow.recentTopNodes();
      expect(result, isEmpty);
    });

    test('orders by mention count desc, ties broken by recency', () async {
      final waist = await _seedMention(engine, nodeName: '허리');
      await _seedMention(engine, nodeName: '허리', reuseNodeId: waist);
      await _seedMention(engine, nodeName: '허리', reuseNodeId: waist);
      await _seedMention(engine, nodeName: '디스크');
      await _seedMention(engine, nodeName: '진단');

      final result = await flow.recentTopNodes(limit: 5);
      expect(result.first.name, '허리');
      expect(result.first.mentionCount, 3);
      expect(result.length, 3);
    });

    test('respects [limit]', () async {
      for (final n in ['a', 'b', 'c', 'd', 'e', 'f']) {
        await _seedMention(engine, nodeName: n);
      }
      final result = await flow.recentTopNodes(limit: 3);
      expect(result.length, 3);
    });

    test('excludes mentions older than [daysBack]', () async {
      // 30-day-old sentence — should be filtered out by a 7-day window.
      await _seedMention(
        engine,
        nodeName: 'old',
        createdAt: '2026-03-01 12:00:00',
      );
      await _seedMention(engine, nodeName: 'fresh');

      final result = await flow.recentTopNodes(daysBack: 7);
      expect(result.map((r) => r.name), contains('fresh'));
      expect(result.map((r) => r.name), isNot(contains('old')));
    });

    test('limit <= 0 short-circuits to empty', () async {
      await _seedMention(engine, nodeName: 'x');
      expect(await flow.recentTopNodes(limit: 0), isEmpty);
      expect(await flow.recentTopNodes(limit: -1), isEmpty);
    });
  });
}

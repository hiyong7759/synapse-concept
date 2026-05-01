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
}

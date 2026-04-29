@Tags(['perf'])
library;

import 'dart:io' show File, Platform;

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';

/// Live perf measurement for `synapseTurn`. Loads a real GGUF model
/// against a snapshot of the user's dogfood DB and runs one or more
/// turns — the [synapseTurn] kDebugMode print line carries the
/// per-stage milliseconds (PLAN-20260429-SYN-synapse-perf 마일스톤 F).
///
/// Required environment:
///   - SYNAPSE_TEST_MODEL          GGUF path
///   - SYNAPSE_TEST_DB             snapshot DB (default `/tmp/synapse_perf.db`)
///   - SYNAPSE_TEST_PROMPT_DIR     prompts dir (default `../docs`)
///
/// Run:
///   SYNAPSE_TEST_MODEL=/Volumes/macex/models/gemma-4-E2B-it-Q4_K_M.gguf \
///   flutter test test/flow/perf_measure_test.dart --tags perf
void main() {
  final modelPath = Platform.environment['SYNAPSE_TEST_MODEL'];
  final dbPath =
      Platform.environment['SYNAPSE_TEST_DB'] ?? '/tmp/synapse_perf.db';
  final promptDir =
      Platform.environment['SYNAPSE_TEST_PROMPT_DIR'] ?? '../docs';
  final maxSentences = int.tryParse(
        Platform.environment['SYNAPSE_TEST_MAX_SENT'] ?? '',
      ) ??
      50;
  final gpuLayers = int.tryParse(
        Platform.environment['SYNAPSE_TEST_GPU_LAYERS'] ?? '',
      ) ??
      99;

  String? resolveSkipReason() {
    if (modelPath == null) {
      return 'SYNAPSE_TEST_MODEL not set — perf measurement skipped';
    }
    if (!File(modelPath).existsSync()) {
      return 'model not found at $modelPath';
    }
    if (!File(dbPath).existsSync()) {
      return 'DB snapshot not found at $dbPath';
    }
    return null;
  }

  final skipReason = resolveSkipReason();

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('synapseTurn perf', () {
    late SynapseEngine engine;

    setUpAll(() async {
      if (skipReason != null) return;

      final overrides = <String, String>{
        for (final entry in const {
          'category': 'CATEGORY_SYSTEMPROMPT.md',
          'metaFilter': 'META_FILTER_SYSTEMPROMPT.md',
          'retrieveExpand': 'RETRIEVE_EXPAND_SYSTEMPROMPT.md',
          'retrieveFilter': 'RETRIEVE_FILTER_SYSTEMPROMPT.md',
          'synapseAnswer': 'SYNAPSE_ANSWER_SYSTEMPROMPT.md',
        }.entries)
          entry.key: await File('$promptDir/${entry.value}').readAsString(),
      };

      // Try the production FFI Kiwi first; fall back to in-memory if the
      // dylib isn't loadable in this test process. SynapseFlow attaches
      // only when `kiwi` is non-null, and noun extraction during
      // retrieve-expand directly affects BFS seed coverage — so the FFI
      // path makes the measurement match dogfood reality.
      KiwiBackend kiwi;
      try {
        kiwi = await FlutterKiwiBackend.load();
      } catch (_) {
        kiwi = InMemoryKiwiBackend();
      }

      engine = await SynapseEngine.create(
        EngineConfig(
          appName: 'perf_measure',
          allowedKinds: const ['note', 'synapse', 'insight'],
          reservedKinds: const ['synapse', 'insight'],
          dbPath: dbPath,
          categorySeed: CategorySeed.synapse19(),
          modelPath: modelPath,
          promptOverrides: overrides,
          retrieveMaxSentences: maxSentences,
          gpuLayers: gpuLayers,
        ),
        kiwiOverride: kiwi,
      );
    });

    tearDownAll(() async {
      if (skipReason != null) return;
      await engine.dispose();
    });

    test('turn 1 — 취업규칙 휴가 질문 (사용자 dogfood 재현)', () async {
      final flow = engine.flow!;
      const question = '취업규칙에서 휴가 며칠 주게 되어 있어?';
      final result = await flow.synapseTurn(question: question);
      expect(result.answer, isNotEmpty);
      expect(result.postId, isPositive);
      // ignore: avoid_print
      print('\n══ Q1 ══\n$question\n── A1 ──\n${result.answer}\n'
          '── ctx=${result.contextSentenceIds.length} ══\n');
    }, skip: skipReason, timeout: const Timeout(Duration(minutes: 5)));

    test('turn 2 — 다른 주제 (변동 확인)', () async {
      final flow = engine.flow!;
      const question = '최근 한 일 정리해줘';
      final result = await flow.synapseTurn(question: question);
      expect(result.answer, isNotEmpty);
      // ignore: avoid_print
      print('\n══ Q2 ══\n$question\n── A2 ──\n${result.answer}\n'
          '── ctx=${result.contextSentenceIds.length} ══\n');
    }, skip: skipReason, timeout: const Timeout(Duration(minutes: 5)));
  });
}

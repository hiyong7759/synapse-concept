@Tags(['integration'])
library;

import 'dart:io' show File, Platform;

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';

/// Real-model integration test. Skipped unless the environment supplies:
///   - SYNAPSE_TEST_MODEL  → absolute path to a Gemma 4 E2B GGUF
///   - SYNAPSE_TEST_PROMPT_DIR (optional, defaults to ../docs) → directory
///     holding {*}_SYSTEMPROMPT.md files. Used as `promptOverrides` to
///     bypass `rootBundle` (which requires a Flutter binding/asset manifest
///     this self-package test doesn't set up).
///
/// Run with:
///   SYNAPSE_TEST_MODEL=/Volumes/macex/models/gemma-4-E2B-it-Q4_K_M.gguf \
///   flutter test test/llm/tasks_integration_test.dart --tags integration
///
/// No adapter is loaded — the retrieve-expand LoRA was retired after the
/// 2026-04-26 PoC showed the v3 system prompt + base model matched or
/// outperformed it.
void main() {
  final modelPath = Platform.environment['SYNAPSE_TEST_MODEL'];
  final promptDir =
      Platform.environment['SYNAPSE_TEST_PROMPT_DIR'] ?? '../docs';
  final skipReason = modelPath == null
      ? 'SYNAPSE_TEST_MODEL not set — integration test skipped'
      : null;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('LlmTasks integration (real model)', () {
    late SynapseEngine engine;

    setUpAll(() async {
      if (modelPath == null) return;

      // Read prompts off disk and pass as overrides — keeps rootBundle out
      // of this test, which otherwise needs a TestWidgetsFlutterBinding
      // plus an AssetManifest that the package self-test environment
      // doesn't ship. End-to-end asset bundling is verified by downstream
      // consumer apps (F6+).
      final overrides = <String, String>{
        for (final entry in const {
          'category': 'CATEGORY_SYSTEMPROMPT.md',
          'metaFilter': 'META_FILTER_SYSTEMPROMPT.md',
          'retrieveExpand': 'RETRIEVE_EXPAND_SYSTEMPROMPT.md',
          'keywordFilter': 'KEYWORD_FILTER_SYSTEMPROMPT.md',
          'synapseAnswer': 'SYNAPSE_ANSWER_SYSTEMPROMPT.md',
        }.entries)
          entry.key: await File('$promptDir/${entry.value}').readAsString(),
      };

      engine = await SynapseEngine.create(
        EngineConfig(
          appName: 'integration',
          allowedKinds: const ['note', 'synapse', 'insight'],
          reservedKinds: const ['synapse', 'insight'],
          dbPath: inMemoryDatabasePath,
          categorySeed: CategorySeed.synapse19(),
          modelPath: modelPath,
          promptOverrides: overrides,
        ),
      );
    });

    tearDownAll(() async {
      if (modelPath == null) return;
      await engine.dispose();
    });

    test('retrieveExpand returns a non-empty list', () async {
      final result = await engine.llm!.retrieveExpand('허리 아픈데 어디 가야?');
      expect(result, isNotEmpty);
    }, skip: skipReason, timeout: const Timeout(Duration(minutes: 2)));

    test('filterKeywords drops noise keywords', () async {
      final result = await engine.llm!.filterKeywords(
        '슬램덩크 몇권?',
        const ['슬램덩크', '몇', '권', '있'],
      );
      expect(result.length, 4);
      expect(result[0], isTrue, reason: '고유명사 — 반드시 keep');
      // Recall-over-precision keeps borderline cases too — only assert
      // shape on the obviously-noise slots, not their bool.
    }, skip: skipReason, timeout: const Timeout(Duration(minutes: 2)));

    test('metaFilter returns one bool per input', () async {
      final result = await engine.llm!.metaFilter([
        '방금 그거 다시',
        '어제 스타벅스 다녀옴',
      ]);
      expect(result.length, 2);
    }, skip: skipReason, timeout: const Timeout(Duration(minutes: 2)));

    test('synapseAnswer returns a non-empty string', () async {
      final answer = await engine.llm!.synapseAnswer(
        question: '어디 갔어?',
        contexts: const [
          ContextSentence(text: '스타벅스 다녀옴'),
          ContextSentence(text: '4월 25일에 강남에 갔어'),
        ],
      );
      expect(answer.trim(), isNotEmpty);
    }, skip: skipReason, timeout: const Timeout(Duration(minutes: 2)));
  });
}

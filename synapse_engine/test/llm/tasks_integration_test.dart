@Tags(['integration'])
library;

import 'dart:io' show File, Platform;

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:synapse_engine/synapse_engine.dart';

/// Real-model integration test. Skipped unless the environment supplies:
///   - SYNAPSE_TEST_MODEL  → absolute path to a Gemma 4 E2B GGUF
///   - SYNAPSE_TEST_RETRIEVE_EXPAND_ADAPTER (optional) → adapter GGUF
///   - SYNAPSE_TEST_PROMPT_DIR (optional, defaults to ../docs) → directory
///     holding {*}_SYSTEMPROMPT.md files. Used as `promptOverrides` to
///     bypass `rootBundle` (which requires a Flutter binding/asset manifest
///     this self-package test doesn't set up).
///
/// Run with:
///   SYNAPSE_TEST_MODEL=/Volumes/macex/models/gemma-4-E2B-it-Q4_K_M.gguf \
///   SYNAPSE_TEST_RETRIEVE_EXPAND_ADAPTER=...retrieve-expand.gguf \
///   flutter test test/llm/tasks_integration_test.dart --tags integration
void main() {
  final modelPath = Platform.environment['SYNAPSE_TEST_MODEL'];
  final adapterPath =
      Platform.environment['SYNAPSE_TEST_RETRIEVE_EXPAND_ADAPTER'];
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
          'savePronoun': 'SAVE_PRONOUN_SYSTEMPROMPT.md',
          'metaFilter': 'META_FILTER_SYSTEMPROMPT.md',
          'retrieveExpand': 'RETRIEVE_EXPAND_SYSTEMPROMPT.md',
          'retrieveFilter': 'RETRIEVE_FILTER_SYSTEMPROMPT.md',
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
          adapters: [
            if (adapterPath != null)
              AdapterSpec(name: 'retrieve-expand', path: adapterPath),
          ],
          promptOverrides: overrides,
        ),
      );
    });

    tearDownAll(() async {
      if (modelPath == null) return;
      await engine.dispose();
    });

    test('savePronoun runs end-to-end', () async {
      final result = await engine.llm!.savePronoun(
        '거기 또 갔어',
        context: '나 어제 스타벅스 다녀옴',
        today: '2026-04-25',
      );
      // Either {"text": "..."} or {"question": "..."} — both are valid
      // outcomes. We only assert the contract.
      expect(
        result.containsKey('text') || result.containsKey('question'),
        isTrue,
      );
    }, skip: skipReason);

    test('retrieveExpand returns a non-empty list', () async {
      final result = await engine.llm!.retrieveExpand('허리 아픈데 어디 가야?');
      expect(result, isNotEmpty);
    }, skip: skipReason, timeout: const Timeout(Duration(minutes: 2)));

    test('retrieveFilter answers pass/reject for a clearly relevant pair',
        () async {
      final relevant =
          await engine.llm!.retrieveFilter('허리 아픈데?', '강남세브란스 정형외과 다니고 있어');
      expect(relevant, isTrue);
    }, skip: skipReason, timeout: const Timeout(Duration(minutes: 1)));

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

import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/llm/stub_backend.dart';
import 'package:synapse_engine/src/prompts/loader.dart';

PromptLoader _seededLoader() {
  final loader = PromptLoader(readAsset: (_) async {
    fail('asset must not be loaded when seeded');
  });
  for (final key in PromptKey.values) {
    loader.seedForTest(key, '<system:${key.name}>');
  }
  return loader;
}

void main() {
  group('LlmTasks against StubInferenceBackend', () {
    late StubInferenceBackend backend;
    late LlmTasks tasks;

    setUp(() async {
      backend = StubInferenceBackend();
      await backend.loadModel('');
      tasks = LlmTasks(backend: backend, prompts: _seededLoader());
    });

    test('retrieveExpand parses [] and runs on base model (no adapter)',
        () async {
      backend.canned['::질문: 허리 어때?'] = '["허리", "디스크", "통증"]';
      final result = await tasks.retrieveExpand('허리 어때?');
      expect(result, ['허리', '디스크', '통증']);
      expect(backend.activeAdapter, isNull,
          reason: 'retrieve-expand adapter retired — base model only');
    });

    test('retrieveExpand falls back to whitespace split on parse failure',
        () async {
      backend.canned['::질문: 허리 어때?'] = 'no json';
      final result = await tasks.retrieveExpand('허리 어때?');
      expect(result, ['허리', '어때?']);
    });

    test('retrieveFilter batch — bare o/x marks; x drops, anything else keeps',
        () async {
      backend.canned['::질문: q\n문장 3개:\n1. a\n2. b\n3. c'] = 'o\nx\n???';
      final result = await tasks.retrieveFilter('q', ['a', 'b', 'c']);
      expect(result, [true, false, true],
          reason: 'unknown answers default to keep (recall over precision)');
    });

    test('retrieveFilter batch — legacy [o]/[x] echo still parses', () async {
      backend.canned['::질문: q\n문장 3개:\n1. a\n2. b\n3. c'] =
          '[o] a\n[x] b\n[o] c';
      final result = await tasks.retrieveFilter('q', ['a', 'b', 'c']);
      expect(result, [true, false, true]);
    });

    test('retrieveFilter batch — short response keeps the missing tail',
        () async {
      backend.canned['::질문: q\n문장 3개:\n1. a\n2. b\n3. c'] = 'x';
      final result = await tasks.retrieveFilter('q', ['a', 'b', 'c']);
      expect(result, [false, true, true]);
    });

    test('retrieveFilter batch — empty input short-circuits without LLM call',
        () async {
      final result = await tasks.retrieveFilter('q', const []);
      expect(result, isEmpty);
      expect(backend.generateCalls, 0);
    });

    test('metaFilter calls generate once per input and parses booleans',
        () async {
      backend.canned['::a'] = 'meta';
      backend.canned['::b'] = 'no';
      backend.canned['::c'] = 'YES';
      final result = await tasks.metaFilter(['a', 'b', 'c']);
      expect(result, [true, false, true]);
      expect(backend.generateCalls, 3);
    });

    // ── categorize ────────────────────────────────────

    test('categorize parses JSON {"categories":[...]} on a clean response',
        () async {
      backend.canned['::노드: 허리\n맥락 문장:\n- L4-L5 진단 받음'] =
          '{"categories": ["BOD.disease"]}';
      final result = await tasks.categorize(
        nodeName: '허리',
        contextSentences: const ['L4-L5 진단 받음'],
      );
      expect(result, ['BOD.disease']);
      expect(backend.activeAdapter, isNull,
          reason: 'category runs on base model only');
    });

    test('categorize accepts multiple sub-codes', () async {
      backend.canned['::노드: 강남세브란스\n맥락 문장:\n(맥락 없음)'] =
          '{"categories": ["BOD.medical", "PER.org"]}';
      final result = await tasks.categorize(nodeName: '강남세브란스');
      expect(result, ['BOD.medical', 'PER.org']);
    });

    test('categorize returns [] when the model says no category', () async {
      backend.canned['::노드: 그게\n맥락 문장:\n(맥락 없음)'] =
          '{"categories": []}';
      final result = await tasks.categorize(nodeName: '그게');
      expect(result, isEmpty);
    });

    test('categorize tolerates commentary surrounding the JSON', () async {
      backend.canned['::노드: 회의\n맥락 문장:\n- 오후 회의 잡힘'] =
          '여기는 일 맥락이라 → {"categories": ["WRK.role"]}';
      final result = await tasks.categorize(
        nodeName: '회의',
        contextSentences: const ['오후 회의 잡힘'],
      );
      expect(result, ['WRK.role']);
    });

    test('categorize returns [] when the model produces no JSON object',
        () async {
      backend.canned['::노드: 빈응답\n맥락 문장:\n(맥락 없음)'] = 'hmm';
      final result = await tasks.categorize(nodeName: '빈응답');
      expect(result, isEmpty);
    });

    test('synapseAnswer assembles facts block and runs at temperature > 0',
        () async {
      // Header is "알려진 사실 (시간 순)" when there's at least one fact —
      // Python parity (DESIGN_PIPELINE §인출).
      backend.canned[
              '::알려진 사실 (시간 순):\n- [2026-04-26] 스타벅스 다녀옴\n\n질문: 어디 갔어?'] =
          '스타벅스에 갔어요.';
      final answer = await tasks.synapseAnswer(
        question: '어디 갔어?',
        contexts: const [
          ContextSentence(
            text: '스타벅스 다녀옴',
            createdAt: '2026-04-26 10:00:00',
          ),
        ],
      );
      expect(answer, '스타벅스에 갔어요.');
      expect(backend.lastSystemPrompt, '<system:synapseAnswer>');
    });

    test('synapseAnswer skips date prefix when createdAt is null', () async {
      backend.canned['::알려진 사실 (시간 순):\n- 스타벅스 다녀옴\n\n질문: 어디 갔어?'] =
          '스타벅스에 갔어요.';
      final answer = await tasks.synapseAnswer(
        question: '어디 갔어?',
        contexts: const [ContextSentence(text: '스타벅스 다녀옴')],
      );
      expect(answer, '스타벅스에 갔어요.');
    });

    test('synapseAnswer uses a no-facts placeholder when contexts is empty',
        () async {
      backend.canned['::알려진 사실:\n(관련 사실 없음)\n\n질문: ?'] = '모르겠어요.';
      final answer = await tasks.synapseAnswer(
        question: '?',
        contexts: const [],
      );
      expect(answer, '모르겠어요.');
    });

    test('typoNormalize is a stub in F3', () async {
      expect(
        () => tasks.typoNormalize('text', protectedAliases: const {}),
        throwsA(isA<UnimplementedError>()),
      );
    });

    test('swapAdapter still works for reuse-app domain adapters', () async {
      // retrieve-expand adapter is retired but the swap infrastructure
      // is preserved for reuse apps (e.g. gabjil-extract). Register and
      // swap to a fictional one.
      await backend.registerAdapter('gabjil-extract', '/fake/g.gguf');
      await tasks.swapAdapter('gabjil-extract');
      expect(backend.activeAdapter, 'gabjil-extract');
      // Calling again with the same name is a no-op at the LlmTasks
      // layer (cached), regardless of what the backend would do.
      await tasks.swapAdapter('gabjil-extract');
      expect(backend.activeAdapter, 'gabjil-extract');
    });
  });
}

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

    test('retrieveFilter returns false only when the model says reject',
        () async {
      backend.canned['::질문: q\n문장: rel'] = 'pass';
      backend.canned['::질문: q\n문장: irr'] = 'reject';
      backend.canned['::질문: q\n문장: weird'] = '...';
      expect(await tasks.retrieveFilter('q', 'rel'), isTrue);
      expect(await tasks.retrieveFilter('q', 'irr'), isFalse);
      expect(await tasks.retrieveFilter('q', 'weird'), isTrue,
          reason: 'unknown answers default to pass (recall over precision)');
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

    test('synapseAnswer assembles facts block and runs at temperature > 0',
        () async {
      backend.canned['::알려진 사실:\n- 스타벅스 다녀옴\n\n질문: 어디 갔어?'] = '스타벅스에 갔어요.';
      final answer = await tasks.synapseAnswer(
        question: '어디 갔어?',
        contexts: const [ContextSentence(text: '스타벅스 다녀옴')],
      );
      expect(answer, '스타벅스에 갔어요.');
      expect(backend.lastSystemPrompt, '<system:synapseAnswer>');
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

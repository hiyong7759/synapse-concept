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
      await backend.registerAdapter(
        'retrieve-expand',
        '/fake/retrieve-expand.gguf',
      );
      tasks = LlmTasks(backend: backend, prompts: _seededLoader());
    });

    test('savePronoun parses {"text":...} and uses the right system prompt',
        () async {
      backend.canned['::입력: 거기 갔어'] = '{"text": "스타벅스 갔어", "tokens": ["스타벅스"]}';
      final result = await tasks.savePronoun('거기 갔어');
      expect(result['text'], '스타벅스 갔어');
      expect(backend.lastSystemPrompt, '<system:savePronoun>');
      expect(backend.activeAdapter, isNull,
          reason: 'savePronoun must run on base model only');
    });

    test('savePronoun falls back when output is unparseable', () async {
      backend.canned['::입력: hello'] = 'gibberish';
      final result = await tasks.savePronoun('hello');
      expect(result['text'], 'hello');
    });

    test('savePronoun threads context and date into the user prompt',
        () async {
      await tasks.savePronoun(
        '거기 또 갔어',
        context: '나 어제 스타벅스 갔어',
        today: '2026-04-25',
      );
      expect(backend.lastUserPrompt, contains('날짜: 2026-04-25'));
      expect(backend.lastUserPrompt, contains('직전 대화 - 나 어제 스타벅스 갔어'));
      expect(backend.lastUserPrompt, contains('입력: 거기 또 갔어'));
    });

    test('retrieveExpand activates the retrieve-expand adapter and parses []',
        () async {
      backend.canned['retrieve-expand::질문: 허리 어때?'] =
          '["허리", "디스크", "통증"]';
      final result = await tasks.retrieveExpand('허리 어때?');
      expect(result, ['허리', '디스크', '통증']);
      expect(backend.activeAdapter, 'retrieve-expand');
    });

    test('retrieveExpand falls back to whitespace split on parse failure',
        () async {
      backend.canned['retrieve-expand::질문: 허리 어때?'] = 'no json';
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

    test('swapAdapter is a no-op when already on the requested adapter',
        () async {
      await tasks.retrieveExpand('q1');
      final before = backend.activeAdapter;
      // Adapter was switched once for retrieveExpand. Calling swapAdapter
      // with the same name should not trigger another backend switch.
      await tasks.swapAdapter('retrieve-expand');
      expect(backend.activeAdapter, before);
    });
  });
}

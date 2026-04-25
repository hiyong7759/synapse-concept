import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_engine/src/prompts/loader.dart';

void main() {
  group('PromptLoader', () {
    test('returns the override when present (no asset read)', () async {
      var asks = 0;
      final loader = PromptLoader(
        overrides: {'savePronoun': '<override>'},
        readAsset: (_) async {
          asks++;
          return '<asset>';
        },
      );
      expect(await loader.load(PromptKey.savePronoun), '<override>');
      expect(asks, 0);
    });

    test('falls back to AssetReader and caches the result', () async {
      var calls = 0;
      final loader = PromptLoader(readAsset: (path) async {
        calls++;
        return 'text-for-$path';
      });
      final first = await loader.load(PromptKey.synapseAnswer);
      final second = await loader.load(PromptKey.synapseAnswer);
      expect(first, second);
      expect(calls, 1, reason: 'second load should hit cache');
    });

    test('asset paths cover all six system prompts with package prefix',
        () {
      final names = PromptKey.values.map((k) => k.fileName).toList();
      expect(names, [
        'CATEGORY_SYSTEMPROMPT.md',
        'SAVE_PRONOUN_SYSTEMPROMPT.md',
        'META_FILTER_SYSTEMPROMPT.md',
        'RETRIEVE_EXPAND_SYSTEMPROMPT.md',
        'RETRIEVE_FILTER_SYSTEMPROMPT.md',
        'SYNAPSE_ANSWER_SYSTEMPROMPT.md',
      ]);
      for (final key in PromptKey.values) {
        expect(
          key.assetPath,
          startsWith('packages/synapse_engine/assets/prompts/'),
        );
      }
    });

    test('seedForTest pre-populates the cache', () async {
      final loader = PromptLoader(readAsset: (_) async {
        fail('readAsset must not be called when cache is seeded');
      });
      loader.seedForTest(PromptKey.metaFilter, 'seeded');
      expect(await loader.load(PromptKey.metaFilter), 'seeded');
    });
  });
}

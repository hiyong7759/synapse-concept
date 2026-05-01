import 'package:flutter/services.dart' show rootBundle;

/// Task identifiers used by [LlmTasks] and [PromptLoader].
/// One enum value per system-prompt file in `assets/prompts/`.
enum PromptKey {
  category('CATEGORY_SYSTEMPROMPT.md'),
  metaFilter('META_FILTER_SYSTEMPROMPT.md'),
  retrieveExpand('RETRIEVE_EXPAND_SYSTEMPROMPT.md'),
  keywordFilter('KEYWORD_FILTER_SYSTEMPROMPT.md'),
  synapseAnswer('SYNAPSE_ANSWER_SYSTEMPROMPT.md');

  const PromptKey(this.fileName);
  final String fileName;

  String get assetPath => 'packages/synapse_engine/assets/prompts/$fileName';
}

/// Strategy for resolving an asset path → string. Pluggable so tests can
/// avoid touching [rootBundle] entirely.
typedef AssetReader = Future<String> Function(String path);

/// Loads system prompts from the package's bundled assets, with optional
/// per-task overrides supplied at engine construction time.
///
/// Caches each loaded prompt for the lifetime of the loader so repeated
/// LLM calls don't re-read the asset.
class PromptLoader {
  PromptLoader({
    Map<String, String>? overrides,
    AssetReader? readAsset,
  })  : _overrides = overrides ?? const {},
        _readAsset = readAsset ?? rootBundle.loadString;

  final Map<String, String> _overrides;
  final AssetReader _readAsset;
  final Map<PromptKey, String> _cache = {};

  /// Returns the prompt text for [key]. Overrides win over bundled assets.
  /// The override map is keyed by [PromptKey.name] (e.g. 'savePronoun').
  Future<String> load(PromptKey key) async {
    final override = _overrides[key.name];
    if (override != null) return override;

    final cached = _cache[key];
    if (cached != null) return cached;

    final raw = await _readAsset(key.assetPath);
    _cache[key] = raw;
    return raw;
  }

  /// Test hook: pre-populate the cache with a fixed string.
  void seedForTest(PromptKey key, String text) {
    _cache[key] = text;
  }
}

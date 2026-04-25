import 'db/category_seed.dart';

/// Engine configuration. See docs/DESIGN_ENGINE.md §3.
///
/// LLM and Kiwi fields are nullable so an app can construct an engine that
/// only uses GraphOps (e.g. for tests, headless graph-only flows, or while
/// the LLM model file is still downloading).
class EngineConfig {
  const EngineConfig({
    required this.appName,
    required this.allowedKinds,
    required this.reservedKinds,
    required this.dbPath,
    required this.categorySeed,
    this.modelPath,
    this.adapters = const [],
    this.kiwiAssetPath,
    this.promptOverrides,
  });

  /// 'synapse_app' / 'gabjil_app' / etc. Used for logging and DB filename hints.
  final String appName;

  /// Kinds permitted for `posts.kind`. The first entry is the table default.
  final List<String> allowedKinds;

  /// Kinds that, when present, activate `SynapseFlow`. Synapse app sets
  /// `['synapse', 'insight']`; reuse apps set `[]` to keep flow disabled.
  final List<String> reservedKinds;

  /// Absolute path to the sqflite DB file.
  final String dbPath;

  /// Category seed bundle. `CategorySeed.synapse19()` covers the default
  /// 19-macro hierarchy.
  final CategorySeed categorySeed;

  /// Base GGUF model path. Required from F3 onward; null at F2 means LLM
  /// tasks are unavailable.
  final String? modelPath;

  /// LoRA adapter specs to make available for hotswap.
  final List<AdapterSpec> adapters;

  /// Asset directory containing kiwi-nlp WASM + dictionaries. Required at F4.
  final String? kiwiAssetPath;

  /// Optional per-task system-prompt overrides. Keys are task names
  /// (e.g. 'save_pronoun', 'retrieve_expand'). Values are full prompt text.
  final Map<String, String>? promptOverrides;

  /// True iff this config has both reserved kinds for the synapse flow
  /// activated (`'synapse'` and `'insight'`).
  bool get isSynapseFlowEnabled =>
      reservedKinds.contains('synapse') && reservedKinds.contains('insight');
}

/// One LoRA adapter binding. Adapter is loaded by llamadart at F3.
class AdapterSpec {
  const AdapterSpec({required this.name, required this.path});

  final String name;
  final String path;
}

/// Bundle of seed category roots passed into the engine at create time.
class CategorySeed {
  const CategorySeed({required this.roots});

  final List<CategorySeedRoot> roots;

  /// Default seed: the 19-macro hierarchy from docs/DESIGN_CATEGORY.md.
  /// Inserts 19 roots + 114 leaves = 133 rows on first migration.
  factory CategorySeed.synapse19() => const CategorySeed(roots: seedRoots19);

  /// No seed at all. Useful for reuse apps that want to install their own
  /// taxonomy entirely (e.g. gabjil's character/episode roots).
  factory CategorySeed.empty() => const CategorySeed(roots: []);
}

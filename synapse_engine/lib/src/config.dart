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
    this.retrieveMaxSentences = 500,
    this.retrieveStopwordThreshold = 50,
    this.gpuLayers = 99,
    this.contextSize = 8192,
    this.inferenceBatchSize = 4096,
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

  /// Hard cap on sentences a single `synapseTurn` may collect. The BFS
  /// terminates once it reaches this number, which is more predictable than
  /// "depth N" because graph shape varies wildly across users.
  final int retrieveMaxSentences;

  /// Mention-count threshold for the BFS frequency stopword filter
  /// (DESIGN_PIPELINE §인출 — 노드 폭증 억제). Nodes appearing in this many
  /// or more sentences are dropped from BFS expansion (still surfaced if
  /// they're the start node themselves). Set to `0` to disable.
  final int retrieveStopwordThreshold;

  /// llamadart GPU offload layer count. 99 = "all that fit" (default —
  /// matches `LlamadartInferenceBackend` default). Set to `0` to force
  /// CPU-only inference; useful for measurement environments where the
  /// Metal context isn't available (e.g. `flutter test` runs the
  /// `flutter_tester` with `--enable-software-rendering`, blocking GPU
  /// access — see PLAN-20260429-SYN-synapse-perf §B Metal isolation).
  final int gpuLayers;

  /// llama.cpp context window (`n_ctx`). 8K is enough margin for the
  /// retrieve-filter prompt — Korean sentences run ~140 tokens apiece,
  /// so a single 50-sentence batch + system prompt + response stays
  /// inside the window without the OOM that happens when `contextSize`
  /// is pushed to 32K and batch buffers blow up the Metal allocator.
  final int contextSize;

  /// llama.cpp logical max batch (`n_batch`). Default 0 in `ModelParams`
  /// promotes to `contextSize`, which makes large windows allocate
  /// matching batch buffers and push GPU memory off a cliff. Pinning at
  /// 4096 keeps batch memory bounded while letting the KV cache scale
  /// with `contextSize`.
  final int inferenceBatchSize;

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

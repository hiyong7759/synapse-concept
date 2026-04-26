/// synapse_engine — on-device hypergraph engine.
///
/// Single entry point. Consumers import `package:synapse_engine/synapse_engine.dart`
/// and never reach into `src/` directly.
///
/// Two-layer API:
///   - SynapseFlow  (synapse-app only; activated when reservedKinds includes
///                   'synapse' and 'insight')
///   - LlmTasks + GraphOps  (any app; LLM-free graph ops keep working without a model)
///
/// See `docs/DESIGN_ENGINE.md` §2 for the full surface.
library synapse_engine;

// F2 — DB layer surfaces.
export 'src/config.dart' show EngineConfig, AdapterSpec, CategorySeed;
export 'src/db/category_seed.dart' show CategorySeedRoot;
export 'src/engine.dart' show SynapseEngine;

// F3 — LLM task surfaces.
export 'src/llm/inference_backend.dart' show InferenceBackend, LlmError;
export 'src/llm/tasks.dart' show LlmTasks, ContextSentence, Correction;
export 'src/prompts/loader.dart' show PromptKey;

// F4 — graph + Kiwi surfaces.
export 'src/graph/bfs.dart' show MentionFilter;
export 'src/graph/ops.dart' show GraphOps;
export 'src/graph/seed_matching.dart'
    show matchStartNodes, headingSubtreeSeeds, sameCategoryNodes,
        HeadingSubtreeSeeds;
export 'src/kiwi/kiwi_wasm.dart'
    show KiwiBackend, FlutterKiwiBackend, InMemoryKiwiBackend;
export 'src/kiwi/tokens.dart' show KiwiToken;
export 'src/models/graph_models.dart'
    show Node, Sentence, Mention, Alias, TypoCandidate, EngineStats;

// F5 — synapse flow (note + retrieve + insight).
export 'src/flow/results.dart'
    show NoteProcessResult, SynapseTurnResult, InsightResult;
export 'src/flow/synapse_flow.dart'
    show SynapseFlow, PostMeta, PostDetail, SentenceRow;

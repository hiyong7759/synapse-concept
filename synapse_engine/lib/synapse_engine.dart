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

// F3~F5 will append:
//   export 'src/flow/synapse_flow.dart';
//   export 'src/llm/tasks.dart';
//   export 'src/graph/ops.dart';
//   export 'src/models/...';

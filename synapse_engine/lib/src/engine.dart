import 'package:sqflite/sqflite.dart';

import 'config.dart';
import 'db/migrations.dart';
import 'db/schema.dart';
import 'flow/categorize_queue.dart';
import 'flow/synapse_flow.dart';
import 'graph/ops.dart';
import 'kiwi/kiwi_wasm.dart';
import 'llm/inference_backend.dart';
import 'llm/llamadart_backend.dart';
import 'llm/tasks.dart';
import 'prompts/loader.dart';

/// SynapseEngine — DI container + lifecycle.
/// See docs/DESIGN_ENGINE.md §2 (two-layer API) and §3 (EngineConfig).
///
/// As of F5a the engine owns:
///   - `db`    — sqflite Database (always present)
///   - `llm`   — LlmTasks, when `modelPath` is configured
///   - `graph` — GraphOps, when a [KiwiBackend] is supplied via [kiwiOverride]
///   - `flow`  — SynapseFlow (note autosave/process + post management),
///               attached when `reservedKinds` includes both 'synapse' and
///               'insight' AND `graph` is available.
///
/// Platform note: callers must initialise the sqflite factory before invoking
/// [create] (mobile uses `package:sqflite/sqflite.dart`; desktop and tests
/// use `package:sqflite_common_ffi/sqflite_ffi.dart`). The engine itself is
/// factory-agnostic — it opens through `databaseFactory`.
class SynapseEngine {
  SynapseEngine._({
    required this.config,
    required this.db,
    required this.llm,
    required this.graph,
    required this.flow,
    required this.categorizeQueue,
    required InferenceBackend? backend,
    required KiwiBackend? kiwi,
  })  : _backend = backend,
        _kiwi = kiwi;

  final EngineConfig config;
  final Database db;

  /// LLM task surface. `null` when [EngineConfig.modelPath] was not provided,
  /// in which case graph-only flows still work (원칙 11 — engine remains
  /// useful without a model loaded).
  final LlmTasks? llm;

  /// Graph + Kiwi surface. `null` when no [KiwiBackend] was supplied —
  /// callers can still use `db` directly for DB-only paths.
  final GraphOps? graph;

  /// Synapse-app high-level flow. `null` for reuse apps that don't activate
  /// the synapse/insight kinds.
  final SynapseFlow? flow;

  /// Background queue that classifies nodes into seed-19 categories. `null`
  /// when LLM or GraphOps are missing. The autosave path enqueues this; the
  /// app boot path calls [startBackgroundBackfill] once to pick up nodes
  /// added before the queue existed.
  final CategorizeQueue? categorizeQueue;

  final InferenceBackend? _backend;
  final KiwiBackend? _kiwi;

  /// Opens (or creates) the configured DB, runs pending migrations, and —
  /// if [config.modelPath] is set — loads the LLM backend and registers
  /// every adapter in [config.adapters].
  ///
  /// Kiwi is **opt-in**: pass [kiwiOverride] (typically
  /// `await FlutterKiwiBackend.load()` in production, or
  /// `InMemoryKiwiBackend()` in tests). Without it the engine still works
  /// for DB-only flows, and `graph` will be null. The reason the engine
  /// does not auto-load Kiwi is that the native bridge library is only
  /// present once the host app has gone through `flutter build` /
  /// `pod install` — bare `flutter test` against the package can't find
  /// it.
  ///
  /// Test overrides:
  ///   - [backendOverride] — injects an [InferenceBackend] (e.g. stub).
  ///   - [kiwiOverride]    — injects a [KiwiBackend] (e.g. InMemoryKiwiBackend).
  static Future<SynapseEngine> create(
    EngineConfig config, {
    InferenceBackend? backendOverride,
    KiwiBackend? kiwiOverride,
  }) async {
    final db = await databaseFactory.openDatabase(
      config.dbPath,
      options: OpenDatabaseOptions(
        version: schemaVersion,
        onConfigure: _enableForeignKeys,
        onCreate: (db, version) async {
          await migrateV1(
            db,
            allowedKinds: config.allowedKinds,
            seedRoots: config.categorySeed.roots,
            seedFirstPersonAliases: config.isSynapseFlowEnabled,
          );
        },
        onUpgrade: (db, oldVersion, newVersion) async {
          // No upgrades yet — v1 is the only version.
          throw StateError(
            'No upgrade path defined from v$oldVersion to v$newVersion',
          );
        },
      ),
    );

    // ── Kiwi (opt-in via kiwiOverride) ──────────────────
    final kiwi = kiwiOverride;
    final graph = kiwi == null ? null : GraphOps(db: db, kiwi: kiwi);

    // ── LLM ────────────────────────────────────────────
    final modelPath = config.modelPath;
    InferenceBackend? backend;
    LlmTasks? tasks;
    if (backendOverride != null) {
      backend = backendOverride;
      await backend.loadModel(modelPath ?? '');
      for (final adapter in config.adapters) {
        await backend.registerAdapter(adapter.name, adapter.path);
      }
      tasks = LlmTasks(
        backend: backend,
        prompts: PromptLoader(overrides: config.promptOverrides),
      );
    } else if (modelPath != null) {
      backend = LlamadartInferenceBackend(
        gpuLayers: config.gpuLayers,
        contextSize: config.contextSize,
        batchSize: config.inferenceBatchSize,
      );
      await backend.loadModel(modelPath);
      for (final adapter in config.adapters) {
        await backend.registerAdapter(adapter.name, adapter.path);
      }
      tasks = LlmTasks(
        backend: backend,
        prompts: PromptLoader(overrides: config.promptOverrides),
      );
    }

    // ── SynapseFlow (synapse-app activation) ───────────
    SynapseFlow? flow;
    if (config.isSynapseFlowEnabled && graph != null && kiwi != null) {
      flow = SynapseFlow(
        db: db,
        graph: graph,
        kiwi: kiwi,
        llm: tasks,
        retrieveMaxSentences: config.retrieveMaxSentences,
        retrieveStopwordThreshold: config.retrieveStopwordThreshold,
      );
    }

    // ── Categorize queue ───────────────────────────────
    // Background classifier — needs both an LLM and graph ops. The queue
    // is created here but never started automatically; app boot calls
    // [startBackgroundBackfill] once it's ready to process old nodes.
    CategorizeQueue? categorizeQueue;
    if (tasks != null && graph != null) {
      categorizeQueue =
          CategorizeQueue(db: db, graph: graph, llm: tasks);
    }

    return SynapseEngine._(
      config: config,
      db: db,
      llm: tasks,
      graph: graph,
      flow: flow,
      categorizeQueue: categorizeQueue,
      backend: backend,
      kiwi: kiwi,
    );
  }

  /// Enqueues every node lacking an `origin='ai'` category mention. App
  /// boot calls this once after the engine is ready so nodes added before
  /// F-bundle 7 (or before the queue existed) get classified in the
  /// background. Safe to call repeatedly — dedup keeps the queue clean.
  Future<void> startBackgroundBackfill() async {
    await categorizeQueue?.enqueueAll();
  }

  Future<void> dispose() async {
    categorizeQueue?.stop();
    await _backend?.dispose();
    await _kiwi?.dispose();
    await db.close();
  }
}

Future<void> _enableForeignKeys(Database db) async {
  await db.execute('PRAGMA foreign_keys = ON');
}

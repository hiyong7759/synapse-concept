import 'package:sqflite/sqflite.dart';

import 'config.dart';
import 'db/migrations.dart';
import 'db/schema.dart';
import 'graph/ops.dart';
import 'kiwi/kiwi_wasm.dart';
import 'llm/inference_backend.dart';
import 'llm/llamadart_backend.dart';
import 'llm/tasks.dart';
import 'prompts/loader.dart';

/// SynapseEngine — DI container + lifecycle.
/// See docs/DESIGN_ENGINE.md §2 (two-layer API) and §3 (EngineConfig).
///
/// As of F4 the engine owns:
///   - `db`    — sqflite Database (always present)
///   - `llm`   — LlmTasks, when `modelPath` is configured
///   - `graph` — GraphOps, when a [KiwiBackend] is available (default
///               `FlutterKiwiBackend`, or test-supplied via `kiwiOverride`)
///
/// `flow` (SynapseFlow) lands in F5.
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

  /// Graph + Kiwi surface. `null` only when [SynapseEngine.create] is asked
  /// to skip Kiwi setup (for DB-only smoke paths). Default behaviour wires
  /// up [FlutterKiwiBackend] using bundled assets.
  final GraphOps? graph;

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
      backend = LlamadartInferenceBackend();
      await backend.loadModel(modelPath);
      for (final adapter in config.adapters) {
        await backend.registerAdapter(adapter.name, adapter.path);
      }
      tasks = LlmTasks(
        backend: backend,
        prompts: PromptLoader(overrides: config.promptOverrides),
      );
    }

    return SynapseEngine._(
      config: config,
      db: db,
      llm: tasks,
      graph: graph,
      backend: backend,
      kiwi: kiwi,
    );
  }

  Future<void> dispose() async {
    await _backend?.dispose();
    await _kiwi?.dispose();
    await db.close();
  }
}

Future<void> _enableForeignKeys(Database db) async {
  await db.execute('PRAGMA foreign_keys = ON');
}

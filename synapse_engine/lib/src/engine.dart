import 'package:sqflite/sqflite.dart';

import 'config.dart';
import 'db/migrations.dart';
import 'db/schema.dart';
import 'llm/inference_backend.dart';
import 'llm/llamadart_backend.dart';
import 'llm/tasks.dart';
import 'prompts/loader.dart';

/// SynapseEngine — DI container + lifecycle.
/// See docs/DESIGN_ENGINE.md §2 (two-layer API) and §3 (EngineConfig).
///
/// As of F3 the engine owns the sqflite [Database] and, when a model path is
/// configured, an [LlmTasks] instance backed by llamadart. The remaining
/// higher layers (`SynapseFlow`, `GraphOps`) land in F4~F5.
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
    required InferenceBackend? backend,
  }) : _backend = backend;

  final EngineConfig config;
  final Database db;

  /// LLM task surface. `null` when [EngineConfig.modelPath] was not provided,
  /// in which case graph-only flows still work (원칙 11 — engine remains
  /// useful without a model loaded).
  final LlmTasks? llm;

  final InferenceBackend? _backend;

  /// Opens (or creates) the configured DB, runs pending migrations, and —
  /// if [config.modelPath] is set — loads the LLM backend and registers
  /// every adapter in [config.adapters].
  ///
  /// Override [backendOverride] in tests to inject a [StubInferenceBackend]
  /// without touching the production llamadart path.
  static Future<SynapseEngine> create(
    EngineConfig config, {
    InferenceBackend? backendOverride,
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
      backend: backend,
    );
  }

  Future<void> dispose() async {
    await _backend?.dispose();
    await db.close();
  }
}

Future<void> _enableForeignKeys(Database db) async {
  await db.execute('PRAGMA foreign_keys = ON');
}

import 'package:sqflite/sqflite.dart';

import 'config.dart';
import 'db/migrations.dart';
import 'db/schema.dart';

/// SynapseEngine — DI container + lifecycle.
/// See docs/DESIGN_ENGINE.md §2 (two-layer API) and §3 (EngineConfig).
///
/// At F2 the engine only owns the sqflite [Database]; the higher layers
/// (`SynapseFlow`, `LlmTasks`, `GraphOps`) land in F3~F5 and will be wired
/// onto this same instance.
///
/// Platform note: callers must initialise the sqflite factory before invoking
/// [create] (mobile uses `package:sqflite/sqflite.dart`; desktop and tests
/// use `package:sqflite_common_ffi/sqflite_ffi.dart`). The engine itself is
/// factory-agnostic — it opens through `databaseFactory`.
class SynapseEngine {
  SynapseEngine._({required this.config, required this.db});

  final EngineConfig config;
  final Database db;

  /// Opens (or creates) the configured DB and runs pending migrations.
  static Future<SynapseEngine> create(EngineConfig config) async {
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
    return SynapseEngine._(config: config, db: db);
  }

  Future<void> dispose() async {
    await db.close();
  }
}

Future<void> _enableForeignKeys(Database db) async {
  await db.execute('PRAGMA foreign_keys = ON');
}

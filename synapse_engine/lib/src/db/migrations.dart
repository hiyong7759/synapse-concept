import 'package:sqflite/sqflite.dart';

import 'category_seed.dart';
import 'schema.dart';

/// Migration version 1: initial schema + 19-macro category seed +
/// first-person alias seed.
///
/// Runs inside a transaction so a partial failure leaves the DB empty.
/// Idempotent against the version number — sqflite's `onCreate` only fires
/// when the file does not yet exist, so this function is the create path.
Future<void> migrateV1(
  Database db, {
  required List<String> allowedKinds,
  required List<CategorySeedRoot> seedRoots,
  bool seedFirstPersonAliases = true,
}) async {
  await db.execute(buildPostsDdl(allowedKinds));
  for (final ddl in staticDdl) {
    await db.execute(ddl);
  }
  for (final ddl in indexDdl) {
    await db.execute(ddl);
  }
  await _seedCategories(db, seedRoots);
  if (seedFirstPersonAliases) {
    await _seedFirstPerson(db);
  }
}

Future<void> _seedCategories(
  Database db,
  List<CategorySeedRoot> roots,
) async {
  for (final root in roots) {
    final rootId = await db.insert('categories', {
      'name': root.code,
      'parent_id': null,
    });
    for (final sub in root.subs) {
      await db.insert('categories', {
        'name': sub,
        'parent_id': rootId,
      });
    }
  }
}

/// Inserts the `"나"` node and seeds the 11 first-person aliases onto it
/// (`origin='system'`). Mirrors `engine/save.py:_register_first_person_aliases`.
/// Aliases collapse "내가/저는/제가/..." onto the same node id so future
/// upserts via [GraphOps.upsertNode] hit the existing row.
Future<void> _seedFirstPerson(Database db) async {
  final naId = await db.insert('nodes', {'name': '나'});
  for (final alias in firstPersonAliases) {
    await db.insert(
      'aliases',
      {'alias': alias, 'node_id': naId, 'origin': 'system'},
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
  }
}

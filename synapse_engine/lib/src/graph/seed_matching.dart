import 'package:sqflite/sqflite.dart';

/// Resolve question keywords to start node ids. Mirrors Python
/// `engine/retrieve.py::_match_start_nodes`: alias substring inside the raw
/// question first, then alias exact, then `nodes.name` exact, then `name LIKE`.
///
/// Returns `{nodeId: name}` — id is unique per node (the same node can match
/// multiple keywords but only appears once in the result).
Future<Map<int, String>> matchStartNodes(
  Database db, {
  required List<String> keywords,
  required String question,
}) async {
  final result = <int, String>{};
  final resolvedNames = <String>{};

  // (a) Alias substring scan against the raw question — catches aliases that
  // never made it into the tokenised keyword list (e.g. punctuation-glued).
  if (question.isNotEmpty) {
    final rows = await db.rawQuery(
      'SELECT a.alias, n.id, n.name FROM aliases a '
      'JOIN nodes n ON n.id = a.node_id',
    );
    for (final r in rows) {
      final alias = r['alias'] as String;
      if (question.contains(alias)) {
        final id = r['id'] as int;
        final name = r['name'] as String;
        result[id] = name;
        resolvedNames.add(name);
      }
    }
  }

  for (final kw in keywords) {
    if (kw.isEmpty || resolvedNames.contains(kw)) continue;

    // (b) Exact alias match.
    final aliasRow = await db.rawQuery(
      'SELECT n.id, n.name FROM aliases a '
      'JOIN nodes n ON n.id = a.node_id '
      'WHERE a.alias = ? LIMIT 1',
      [kw],
    );
    if (aliasRow.isNotEmpty) {
      final id = aliasRow.first['id'] as int;
      final name = aliasRow.first['name'] as String;
      result[id] = name;
      resolvedNames.add(name);
      continue;
    }

    // (c) Exact node name.
    final exactRows = await db.rawQuery(
      'SELECT id, name FROM nodes WHERE name = ?',
      [kw],
    );
    if (exactRows.isNotEmpty) {
      for (final r in exactRows) {
        final id = r['id'] as int;
        result[id] = r['name'] as String;
      }
      continue;
    }

    // (d) Fuzzy substring (LIKE), capped to keep noise down.
    final likeRows = await db.rawQuery(
      "SELECT id, name FROM nodes WHERE name LIKE ? LIMIT 5",
      ['%$kw%'],
    );
    for (final r in likeRows) {
      final id = r['id'] as int;
      final name = r['name'] as String;
      if (resolvedNames.contains(name)) continue;
      result[id] = name;
    }
  }

  return result;
}

// Path-2/3 helpers (`headingSubtreeSeeds`, `sameCategoryNodes`,
// `HeadingSubtreeSeeds`) used to live here. The 2026-04-29 retrieval
// redesign replaced them with the equivalent functions in
// `lookup.dart` (`collectMentionsByHeadingSubtree`,
// `collectMentionsByCategorySharing`) which run inside the new
// orchestrator (`flow/retrieve.dart`).

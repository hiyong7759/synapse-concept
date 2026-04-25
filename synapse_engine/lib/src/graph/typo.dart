import 'package:sqflite/sqflite.dart';

import '../internal/jamo.dart';
import '../models/graph_models.dart';

/// Scans every node pair for jamo distance ≤ [maxDist]. O(n²) — acceptable
/// at F4 scale (a few thousand nodes); a follow-up milestone will replace
/// this with a jamo-prefix bucket index for the personal hypergraph
/// volumes seen in dogfood.
///
/// The pre-filter from `engine/jamo.py:is_typo_candidate` keeps the inner
/// loop cheap: nodes shorter than 6 jamo are skipped, and pairs whose
/// jamo lengths differ by more than [maxDist] short-circuit before the
/// Levenshtein call.
Future<List<TypoCandidate>> findSuspectedTypos(
  Database db, {
  int maxDist = 1,
  int minJamoLen = 6,
}) async {
  final rows = await db.rawQuery('SELECT id, name FROM nodes');
  final nodes = <Node>[];
  final decomposed = <String>[];
  for (final r in rows) {
    final name = r['name'] as String;
    final jamo = decompose(name);
    if (jamo.length < minJamoLen) continue;
    nodes.add(Node(id: r['id'] as int, name: name));
    decomposed.add(jamo);
  }

  final out = <TypoCandidate>[];
  for (var i = 0; i < nodes.length; i++) {
    for (var j = i + 1; j < nodes.length; j++) {
      final a = decomposed[i];
      final b = decomposed[j];
      if ((a.length - b.length).abs() > maxDist) continue;
      if (nodes[i].name == nodes[j].name) continue;
      final d = levenshtein(a, b);
      if (d <= maxDist) {
        out.add(TypoCandidate(
          left: nodes[i],
          right: nodes[j],
          distance: d,
        ));
      }
    }
  }
  return out;
}

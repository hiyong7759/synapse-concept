/// Negation post-processing — port of save.py _postprocess_negation.
///
/// "안 좋아" → 3 nodes (src, 안, 좋아) + 2 null-label edges.
/// 1-pass: label→node conversion when label is "안" or "못".
/// 2-pass: LLM fallback for missed negations (deferred to caller).

/// Check if extracted edges contain negation labels and convert them.
///
/// Returns (updatedNodes, updatedEdges) with negation adverbs split.
(List<Map<String, dynamic>>, List<Map<String, dynamic>>) postprocessNegation(
  List<Map<String, dynamic>> nodes,
  List<Map<String, dynamic>> edges,
) {
  final updatedNodes = List<Map<String, dynamic>>.from(nodes);
  final updatedEdges = <Map<String, dynamic>>[];
  final existingNames = updatedNodes.map((n) => n['name'] as String).toSet();

  for (final edge in edges) {
    final label = edge['label'] as String?;
    final source = edge['source'] as String;
    final target = edge['target'] as String;

    if (label == '안' || label == '못') {
      // Convert label to independent node:
      // source →(안)→ target becomes source → 안 → target
      if (!existingNames.contains(label)) {
        updatedNodes.add({'name': label, 'category': null});
        existingNames.add(label!);
      }
      updatedEdges.add({
        'source': source,
        'label': null,
        'target': label,
      });
      updatedEdges.add({
        'source': label,
        'label': null,
        'target': target,
      });
    } else {
      updatedEdges.add(edge);
    }
  }

  return (updatedNodes, updatedEdges);
}

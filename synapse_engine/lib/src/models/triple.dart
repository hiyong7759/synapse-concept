/// A directed relation in the knowledge graph.
class Triple {
  final String src;
  final String? label;
  final String tgt;
  final int edgeId;
  final int srcId;
  final int tgtId;
  final int? sentenceId;
  final String? sentenceText;

  const Triple({
    required this.src,
    this.label,
    required this.tgt,
    required this.edgeId,
    this.srcId = 0,
    this.tgtId = 0,
    this.sentenceId,
    this.sentenceText,
  });

  @override
  String toString() {
    if (label != null) return '$src —($label)→ $tgt';
    return '$src → $tgt';
  }
}

/// v15: 같은 sentence 바구니에 공출현한 두 노드를 트리플처럼 표현 (시각화·API 호환용).
/// edges 테이블 폐기로 label은 항상 null. 의미 관계 해석은 외부 지능체 몫.
class Triple {
  final String src;
  final String? label;  // v15: 항상 null
  final String tgt;
  final int srcId;
  final int tgtId;
  final int? sentenceId;
  final String? sentenceText;

  const Triple({
    required this.src,
    this.label,
    required this.tgt,
    this.srcId = 0,
    this.tgtId = 0,
    this.sentenceId,
    this.sentenceText,
  });

  @override
  String toString() {
    if (tgt.isEmpty) return src;
    return '$src ↔ $tgt';
  }
}

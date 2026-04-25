/// v15: 하이퍼그래프 직접 쿼리 파라미터 (구 GraphQuery 대체).
/// 같은 문장 바구니·카테고리 바구니 멤버 조회에 사용.
class HypergraphQuery {
  final String? nodeName;
  final int? nodeId;
  final String? category;
  final Duration? lastDuration;
  final int? limit;
  final bool includeInactive;

  const HypergraphQuery({
    this.nodeName,
    this.nodeId,
    this.category,
    this.lastDuration,
    this.limit,
    this.includeInactive = false,
  });
}

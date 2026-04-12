/// Query parameters for direct graph access.
class GraphQuery {
  final String? nodeName;
  final int? nodeId;
  final String? category;
  final Duration? lastDuration;
  final int? limit;
  final bool includeInactive;

  const GraphQuery({
    this.nodeName,
    this.nodeId,
    this.category,
    this.lastDuration,
    this.limit,
    this.includeInactive = false,
  });
}

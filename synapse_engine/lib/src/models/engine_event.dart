/// v15: 하이퍼그래프 이벤트. edges 테이블 폐기로 트리플·엣지 중심 이벤트를
/// 문장 바구니·노드 중심으로 재구성.

/// Emitted when a sentence is committed — sentence + 그 바구니의 노드 멤버십.
class SentenceCommittedEvent {
  final int sentenceId;
  final String text;
  final List<int> mentionedNodeIds;
  final List<String> mentionedNodeNames;
  final DateTime timestamp;

  const SentenceCommittedEvent({
    required this.sentenceId,
    required this.text,
    required this.mentionedNodeIds,
    required this.mentionedNodeNames,
    required this.timestamp,
  });
}

/// Emitted when a node is deactivated.
class NodeDeactivatedEvent {
  final int nodeId;
  final String name;
  final String reason; // "conflict" | "manual"

  const NodeDeactivatedEvent({
    required this.nodeId,
    required this.name,
    required this.reason,
  });
}

/// Emitted when a new node is created.
class NodeCreatedEvent {
  final String name;
  final List<String>? categories;
  final int nodeId;

  const NodeCreatedEvent({
    required this.name,
    this.categories,
    required this.nodeId,
  });
}

/// Pipeline progress steps.
enum PipelineStep {
  retrieveExpand,
  bfs,
  retrieveFilter,
  categorySupplement,
  savePronoun,
  extract,
  negation,
  typoCorrect,
  dbSave,
  aliasSuggest,
  chat,
}

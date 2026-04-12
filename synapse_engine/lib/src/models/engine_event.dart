import 'triple.dart';

/// Emitted when a triple is added to the graph.
class TripleAddedEvent {
  final Triple triple;
  final int sentenceId;
  final DateTime timestamp;

  const TripleAddedEvent({
    required this.triple,
    required this.sentenceId,
    required this.timestamp,
  });
}

/// Emitted when an edge is deactivated.
class EdgeDeactivatedEvent {
  final Triple triple;
  final String reason; // "conflict" | "manual"

  const EdgeDeactivatedEvent({
    required this.triple,
    required this.reason,
  });
}

/// Emitted when a new node is created.
class NodeCreatedEvent {
  final String name;
  final String? category;
  final int nodeId;

  const NodeCreatedEvent({
    required this.name,
    this.category,
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

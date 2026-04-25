import 'triple.dart';

/// Result of the retrieve pipeline.
class RetrieveResult {
  final List<Triple> contextTriples;
  String? answer;
  final List<String> startNodes;

  RetrieveResult({
    List<Triple>? contextTriples,
    this.answer,
    List<String>? startNodes,
  })  : contextTriples = contextTriples ?? [],
        startNodes = startNodes ?? [];
}

/// Result of the save pipeline.
class SaveResult {
  final List<int> sentenceIds;
  final List<(String, String?, String)> triplesAdded;
  final List<int> edgeIdsAdded;
  final List<String> nodesAdded;
  final List<int> nodeIdsAdded;
  final List<(String, String?, String)> edgesDeactivated;
  final List<(String, String)> aliasesAdded;
  final List<(String, String)> typosCorrected;
  final String? question;
  final bool isQuestion;

  SaveResult({
    List<int>? sentenceIds,
    List<(String, String?, String)>? triplesAdded,
    List<int>? edgeIdsAdded,
    List<String>? nodesAdded,
    List<int>? nodeIdsAdded,
    List<(String, String?, String)>? edgesDeactivated,
    List<(String, String)>? aliasesAdded,
    List<(String, String)>? typosCorrected,
    this.question,
    this.isQuestion = false,
  })  : sentenceIds = sentenceIds ?? [],
        triplesAdded = triplesAdded ?? [],
        edgeIdsAdded = edgeIdsAdded ?? [],
        nodesAdded = nodesAdded ?? [],
        nodeIdsAdded = nodeIdsAdded ?? [],
        edgesDeactivated = edgesDeactivated ?? [],
        aliasesAdded = aliasesAdded ?? [],
        typosCorrected = typosCorrected ?? [];
}

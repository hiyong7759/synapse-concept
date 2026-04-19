/// Result of the save pipeline. v15: edges 테이블 폐기로 트리플·엣지 필드 제거.
class SaveResult {
  int? postId;
  final List<int> sentenceIds;
  final List<String> nodesAdded;
  final List<int> nodeIdsAdded;
  int mentionsAdded;
  final List<(int, String)> unresolvedAdded;  // (sentence_id, token)
  final List<String> nodesDeactivated;        // v15: 상태변경된 노드 식별자
  String? markdownDraft;                      // structure-suggest 초안
  String? question;
  bool isQuestion;

  SaveResult({
    this.postId,
    List<int>? sentenceIds,
    List<String>? nodesAdded,
    List<int>? nodeIdsAdded,
    this.mentionsAdded = 0,
    List<(int, String)>? unresolvedAdded,
    List<String>? nodesDeactivated,
    this.markdownDraft,
    this.question,
    this.isQuestion = false,
  })  : sentenceIds = sentenceIds ?? [],
        nodesAdded = nodesAdded ?? [],
        nodeIdsAdded = nodeIdsAdded ?? [],
        unresolvedAdded = unresolvedAdded ?? [],
        nodesDeactivated = nodesDeactivated ?? [];
}

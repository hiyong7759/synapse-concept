// Data classes returned by GraphOps. Immutable.
// Mirrors the schema defined in docs/DESIGN_HYPERGRAPH.md.

class Node {
  const Node({required this.id, required this.name});
  final int id;
  final String name;

  @override
  String toString() => 'Node($id, "$name")';
}

class Sentence {
  const Sentence({
    required this.id,
    required this.postId,
    required this.text,
    this.position = 0,
    this.role = 'user',
    this.origin,
  });
  final int id;
  final int postId;
  final String text;
  final int position;
  final String role;

  /// `null`, `'user'`, or `'insight'`. The `'insight'` value marks a
  /// promoted sentence whose body is not editable. See DESIGN_HYPERGRAPH §스키마.
  final String? origin;

  bool get isInsight => origin == 'insight';
}

/// One row of `node_sentence_mentions`, optionally enriched with the
/// matching node name and sentence text (for retrieve / display paths).
///
/// `sentenceCreatedAt` is included so retrieve callers can sort by time
/// without an extra round-trip to the `sentences` table — the BFS JOIN
/// already touches that row, so we widen the SELECT instead of issuing a
/// follow-up query (DESIGN_PIPELINE §인출 — 시간 순 정렬은 LLM 답변 합성의 핵심 입력).
class Mention {
  const Mention({
    required this.nodeId,
    required this.sentenceId,
    this.origin = 'system',
    this.nodeName,
    this.sentenceText,
    this.sentenceCreatedAt,
  });
  final int nodeId;
  final int sentenceId;
  final String origin;
  final String? nodeName;
  final String? sentenceText;

  /// `sentences.created_at` — `YYYY-MM-DD HH:MM:SS` (sqflite TEXT default).
  final String? sentenceCreatedAt;
}

class Alias {
  const Alias({
    required this.alias,
    required this.nodeId,
    required this.origin,
  });
  final String alias;
  final int nodeId;
  final String origin;
}

/// One pair of nodes that look like typos of each other (jamo distance ≤
/// [distance]). Both nodes already exist in the graph; resolving the pair
/// is a `/review` decision (DESIGN_REVIEW §섹션별 도출기 — suspected_typos).
class TypoCandidate {
  const TypoCandidate({
    required this.left,
    required this.right,
    required this.distance,
  });
  final Node left;
  final Node right;
  final int distance;
}

/// Lightweight rollup for diagnostics + the `/review` summary header.
/// Each field is a row count in the corresponding table.
class EngineStats {
  const EngineStats({
    required this.postCount,
    required this.sentenceCount,
    required this.nodeCount,
    required this.mentionCount,
    required this.aliasCount,
    required this.categoryCount,
    required this.unresolvedTokenCount,
  });
  final int postCount;
  final int sentenceCount;
  final int nodeCount;
  final int mentionCount;
  final int aliasCount;
  final int categoryCount;
  final int unresolvedTokenCount;
}

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

/// Per-post / per-nodeIds / full snapshot of the hypergraph for visualization.
///
/// Returned by `SynapseFlow.getGraph({postId?, nodeIds?})`. Single entry point
/// for the F8 `/hypergraph` route, F7d `/note` graph panel, and F9 `/synapse`
/// graph panel — they only differ in the filter passed.
///
/// `degree`, `isInsight`, and `primaryCategoryCode` are pre-computed in SQL so
/// the visualization layer (vis-network) can map straight to node radius /
/// glow / color without a second pass.
class GraphData {
  const GraphData({
    required this.nodes,
    required this.sentences,
    required this.mentions,
    required this.categories,
    required this.nodeCategories,
    this.sentenceCategories = const [],
  });

  final List<GraphNode> nodes;
  final List<GraphSentence> sentences;
  final List<GraphMention> mentions;
  final List<GraphCategory> categories;
  final List<GraphNodeCategory> nodeCategories;

  /// `sentence_categories` rows scoped to the working sentence set.
  /// Used by the visualization layer to color sentence baskets by their
  /// user-heading root (vs seed-19 categories on nodes).
  final List<GraphSentenceCategory> sentenceCategories;

  bool get isEmpty => nodes.isEmpty && sentences.isEmpty;
}

class GraphNode {
  const GraphNode({
    required this.id,
    required this.name,
    required this.degree,
    required this.isInsight,
    this.primaryCategoryCode,
  });

  final int id;
  final String name;

  /// `node_sentence_mentions` row count for this node, after the filter.
  /// Drives node radius (`min(14, 3 + sqrt(degree) * 2.2)`).
  final int degree;

  /// True if this node is connected to any `sentences.origin = 'insight'`
  /// sentence. Drives the amber glow + outer ring.
  final bool isInsight;

  /// First seed-root category code (`BOD` / `WRK` / `FOD` / ...) attached to
  /// this node via `node_category_mentions`, picked deterministically by
  /// lowest `category_id`. Drives node fill color in `/hypergraph`. `null`
  /// when the node has no seed-root mapping yet.
  final String? primaryCategoryCode;
}

class GraphSentence {
  const GraphSentence({
    required this.id,
    required this.postId,
    required this.text,
    required this.role,
    this.origin,
  });
  final int id;
  final int postId;
  final String text;
  final String role;
  final String? origin;

  bool get isInsight => origin == 'insight';
}

class GraphMention {
  const GraphMention({
    required this.nodeId,
    required this.sentenceId,
  });
  final int nodeId;
  final int sentenceId;
}

class GraphCategory {
  const GraphCategory({
    required this.id,
    required this.name,
    this.parentId,
    this.code,
  });
  final int id;
  final String name;
  final int? parentId;

  /// 3-letter seed-root code (`BOD` / `WRK` / ...) when this row is itself
  /// a seed root (i.e. `parent_id IS NULL` AND `name` is in `seedRoots19`).
  /// `null` for user-heading categories and leaf rows under a seed root.
  final String? code;
}

class GraphNodeCategory {
  const GraphNodeCategory({
    required this.nodeId,
    required this.categoryId,
    required this.origin,
  });
  final int nodeId;
  final int categoryId;
  final String origin;
}

class GraphSentenceCategory {
  const GraphSentenceCategory({
    required this.sentenceId,
    required this.categoryId,
    required this.origin,
  });
  final int sentenceId;
  final int categoryId;
  final String origin;
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

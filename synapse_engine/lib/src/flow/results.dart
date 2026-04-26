import '../llm/tasks.dart';
import '../models/graph_models.dart';

/// Outcome of [SynapseFlow.noteProcess].
///
/// `corrections` carries typo-normalize candidates the UI should render as
/// inline cards. They are NOT applied automatically (DESIGN_PRINCIPLES
/// 14-③); the user clicks [적용] to commit them. Empty in F5a since
/// `LlmTasks.typoNormalize` is still a stub.
class NoteProcessResult {
  const NoteProcessResult({
    required this.postId,
    required this.sentencesAdded,
    required this.unresolvedTokens,
    this.corrections = const [],
  });

  /// The post that was reprocessed.
  final int postId;

  /// Sentence rows newly inserted by this run. Caller can present them as
  /// the rendered note state.
  final List<Sentence> sentencesAdded;

  /// `(sentence_id, token)` pairs the engine could not resolve at save
  /// time. Already INSERTed into `unresolved_tokens`; included here so the
  /// UI can flag them inline ("이 문장에 모호한 지시어가 있어요").
  final List<({int sentenceId, String token})> unresolvedTokens;

  /// Pending typo-normalize suggestions (UI cards). Empty until typoNormalize
  /// lands.
  final List<Correction> corrections;
}

/// Outcome of [SynapseFlow.synapseTurn]. The post-id is reused on follow-up
/// turns so a session keeps accumulating Q/A pairs; `retrievedNodeIds` is
/// the cache the UI hands back to [SynapseFlow.promoteToInsight] when the
/// user marks an answer as a keeper.
class SynapseTurnResult {
  const SynapseTurnResult({
    required this.postId,
    required this.questionSentenceId,
    required this.answerSentenceId,
    required this.answer,
    required this.retrievedNodeIds,
    required this.contextSentenceIds,
  });

  final int postId;
  final int questionSentenceId;
  final int answerSentenceId;
  final String answer;

  /// Every node id BFS visited on this turn (start nodes + expanded co-nodes
  /// + heading-subtree co-nodes + axis-B supplements). Pass-through to
  /// `promoteToInsight.snapshotNodeIds` when the user promotes.
  final List<int> retrievedNodeIds;

  /// Sentence ids that fed into the answer composition step. UI debug
  /// panels can use this to highlight the supporting evidence.
  final List<int> contextSentenceIds;
}

/// Outcome of [SynapseFlow.promoteToInsight].
class InsightResult {
  const InsightResult({
    required this.postId,
    required this.sentenceIds,
    required this.connectedNodeCount,
  });

  /// New `posts.id` (kind='insight').
  final int postId;

  /// Every `sentences.id` inserted under the new insight post.
  final List<int> sentenceIds;

  /// Total `node_sentence_mentions` rows newly written (snapshot snapshot
  /// + Kiwi-extracted nodes, both deduped against UNIQUE conflicts).
  final int connectedNodeCount;
}

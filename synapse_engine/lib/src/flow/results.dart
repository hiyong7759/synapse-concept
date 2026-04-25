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

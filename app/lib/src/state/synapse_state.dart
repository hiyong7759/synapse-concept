import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:synapse_engine/synapse_engine.dart';

import 'note_state.dart';

/// One turn rendered in the `/synapse` thread. Sealed so the UI matches
/// against `SynapseQuestion` / `SynapseAnswer` exhaustively.
sealed class SynapseMessage {
  const SynapseMessage();
}

class SynapseQuestion extends SynapseMessage {
  const SynapseQuestion({required this.text});
  final String text;
}

class SynapseAnswer extends SynapseMessage {
  const SynapseAnswer({
    required this.text,
    required this.retrievedNodeIds,
    required this.questionSentenceId,
    required this.answerSentenceId,
  });
  final String text;
  final List<int> retrievedNodeIds;
  final int questionSentenceId;
  final int answerSentenceId;
}

/// Active synapse `posts.id`. Stays `null` until the first `synapseTurn`
/// returns a fresh post id, which lets follow-up turns reuse the session.
final synapseActivePostIdProvider = StateProvider<int?>((ref) => null);

/// In-memory message log for the current synapse session. Cleared when
/// the user starts a new session ([startNewSynapseSession]).
final synapseMessagesProvider =
    StateProvider<List<SynapseMessage>>((ref) => const []);

/// Current stage of the in-flight `synapseTurn`. `null` means idle. The
/// UI maps any non-null value (other than `done`) to "loading" — the
/// input bar disables itself and the loading indicator labels the active
/// stage (`🔑 키워드 추출`, `🎯 노드 매칭`, `🕸️ 관련 문장 찾기`,
/// `✍️ 답변 생성`).
final synapseProgressProvider =
    StateProvider<SynapseProgressStage?>((ref) => null);

/// Convenience derived signal: true while a turn is in flight (any
/// non-idle, non-done stage). Kept so the input bar / send button can
/// stay declarative without each callsite computing the predicate.
final synapseLoadingProvider = Provider<bool>((ref) {
  final stage = ref.watch(synapseProgressProvider);
  return stage != null && stage != SynapseProgressStage.done;
});

/// Single chip surfaced in the empty-state. `text` is what gets dropped
/// into the input controller; `label` is the short button face. A
/// `[주제]`-style placeholder inside `text` signals the input bar to
/// auto-select that range so the user can type-replace it instantly.
class SuggestionChip {
  const SuggestionChip({required this.label, required this.text});
  final String label;
  final String text;
}

/// Empty-state chips derived from the user's own recent activity.
/// Returns at most 4 chips by mapping the top recent nodes onto the
/// four canonical patterns. Empty list → UI shows a guidance card.
final suggestionChipsProvider =
    FutureProvider.autoDispose<List<SuggestionChip>>((ref) async {
  // Sidebar refreshes invalidate this provider, so chips re-derive after
  // a new note lands without explicit wiring per call site.
  ref.watch(postListProvider);
  final engine = await ref.watch(engineProvider.future);
  final flow = engine.flow;
  if (flow == null) return const [];
  final nodes = await flow.recentTopNodes(limit: 5, daysBack: 7);
  return _buildChips(nodes);
});

List<SuggestionChip> _buildChips(List<RecentNode> nodes) {
  final out = <SuggestionChip>[];
  if (nodes.isNotEmpty) {
    out.add(SuggestionChip(
      label: '📅 ${nodes[0].name}',
      text: '${nodes[0].name} 어떻게 진행되고 있어?',
    ));
  }
  if (nodes.length >= 2) {
    out.add(SuggestionChip(
      label: '📝 ${nodes[1].name}',
      text: '${nodes[1].name} 최근 정리해줘',
    ));
  }
  if (nodes.length >= 4) {
    out.add(SuggestionChip(
      label: '🔗 ${nodes[2].name} × ${nodes[3].name}',
      text: '${nodes[2].name} 와(과) ${nodes[3].name} 가 어떻게 연결돼?',
    ));
  }
  if (nodes.length >= 5) {
    out.add(SuggestionChip(
      label: '💡 ${nodes[4].name}',
      text: '${nodes[4].name} 에 대해 내가 한 결정은?',
    ));
  }
  return out;
}

/// Sends [question] through `synapseTurn`. The Q card lands immediately
/// so the user sees their input echo even while the round trip is in
/// flight; the A card lands when the turn completes (or when the
/// fallback answer comes back if the LLM is not attached).
Future<void> sendQuestion(WidgetRef ref, String question) async {
  final trimmed = question.trim();
  if (trimmed.isEmpty) return;

  final engine = await ref.read(engineProvider.future);
  final flow = engine.flow;
  if (flow == null) {
    throw StateError('SynapseFlow not enabled — synapse turn unavailable');
  }

  final messagesNotifier = ref.read(synapseMessagesProvider.notifier);
  messagesNotifier.state = [
    ...messagesNotifier.state,
    SynapseQuestion(text: trimmed),
  ];
  final progressNotifier = ref.read(synapseProgressProvider.notifier);
  progressNotifier.state = SynapseProgressStage.expanding;

  final priorPostId = ref.read(synapseActivePostIdProvider);
  try {
    final result = await flow.synapseTurn(
      question: trimmed,
      postId: priorPostId,
      onProgress: (stage) => progressNotifier.state = stage,
    );
    ref.read(synapseActivePostIdProvider.notifier).state = result.postId;
    messagesNotifier.state = [
      ...messagesNotifier.state,
      SynapseAnswer(
        text: result.answer,
        retrievedNodeIds: result.retrievedNodeIds,
        questionSentenceId: result.questionSentenceId,
        answerSentenceId: result.answerSentenceId,
      ),
    ];
    // First turn of a fresh session — the sidebar needs to learn about
    // the new `kind='synapse'` row.
    if (priorPostId == null) {
      ref.invalidate(postListProvider);
    }
  } finally {
    progressNotifier.state = null;
  }
}

/// Resets the in-memory thread back to the empty state and re-derives
/// suggestion chips from the latest DB snapshot. Called by the
/// `+ 새 시냅스` button (post_sidebar) and after the user promotes a
/// turn to insight, so the next session starts on a clean slate.
void startNewSynapseSession(WidgetRef ref) {
  ref.read(synapseActivePostIdProvider.notifier).state = null;
  ref.read(synapseMessagesProvider.notifier).state = const [];
  ref.invalidate(suggestionChipsProvider);
}

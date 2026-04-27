import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/note_process.dart';
import '../theme/tokens.dart';
import 'correction_card.dart';

/// Inline list of LLM correction suggestions, rendered below the editor.
/// Sourced from `noteProcessProvider.result.corrections`. Until F3's
/// `typoNormalize` lands, the engine returns an empty list — the list
/// degrades gracefully to a "정정 후보 없음" placeholder right after a
/// successful pass.
class CorrectionList extends ConsumerWidget {
  const CorrectionList({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(noteProcessProvider);
    if (state.status == NoteProcessStatus.idle ||
        state.status == NoteProcessStatus.processing) {
      return const SizedBox.shrink();
    }
    if (state.status == NoteProcessStatus.error) {
      return _Frame(
        child: Text(
          '정리 실패: ${state.error}',
          style: SynapseTokens.caption.copyWith(color: Colors.red),
        ),
      );
    }
    final corrections = state.result?.corrections ?? const [];
    if (corrections.isEmpty) {
      return _Frame(
        child: Text(
          '정정 후보 없음 — 의미 처리만 완료',
          style: SynapseTokens.caption,
        ),
      );
    }
    return _Frame(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _Header(),
          const SizedBox(height: SynapseTokens.spaceS),
          for (final c in corrections)
            CorrectionCard(
              correction: c,
              onApply: () {
                // F3 stub — the engine's `LlmTasks.typoNormalize` isn't
                // wired yet, so we can't actually apply. Card just
                // disappears via clear() below.
                ref.read(noteProcessProvider.notifier).clear();
              },
              onDismiss: () =>
                  ref.read(noteProcessProvider.notifier).clear(),
            ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text('—', style: SynapseTokens.caption),
        const SizedBox(width: SynapseTokens.spaceXs),
        Text('LLM 정정 후보', style: SynapseTokens.caption),
        const SizedBox(width: SynapseTokens.spaceXs),
        Text('—', style: SynapseTokens.caption),
      ],
    );
  }
}

class _Frame extends StatelessWidget {
  const _Frame({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        SynapseTokens.spaceL,
        0,
        SynapseTokens.spaceL,
        SynapseTokens.spaceL,
      ),
      child: child,
    );
  }
}

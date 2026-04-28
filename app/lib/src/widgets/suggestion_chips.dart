import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../state/synapse_state.dart';
import '../theme/tokens.dart';
import 'components.dart';

/// Empty-state chips for the `/synapse` thread. Pulls
/// [suggestionChipsProvider] (derived from the user's recent activity)
/// and renders one button per chip. Tapping a chip drops its full
/// question text into the parent input controller via [onPick].
///
/// When the DB has no recent mentions the provider returns an empty
/// list — the widget then surfaces a guidance card pointing the user
/// at `/note`.
class SuggestionChips extends ConsumerWidget {
  const SuggestionChips({super.key, required this.onPick});

  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final chipsAsync = ref.watch(suggestionChipsProvider);
    return chipsAsync.when(
      loading: () => const _ChipsSkeleton(),
      error: (_, _) => const SizedBox.shrink(),
      data: (chips) => chips.isEmpty
          ? const _EmptyDbGuide()
          : _ChipsWrap(chips: chips, onPick: onPick),
    );
  }
}

class _ChipsWrap extends StatelessWidget {
  const _ChipsWrap({required this.chips, required this.onPick});

  final List<SuggestionChip> chips;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 560),
      child: Wrap(
        alignment: WrapAlignment.center,
        spacing: SynapseTokens.s2,
        runSpacing: SynapseTokens.s2,
        children: [
          for (final c in chips) _Chip(chip: c, onPick: onPick),
        ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.chip, required this.onPick});

  final SuggestionChip chip;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => onPick(chip.text),
        borderRadius: BorderRadius.circular(SynapseTokens.rXl),
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: SynapseTokens.s4,
            vertical: SynapseTokens.s2,
          ),
          decoration: BoxDecoration(
            color: SynapseTokens.accentSoft,
            borderRadius: BorderRadius.circular(SynapseTokens.rXl),
            border: Border.all(color: SynapseTokens.accentLine),
          ),
          child: Text(
            chip.label,
            style: SynapseTokens.bodyStyle(
              size: SynapseTokens.tBase,
              color: SynapseTokens.accent2,
              weight: FontWeight.w500,
            ),
          ),
        ),
      ),
    );
  }
}

class _ChipsSkeleton extends StatelessWidget {
  const _ChipsSkeleton();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 32,
      width: 120,
      child: Center(
        child: SizedBox(
          width: 14,
          height: 14,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: SynapseTokens.text3,
          ),
        ),
      ),
    );
  }
}

class _EmptyDbGuide extends StatelessWidget {
  const _EmptyDbGuide();

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 480),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '아직 떠올릴 재료가 없어요.',
            style: SynapseTokens.bodyStyle(
              size: SynapseTokens.tMd,
              color: SynapseTokens.text2,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: SynapseTokens.s2),
          Text(
            '먼저 노트로 생각을 적어두면, 시냅스가 그 위에서 새로운 연결을 점화합니다.',
            style: SynapseTokens.bodyStyle(
              size: SynapseTokens.tBase,
              color: SynapseTokens.text3,
              height: 1.6,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: SynapseTokens.s4),
          SButton(
            label: '노트 작성하러 가기',
            variant: SButtonVariant.primary,
            size: SButtonSize.md,
            onPressed: () => context.go('/note'),
          ),
        ],
      ),
    );
  }
}

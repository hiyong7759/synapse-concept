import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Slim status strip above the editor — DESIGN_UI line 128 / §자동저장 상태.
/// Mirrors the four [AutosaveStatus] phases plus a hidden state when no
/// note is selected.
class SaveStatusBar extends ConsumerWidget {
  const SaveStatusBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selectedId = ref.watch(selectedPostIdProvider);
    final state = ref.watch(autosaveProvider);

    if (selectedId == null) {
      return const SizedBox(height: 0);
    }

    final label = autosaveStatusLabel(state);
    final color = state.error != null
        ? Colors.red
        : SynapseTokens.onSurfaceMuted;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: SynapseTokens.spaceM,
        vertical: SynapseTokens.spaceXs,
      ),
      decoration: const BoxDecoration(
        border: Border(
          bottom: BorderSide(color: SynapseTokens.background),
        ),
      ),
      child: Text(
        label,
        style: SynapseTokens.caption.copyWith(color: color),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Tiny visual signal for autosave activity — a 60×2 indicator that
/// peripheral vision can register without you having to look at it.
///
///   - dirty / saving → indeterminate sweep (좌→우 흐르는 막대)
///   - saved          → static accent-coloured bar
///   - idle (no save) → empty rail
///   - error          → red bar
///
/// No text — the indicator's width never changes, so right-aligning it in
/// the title row doesn't shift surrounding glyphs.
class SaveStatusBar extends ConsumerWidget {
  const SaveStatusBar({super.key});

  static const double _width = 60;
  static const double _height = 2;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selectedId = ref.watch(selectedPostIdProvider);
    if (selectedId == null) return const SizedBox.shrink();

    final state = ref.watch(autosaveProvider);
    return SizedBox(
      width: _width,
      height: _height,
      child: _indicator(state),
    );
  }

  Widget _indicator(AutosaveState state) {
    if (state.error != null) {
      return _staticBar(Colors.red.shade400);
    }
    switch (state.status) {
      case AutosaveStatus.dirty:
      case AutosaveStatus.saving:
        return LinearProgressIndicator(
          minHeight: _height,
          backgroundColor: SynapseTokens.background,
          valueColor: const AlwaysStoppedAnimation<Color>(
            SynapseTokens.accent,
          ),
        );
      case AutosaveStatus.saved:
        return _staticBar(SynapseTokens.accent);
      case AutosaveStatus.idle:
        return state.lastSavedAt == null
            ? _staticBar(SynapseTokens.background)
            : _staticBar(SynapseTokens.accent.withValues(alpha: 0.4));
    }
  }

  Widget _staticBar(Color color) =>
      Container(decoration: BoxDecoration(color: color));
}

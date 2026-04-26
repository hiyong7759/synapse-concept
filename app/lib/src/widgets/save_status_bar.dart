import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Slim status strip above the editor — DESIGN_UI line 128 / §자동저장 상태.
/// Mirrors the four [AutosaveStatus] phases plus a hidden state when no
/// note is selected. Adds a "..." pulsing animation while dirty so the
/// user feels the system is alive between keystrokes.
class SaveStatusBar extends ConsumerStatefulWidget {
  const SaveStatusBar({super.key});

  @override
  ConsumerState<SaveStatusBar> createState() => _SaveStatusBarState();
}

class _SaveStatusBarState extends ConsumerState<SaveStatusBar> {
  Timer? _dotTimer;
  int _dots = 1;

  void _startDots() {
    _dotTimer ??=
        Timer.periodic(const Duration(milliseconds: 400), (_) {
      if (!mounted) return;
      setState(() => _dots = _dots == 3 ? 1 : _dots + 1);
    });
  }

  void _stopDots() {
    _dotTimer?.cancel();
    _dotTimer = null;
    _dots = 1;
  }

  @override
  void dispose() {
    _dotTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selectedId = ref.watch(selectedPostIdProvider);
    final state = ref.watch(autosaveProvider);

    if (selectedId == null) {
      _stopDots();
      return const SizedBox(height: 0);
    }

    if (state.status == AutosaveStatus.dirty) {
      _startDots();
    } else {
      _stopDots();
    }

    var label = autosaveStatusLabel(state);
    if (state.status == AutosaveStatus.dirty) {
      label = '$label${'.' * _dots}';
    }
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

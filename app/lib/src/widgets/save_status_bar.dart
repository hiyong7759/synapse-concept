import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Slim status strip above the editor. Shows the three transient phases
/// (입력 중 / 저장 중 / 저장됨); the absolute "when" lives in the sidebar
/// so the editor header stays calm and stable across idle windows.
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
      return const SizedBox.shrink();
    }

    if (state.status == AutosaveStatus.dirty) {
      _startDots();
    } else {
      _stopDots();
    }

    final label = autosaveStatusLabel(state);
    final color = state.error != null
        ? Colors.red
        : SynapseTokens.onSurfaceMuted;
    final style = SynapseTokens.caption.copyWith(color: color);

    if (state.status == AutosaveStatus.dirty) {
      // "입력 중" stays put and only the dots animate inside a fixed
      // 16-pixel slot — the row is right-aligned, so any width change
      // would jiggle the whole label.
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: style),
          SizedBox(
            width: 16,
            child: Text('.' * _dots, style: style),
          ),
        ],
      );
    }

    return Text(label, style: style);
  }
}

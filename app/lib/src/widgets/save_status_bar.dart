import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/autosave.dart';
import '../state/note_process.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Tiny status label in the title row, right-aligned. Shows whichever of
/// the autosave / meaning-pass signals is most relevant right now:
///
///   processing > autosave-error > autosave-dirty / -saving > done > saved
///
/// shimmer (좌→우 흰 sweep on glyph strokes) only fires for the two
/// "actively working" states (사용자 입력 / 의미 처리).
class SaveStatusBar extends ConsumerWidget {
  const SaveStatusBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selectedId = ref.watch(selectedPostIdProvider);
    if (selectedId == null) return const SizedBox.shrink();

    final autosave = ref.watch(autosaveProvider);
    final process = ref.watch(noteProcessProvider);
    final spec = _resolveSpec(autosave, process);
    if (spec == null) return const SizedBox.shrink();

    final color = spec.error
        ? SynapseTokens.danger
        : spec.success
            ? SynapseTokens.success
            : SynapseTokens.text3;
    final style = SynapseTokens.bodyStyle(
      size: SynapseTokens.tSm,
      color: color,
    );

    if (spec.shimmer) {
      return _ShimmerText(label: spec.label, baseStyle: style);
    }
    return Text(spec.label, style: style);
  }
}

({String label, bool shimmer, bool error, bool success})? _resolveSpec(
  AutosaveState autosave,
  NoteProcessState process,
) {
  // Meaning pass takes the spotlight while running — it was triggered
  // explicitly so the user is watching for the result.
  if (process.status == NoteProcessStatus.processing) {
    return (label: '정리 중', shimmer: true, error: false, success: false);
  }
  if (process.status == NoteProcessStatus.error) {
    return (label: '정리 실패', shimmer: false, error: true, success: false);
  }
  if (autosave.error != null) {
    return (
      label: '저장 실패 — 다시 시도 중',
      shimmer: false,
      error: true,
      success: false
    );
  }
  switch (autosave.status) {
    case AutosaveStatus.dirty:
      return (label: '입력 중', shimmer: true, error: false, success: false);
    case AutosaveStatus.saving:
      return (
        label: '저장 중...',
        shimmer: false,
        error: false,
        success: false
      );
    case AutosaveStatus.saved:
      return (
        label: '저장됨',
        shimmer: false,
        error: false,
        success: true,
      );
    case AutosaveStatus.idle:
      // noteProcess just finished and the user hasn't started typing
      // again — show the "정리됨" badge instead of the older "저장됨".
      if (process.status == NoteProcessStatus.done) {
        return (
          label: '정리됨',
          shimmer: false,
          error: false,
          success: true,
        );
      }
      if (autosave.lastSavedAt != null) {
        return (
          label: '저장됨',
          shimmer: false,
          error: false,
          success: true,
        );
      }
      return null;
  }
}

/// 텍스트 stroke 픽셀 위로만 흰 sweep band 가 좌→우 linear 로 흐른다.
class _ShimmerText extends StatefulWidget {
  const _ShimmerText({required this.label, required this.baseStyle});
  final String label;
  final TextStyle baseStyle;

  @override
  State<_ShimmerText> createState() => _ShimmerTextState();
}

class _ShimmerTextState extends State<_ShimmerText>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _curved;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..repeat();
    _curved = CurvedAnimation(parent: _ctrl, curve: Curves.easeInCubic);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final whiteStyle = widget.baseStyle.copyWith(color: Colors.white);
    return Stack(
      children: [
        Text(widget.label, style: widget.baseStyle),
        Positioned.fill(
          child: AnimatedBuilder(
            animation: _curved,
            builder: (_, child) {
              return ShaderMask(
                blendMode: BlendMode.srcIn,
                shaderCallback: (bounds) {
                  final p = _curved.value;
                  final w = bounds.width;
                  final bandHalf = w * 0.25;
                  return ui.Gradient.linear(
                    Offset(w * p - bandHalf, 0),
                    Offset(w * p + bandHalf, 0),
                    const <Color>[
                      Color(0x00FFFFFF),
                      Color(0xFFFFFFFF),
                      Color(0x00FFFFFF),
                    ],
                    const <double>[0.0, 0.5, 1.0],
                    TileMode.decal,
                  );
                },
                child: Text(widget.label, style: whiteStyle),
              );
            },
          ),
        ),
      ],
    );
  }
}

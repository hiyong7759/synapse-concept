import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Tiny status label in the title row, right-aligned.
///
///   - dirty   → "입력 중" 글자 stroke (폰트 픽셀) 위로 흰 sweep band
///   - saving  → "저장 중..." 텍스트만
///   - saved / idle (저장 있음) → "저장됨" 텍스트만
///   - idle (no save) → 빈
///   - error   → "저장 실패 — 다시 시도 중" (빨강)
///
/// dirty 일 때 흰 sweep 은 텍스트의 글자 stroke 자체에만 적용 — Stack +
/// ShaderMask + BlendMode.srcIn 으로 흰 텍스트 위에 sweep gradient 가
/// 마스크 역할. 결과는 회색 라벨 위로 광이 글자 모양 그대로 지나감.
class SaveStatusBar extends ConsumerWidget {
  const SaveStatusBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selectedId = ref.watch(selectedPostIdProvider);
    if (selectedId == null) return const SizedBox.shrink();

    final state = ref.watch(autosaveProvider);
    final label = autosaveStatusLabel(state);
    if (label.isEmpty) return const SizedBox.shrink();

    final color = state.error != null
        ? Colors.red
        : SynapseTokens.onSurfaceMuted;
    final style = SynapseTokens.caption.copyWith(color: color);

    if (state.status == AutosaveStatus.dirty) {
      return _ShimmerText(label: label, baseStyle: style);
    }
    return Text(label, style: style);
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
      duration: const Duration(milliseconds: 1400),
    )..repeat();
    // ease-in: 좌측에서 천천히 출발해 우측 끝으로 갈수록 가속.
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
                  // sweep band half-width as a fraction of the text box.
                  // Smaller = sharper highlight; larger = softer glow.
                  final bandHalf = w * 0.18;
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

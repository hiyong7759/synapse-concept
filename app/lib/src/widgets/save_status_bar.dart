import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Tiny status label in the title row, right-aligned.
///
///   - dirty   → "입력 중" 텍스트 위로 흰 세로 막대가 좌→우 linear sweep
///   - saving  → "저장 중..." 텍스트만
///   - saved / idle (저장 있음) → "저장됨" 텍스트만
///   - idle (no save) → 빈
///   - error   → "저장 실패 — 다시 시도 중" (빨강)
///
/// 80px 고정 폭 + 우측 정렬이라 라벨 글자 폭이 바뀌어도 위치 흔들림 없음.
class SaveStatusBar extends ConsumerWidget {
  const SaveStatusBar({super.key});

  static const double _width = 80;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selectedId = ref.watch(selectedPostIdProvider);
    if (selectedId == null) return const SizedBox.shrink();

    final state = ref.watch(autosaveProvider);
    final label = autosaveStatusLabel(state);
    final color = state.error != null
        ? Colors.red
        : SynapseTokens.onSurfaceMuted;
    final style = SynapseTokens.caption.copyWith(color: color);

    return SizedBox(
      width: _width,
      child: Stack(
        children: [
          Align(
            alignment: Alignment.centerRight,
            child: Text(label, style: style),
          ),
          if (state.status == AutosaveStatus.dirty)
            const Positioned.fill(child: _SweepOverlay()),
        ],
      ),
    );
  }
}

/// Opaque white vertical bar that travels left → right across the parent
/// in a single direction, then loops back from the left. Sits as a Stack
/// overlay above the dirty-state label so the label briefly disappears
/// behind the bar as it passes — same pattern as skeleton shimmer.
class _SweepOverlay extends StatefulWidget {
  const _SweepOverlay();

  @override
  State<_SweepOverlay> createState() => _SweepOverlayState();
}

class _SweepOverlayState extends State<_SweepOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return CustomPaint(painter: _SweepPainter(progress: _ctrl));
  }
}

class _SweepPainter extends CustomPainter {
  _SweepPainter({required this.progress}) : super(repaint: progress);

  final Animation<double> progress;

  static const double _barWidth = 8;

  @override
  void paint(Canvas canvas, Size size) {
    // No background — overlay sits over the existing label so the rest of
    // the row stays transparent.
    final span = size.width + _barWidth;
    final x = span * progress.value - _barWidth;
    final paint = Paint()..color = Colors.white;
    canvas.drawRect(
      Rect.fromLTWH(x, 0, _barWidth, size.height),
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant _SweepPainter oldDelegate) => false;
}

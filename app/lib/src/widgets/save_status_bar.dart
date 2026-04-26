import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Tiny visual signal for autosave activity — a 60×2 indicator that
/// peripheral vision can register without you having to look at it.
///
///   - dirty / saving → 흰색 세로 막대가 좌→우 linear sweep (shimmer)
///   - saved          → 정적 accent 막대
///   - idle (저장 있음) → accent 40% opacity 정적 막대
///   - idle (저장 없음) → 빈 rail
///   - error          → 빨간 막대
///
/// 60px 고정 폭 — 우측 정렬해도 라벨 글자 폭 차이로 흔들림 없음.
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
        return const _SweepBar();
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

/// 좌→우 한 방향 linear sweep — 회색 배경 위로 흰 막대가 흘러갔다가
/// 우측 끝에 닿으면 다시 좌측에서 출발. Material 기본
/// LinearProgressIndicator 의 양방향 oscillation 과 다름.
class _SweepBar extends StatefulWidget {
  const _SweepBar();

  @override
  State<_SweepBar> createState() => _SweepBarState();
}

class _SweepBarState extends State<_SweepBar>
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
    return CustomPaint(
      painter: _SweepPainter(progress: _ctrl),
    );
  }
}

class _SweepPainter extends CustomPainter {
  _SweepPainter({required this.progress}) : super(repaint: progress);

  final Animation<double> progress;

  static const double _barWidth = 12;
  static final Color _track = SynapseTokens.accent.withValues(alpha: 0.18);
  static const Color _bar = Colors.white;

  @override
  void paint(Canvas canvas, Size size) {
    final track = Paint()..color = _track;
    canvas.drawRect(Offset.zero & size, track);

    // Slide x from -_barWidth (off-screen left) to size.width (off-screen
    // right) so the leading edge appears from the left and the trailing
    // edge fully exits on the right before the next loop starts.
    final span = size.width + _barWidth;
    final x = span * progress.value - _barWidth;
    final bar = Paint()..color = _bar;
    canvas.drawRect(
      Rect.fromLTWH(x, 0, _barWidth, size.height),
      bar,
    );
  }

  @override
  bool shouldRepaint(covariant _SweepPainter oldDelegate) => false;
}

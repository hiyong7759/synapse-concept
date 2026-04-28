import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// Three-pane horizontal split with two draggable handles.
///
/// `start` and `end` are the side panels (sidebar, graph rail). `center`
/// expands to take the rest. Handles sit on the inside of each side panel,
/// 4px wide, picking up an accent tint while dragged.
///
/// Widths are owned locally — they reset to [initialStart] / [initialEnd]
/// when the widget remounts (route change, hot reload). Persisting across
/// launches is a separate task; the on-device data dir would be the right
/// place when we get there.
class ResizableSplit extends StatefulWidget {
  const ResizableSplit({
    super.key,
    required this.start,
    required this.center,
    required this.end,
    this.initialStart = 220,
    this.initialEnd = 320,
    this.minStart = 160,
    this.maxStart = 360,
    this.minEnd = 240,
    this.maxEnd = 480,
    this.minCenter = 360,
  });

  final Widget start;
  final Widget center;
  final Widget end;

  final double initialStart;
  final double initialEnd;
  final double minStart;
  final double maxStart;
  final double minEnd;
  final double maxEnd;

  /// Soft floor for the centre — handle drags stop short so the editor
  /// never collapses below this.
  final double minCenter;

  @override
  State<ResizableSplit> createState() => _ResizableSplitState();
}

class _ResizableSplitState extends State<ResizableSplit> {
  late double _startWidth = widget.initialStart;
  late double _endWidth = widget.initialEnd;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final total = constraints.maxWidth;
        // Re-clamp on resize — if the window shrinks, side panels shouldn't
        // squeeze the centre below its floor. When the window is narrower
        // than (minStart + minCenter + minEnd) the available space goes
        // negative; we floor each upper bound to its corresponding minimum
        // so clamp(min, max) never sees max<min (would throw).
        final rawMaxStart = total - widget.minCenter - widget.minEnd;
        final maxStart = math.max(
          widget.minStart,
          math.min(widget.maxStart, rawMaxStart),
        );
        final start = _startWidth.clamp(widget.minStart, maxStart);
        final rawMaxEnd = total - widget.minCenter - start;
        final maxEnd = math.max(
          widget.minEnd,
          math.min(widget.maxEnd, rawMaxEnd),
        );
        final end = _endWidth.clamp(widget.minEnd, maxEnd);

        return Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(width: start, child: widget.start),
            _Handle(
              onDelta: (dx) {
                setState(() {
                  _startWidth = (start + dx)
                      .clamp(widget.minStart, maxStart);
                });
              },
            ),
            Expanded(child: widget.center),
            _Handle(
              onDelta: (dx) {
                setState(() {
                  _endWidth = (end - dx).clamp(widget.minEnd, maxEnd);
                });
              },
            ),
            SizedBox(width: end, child: widget.end),
          ],
        );
      },
    );
  }
}

class _Handle extends StatefulWidget {
  const _Handle({required this.onDelta});
  final ValueChanged<double> onDelta;

  @override
  State<_Handle> createState() => _HandleState();
}

class _HandleState extends State<_Handle> {
  bool _hover = false;
  bool _dragging = false;

  @override
  Widget build(BuildContext context) {
    final active = _hover || _dragging;
    return MouseRegion(
      cursor: SystemMouseCursors.resizeColumn,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onHorizontalDragStart: (_) => setState(() => _dragging = true),
        onHorizontalDragEnd: (_) => setState(() => _dragging = false),
        onHorizontalDragCancel: () => setState(() => _dragging = false),
        onHorizontalDragUpdate: (d) => widget.onDelta(d.delta.dx),
        child: AnimatedContainer(
          duration: SynapseTokens.durFast,
          curve: SynapseTokens.ease,
          width: 4,
          color: active
              ? SynapseTokens.accentLine
              : SynapseTokens.border,
        ),
      ),
    );
  }
}

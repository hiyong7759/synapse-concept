import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// Two-neuron synapse mark — the firing arc connects two amber nodes, each
/// with a small inner punch. Mirrors `SynapseMark` from the design bundle.
/// Used in the top bar (`SBrandLockup`), splash, and at-rest empty states.
class SBrandMark extends StatelessWidget {
  const SBrandMark({super.key, this.size = 24, this.glow = false});

  final double size;

  /// Soft amber glow. Used at large sizes (≥40px) and on splash/cover —
  /// never as a static highlight in dense UI.
  final bool glow;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _SBrandMarkPainter(glow: glow),
      ),
    );
  }
}

class _SBrandMarkPainter extends CustomPainter {
  _SBrandMarkPainter({required this.glow});

  final bool glow;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final cx1 = w * 0.18;
    final cx2 = w * 0.82;
    final cy = w * 0.5;
    final r = w * 0.18;
    final innerR = r * 0.4;

    if (glow) {
      final glowPaint = Paint()
        ..color = const Color(0x99C8A96E)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6);
      canvas
        ..drawCircle(Offset(cx1, cy), r, glowPaint)
        ..drawCircle(Offset(cx2, cy), r, glowPaint);
    }

    // Firing arc.
    final arc = Path()
      ..moveTo(cx1, cy)
      ..quadraticBezierTo(w * 0.5, w * 0.05, cx2, cy);
    final arcPaint = Paint()
      ..color = SynapseTokens.accent
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = w * 0.04;
    canvas.drawPath(arc, arcPaint);

    // Two amber neurons.
    final fill = Paint()..color = SynapseTokens.accent;
    canvas
      ..drawCircle(Offset(cx1, cy), r, fill)
      ..drawCircle(Offset(cx2, cy), r, fill);

    // Inner punch — same as background so it reads as a hole, regardless of
    // whatever sits behind the mark.
    final punch = Paint()..color = SynapseTokens.bg;
    canvas
      ..drawCircle(Offset(cx1, cy), innerR, punch)
      ..drawCircle(Offset(cx2, cy), innerR, punch);
  }

  @override
  bool shouldRepaint(_SBrandMarkPainter old) => old.glow != glow;
}

/// Brand mark + Playfair Display "Synapse" wordmark. The default lockup for
/// every TopBar instance.
class SBrandLockup extends StatelessWidget {
  const SBrandLockup({super.key, this.size = 24, this.glow = true});

  /// Mark height in pixels — the wordmark scales relative to this.
  final double size;
  final bool glow;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        SBrandMark(size: size, glow: glow),
        const SizedBox(width: 10),
        Text(
          'Synapse',
          style: SynapseTokens.displayStyle(
            size: size * 0.78,
            weight: FontWeight.w600,
            color: SynapseTokens.text,
            letterSpacing: 0.02 * size * 0.78,
          ),
        ),
      ],
    );
  }
}

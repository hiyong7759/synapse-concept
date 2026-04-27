import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// Five badge tones — these map 1:1 to the React `Badge` component in the
/// design bundle. `mono` is the only variant that switches to JetBrains Mono
/// + uppercase + tracking; the rest stay on Noto Sans KR.
enum SBadgeTone { neutral, insight, success, danger, mono }

/// Compact pill — used for save status, category codes, "✦ 통찰" markers,
/// and other in-line state indicators.
class SBadge extends StatelessWidget {
  const SBadge({
    super.key,
    required this.label,
    this.tone = SBadgeTone.neutral,
    this.icon,
  });

  final String label;
  final SBadgeTone tone;

  /// Leading glyph. Pass `Icon(Icons.check, size: 11)` or similar — the badge
  /// recolors it to match the tone.
  final Widget? icon;

  _BadgeSpec get _spec {
    switch (tone) {
      case SBadgeTone.neutral:
        return const _BadgeSpec(
          background: SynapseTokens.surface3,
          foreground: SynapseTokens.text2,
          border: SynapseTokens.border,
        );
      case SBadgeTone.insight:
        return const _BadgeSpec(
          background: SynapseTokens.accentSoft,
          foreground: SynapseTokens.accent,
          border: SynapseTokens.accentLine,
        );
      case SBadgeTone.success:
        return const _BadgeSpec(
          background: Color(0x1F5DAB8A),
          foreground: SynapseTokens.success,
          border: Color(0x4D5DAB8A),
        );
      case SBadgeTone.danger:
        return const _BadgeSpec(
          background: Color(0x1FC85D5D),
          foreground: SynapseTokens.danger,
          border: Color(0x4DC85D5D),
        );
      case SBadgeTone.mono:
        return const _BadgeSpec(
          background: Colors.transparent,
          foreground: SynapseTokens.text3,
          border: SynapseTokens.border,
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    final spec = _spec;
    final isMono = tone == SBadgeTone.mono;
    final textStyle = isMono
        ? SynapseTokens.monoStyle(
            size: SynapseTokens.tXs,
            color: spec.foreground,
            letterSpacing: 0.04 * SynapseTokens.tXs,
          ).copyWith(fontWeight: FontWeight.w500)
        : SynapseTokens.bodyStyle(
            size: SynapseTokens.tXs,
            weight: FontWeight.w500,
            color: spec.foreground,
            height: 1.2,
          );

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: spec.background,
        borderRadius: BorderRadius.circular(SynapseTokens.rSm),
        border: Border.all(color: spec.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            IconTheme.merge(
              data: IconThemeData(color: spec.foreground, size: 11),
              child: icon!,
            ),
            const SizedBox(width: 4),
          ],
          Text(
            isMono ? label.toUpperCase() : label,
            style: textStyle,
          ),
        ],
      ),
    );
  }
}

class _BadgeSpec {
  const _BadgeSpec({
    required this.background,
    required this.foreground,
    required this.border,
  });

  final Color background;
  final Color foreground;
  final Color border;
}

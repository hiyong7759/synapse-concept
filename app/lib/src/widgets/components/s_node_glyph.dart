import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// Tiny circular glyph standing in for a single hypergraph node. Used in
/// retrieve-trace rows ("허리 ── 디스크 ── L4-L5"), legend swatches, and as a
/// hover preview. The full graph view (F8) renders nodes through CustomPaint
/// directly — this widget is the inline / chip version only.
class SNodeGlyph extends StatelessWidget {
  const SNodeGlyph({
    super.key,
    this.size = 8,
    this.hub = false,
    this.insight = false,
    this.dim = false,
    this.label,
    this.labelOnLeft = false,
  });

  /// Base diameter. Hubs are drawn 4px larger than this; insight nodes match
  /// hub size and pick up a soft amber glow + ring.
  final double size;

  /// Mention-degree hub. Amber fill + small drop-shadow.
  final bool hub;

  /// `kind='insight'` post anchor. Larger glow, outer ring, signals
  /// "Hebbian centre of gravity".
  final bool insight;

  /// Dimmed sibling — used during BFS hover to fade non-neighbours.
  final bool dim;

  /// Optional inline label — shown next to the dot in JetBrains Mono.
  final String? label;

  /// Default puts the label to the right of the dot. Flip for legend rows
  /// where the dot anchors the right edge.
  final bool labelOnLeft;

  @override
  Widget build(BuildContext context) {
    final fill = insight
        ? SynapseTokens.nodeInsight
        : hub
            ? SynapseTokens.accent
            : SynapseTokens.node;
    final diameter = (hub || insight) ? size + 4 : size;

    final dot = Container(
      width: insight ? diameter + 4 : diameter,
      height: insight ? diameter + 4 : diameter,
      padding: EdgeInsets.all(insight ? 2 : 0),
      decoration: insight
          ? BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: SynapseTokens.accentLine, width: 1),
            )
          : null,
      child: Container(
        width: diameter,
        height: diameter,
        decoration: BoxDecoration(
          color: fill,
          shape: BoxShape.circle,
          boxShadow: insight
              ? const [
                  BoxShadow(
                    color: Color(0xB3D9BC83),
                    blurRadius: 14,
                  ),
                ]
              : hub
                  ? const [
                      BoxShadow(
                        color: Color(0x80C8A96E),
                        blurRadius: 10,
                      ),
                    ]
                  : null,
        ),
      ),
    );

    final children = <Widget>[
      dot,
      if (label != null) ...[
        const SizedBox(width: 6),
        Text(
          label!,
          style: SynapseTokens.monoStyle(
            size: SynapseTokens.tXs,
            color: SynapseTokens.text2,
          ),
        ),
      ],
    ];

    return Opacity(
      opacity: dim ? 0.35 : 1,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: labelOnLeft ? children.reversed.toList() : children,
      ),
    );
  }
}

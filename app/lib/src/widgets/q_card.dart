import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// User question bubble in the `/synapse` thread. Right-aligned with an
/// accent left border to read as a quote — matches DESIGN_UI §/synapse
/// Q card.
class QCard extends StatelessWidget {
  const QCard({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: AlignmentDirectional.centerEnd,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: Container(
          margin: const EdgeInsets.only(bottom: SynapseTokens.s3),
          padding: const EdgeInsets.all(SynapseTokens.s4),
          decoration: BoxDecoration(
            color: SynapseTokens.surface,
            borderRadius: BorderRadius.circular(SynapseTokens.rLg),
            border: const Border(
              left: BorderSide(color: SynapseTokens.accent, width: 2),
            ),
          ),
          child: Text(
            text,
            style: SynapseTokens.bodyStyle(
              size: SynapseTokens.tMd,
              color: SynapseTokens.text,
            ),
          ),
        ),
      ),
    );
  }
}

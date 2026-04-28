import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// Synapse-answer bubble. Left-aligned, surface2 background, no border
/// accent — the visual weight stays with the user's question. Action
/// row (`[⬆ 통찰로 승격]` / `[재질문]` / `[복사]`) lands in 마일스톤 C.
class ACard extends StatelessWidget {
  const ACard({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: Container(
          margin: const EdgeInsets.only(bottom: SynapseTokens.s3),
          padding: const EdgeInsets.all(SynapseTokens.s4),
          decoration: BoxDecoration(
            color: SynapseTokens.surface2,
            borderRadius: BorderRadius.circular(SynapseTokens.rLg),
            border: Border.all(color: SynapseTokens.border),
          ),
          child: SelectableText(
            text,
            style: SynapseTokens.bodyStyle(
              size: SynapseTokens.tMd,
              color: SynapseTokens.text,
              height: 1.7,
            ),
          ),
        ),
      ),
    );
  }
}

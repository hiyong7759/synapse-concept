import 'package:flutter/material.dart';
import 'package:synapse_engine/synapse_engine.dart';

import '../theme/tokens.dart';

/// One inline LLM correction suggestion. Mirrors DESIGN_UI §LLM 정정 카드.
/// Auto-apply is forbidden (DESIGN_PRINCIPLES 14-③) — user must click
/// [적용] or [무시].
class CorrectionCard extends StatelessWidget {
  const CorrectionCard({
    super.key,
    required this.correction,
    required this.onApply,
    required this.onDismiss,
  });

  final Correction correction;
  final VoidCallback onApply;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: SynapseTokens.spaceS),
      padding: const EdgeInsets.all(SynapseTokens.spaceM),
      decoration: BoxDecoration(
        color: SynapseTokens.surface,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SynapseTokens.background),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: RichText(
              text: TextSpan(
                style: SynapseTokens.body,
                children: [
                  TextSpan(
                    text: correction.originalToken,
                    style: SynapseTokens.body
                        .copyWith(decoration: TextDecoration.lineThrough),
                  ),
                  const TextSpan(text: '  →  '),
                  TextSpan(
                    text: correction.suggested,
                    style: SynapseTokens.body
                        .copyWith(color: SynapseTokens.accent),
                  ),
                ],
              ),
            ),
          ),
          TextButton(
            onPressed: onDismiss,
            child: const Text('무시'),
          ),
          const SizedBox(width: SynapseTokens.spaceXs),
          ElevatedButton(
            onPressed: onApply,
            child: const Text('적용'),
          ),
        ],
      ),
    );
  }
}

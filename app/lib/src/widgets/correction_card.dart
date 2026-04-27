import 'package:flutter/material.dart';
import 'package:synapse_engine/synapse_engine.dart';

import '../theme/tokens.dart';
import 'components.dart';

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
    final mono = SynapseTokens.monoStyle(
      size: SynapseTokens.tMd,
      color: SynapseTokens.text3,
    );

    return Container(
      margin: const EdgeInsets.only(bottom: SynapseTokens.s2),
      padding: const EdgeInsets.all(SynapseTokens.s4),
      decoration: BoxDecoration(
        color: SynapseTokens.surface,
        borderRadius: BorderRadius.circular(SynapseTokens.rMd),
        border: Border.all(color: SynapseTokens.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: RichText(
              text: TextSpan(
                style: mono,
                children: [
                  TextSpan(
                    text: correction.originalToken,
                    style: mono.copyWith(
                      decoration: TextDecoration.lineThrough,
                      decorationColor: SynapseTokens.text4,
                    ),
                  ),
                  TextSpan(
                    text: '   →   ',
                    style: mono.copyWith(color: SynapseTokens.text4),
                  ),
                  TextSpan(
                    text: correction.suggested,
                    style: mono.copyWith(
                      color: SynapseTokens.accent,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ),
          ),
          SButton(
            label: '무시',
            variant: SButtonVariant.secondary,
            size: SButtonSize.sm,
            onPressed: onDismiss,
          ),
          const SizedBox(width: SynapseTokens.s2),
          SButton(
            label: '적용',
            variant: SButtonVariant.primary,
            size: SButtonSize.sm,
            onPressed: onApply,
          ),
        ],
      ),
    );
  }
}

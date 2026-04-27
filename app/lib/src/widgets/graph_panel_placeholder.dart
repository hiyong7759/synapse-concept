import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// Right-rail placeholder. F8 will replace this with the per-note graph
/// view (DESIGN_UI §데스크톱 — 노드/하이퍼엣지 시각화). The header chrome
/// here matches the eventual layout (icon + title + collapse affordance)
/// so the panel slot does not jump when the real graph lands.
class GraphPanelPlaceholder extends StatelessWidget {
  const GraphPanelPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 320,
      decoration: const BoxDecoration(
        color: SynapseTokens.bg2,
        border: Border(left: BorderSide(color: SynapseTokens.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _Header(),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(SynapseTokens.s4),
              child: Center(
                child: Text(
                  'F8 에서 구현 — 해당 post 의 노드·하이퍼엣지를 시각화합니다.',
                  textAlign: TextAlign.center,
                  style: SynapseTokens.bodyStyle(
                    size: SynapseTokens.tSm,
                    color: SynapseTokens.text3,
                    height: 1.5,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: SynapseTokens.s4,
        vertical: SynapseTokens.s3,
      ),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: SynapseTokens.border)),
      ),
      child: Row(
        children: [
          const Icon(
            Icons.account_tree_outlined,
            size: 14,
            color: SynapseTokens.text2,
          ),
          const SizedBox(width: SynapseTokens.s2),
          Expanded(
            child: Text(
              '이 노트 그래프',
              style: SynapseTokens.bodyStyle(
                size: SynapseTokens.tSm,
                weight: FontWeight.w500,
                color: SynapseTokens.text2,
              ),
            ),
          ),
          const Icon(
            Icons.unfold_less,
            size: 14,
            color: SynapseTokens.text3,
          ),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// Right-rail placeholder. F7d will replace this with the per-note graph
/// view (DESIGN_UI §데스크톱 line 122-152 — 노드/하이퍼엣지 시각화).
class GraphPanelPlaceholder extends StatelessWidget {
  const GraphPanelPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 280,
      color: SynapseTokens.surface,
      child: Padding(
        padding: const EdgeInsets.all(SynapseTokens.spaceM),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('📊 이 노트 그래프', style: SynapseTokens.title),
            const SizedBox(height: SynapseTokens.spaceM),
            Text(
              'F7d 에서 구현 — 해당 post 의 노드·하이퍼엣지를 시각화합니다.',
              style: SynapseTokens.caption,
            ),
          ],
        ),
      ),
    );
  }
}

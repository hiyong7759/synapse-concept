import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/hypergraph_state.dart';
import '../theme/tokens.dart';
import '../widgets/graph_view.dart';
import '../widgets/top_bar.dart';

/// `/hypergraph` route — full accumulated graph (DESIGN_UI §/hypergraph).
///
/// F8'-2 lays down the chrome + graph canvas. Filter sidebar (left) and
/// node-detail panel (right) are placeholders — F8'-3 wires the click /
/// detail flow, F8'-4 wires search / filter / depth slider.
class HypergraphPage extends ConsumerWidget {
  const HypergraphPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      backgroundColor: SynapseTokens.bg,
      body: Column(
        children: [
          const TopBar(active: 'hypergraph'),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: const [
                _FilterPanelPlaceholder(),
                VerticalDivider(width: 1, color: SynapseTokens.border),
                Expanded(child: _GraphCanvas()),
                VerticalDivider(width: 1, color: SynapseTokens.border),
                _DetailPanelPlaceholder(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _GraphCanvas extends ConsumerWidget {
  const _GraphCanvas();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(hypergraphGraphProvider);
    return async.when(
      data: (g) => VisNetworkGraphView(data: g),
      loading: () => const ColoredBox(
        color: SynapseTokens.bg,
        child: Center(
          child: SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      ),
      error: (e, _) => ColoredBox(
        color: SynapseTokens.bg,
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(SynapseTokens.s5),
            child: Text(
              '그래프 로드 실패\n$e',
              textAlign: TextAlign.center,
              style: SynapseTokens.bodyStyle(color: SynapseTokens.danger),
            ),
          ),
        ),
      ),
    );
  }
}

/// 220px filter sidebar — F8'-4 will replace with search / chips / BFS
/// depth slider / category checkboxes / stats.
class _FilterPanelPlaceholder extends StatelessWidget {
  const _FilterPanelPlaceholder();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 220,
      color: SynapseTokens.bg2,
      padding: const EdgeInsets.all(SynapseTokens.s4),
      child: Text(
        '─── FILTERS ───\n\nF8\'-4 에서 추가\n· 검색\n· 칩 (전체/허브/✦/고립)\n· BFS 깊이\n· 카테고리 19 (8 그룹)\n· 통계',
        style: SynapseTokens.monoStyle(
          size: SynapseTokens.tXs,
          color: SynapseTokens.text4,
        ),
      ),
    );
  }
}

/// 280px node-detail panel — F8'-3 will replace with the click-to-detail
/// flow (바구니 원문 · 카테고리 · 별칭 · `[▷ 노트로 이동]`).
class _DetailPanelPlaceholder extends StatelessWidget {
  const _DetailPanelPlaceholder();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 280,
      color: SynapseTokens.bg2,
      padding: const EdgeInsets.all(SynapseTokens.s4),
      child: Text(
        '─── NODE DETAIL ───\n\nF8\'-3 에서 추가\n· 노드 클릭 시\n  바구니 원문 N개\n· 카테고리\n· 별칭\n· [▷ 노트로 이동]',
        style: SynapseTokens.monoStyle(
          size: SynapseTokens.tXs,
          color: SynapseTokens.text4,
        ),
      ),
    );
  }
}

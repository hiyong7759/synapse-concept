import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:synapse_engine/synapse_engine.dart';

import '../state/hypergraph_state.dart';
import '../state/note_state.dart';
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
                _NodeDetailPanel(),
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
      data: (g) => VisNetworkGraphView(
        data: g,
        onNodeTap: (id) =>
            ref.read(selectedNodeIdProvider.notifier).state = id,
      ),
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

/// 280px node-detail panel. Driven by [selectedNodeIdProvider] — empty
/// state when nothing is selected, otherwise pulls the selected node's
/// basket members / sentence excerpts / categories / aliases out of the
/// already-fetched [hypergraphGraphProvider] snapshot (no extra
/// round-trips except aliases, which the snapshot doesn't carry).
class _NodeDetailPanel extends ConsumerWidget {
  const _NodeDetailPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selectedId = ref.watch(selectedNodeIdProvider);
    final asyncGraph = ref.watch(hypergraphGraphProvider);
    return Container(
      width: 280,
      color: SynapseTokens.bg2,
      child: selectedId == null
          ? const _DetailEmpty()
          : asyncGraph.when(
              data: (g) {
                final node = _findNode(g, selectedId);
                if (node == null) return const _DetailEmpty();
                return _DetailContent(graph: g, node: node);
              },
              loading: () => const _DetailEmpty(),
              error: (_, __) => const _DetailEmpty(),
            ),
    );
  }

  GraphNode? _findNode(GraphData g, int id) {
    for (final n in g.nodes) {
      if (n.id == id) return n;
    }
    return null;
  }
}

class _DetailEmpty extends StatelessWidget {
  const _DetailEmpty();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(SynapseTokens.s4),
      child: Text(
        '─── NODE DETAIL ───\n\n노드를 클릭하세요.\n\n· 같은 바구니 멤버 + 원문\n· 카테고리\n· 별칭\n· [▷ 노트로 이동]',
        style: SynapseTokens.monoStyle(
          size: SynapseTokens.tXs,
          color: SynapseTokens.text4,
        ),
      ),
    );
  }
}

class _DetailContent extends ConsumerWidget {
  const _DetailContent({required this.graph, required this.node});
  final GraphData graph;
  final GraphNode node;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Same-basket members: every node sharing a sentence with [node].
    final ownSentenceIds = <int>{};
    for (final m in graph.mentions) {
      if (m.nodeId == node.id) ownSentenceIds.add(m.sentenceId);
    }
    final sentenceById = {for (final s in graph.sentences) s.id: s};
    final sortedSentences = ownSentenceIds
        .map((id) => sentenceById[id])
        .whereType<GraphSentence>()
        .toList()
      ..sort((a, b) => a.id.compareTo(b.id));

    // Categories — walk leaf → root (display root code) and surface origin.
    final categoryById = {for (final c in graph.categories) c.id: c};
    final categories = <_CategoryEntry>[];
    final seenCatIds = <int>{};
    for (final nc in graph.nodeCategories) {
      if (nc.nodeId != node.id) continue;
      if (!seenCatIds.add(nc.categoryId)) continue;
      var cat = categoryById[nc.categoryId];
      String? rootCode;
      while (cat != null && cat.code == null && cat.parentId != null) {
        cat = categoryById[cat.parentId!];
      }
      rootCode = cat?.code;
      final leaf = categoryById[nc.categoryId];
      categories.add(_CategoryEntry(
        rootCode: rootCode,
        leafName: leaf?.name ?? '?',
        origin: nc.origin,
      ));
    }

    final asyncAliases = ref.watch(nodeAliasesProvider(node.id));

    return ListView(
      padding: const EdgeInsets.all(SynapseTokens.s4),
      children: [
        _SectionHeader(label: 'NODE'),
        Text(
          node.isInsight ? '✦ ${node.name}' : node.name,
          style: SynapseTokens.monoStyle(
            size: SynapseTokens.tBase,
            weight: FontWeight.w600,
            color: SynapseTokens.text,
          ),
        ),
        const SizedBox(height: SynapseTokens.s2),
        Text(
          'degree ${node.degree}'
          '${node.isInsight ? ' · ✦ insight' : ''}'
          '${node.degree == 0 ? ' · isolated' : ''}',
          style: SynapseTokens.monoStyle(
            size: SynapseTokens.tXs,
            color: SynapseTokens.text3,
          ),
        ),
        const SizedBox(height: SynapseTokens.s5),
        if (sortedSentences.isNotEmpty) ...[
          _SectionHeader(label: '바구니 ${sortedSentences.length}'),
          for (final s in sortedSentences.take(8))
            _SentenceTile(graph: graph, sentence: s, focusNode: node),
          if (sortedSentences.length > 8)
            Padding(
              padding: const EdgeInsets.only(top: SynapseTokens.s2),
              child: Text(
                '외 ${sortedSentences.length - 8}',
                style: SynapseTokens.monoStyle(
                  size: SynapseTokens.tXs,
                  color: SynapseTokens.text4,
                ),
              ),
            ),
          const SizedBox(height: SynapseTokens.s5),
        ],
        if (categories.isNotEmpty) ...[
          _SectionHeader(label: '카테고리'),
          for (final c in categories)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text(
                '${c.rootCode ?? '—'} / ${c.leafName}  (${c.origin})',
                style: SynapseTokens.monoStyle(
                  size: SynapseTokens.tXs,
                  color: SynapseTokens.text2,
                ),
              ),
            ),
          const SizedBox(height: SynapseTokens.s5),
        ],
        _SectionHeader(label: '별칭'),
        asyncAliases.when(
          data: (list) => list.isEmpty
              ? Text(
                  '없음',
                  style: SynapseTokens.monoStyle(
                    size: SynapseTokens.tXs,
                    color: SynapseTokens.text4,
                  ),
                )
              : Text(
                  list.join(', '),
                  style: SynapseTokens.monoStyle(
                    size: SynapseTokens.tXs,
                    color: SynapseTokens.text2,
                  ),
                ),
          loading: () => Text(
            '…',
            style: SynapseTokens.monoStyle(
              size: SynapseTokens.tXs,
              color: SynapseTokens.text4,
            ),
          ),
          error: (_, __) => Text(
            '별칭 로드 실패',
            style: SynapseTokens.monoStyle(
              size: SynapseTokens.tXs,
              color: SynapseTokens.danger,
            ),
          ),
        ),
        const SizedBox(height: SynapseTokens.s5),
        if (sortedSentences.isNotEmpty)
          _GotoNoteButton(postId: sortedSentences.first.postId, ref: ref),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: SynapseTokens.s2),
      child: Text(
        '─── $label ───',
        style: SynapseTokens.monoStyle(
          size: SynapseTokens.tXs,
          color: SynapseTokens.text4,
        ),
      ),
    );
  }
}

class _SentenceTile extends StatelessWidget {
  const _SentenceTile({
    required this.graph,
    required this.sentence,
    required this.focusNode,
  });
  final GraphData graph;
  final GraphSentence sentence;
  final GraphNode focusNode;

  @override
  Widget build(BuildContext context) {
    // Co-occurring node names (excluding the focus node itself).
    final names = <String>[];
    final nameById = {for (final n in graph.nodes) n.id: n.name};
    for (final m in graph.mentions) {
      if (m.sentenceId != sentence.id) continue;
      if (m.nodeId == focusNode.id) continue;
      final n = nameById[m.nodeId];
      if (n != null) names.add(n);
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: SynapseTokens.s2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            sentence.text,
            style: SynapseTokens.bodyStyle(
              size: SynapseTokens.tXs,
              color: SynapseTokens.text2,
            ),
          ),
          if (names.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text(
              '· ${names.take(6).join(' · ')}'
              '${names.length > 6 ? ' …' : ''}',
              style: SynapseTokens.monoStyle(
                size: SynapseTokens.tXs,
                color: SynapseTokens.text4,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _GotoNoteButton extends StatelessWidget {
  const _GotoNoteButton({required this.postId, required this.ref});
  final int postId;
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () {
        ref.read(selectedPostIdProvider.notifier).state = postId;
        context.go('/note');
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: SynapseTokens.s2),
        child: Text(
          '[▷ 노트로 이동]',
          style: SynapseTokens.monoStyle(
            size: SynapseTokens.tXs,
            color: SynapseTokens.accent,
          ),
        ),
      ),
    );
  }
}

class _CategoryEntry {
  const _CategoryEntry({
    required this.rootCode,
    required this.leafName,
    required this.origin,
  });
  final String? rootCode;
  final String leafName;
  final String origin;
}

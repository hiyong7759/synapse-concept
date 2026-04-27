import 'package:flutter/material.dart';

import '../layout/responsive.dart';
import '../theme/tokens.dart';
import '../widgets/components.dart';
import '../widgets/graph_panel_placeholder.dart';
import '../widgets/post_sidebar.dart';
import '../widgets/top_bar.dart';

/// `/synapse` placeholder. F9 will replace the centre column with the Q/A
/// thread, the `[⬆ 통찰로 승격]` modal, and the per-session retrieve-cache
/// graph (right rail). The 3-pane chrome here is the final layout — only
/// the centre is stubbed.
class SynapsePage extends StatelessWidget {
  const SynapsePage({super.key});

  @override
  Widget build(BuildContext context) {
    return ResponsiveLayout(
      mobile: (_) => const _MobileLayout(),
      desktop: (_) => const _DesktopLayout(),
    );
  }
}

class _DesktopLayout extends StatelessWidget {
  const _DesktopLayout();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SynapseTokens.bg,
      body: Column(
        children: const [
          TopBar(active: 'synapse'),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                PostSidebar(),
                Expanded(child: _SynapseStub(showGraphHint: true)),
                GraphPanelPlaceholder(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MobileLayout extends StatelessWidget {
  const _MobileLayout();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SynapseTokens.bg,
      drawer: const Drawer(
        backgroundColor: SynapseTokens.bg2,
        child: PostSidebar(),
      ),
      body: Column(
        children: [
          Builder(
            builder: (ctx) => TopBar(
              active: 'synapse',
              leading: IconButton(
                icon: const Icon(Icons.menu, size: 18),
                color: SynapseTokens.text2,
                tooltip: '시냅스 목록',
                onPressed: () => Scaffold.of(ctx).openDrawer(),
              ),
            ),
          ),
          const Expanded(child: _SynapseStub(showGraphHint: false)),
        ],
      ),
    );
  }
}

class _SynapseStub extends StatelessWidget {
  const _SynapseStub({required this.showGraphHint});
  final bool showGraphHint;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: SynapseTokens.bg,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(SynapseTokens.s6),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SBrandMark(size: 56, glow: true),
              const SizedBox(height: SynapseTokens.s5),
              Text(
                '/synapse',
                style: SynapseTokens.displayStyle(
                  size: SynapseTokens.t3xl,
                  color: SynapseTokens.text,
                ),
              ),
              const SizedBox(height: SynapseTokens.s3),
              Text(
                'F9 에서 구현 — Q/A 스레드, 통찰 승격 모달, 세션 그래프 패널.',
                style: SynapseTokens.bodyStyle(
                  size: SynapseTokens.tBase,
                  color: SynapseTokens.text2,
                ),
                textAlign: TextAlign.center,
              ),
              if (showGraphHint) ...[
                const SizedBox(height: SynapseTokens.s2),
                Text(
                  '(데스크톱 레이아웃 — 그래프 패널 자리)',
                  style: SynapseTokens.bodyStyle(
                    size: SynapseTokens.tSm,
                    color: SynapseTokens.text3,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

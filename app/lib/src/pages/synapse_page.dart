import 'package:flutter/material.dart';

import '../layout/responsive.dart';
import '../theme/tokens.dart';
import '../widgets/graph_panel_placeholder.dart';
import '../widgets/post_sidebar.dart';
import '../widgets/resizable_split.dart';
import '../widgets/synapse_thread.dart';
import '../widgets/top_bar.dart';

/// `/synapse` route. The 3-pane chrome (post sidebar · Q/A thread ·
/// session graph panel) matches DESIGN_UI §/synapse. The graph panel
/// (right rail) lands in 마일스톤 D — for now it stays as a placeholder
/// so the layout doesn't shift when the panel ships.
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
            child: ResizableSplit(
              start: PostSidebar(),
              center: SynapseThread(),
              end: GraphPanelPlaceholder(),
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
          const Expanded(child: SynapseThread()),
        ],
      ),
    );
  }
}

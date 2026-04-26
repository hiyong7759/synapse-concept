import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../layout/responsive.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';
import '../widgets/graph_panel_placeholder.dart';
import '../widgets/note_editor.dart';
import '../widgets/post_sidebar.dart';

/// `/note` page — DESIGN_UI §/note. Desktop renders all three panes
/// inline; mobile shows just the editor and lets the user swing the
/// sidebar / graph in via the AppBar toggles.
class NotePage extends ConsumerWidget {
  const NotePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Block the page until the engine is ready — `engineProvider` opens
    // the DB and runs migrations, and the sidebar / editor both depend
    // on it being live.
    final engineAsync = ref.watch(engineProvider);

    return engineAsync.when(
      data: (_) => const _NoteScaffold(),
      loading: () => const _BootScreen(label: '엔진 준비 중...'),
      error: (e, _) => _BootScreen(label: '엔진 시작 실패\n$e', isError: true),
    );
  }
}

class _NoteScaffold extends StatelessWidget {
  const _NoteScaffold();

  @override
  Widget build(BuildContext context) {
    return ResponsiveLayout(
      mobile: (_) => const _MobileLayout(),
      desktop: (_) => const _DesktopLayout(),
    );
  }
}

// ── Desktop ──────────────────────────────────────────────

class _DesktopLayout extends StatelessWidget {
  const _DesktopLayout();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Synapse'),
        actions: const [_RouteSwitcher()],
      ),
      body: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: const [
          PostSidebar(),
          VerticalDivider(width: 1),
          Expanded(child: NoteEditor()),
          VerticalDivider(width: 1),
          GraphPanelPlaceholder(),
        ],
      ),
    );
  }
}

// ── Mobile ───────────────────────────────────────────────

class _MobileLayout extends StatefulWidget {
  const _MobileLayout();

  @override
  State<_MobileLayout> createState() => _MobileLayoutState();
}

class _MobileLayoutState extends State<_MobileLayout> {
  bool _showGraph = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Synapse'),
        leading: Builder(
          builder: (ctx) => IconButton(
            icon: const Icon(Icons.menu),
            tooltip: '노트 목록',
            onPressed: () => Scaffold.of(ctx).openDrawer(),
          ),
        ),
        actions: [
          IconButton(
            icon: Icon(_showGraph ? Icons.edit_note : Icons.bubble_chart),
            tooltip: _showGraph ? '본문' : '그래프',
            onPressed: () => setState(() => _showGraph = !_showGraph),
          ),
          const _RouteSwitcher(),
        ],
      ),
      drawer: const Drawer(child: PostSidebar()),
      body: _showGraph ? const GraphPanelPlaceholder() : const NoteEditor(),
    );
  }
}

// ── Shared ───────────────────────────────────────────────

class _RouteSwitcher extends StatelessWidget {
  const _RouteSwitcher();

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: () => context.go('/synapse'),
      child: const Text('Synapse →'),
    );
  }
}

class _BootScreen extends StatelessWidget {
  const _BootScreen({required this.label, this.isError = false});
  final String label;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(SynapseTokens.spaceL),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (!isError)
                const CircularProgressIndicator.adaptive()
              else
                const Icon(Icons.error_outline, color: Colors.red, size: 32),
              const SizedBox(height: SynapseTokens.spaceM),
              Text(label, textAlign: TextAlign.center, style: SynapseTokens.body),
            ],
          ),
        ),
      ),
    );
  }
}

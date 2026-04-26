import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../layout/responsive.dart';
import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';
import '../widgets/graph_panel_placeholder.dart';
import '../widgets/note_editor.dart';
import '../widgets/post_sidebar.dart';
import '../widgets/save_status_bar.dart';
import '../widgets/title_editor.dart';

/// `/note` page — DESIGN_UI §/note. Owns the autosave-flush lifecycle for
/// the editor (page disposal, app lifecycle) so the editor widget itself
/// stays narrowly focused on its TextEditingController.
class NotePage extends ConsumerStatefulWidget {
  const NotePage({super.key});

  @override
  ConsumerState<NotePage> createState() => _NotePageState();
}

class _NotePageState extends ConsumerState<NotePage>
    with WidgetsBindingObserver {
  // Cache the controller in initState so `dispose` doesn't have to touch
  // `ref` (Riverpod marks the ConsumerState ref as disposed before our
  // own dispose runs, which would throw on `ref.read`).
  AutosaveController? _autosave;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _autosave = ref.read(autosaveProvider.notifier);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    // Fire-and-forget — sqflite finishes the write on the same isolate.
    _autosave?.flush();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      _autosave?.flush();
    }
  }

  @override
  Widget build(BuildContext context) {
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
          Expanded(
            child: Column(
              children: [
                TitleEditor(),
                SaveStatusBar(),
                Expanded(child: NoteEditor()),
              ],
            ),
          ),
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
      body: _showGraph
          ? const GraphPanelPlaceholder()
          : const Column(
              children: [
                TitleEditor(),
                SaveStatusBar(),
                Expanded(child: NoteEditor()),
              ],
            ),
    );
  }
}

// ── Shared ───────────────────────────────────────────────

class _RouteSwitcher extends ConsumerWidget {
  const _RouteSwitcher();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return TextButton(
      onPressed: () async {
        // Persist before leaving — go_router won't dispose the page
        // until after navigation completes, and we'd rather the save
        // commit before the new page mounts.
        await flushAutosave(ref);
        if (!context.mounted) return;
        context.go('/synapse');
      },
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

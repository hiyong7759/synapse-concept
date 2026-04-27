import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../layout/responsive.dart';
import '../state/autosave.dart';
import '../state/note_process.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';
import '../widgets/components.dart';
import '../widgets/correction_list.dart';
import '../widgets/graph_panel_placeholder.dart';
import '../widgets/note_editor.dart';
import '../widgets/post_sidebar.dart';
import '../widgets/save_status_bar.dart';
import '../widgets/title_editor.dart';
import '../widgets/top_bar.dart';

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
    final body = engineAsync.when(
      data: (_) => const _NoteScaffold(),
      loading: () => const _BootScreen(label: '엔진 준비 중...'),
      error: (e, _) => _BootScreen(label: '엔진 시작 실패\n$e', isError: true),
    );
    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        const SingleActivator(LogicalKeyboardKey.keyS, meta: true):
            () => runMeaningPass(ref),
        const SingleActivator(LogicalKeyboardKey.keyS, control: true):
            () => runMeaningPass(ref),
      },
      child: Focus(autofocus: true, child: body),
    );
  }
}

/// Shared between the ⌘S keyboard handler and the on-screen "정리" button.
/// Lives at module scope so the button (which only has `ref` access) can
/// trigger it without reaching back into [_NotePageState].
Future<void> runMeaningPass(WidgetRef ref) async {
  final postId = ref.read(selectedPostIdProvider);
  if (postId == null) return;
  await ref.read(autosaveProvider.notifier).flush();
  final source = ref.read(editorDraftProvider);
  await ref
      .read(noteProcessProvider.notifier)
      .run(postId: postId, source: source);
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
      backgroundColor: SynapseTokens.bg,
      body: Column(
        children: const [
          TopBar(active: 'note'),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                PostSidebar(),
                Expanded(child: _NoteEditorPane()),
                GraphPanelPlaceholder(),
              ],
            ),
          ),
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
      backgroundColor: SynapseTokens.bg,
      drawer: const Drawer(
        backgroundColor: SynapseTokens.bg2,
        child: PostSidebar(),
      ),
      body: Column(
        children: [
          Builder(
            builder: (ctx) => TopBar(
              active: 'note',
              leading: IconButton(
                icon: const Icon(Icons.menu, size: 18),
                color: SynapseTokens.text2,
                tooltip: '노트 목록',
                onPressed: () => Scaffold.of(ctx).openDrawer(),
              ),
              actions: [
                IconButton(
                  icon: Icon(
                    _showGraph
                        ? Icons.edit_note_outlined
                        : Icons.account_tree_outlined,
                    size: 18,
                  ),
                  color: SynapseTokens.text2,
                  tooltip: _showGraph ? '본문' : '그래프',
                  onPressed: () => setState(() => _showGraph = !_showGraph),
                ),
              ],
            ),
          ),
          Expanded(
            child: _showGraph
                ? const GraphPanelPlaceholder()
                : const _NoteEditorPane(),
          ),
        ],
      ),
    );
  }
}

/// Editor pane — matches DESIGN_UI §/note `NoteEditorPane`. Stack:
///   1. Status row (autosave badge + ⌘S 정리 trigger)
///   2. Title editor (Playfair display)
///   3. Body editor (Noto Sans KR, expands)
///   4. Inline correction list (LLM 정정 후보)
class _NoteEditorPane extends StatelessWidget {
  const _NoteEditorPane();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: SynapseTokens.bg,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: const [
          _StatusRow(),
          _TitleRow(),
          Expanded(child: NoteEditor()),
          CorrectionList(),
        ],
      ),
    );
  }
}

class _StatusRow extends ConsumerWidget {
  const _StatusRow();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: SynapseTokens.s6,
        vertical: SynapseTokens.s3,
      ),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: SynapseTokens.border)),
      ),
      child: Row(
        children: [
          const SaveStatusBar(),
          const Spacer(),
          SButton(
            label: '정리',
            icon: const Text(
              '✦',
              style: TextStyle(
                fontSize: 13,
                color: Color(0xFF1A1408),
                fontWeight: FontWeight.w600,
              ),
            ),
            kbd: '⌘S',
            variant: SButtonVariant.primary,
            size: SButtonSize.sm,
            onPressed: () => runMeaningPass(ref),
          ),
        ],
      ),
    );
  }
}

class _TitleRow extends StatelessWidget {
  const _TitleRow();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.fromLTRB(
        SynapseTokens.s6,
        SynapseTokens.s8,
        SynapseTokens.s6,
        SynapseTokens.s2,
      ),
      child: TitleEditor(),
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
      backgroundColor: SynapseTokens.bg,
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(SynapseTokens.s6),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (!isError)
                const SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: SynapseTokens.accent,
                  ),
                )
              else
                const Icon(
                  Icons.error_outline,
                  color: SynapseTokens.danger,
                  size: 32,
                ),
              const SizedBox(height: SynapseTokens.s4),
              Text(
                label,
                textAlign: TextAlign.center,
                style: SynapseTokens.bodyStyle(
                  size: SynapseTokens.tBase,
                  color: SynapseTokens.text2,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

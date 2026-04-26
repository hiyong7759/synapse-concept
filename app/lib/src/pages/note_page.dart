import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../layout/responsive.dart';
import '../theme/tokens.dart';

/// `/note` placeholder. F7 will replace this with the real note experience
/// (sidebar post list, single editor, autosave debounce, ⌘S meaning trigger,
/// inline correction cards, per-note graph panel).
class NotePage extends StatelessWidget {
  const NotePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Note'),
        actions: [
          TextButton(
            onPressed: () => context.go('/synapse'),
            child: const Text('Synapse →'),
          ),
        ],
      ),
      body: ResponsiveLayout(
        mobile: (_) => const _NoteScaffold(),
        desktop: (_) => const _NoteScaffold(showSidebarHint: true),
      ),
    );
  }
}

class _NoteScaffold extends StatelessWidget {
  const _NoteScaffold({this.showSidebarHint = false});
  final bool showSidebarHint;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(SynapseTokens.spaceL),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('/note', style: SynapseTokens.display),
            const SizedBox(height: SynapseTokens.spaceM),
            const Text(
              'F7 에서 구현 — 사이드바, 자동저장, ⌘S 정리, 정정 카드, 그래프 패널.',
              style: SynapseTokens.body,
              textAlign: TextAlign.center,
            ),
            if (showSidebarHint) ...[
              const SizedBox(height: SynapseTokens.spaceS),
              const Text(
                '(데스크톱 레이아웃 — 사이드바 자리)',
                style: SynapseTokens.caption,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

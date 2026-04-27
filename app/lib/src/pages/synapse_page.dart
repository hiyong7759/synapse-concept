import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../layout/responsive.dart';
import '../theme/tokens.dart';

/// `/synapse` placeholder. F9 will replace this with the Q/A thread, answer
/// markdown rendering, the `[⬆ 통찰로 승격]` modal, and the per-session graph
/// panel that highlights retrieved nodes.
class SynapsePage extends StatelessWidget {
  const SynapsePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Synapse'),
        actions: [
          TextButton(
            onPressed: () => context.go('/note'),
            child: const Text('← Note'),
          ),
        ],
      ),
      body: ResponsiveLayout(
        mobile: (_) => const _SynapseScaffold(),
        desktop: (_) => const _SynapseScaffold(showGraphHint: true),
      ),
    );
  }
}

class _SynapseScaffold extends StatelessWidget {
  const _SynapseScaffold({this.showGraphHint = false});
  final bool showGraphHint;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(SynapseTokens.spaceL),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('/synapse', style: SynapseTokens.display),
            const SizedBox(height: SynapseTokens.spaceM),
            Text(
              'F9 에서 구현 — Q/A 스레드, 통찰 승격 모달, 세션 그래프 패널.',
              style: SynapseTokens.body,
              textAlign: TextAlign.center,
            ),
            if (showGraphHint) ...[
              const SizedBox(height: SynapseTokens.spaceS),
              Text(
                '(데스크톱 레이아웃 — 그래프 패널 자리)',
                style: SynapseTokens.caption,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../state/autosave.dart';
import '../theme/tokens.dart';
import 'components.dart';

/// Top bar shared by every route. 48px tall, surface-2 fill, brand lockup on
/// the left, route tabs on the right (mono `/note`, `/synapse`,
/// `/hypergraph`). Mirrors the React `TopBar` from the design bundle.
///
/// `/hypergraph` is kept as a visible-but-disabled tab — the route is built
/// in F8, this widget signals where it will land.
class TopBar extends ConsumerWidget {
  const TopBar({super.key, required this.active, this.leading, this.actions});

  /// One of `'note'`, `'synapse'`, `'hypergraph'`. Controls which tab paints
  /// the accent underline.
  final String active;

  /// Mobile-only override — drawer hamburger or back affordance. Desktop
  /// usage leaves this null and lets the brand lockup take the slot.
  final Widget? leading;

  /// Trailing slot before the route tabs. Mobile uses this for the
  /// "graph toggle" icon.
  final List<Widget>? actions;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      height: 48,
      decoration: const BoxDecoration(
        color: SynapseTokens.bg2,
        border: Border(bottom: BorderSide(color: SynapseTokens.border)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: SynapseTokens.s5),
      child: Row(
        children: [
          if (leading != null) ...[
            leading!,
            const SizedBox(width: SynapseTokens.s3),
          ],
          const SBrandLockup(size: 20),
          const Spacer(),
          if (actions != null) ...[
            ...actions!,
            const SizedBox(width: SynapseTokens.s2),
          ],
          _RouteTab(
            id: 'note',
            active: active == 'note',
            onTap: () => _navigate(ref, context, '/note'),
          ),
          _RouteTab(
            id: 'synapse',
            active: active == 'synapse',
            onTap: () => _navigate(ref, context, '/synapse'),
          ),
          const _RouteTab(
            id: 'hypergraph',
            active: false,
            onTap: null,
          ),
        ],
      ),
    );
  }

  Future<void> _navigate(
    WidgetRef ref,
    BuildContext context,
    String location,
  ) async {
    if (GoRouterState.of(context).matchedLocation == location) return;
    // Persist before leaving — go_router won't dispose the page until after
    // navigation, and we'd rather the save commit before the new page
    // mounts.
    await flushAutosave(ref);
    if (!context.mounted) return;
    context.go(location);
  }
}

class _RouteTab extends StatefulWidget {
  const _RouteTab({
    required this.id,
    required this.active,
    required this.onTap,
  });

  final String id;
  final bool active;
  final VoidCallback? onTap;

  @override
  State<_RouteTab> createState() => _RouteTabState();
}

class _RouteTabState extends State<_RouteTab> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final disabled = widget.onTap == null;
    final color = disabled
        ? SynapseTokens.text4
        : widget.active
            ? SynapseTokens.accent
            : _hover
                ? SynapseTokens.text2
                : SynapseTokens.text3;
    return MouseRegion(
      cursor: disabled
          ? SystemMouseCursors.basic
          : SystemMouseCursors.click,
      onEnter: (_) {
        if (!disabled) setState(() => _hover = true);
      },
      onExit: (_) {
        if (!disabled) setState(() => _hover = false);
      },
      child: GestureDetector(
        onTap: widget.onTap,
        behavior: HitTestBehavior.opaque,
        child: Tooltip(
          message: disabled ? 'F8 에서 구현 예정' : '/${widget.id}',
          waitDuration: const Duration(milliseconds: 600),
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: SynapseTokens.s3,
              vertical: 4,
            ),
            decoration: BoxDecoration(
              border: Border(
                bottom: BorderSide(
                  color: widget.active
                      ? SynapseTokens.accent
                      : Colors.transparent,
                ),
              ),
            ),
            child: Text(
              '/${widget.id}',
              style: SynapseTokens.monoStyle(
                size: SynapseTokens.tSm,
                color: color,
                letterSpacing: 0.05 * SynapseTokens.tSm,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

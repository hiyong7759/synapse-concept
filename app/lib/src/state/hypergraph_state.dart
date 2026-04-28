import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:synapse_engine/synapse_engine.dart';

import 'note_state.dart';

/// Full-snapshot graph for `/hypergraph`. F7d / F9 will add their own
/// providers (postId / nodeIds filtered) using the same `flow.getGraph`
/// entry point.
///
/// Not auto-disposed — the StatefulShellRoute keeps `/hypergraph` mounted
/// across tab switches anyway, but explicitly cacheing the snapshot also
/// guards reuse apps that might mount the page outside the shell. The
/// provider is invalidated on ⌘S meaning-pass completion (F8'-3c) so new
/// nodes flow in without a full refetch on every tab visit.
final hypergraphGraphProvider =
    FutureProvider<GraphData>((ref) async {
  final engine = await ref.watch(engineProvider.future);

  // Categorize queue makes async progress (backfill drains node-by-node).
  // Watch its progress notifier so colors flow in as mentions land.
  // Trailing-edge debounce coalesces bursts; max-wait still lets colors
  // land progressively during a long uninterrupted drain (without it the
  // trailing timer keeps resetting and the user sees no update until the
  // entire backfill finishes).
  final queue = engine.categorizeQueue;
  if (queue != null) {
    Timer? trailing;
    Timer? maxWait;
    void invalidate() {
      trailing?.cancel();
      trailing = null;
      maxWait?.cancel();
      maxWait = null;
      ref.invalidateSelf();
    }
    void onProgress() {
      trailing?.cancel();
      trailing = Timer(const Duration(milliseconds: 500), invalidate);
      maxWait ??= Timer(const Duration(seconds: 5), invalidate);
    }
    queue.processedNotifier.addListener(onProgress);
    ref.onDispose(() {
      queue.processedNotifier.removeListener(onProgress);
      trailing?.cancel();
      maxWait?.cancel();
    });
  }

  final flow = engine.flow;
  if (flow == null) {
    // Reuse-app config without SynapseFlow — show empty graph instead of
    // throwing so the panel still renders the empty state.
    return const GraphData(
      nodes: [],
      sentences: [],
      mentions: [],
      categories: [],
      nodeCategories: [],
    );
  }
  return flow.getGraph();
});

/// Currently-selected node in `/hypergraph`. `null` = nothing selected
/// (detail panel shows the empty hint). Set by VisNetworkGraphView's
/// click bridge.
final selectedNodeIdProvider = StateProvider<int?>((ref) => null);

/// Aliases for [nodeId]. Lives outside [hypergraphGraphProvider]'s
/// `GraphData` because aliases would inflate the snapshot for thousands
/// of nodes most users never click. Fetched on demand when the detail
/// panel opens for a node.
final nodeAliasesProvider =
    FutureProvider.autoDispose.family<List<String>, int>((ref, nodeId) async {
  final engine = await ref.watch(engineProvider.future);
  final rows = await engine.db.query(
    'aliases',
    columns: ['alias'],
    where: 'node_id = ?',
    whereArgs: [nodeId],
    orderBy: 'alias',
  );
  return [for (final r in rows) r['alias']! as String];
});

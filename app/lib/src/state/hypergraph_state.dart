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

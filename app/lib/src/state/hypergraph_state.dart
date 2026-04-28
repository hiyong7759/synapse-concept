import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:synapse_engine/synapse_engine.dart';

import 'note_state.dart';

/// Full-snapshot graph for `/hypergraph`. F7d / F9 will add their own
/// providers (postId / nodeIds filtered) using the same `flow.getGraph`
/// entry point.
final hypergraphGraphProvider =
    FutureProvider.autoDispose<GraphData>((ref) async {
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

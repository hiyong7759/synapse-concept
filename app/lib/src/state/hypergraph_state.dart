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

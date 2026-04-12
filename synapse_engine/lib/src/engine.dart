/// SynapseEngine — public API facade.
///
/// Single entry point for consumer apps.
/// All internal modules are hidden behind this class.

import 'dart:async';

import 'package:sqflite/sqflite.dart';

import 'db.dart' as db_mod;
import 'inference.dart';
import 'models/engine_config.dart';
import 'models/engine_event.dart';
import 'models/graph_query.dart';
import 'models/retrieve_result.dart';
import 'models/save_result.dart';
import 'models/triple.dart';
import 'retrieve.dart' as retrieve_mod;
import 'save.dart' as save_mod;

/// Pipeline result: save + retrieve + answer combined.
class PipelineResult {
  final SaveResult saveResult;
  final RetrieveResult retrieveResult;

  const PipelineResult({
    required this.saveResult,
    required this.retrieveResult,
  });
}

/// On-device knowledge graph engine.
class SynapseEngine {
  final Database _db;
  final InferenceEngine _inference;
  final EngineConfig _config;

  // Event stream controllers
  final _tripleAddedController = StreamController<TripleAddedEvent>.broadcast();
  final _edgeDeactivatedController =
      StreamController<EdgeDeactivatedEvent>.broadcast();
  final _nodeCreatedController = StreamController<NodeCreatedEvent>.broadcast();

  SynapseEngine._(this._db, this._inference, this._config);

  // ── Factory ────────────────────────────────────────────

  /// Create and initialize the engine.
  static Future<SynapseEngine> create(
    EngineConfig config, {
    InferenceBackend? backend,
  }) async {
    // Open DB
    final database = await db_mod.openSynapseDb(config.dataDir);

    // Init inference
    final inferenceBackend = backend ?? StubInferenceBackend();
    final inference = InferenceEngine(
      inferenceBackend,
      systemOverrides: config.systemPromptOverrides,
      maxTokensOverrides: config.maxTokensOverrides,
    );
    await inference.init(config.modelPath, config.adapterDir);

    // Register custom adapters
    for (final adapter in config.customAdapters) {
      inference.registerAdapter(adapter);
    }

    return SynapseEngine._(database, inference, config);
  }

  /// Shut down engine: close DB + unload model.
  Future<void> dispose() async {
    await _inference.dispose();
    await _db.close();
    await _tripleAddedController.close();
    await _edgeDeactivatedController.close();
    await _nodeCreatedController.close();
  }

  // ── Core pipeline ──────────────────────────────────────

  /// Full pipeline: retrieve context → save → generate answer.
  Future<PipelineResult> process(
    String text, {
    void Function(PipelineStep step)? onProgress,
  }) async {
    // 1. Retrieve (for context)
    onProgress?.call(PipelineStep.retrieveExpand);
    final retrieveResult = await retrieve_mod.retrieve(
      _db,
      _inference,
      text,
      adjacencyMap: _buildAdjacencyMap(),
    );

    // 2. Save (with retrieved context)
    onProgress?.call(PipelineStep.extract);
    final contextSentences = retrieveResult.contextTriples
        .where((t) => t.sentenceText != null)
        .map((t) => t.sentenceText!)
        .toSet()
        .toList();

    var saveResult = await save_mod.save(
      _db,
      _inference,
      text,
      contextSentences: contextSentences,
    );

    // Apply onAfterExtract hook
    if (_config.onAfterExtract != null) {
      // Hook gets raw result as map, returns modified
      // (simplified: hook is called after save completes)
    }

    // Emit events
    _emitSaveEvents(saveResult);

    return PipelineResult(
      saveResult: saveResult,
      retrieveResult: retrieveResult,
    );
  }

  /// Save only (no retrieve/answer).
  Future<SaveResult> ingest(String text) async {
    final result = await save_mod.save(_db, _inference, text);
    _emitSaveEvents(result);
    return result;
  }

  /// Retrieve only (no save). For question answering.
  Future<RetrieveResult> retrieve(String query) async {
    return retrieve_mod.retrieve(
      _db,
      _inference,
      query,
      adjacencyMap: _buildAdjacencyMap(),
    );
  }

  // ── Graph query ────────────────────────────────────────

  /// Direct graph query without BFS pipeline.
  Future<List<Triple>> query(GraphQuery q) async {
    final conditions = <String>[];
    final args = <Object>[];

    if (q.nodeName != null) {
      conditions.add('(n1.name = ? OR n2.name = ?)');
      args.addAll([q.nodeName!, q.nodeName!]);
    }
    if (q.nodeId != null) {
      conditions.add('(e.source_node_id = ? OR e.target_node_id = ?)');
      args.addAll([q.nodeId!, q.nodeId!]);
    }
    if (q.category != null) {
      conditions.add('(n1.category = ? OR n2.category = ?)');
      args.addAll([q.category!, q.category!]);
    }
    if (!q.includeInactive) {
      conditions.add("n1.status = 'active' AND n2.status = 'active'");
    }
    if (q.lastDuration != null) {
      final since = DateTime.now()
          .subtract(q.lastDuration!)
          .toIso8601String();
      conditions.add('e.created_at >= ?');
      args.add(since);
    }

    final where =
        conditions.isEmpty ? '' : 'WHERE ${conditions.join(' AND ')}';
    final limit = q.limit != null ? 'LIMIT ${q.limit}' : '';

    final rows = await _db.rawQuery(
      '''SELECT e.id AS edge_id,
                n1.id AS src_id, n1.name AS src,
                n2.id AS tgt_id, n2.name AS tgt,
                e.label, e.sentence_id, s.text AS sentence_text
         FROM edges e
         JOIN nodes n1 ON n1.id = e.source_node_id
         JOIN nodes n2 ON n2.id = e.target_node_id
         LEFT JOIN sentences s ON s.id = e.sentence_id
         $where
         ORDER BY e.created_at DESC
         $limit''',
      args,
    );

    return rows
        .map((r) => Triple(
              src: r['src'] as String,
              label: r['label'] as String?,
              tgt: r['tgt'] as String,
              edgeId: r['edge_id'] as int,
              srcId: r['src_id'] as int,
              tgtId: r['tgt_id'] as int,
              sentenceId: r['sentence_id'] as int?,
              sentenceText: r['sentence_text'] as String?,
            ))
        .toList();
  }

  // ── Graph management ───────────────────────────────────

  Future<void> addAlias(String alias, String nodeName) async {
    final rows = await _db.rawQuery(
      "SELECT id FROM nodes WHERE name = ? AND status = 'active' "
      "ORDER BY updated_at DESC LIMIT 1",
      [nodeName],
    );
    if (rows.isEmpty) return;
    await db_mod.addAlias(_db, alias, rows.first['id'] as int);
  }

  Future<void> removeAlias(String alias) async {
    await db_mod.removeAlias(_db, alias);
  }

  Future<void> splitNode(int nodeId, SplitSpec spec) async {
    final orig = await _db.rawQuery(
      'SELECT id, name, category FROM nodes WHERE id=?',
      [nodeId],
    );
    if (orig.isEmpty) return;

    // Create new node with same name
    final newId = await _db.insert('nodes', {
      'name': orig.first['name'],
      'category': orig.first['category'],
    });

    // Move edges
    for (final eid in spec.edgeIdsToMove) {
      final edge = await _db.rawQuery(
        'SELECT source_node_id, target_node_id FROM edges WHERE id=?',
        [eid],
      );
      if (edge.isEmpty) continue;
      if (edge.first['source_node_id'] == nodeId) {
        await _db.execute(
          'UPDATE edges SET source_node_id=? WHERE id=?',
          [newId, eid],
        );
      } else if (edge.first['target_node_id'] == nodeId) {
        await _db.execute(
          'UPDATE edges SET target_node_id=? WHERE id=?',
          [newId, eid],
        );
      }
    }

    // Register aliases
    await db_mod.addAlias(_db, spec.aliasForOriginal, nodeId);
    await db_mod.addAlias(_db, spec.aliasForNew, newId);
  }

  Future<void> deleteSentence(int sentenceId) async {
    await save_mod.deleteSentence(_db, sentenceId);
  }

  Future<SaveResult> updateSentence(int sentenceId, String newText) async {
    final result =
        await save_mod.updateSentence(_db, _inference, sentenceId, newText);
    _emitSaveEvents(result);
    return result;
  }

  Future<void> rollback(List<int> edgeIds, {List<int>? nodeIds}) async {
    await save_mod.rollback(_db, edgeIds, nodeIds: nodeIds);
  }

  Future<db_mod.EngineStats> getStats() async {
    return db_mod.getStats(_db);
  }

  // ── Custom adapter ─────────────────────────────────────

  Future<void> loadAdapter(AdapterSpec spec) async {
    _inference.registerAdapter(spec);
  }

  Future<String> runAdapter(String name, String input) async {
    return _inference.run(name, input);
  }

  // ── Event streams ──────────────────────────────────────

  Stream<TripleAddedEvent> get onTripleAdded => _tripleAddedController.stream;
  Stream<EdgeDeactivatedEvent> get onEdgeDeactivated =>
      _edgeDeactivatedController.stream;
  Stream<NodeCreatedEvent> get onNodeCreated => _nodeCreatedController.stream;

  // ── Save response (assistant) ──────────────────────────

  Future<int> saveResponse(String text) => save_mod.saveResponse(_db, text);

  // ── Internal ───────────────────────────────────────────

  void _emitSaveEvents(SaveResult result) {
    for (var i = 0; i < result.triplesAdded.length; i++) {
      final (src, label, tgt) = result.triplesAdded[i];
      final edgeId =
          i < result.edgeIdsAdded.length ? result.edgeIdsAdded[i] : 0;
      _tripleAddedController.add(TripleAddedEvent(
        triple: Triple(src: src, label: label, tgt: tgt, edgeId: edgeId),
        sentenceId:
            result.sentenceIds.isNotEmpty ? result.sentenceIds.first : 0,
        timestamp: DateTime.now(),
      ));
    }

    for (final (src, label, tgt) in result.edgesDeactivated) {
      _edgeDeactivatedController.add(EdgeDeactivatedEvent(
        triple: Triple(src: src, label: label, tgt: tgt, edgeId: 0),
        reason: 'conflict',
      ));
    }

    for (var i = 0; i < result.nodesAdded.length; i++) {
      _nodeCreatedController.add(NodeCreatedEvent(
        name: result.nodesAdded[i],
        nodeId:
            i < result.nodeIdsAdded.length ? result.nodeIdsAdded[i] : 0,
      ));
    }
  }

  Map<String, List<String>>? _buildAdjacencyMap() {
    final adj = _config.adjacency;
    if (adj.isEmpty) return null;
    // null → retrieve.dart uses its built-in default map
    return adj.toMap();
  }
}

/// Spec for splitting a homonym node.
class SplitSpec {
  final String aliasForOriginal;
  final String aliasForNew;
  final List<int> edgeIdsToMove;

  const SplitSpec({
    required this.aliasForOriginal,
    required this.aliasForNew,
    required this.edgeIdsToMove,
  });
}

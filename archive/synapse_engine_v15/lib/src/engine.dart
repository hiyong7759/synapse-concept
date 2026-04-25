/// SynapseEngine — public API facade (v15).
///
/// Single entry point for consumer apps. All internal modules are hidden
/// behind this class. v15: edges 테이블 폐기. 연결은 node_mentions +
/// node_categories + aliases 세 하이퍼엣지로 표현.

import 'dart:async';

import 'package:sqflite/sqflite.dart';

import 'db.dart' as db_mod;
import 'inference.dart';
import 'models/engine_config.dart';
import 'models/engine_event.dart';
import 'models/hypergraph_query.dart';
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

/// On-device knowledge hypergraph engine.
class SynapseEngine {
  final Database _db;
  final InferenceEngine _inference;
  final EngineConfig _config;

  // Event stream controllers (v15)
  final _sentenceCommittedController =
      StreamController<SentenceCommittedEvent>.broadcast();
  final _nodeDeactivatedController =
      StreamController<NodeDeactivatedEvent>.broadcast();
  final _nodeCreatedController = StreamController<NodeCreatedEvent>.broadcast();

  SynapseEngine._(this._db, this._inference, this._config);

  // ── Factory ────────────────────────────────────────────

  /// Create and initialize the engine.
  static Future<SynapseEngine> create(
    EngineConfig config, {
    InferenceBackend? backend,
  }) async {
    final database = await db_mod.openSynapseDb(config.dataDir);

    final inferenceBackend = backend ?? StubInferenceBackend();
    final inference = InferenceEngine(
      inferenceBackend,
      systemOverrides: config.systemPromptOverrides,
      maxTokensOverrides: config.maxTokensOverrides,
    );
    await inference.init(config.modelPath, config.adapterDir);

    for (final adapter in config.customAdapters) {
      inference.registerAdapter(adapter);
    }

    return SynapseEngine._(database, inference, config);
  }

  /// Shut down engine: close DB + unload model.
  Future<void> dispose() async {
    await _inference.dispose();
    await _db.close();
    await _sentenceCommittedController.close();
    await _nodeDeactivatedController.close();
    await _nodeCreatedController.close();
  }

  // ── Core pipeline ──────────────────────────────────────

  /// Full pipeline: retrieve context → save → generate answer.
  Future<PipelineResult> process(
    String text, {
    void Function(PipelineStep step)? onProgress,
  }) async {
    onProgress?.call(PipelineStep.retrieveExpand);
    final retrieveResult = await retrieve_mod.retrieve(
      _db,
      _inference,
      text,
      adjacencyMap: _buildAdjacencyMap(),
    );

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

  // ── Hypergraph query ───────────────────────────────────

  /// Direct hypergraph query: 같은 문장 바구니에 공출현한 노드 페어를 Triple 형태로 반환.
  /// v15: edges 테이블 폐기로 node_mentions JOIN 기반.
  Future<List<Triple>> query(HypergraphQuery q) async {
    final conditions = <String>[];
    final args = <Object>[];

    if (q.nodeName != null) {
      conditions.add('(n1.name = ? OR n2.name = ?)');
      args.addAll([q.nodeName!, q.nodeName!]);
    }
    if (q.nodeId != null) {
      conditions.add('(m1.node_id = ? OR m2.node_id = ?)');
      args.addAll([q.nodeId!, q.nodeId!]);
    }
    if (q.category != null) {
      conditions.add(
        '(EXISTS (SELECT 1 FROM node_categories nc1 WHERE nc1.node_id = n1.id AND nc1.category = ?) '
        'OR EXISTS (SELECT 1 FROM node_categories nc2 WHERE nc2.node_id = n2.id AND nc2.category = ?))',
      );
      args.addAll([q.category!, q.category!]);
    }
    if (!q.includeInactive) {
      conditions.add("n1.status = 'active' AND n2.status = 'active'");
    }
    if (q.lastDuration != null) {
      final since =
          DateTime.now().subtract(q.lastDuration!).toIso8601String();
      conditions.add('s.created_at >= ?');
      args.add(since);
    }

    final where =
        conditions.isEmpty ? '' : 'WHERE ${conditions.join(' AND ')}';
    final limit = q.limit != null ? 'LIMIT ${q.limit}' : '';

    final rows = await _db.rawQuery(
      '''SELECT n1.id AS src_id, n1.name AS src,
                n2.id AS tgt_id, n2.name AS tgt,
                s.id AS sentence_id, s.text AS sentence_text
         FROM node_mentions m1
         JOIN node_mentions m2
              ON m1.sentence_id = m2.sentence_id AND m1.node_id < m2.node_id
         JOIN nodes n1 ON n1.id = m1.node_id
         JOIN nodes n2 ON n2.id = m2.node_id
         JOIN sentences s ON s.id = m1.sentence_id
         $where
         ORDER BY s.created_at DESC
         $limit''',
      args,
    );

    return rows
        .map((r) => Triple(
              src: r['src'] as String,
              label: null,  // v15: 라벨 없음
              tgt: r['tgt'] as String,
              srcId: r['src_id'] as int,
              tgtId: r['tgt_id'] as int,
              sentenceId: r['sentence_id'] as int?,
              sentenceText: r['sentence_text'] as String?,
            ))
        .toList();
  }

  // ── Hypergraph management ──────────────────────────────

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

  /// 동명이의어 분리. v15: edges 이관 대신 지정한 sentence의 node_mentions를 새 노드로 이관.
  Future<void> splitNode(int nodeId, SplitSpec spec) async {
    final orig = await _db.rawQuery(
      'SELECT id, name FROM nodes WHERE id=?',
      [nodeId],
    );
    if (orig.isEmpty) return;

    final newId = await _db.insert('nodes', {
      'name': orig.first['name'],
    });
    await _db.execute(
      'INSERT OR IGNORE INTO node_categories (node_id, category) '
      'SELECT ?, category FROM node_categories WHERE node_id=?',
      [newId, nodeId],
    );

    // v15: sentence_ids_to_move 기준으로 node_mentions 이관
    if (spec.sentenceIdsToMove.isNotEmpty) {
      final placeholders =
          List.filled(spec.sentenceIdsToMove.length, '?').join(',');
      await _db.execute(
        'UPDATE node_mentions SET node_id=? '
        'WHERE node_id=? AND sentence_id IN ($placeholders)',
        [newId, nodeId, ...spec.sentenceIdsToMove],
      );
    }

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

  /// v15: 문장·노드 롤백. sentence_ids 삭제 → node_mentions CASCADE.
  Future<void> rollback(List<int> sentenceIds, {List<int>? nodeIds}) async {
    await save_mod.rollback(_db, sentenceIds, nodeIds: nodeIds);
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

  // ── Event streams (v15) ────────────────────────────────

  Stream<SentenceCommittedEvent> get onSentenceCommitted =>
      _sentenceCommittedController.stream;
  Stream<NodeDeactivatedEvent> get onNodeDeactivated =>
      _nodeDeactivatedController.stream;
  Stream<NodeCreatedEvent> get onNodeCreated => _nodeCreatedController.stream;

  // ── Save response (assistant) ──────────────────────────

  Future<int> saveResponse(String text) => save_mod.saveResponse(_db, text);

  // ── Internal ───────────────────────────────────────────

  void _emitSaveEvents(SaveResult result) {
    // 문장 커밋 이벤트 (v15)
    for (final sid in result.sentenceIds) {
      _sentenceCommittedController.add(SentenceCommittedEvent(
        sentenceId: sid,
        text: '',  // retrieve 가능하지만 간소화
        mentionedNodeIds: result.nodeIdsAdded,
        mentionedNodeNames: result.nodesAdded,
        timestamp: DateTime.now(),
      ));
    }

    // 노드 비활성화 이벤트
    for (final marker in result.nodesDeactivated) {
      _nodeDeactivatedController.add(NodeDeactivatedEvent(
        nodeId: 0,
        name: marker,
        reason: 'conflict',
      ));
    }

    // 신규 노드 이벤트
    for (var i = 0; i < result.nodesAdded.length; i++) {
      _nodeCreatedController.add(NodeCreatedEvent(
        name: result.nodesAdded[i],
        nodeId: i < result.nodeIdsAdded.length ? result.nodeIdsAdded[i] : 0,
      ));
    }
  }

  Map<String, List<String>>? _buildAdjacencyMap() {
    final adj = _config.adjacency;
    if (adj.isEmpty) return null;
    return adj.toMap();
  }
}

/// Spec for splitting a homonym node. v15: sentence_ids 기준 이관.
class SplitSpec {
  final String aliasForOriginal;
  final String aliasForNew;
  final List<int> sentenceIdsToMove;

  const SplitSpec({
    required this.aliasForOriginal,
    required this.aliasForNew,
    required this.sentenceIdsToMove,
  });
}

/// Synapse save pipeline — port of engine/save.py.
///
/// Flow:
///   input text
///   → sentences insert
///   → LLM preprocess: pronoun/date substitution
///   → LLM extract: retention + nodes + edges + category + deactivate
///   → negation post-processing
///   → typo correction
///   → DB save (nodes + edges with sentence_id)
///   → LLM alias suggestion (new nodes only)

import 'dart:convert';

import 'package:sqflite/sqflite.dart';

import 'db.dart';
import 'inference.dart';
import 'internal/negation.dart';
import 'internal/regex_patterns.dart';
import 'markdown.dart';
import 'models/save_result.dart';
import 'typo.dart';

// ── First-person aliases ─────────────────────────────────

const _firstPersonAliases = [
  '내', '저', '제', '나의', '저의', '제가', '나는', '저는', '내가', '나한테', '저한테',
];

const _aliasSystem = '''당신은 한국어 지식 그래프 별칭 추출기입니다.
주어진 노드 이름의 별칭(줄임말, 영어 원문, 다국어 표기, 흔한 오타)을 JSON 배열로만 출력하세요. 다른 텍스트 금지.

규칙:
- 100% 확실한 동의어만 포함 (추측 금지)
- 노드 이름 자체는 제외
- 없으면 반드시 [] 반환

예시:
"스타벅스" → ["Starbucks", "스벅"]
"리액트 네이티브" → ["React Native", "RN"]
"허리디스크" → ["요추디스크", "추간판탈출증"]
"맥북프로" → ["MacBook Pro", "맥프로"]
"김민수" → []''';

// ── DB helpers ───────────────────────────────────────────

Future<void> _deactivateEdge(Database db, int edgeId) async {
  await db.execute(
    "UPDATE edges SET last_used=datetime('now') WHERE id=?",
    [edgeId],
  );
  await db.execute(
    '''UPDATE nodes SET status='inactive', updated_at=datetime('now')
       WHERE id = (SELECT target_node_id FROM edges WHERE id=?)''',
    [edgeId],
  );
}

Future<List<(String, String?, String)>> _deactivateBySentenceIds(
  Database db,
  List<int> sentenceIds,
) async {
  if (sentenceIds.isEmpty) return [];
  final ph = List.filled(sentenceIds.length, '?').join(',');
  final rows = await db.rawQuery(
    '''SELECT e.id AS edge_id, n1.name AS src, e.label, n2.name AS tgt
       FROM edges e
       JOIN nodes n1 ON n1.id = e.source_node_id
       JOIN nodes n2 ON n2.id = e.target_node_id
       WHERE e.sentence_id IN ($ph)''',
    sentenceIds,
  );
  final deactivated = <(String, String?, String)>[];
  for (final r in rows) {
    await _deactivateEdge(db, r['edge_id'] as int);
    deactivated.add((
      r['src'] as String,
      r['label'] as String?,
      r['tgt'] as String,
    ));
  }
  return deactivated;
}

Future<void> _registerFirstPersonAliases(Database db, int nodeId) async {
  for (final alias in _firstPersonAliases) {
    await db.insert(
      'aliases',
      {'alias': alias, 'node_id': nodeId},
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
  }
}

// ── Main save function ───────────────────────────────────

/// Save text to the knowledge graph.
///
/// Returns [SaveResult] with added triples, nodes, aliases, etc.
/// If [useLlm] is false, skips all LLM steps (for testing).
Future<SaveResult> save(
  Database db,
  InferenceEngine? engine,
  String text, {
  bool useLlm = true,
  List<String>? contextSentences,
}) async {
  final result = SaveResult();

  // Markdown parsing
  final parsed = parseMarkdown(text);
  final isMarkdown = parsed.any((item) => item.$1 != null);

  if (isMarkdown) {
    await _saveItems(db, engine, parsed, result, useLlm, contextSentences);
  } else {
    await _savePlainText(db, engine, text, result, useLlm, contextSentences);
  }

  return result;
}

/// Save markdown items (heading path + list items).
Future<void> _saveItems(
  Database db,
  InferenceEngine? engine,
  List<(String?, String)> items,
  SaveResult result,
  bool useLlm,
  List<String>? contextSentences,
) async {
  for (final (categoryPath, itemText) in items) {
    final sid = await insertSentence(db, itemText);
    result.sentenceIds.add(sid);

    // Extract
    Map<String, dynamic> extracted;
    if (useLlm && engine != null) {
      try {
        extracted = await llmExtract(engine, itemText,
            contextSentences: contextSentences);
      } catch (_) {
        extracted = {'nodes': [], 'edges': []};
      }
    } else {
      extracted = {'nodes': [], 'edges': []};
    }

    var extNodes = List<Map<String, dynamic>>.from(
        (extracted['nodes'] as List?)?.cast<Map<String, dynamic>>() ?? []);
    var extEdges = List<Map<String, dynamic>>.from(
        (extracted['edges'] as List?)?.cast<Map<String, dynamic>>() ?? []);
    final extDeactivate = extracted['deactivate'] as List? ?? [];
    final retention = extracted['retention'] as String? ?? 'memory';

    // Negation post-processing
    final (negNodes, negEdges) = postprocessNegation(extNodes, extEdges);
    extNodes = negNodes;
    extEdges = negEdges;

    // Typo correction
    if (extNodes.isNotEmpty || extEdges.isNotEmpty) {
      final existingEdgeCounts = await _getExistingNodeEdgeCounts(db);
      final corrections = correctTypos(extNodes, existingEdgeCounts);
      for (final (orig, corrected) in corrections) {
        result.typosCorrected.add((orig, corrected));
        // Fix edges too
        for (final e in extEdges) {
          if (e['source'] == orig) e['source'] = corrected;
          if (e['target'] == orig) e['target'] = corrected;
        }
      }
    }

    // Filter invalid edges
    extEdges.removeWhere(
        (e) => e['source'] == null || e['source'] == '' ||
               e['target'] == null || e['target'] == '');

    // Deactivate
    if (extDeactivate.isNotEmpty) {
      final sids = extDeactivate.whereType<int>().toList();
      final deactivated = await _deactivateBySentenceIds(db, sids);
      result.edgesDeactivated.addAll(deactivated);
    }

    // Update retention
    await db.execute(
      'UPDATE sentences SET retention=? WHERE id=?',
      [retention, sid],
    );

    if (extNodes.isEmpty && extEdges.isEmpty) continue;

    // Override category from heading path
    if (categoryPath != null) {
      for (final node in extNodes) {
        node['category'] = categoryPath;
      }
    }

    // Upsert nodes + insert edges
    await _upsertNodesAndEdges(
      db, extNodes, extEdges, sid, categoryPath, result,
    );
  }

  // Alias suggestion for new nodes
  if (useLlm && engine != null && result.nodesAdded.isNotEmpty) {
    await _suggestAliases(db, engine, result);
  }
}

/// Save plain text (no markdown headings).
Future<void> _savePlainText(
  Database db,
  InferenceEngine? engine,
  String text,
  SaveResult result,
  bool useLlm,
  List<String>? contextSentences,
) async {
  // 1. Paragraph split → sentences insert
  final paragraphs = text
      .split('\n\n')
      .map((p) => p.trim())
      .where((p) => p.isNotEmpty)
      .toList();
  if (paragraphs.isEmpty) paragraphs.add(text);

  final sentenceIds = <int>[];
  for (final p in paragraphs) {
    sentenceIds.add(await insertSentence(db, p));
  }
  result.sentenceIds.addAll(sentenceIds);

  // 2. Preprocess: pronoun/date substitution
  var effectiveText = text;
  if (useLlm && engine != null) {
    try {
      final needsToday = dateWordPattern.hasMatch(text) || agePattern.hasMatch(text);
      final today = needsToday ? DateTime.now().toIso8601String().substring(0, 10) : '';

      // Get recent context from DB
      final recent = await db.rawQuery(
        'SELECT text FROM sentences ORDER BY id DESC LIMIT 2',
      );
      final context = recent.reversed
          .map((r) => '사용자: ${r['text']}')
          .join('\n');

      final pre = await savePronoun(engine, text, context: context, today: today);
      if (pre.containsKey('question')) {
        result.question = pre['question'] as String;
        return;
      }
      effectiveText = (pre['text'] as String?) ?? text;
    } catch (_) {
      // LLM failure — continue with original text
    }
  }

  // 3. LLM extract
  Map<String, dynamic> extracted;
  if (useLlm && engine != null) {
    try {
      extracted = await llmExtract(engine, effectiveText,
          contextSentences: contextSentences);
    } catch (_) {
      extracted = {'nodes': [], 'edges': []};
    }
  } else {
    extracted = {'nodes': [], 'edges': []};
  }

  var extNodes = List<Map<String, dynamic>>.from(
      (extracted['nodes'] as List?)?.cast<Map<String, dynamic>>() ?? []);
  var extEdges = List<Map<String, dynamic>>.from(
      (extracted['edges'] as List?)?.cast<Map<String, dynamic>>() ?? []);
  final extDeactivate = extracted['deactivate'] as List? ?? [];
  final retention = extracted['retention'] as String? ?? 'memory';

  // Negation post-processing
  final (negNodes, negEdges) = postprocessNegation(extNodes, extEdges);
  extNodes = negNodes;
  extEdges = negEdges;

  // Typo correction
  if (extNodes.isNotEmpty || extEdges.isNotEmpty) {
    final existingEdgeCounts = await _getExistingNodeEdgeCounts(db);
    final corrections = correctTypos(extNodes, existingEdgeCounts);
    for (final (orig, corrected) in corrections) {
      result.typosCorrected.add((orig, corrected));
      for (final e in extEdges) {
        if (e['source'] == orig) e['source'] = corrected;
        if (e['target'] == orig) e['target'] = corrected;
      }
    }
  }

  // Filter invalid edges
  extEdges.removeWhere(
      (e) => e['source'] == null || e['source'] == '' ||
             e['target'] == null || e['target'] == '');

  // Deactivate
  if (extDeactivate.isNotEmpty) {
    final sids = extDeactivate.whereType<int>().toList();
    final deactivated = await _deactivateBySentenceIds(db, sids);
    result.edgesDeactivated.addAll(deactivated);
  }

  // Update retention
  if (sentenceIds.isNotEmpty) {
    final ph = List.filled(sentenceIds.length, '?').join(',');
    await db.execute(
      'UPDATE sentences SET retention=? WHERE id IN ($ph)',
      [retention, ...sentenceIds],
    );
  }

  if (extNodes.isEmpty && extEdges.isEmpty) return;

  // Upsert nodes + insert edges
  final sentenceId = sentenceIds.isNotEmpty ? sentenceIds.first : null;
  await _upsertNodesAndEdges(
    db, extNodes, extEdges, sentenceId, null, result,
  );

  // Alias suggestion
  if (useLlm && engine != null && result.nodesAdded.isNotEmpty) {
    await _suggestAliases(db, engine, result);
  }
}

// ── Shared helpers ───────────────────────────────────────

/// Returns map of lowercase name → edge count for active nodes + aliases.
Future<Map<String, int>> _getExistingNodeEdgeCounts(Database db) async {
  final rows = await db.rawQuery(
    '''SELECT n.name, COUNT(e.id) AS cnt FROM nodes n
       LEFT JOIN edges e ON (e.source_node_id = n.id OR e.target_node_id = n.id)
       WHERE n.status='active'
       GROUP BY n.name''',
  );
  final result = <String, int>{};
  for (final r in rows) {
    result[(r['name'] as String).toLowerCase()] = (r['cnt'] as int?) ?? 0;
  }

  final aliasRows = await db.rawQuery(
    '''SELECT a.alias, COUNT(e.id) AS cnt FROM aliases a
       JOIN nodes n ON n.id = a.node_id
       LEFT JOIN edges e ON (e.source_node_id = n.id OR e.target_node_id = n.id)
       WHERE n.status = 'active'
       GROUP BY a.alias''',
  );
  for (final r in aliasRows) {
    result[(r['alias'] as String).toLowerCase()] = (r['cnt'] as int?) ?? 0;
  }

  return result;
}

Future<void> _upsertNodesAndEdges(
  Database db,
  List<Map<String, dynamic>> extNodes,
  List<Map<String, dynamic>> extEdges,
  int? sentenceId,
  String? categoryPath,
  SaveResult result,
) async {
  final nameToId = <String, int>{};

  for (final node in extNodes) {
    final name = node['name'] as String;
    final cat = node['category'] as String?;
    final (nid, isNew) = await upsertNode(db, name);
    await addNodeCategory(db, nid, cat);
    nameToId[name] = nid;
    if (isNew) {
      result.nodesAdded.add(name);
      result.nodeIdsAdded.add(nid);
      if (name == '나') await _registerFirstPersonAliases(db, nid);
    }
  }

  for (final edge in extEdges) {
    final src = edge['source'] as String;
    final tgt = edge['target'] as String;
    for (final nm in [src, tgt]) {
      if (!nameToId.containsKey(nm)) {
        final (nid, isNew) = await upsertNode(db, nm);
        await addNodeCategory(db, nid, categoryPath);
        nameToId[nm] = nid;
        if (isNew) {
          result.nodesAdded.add(nm);
          result.nodeIdsAdded.add(nid);
          if (nm == '나') await _registerFirstPersonAliases(db, nid);
        }
      }
    }
  }

  for (final edge in extEdges) {
    final srcId = nameToId[edge['source'] as String];
    final tgtId = nameToId[edge['target'] as String];
    if (srcId == null || tgtId == null) continue;
    final edgeId = await insertEdge(
      db,
      sourceNodeId: srcId,
      targetNodeId: tgtId,
      label: edge['label'] as String?,
      sentenceId: sentenceId,
    );
    result.triplesAdded.add((
      edge['source'] as String,
      edge['label'] as String?,
      edge['target'] as String,
    ));
    result.edgeIdsAdded.add(edgeId);
  }
}


Future<void> _suggestAliases(
  Database db,
  InferenceEngine engine,
  SaveResult result,
) async {
  final nameToId = Map.fromIterables(result.nodesAdded, result.nodeIdsAdded);
  for (final nodeName in result.nodesAdded) {
    try {
      final raw = await engine.chat(_aliasSystem, nodeName,
          temperature: 0, maxTokens: 64);
      final match = RegExp(r'\[.*?\]', dotAll: true).firstMatch(raw);
      if (match == null) continue;
      final candidates = jsonDecode(match.group(0)!) as List;
      final nodeId = nameToId[nodeName];
      if (nodeId == null) continue;
      for (final alias in candidates) {
        if (alias is! String || alias == nodeName) continue;
        await db.insert(
          'aliases',
          {'alias': alias, 'node_id': nodeId},
          conflictAlgorithm: ConflictAlgorithm.ignore,
        );
        result.aliasesAdded.add((alias, nodeName));
      }
    } catch (_) {
      continue;
    }
  }
}

// ── Rollback ─────────────────────────────────────────────

Future<Map<String, int>> rollback(
  Database db,
  List<int> edgeIds, {
  List<int>? nodeIds,
}) async {
  var edgesDeleted = 0;
  var nodesDeleted = 0;

  if (edgeIds.isNotEmpty) {
    final ph = List.filled(edgeIds.length, '?').join(',');
    edgesDeleted = await db.rawDelete(
      'DELETE FROM edges WHERE id IN ($ph)',
      edgeIds,
    );
  }

  if (nodeIds != null && nodeIds.isNotEmpty) {
    final ph = List.filled(nodeIds.length, '?').join(',');
    final orphans = await db.rawQuery(
      '''SELECT id FROM nodes WHERE id IN ($ph)
         AND id NOT IN (SELECT source_node_id FROM edges)
         AND id NOT IN (SELECT target_node_id FROM edges)''',
      nodeIds,
    );
    final orphanIds = orphans.map((r) => r['id'] as int).toList();
    if (orphanIds.isNotEmpty) {
      final ph2 = List.filled(orphanIds.length, '?').join(',');
      nodesDeleted = await db.rawDelete(
        'DELETE FROM nodes WHERE id IN ($ph2)',
        orphanIds,
      );
    }
  }

  return {'edges_deleted': edgesDeleted, 'nodes_deleted': nodesDeleted};
}

// ── Delete/update sentence ──────────────────────────────

Future<Map<String, int>> deleteSentence(Database db, int sentenceId) async {
  // Delete connected edges
  final edgeRows = await db.rawQuery(
    'SELECT id FROM edges WHERE sentence_id=?',
    [sentenceId],
  );
  final edgeIds = edgeRows.map((r) => r['id'] as int).toList();
  var edgesDeleted = 0;
  if (edgeIds.isNotEmpty) {
    final ph = List.filled(edgeIds.length, '?').join(',');
    edgesDeleted = await db.rawDelete(
      'DELETE FROM edges WHERE id IN ($ph)',
      edgeIds,
    );
  }

  // Delete sentence (orphan nodes preserved)
  await db.delete('sentences', where: 'id=?', whereArgs: [sentenceId]);

  return {'edges_deleted': edgesDeleted, 'sentence_deleted': 1};
}

Future<SaveResult> updateSentence(
  Database db,
  InferenceEngine? engine,
  int sentenceId,
  String newText, {
  bool useLlm = true,
}) async {
  // Delete old edges
  await db.delete('edges', where: 'sentence_id=?', whereArgs: [sentenceId]);
  // Update sentence text
  await db.update(
    'sentences',
    {'text': newText},
    where: 'id=?',
    whereArgs: [sentenceId],
  );
  // Re-extract
  return save(db, engine, newText, useLlm: useLlm);
}

/// Save assistant response (no graph extraction).
Future<int> saveResponse(Database db, String text) async {
  return insertSentence(db, text, role: 'assistant');
}

/// Synapse save pipeline — port of engine/save.py (v15).
///
/// Flow:
///   input text
///   → sentences insert (post_id/position 지원)
///   → LLM preprocess: pronoun/date substitution
///   → LLM extract: nodes + categories + deactivate (v15: edges 필드 폐기)
///   → negation post-processing
///   → typo correction
///   → DB save: nodes + node_mentions(문장 바구니 멤버십) + node_categories
///   → LLM alias suggestion (new nodes only)
/// v15: edges 테이블 없음. 연결은 공출현으로 창발.

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
// v15: _deactivateEdge / _deactivateBySentenceIds 제거 — edges 테이블 폐기.
// deactivate 의미 재설계는 Task 6B 재학습과 함께 추후 포팅.

Future<void> _registerFirstPersonAliases(Database db, int nodeId) async {
  for (final alias in _firstPersonAliases) {
    await db.insert(
      'aliases',
      {'alias': alias, 'node_id': nodeId, 'origin': 'rule'},
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

    // Negation post-processing
    final (negNodes, negEdges) = postprocessNegation(extNodes, extEdges);
    extNodes = negNodes;
    extEdges = negEdges;

    // Typo correction (v15: edges 참조 없이 노드 리스트만 보정)
    if (extNodes.isNotEmpty || extEdges.isNotEmpty) {
      final existingEdgeCounts = await _getExistingNodeEdgeCounts(db);
      final corrections = correctTypos(extNodes, existingEdgeCounts);
      for (final (orig, corrected) in corrections) {
        for (final e in extEdges) {
          if (e['source'] == orig) e['source'] = corrected;
          if (e['target'] == orig) e['target'] = corrected;
        }
      }
    }

    // v15: deactivate 축소 — sentence_id 식별자만 수집 (의미 재설계 대기)
    if (extDeactivate.isNotEmpty) {
      final sids = extDeactivate.whereType<int>().toList();
      result.nodesDeactivated
          .addAll(sids.map((s) => 'sentence#$s'));
    }

    // v15: retention 폐기, UPDATE 없음

    if (extNodes.isEmpty) continue;

    // Override category from heading path
    if (categoryPath != null) {
      for (final node in extNodes) {
        node['category'] = categoryPath;
      }
    }

    // Upsert nodes + node_mentions (v15: 문장 바구니 멤버십)
    await _upsertNodesAndMentions(
      db, extNodes, sid, categoryPath, result,
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

  // Negation post-processing
  final (negNodes, negEdges) = postprocessNegation(extNodes, extEdges);
  extNodes = negNodes;
  extEdges = negEdges;

  // Typo correction (v15)
  if (extNodes.isNotEmpty || extEdges.isNotEmpty) {
    final existingEdgeCounts = await _getExistingNodeEdgeCounts(db);
    final corrections = correctTypos(extNodes, existingEdgeCounts);
    for (final (orig, corrected) in corrections) {
      for (final e in extEdges) {
        if (e['source'] == orig) e['source'] = corrected;
        if (e['target'] == orig) e['target'] = corrected;
      }
    }
  }

  // v15: deactivate 축소
  if (extDeactivate.isNotEmpty) {
    final sids = extDeactivate.whereType<int>().toList();
    result.nodesDeactivated
        .addAll(sids.map((s) => 'sentence#$s'));
  }

  // v15: retention 폐기, UPDATE 없음

  if (extNodes.isEmpty) return;

  // Upsert nodes + node_mentions (v15)
  final sentenceId = sentenceIds.isNotEmpty ? sentenceIds.first : null;
  await _upsertNodesAndMentions(
    db, extNodes, sentenceId, null, result,
  );

  // Alias suggestion
  if (useLlm && engine != null && result.nodesAdded.isNotEmpty) {
    await _suggestAliases(db, engine, result);
  }
}

// ── Shared helpers ───────────────────────────────────────

/// v15: 노드별 사용 빈도 맵 (오타 교정 우선순위용). edges 폐기로 단순 count는 0으로 고정.
/// node_mentions 포팅 후 공출현 횟수로 재정의 예정.
Future<Map<String, int>> _getExistingNodeEdgeCounts(Database db) async {
  final result = <String, int>{};
  final rows = await db.rawQuery(
    "SELECT name FROM nodes WHERE status='active'",
  );
  for (final r in rows) {
    result[(r['name'] as String).toLowerCase()] = 0;
  }
  final aliasRows = await db.rawQuery(
    "SELECT a.alias FROM aliases a JOIN nodes n ON n.id = a.node_id "
    "WHERE n.status='active'",
  );
  for (final r in aliasRows) {
    result[(r['alias'] as String).toLowerCase()] = 0;
  }
  return result;
}

/// v15: node 저장 + node_mentions INSERT로 문장 바구니 멤버십 기록.
/// 엣지 INSERT 없음 — 공출현으로 연결 창발.
Future<void> _upsertNodesAndMentions(
  Database db,
  List<Map<String, dynamic>> extNodes,
  int? sentenceId,
  String? categoryPath,
  SaveResult result,
) async {
  for (final node in extNodes) {
    final name = node['name'] as String;
    final cat = node['category'] as String?;
    final (nid, isNew) = await upsertNode(db, name);

    // heading 경로는 origin='user', LLM 추론 카테고리는 origin='ai'
    final origin = (cat == categoryPath) ? 'user' : 'ai';
    await addNodeCategory(db, nid, cat, origin: origin);

    // 문장 바구니 멤버십 (v15 핵심)
    if (sentenceId != null) {
      final added = await addNodeMention(db, nid, sentenceId);
      if (added) result.mentionsAdded += 1;
    }

    if (isNew) {
      result.nodesAdded.add(name);
      result.nodeIdsAdded.add(nid);
      if (name == '나') await _registerFirstPersonAliases(db, nid);
    }
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
      }
    } catch (_) {
      continue;
    }
  }
}

// ── Rollback ─────────────────────────────────────────────

/// v15: sentence 단위 롤백 + 고아 노드 정리.
Future<Map<String, int>> rollback(
  Database db,
  List<int> sentenceIds, {
  List<int>? nodeIds,
}) async {
  var sentencesDeleted = 0;
  var nodesDeleted = 0;

  if (sentenceIds.isNotEmpty) {
    final ph = List.filled(sentenceIds.length, '?').join(',');
    sentencesDeleted = await db.rawDelete(
      'DELETE FROM sentences WHERE id IN ($ph)',
      sentenceIds,
    );
  }

  if (nodeIds != null && nodeIds.isNotEmpty) {
    final ph = List.filled(nodeIds.length, '?').join(',');
    // db.dart에 node_mentions 테이블이 포팅될 때까지 단순 삭제만 수행 (공출현 참조 검사 생략)
    final orphans = await db.rawQuery(
      'SELECT id FROM nodes WHERE id IN ($ph)',
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

  return {'sentences_deleted': sentencesDeleted, 'nodes_deleted': nodesDeleted};
}

// ── Delete/update sentence ──────────────────────────────

/// v15: sentence 삭제. edges 테이블 없음. node_mentions 포팅 후 CASCADE로 처리 예정.
Future<Map<String, int>> deleteSentence(Database db, int sentenceId) async {
  await db.delete('sentences', where: 'id=?', whereArgs: [sentenceId]);
  return {'sentence_deleted': 1};
}

Future<SaveResult> updateSentence(
  Database db,
  InferenceEngine? engine,
  int sentenceId,
  String newText, {
  bool useLlm = true,
}) async {
  // v15: edges 테이블 없음. node_mentions 정리는 포팅 후 추가.
  await db.update(
    'sentences',
    {'text': newText},
    where: 'id=?',
    whereArgs: [sentenceId],
  );
  return save(db, engine, newText, useLlm: useLlm);
}

/// Save assistant response (no graph extraction).
Future<int> saveResponse(Database db, String text) async {
  return insertSentence(db, text, role: 'assistant');
}

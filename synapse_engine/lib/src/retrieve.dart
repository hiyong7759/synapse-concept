/// Synapse retrieve pipeline — port of engine/retrieve.py.
///
/// Flow:
///   question
///   → LLM expand: keyword candidates
///   → DB match: aliases → name → substring
///   → BFS loop: get_triples → LLM filter → expand
///   → category supplement: adjacent subcategories
///   → LLM answer

import 'package:sqflite/sqflite.dart';

import 'inference.dart';
import 'models/retrieve_result.dart';
import 'models/triple.dart';

// ── Adjacent pairs (from retrieve.py) ────────────────────

const _adjacentPairs = <(String, String)>[
  ('BOD.disease', 'MND.mental'),
  ('BOD.sleep', 'MND.mental'),
  ('BOD.sleep', 'MND.coping'),
  ('BOD.exercise', 'HOB.sport'),
  ('BOD.nutrition', 'FOD.ingredient'),
  ('BOD.nutrition', 'FOD.product'),
  ('BOD.medical', 'MON.insurance'),
  ('MND.emotion', 'REL.romance'),
  ('MND.emotion', 'REL.conflict'),
  ('MND.motivation', 'WRK.jobchange'),
  ('MND.motivation', 'EDU.online'),
  ('MND.coping', 'HOB.sport'),
  ('MND.coping', 'HOB.outdoor'),
  ('MND.coping', 'REG.practice'),
  ('HOB.sing', 'CUL.music'),
  ('HOB.outdoor', 'TRV.domestic'),
  ('HOB.outdoor', 'NAT.terrain'),
  ('HOB.outdoor', 'NAT.weather'),
  ('HOB.game', 'TEC.sw'),
  ('HOB.game', 'TEC.hw'),
  ('HOB.craft', 'LIV.supply'),
  ('HOB.collect', 'CUL.art'),
  ('HOB.collect', 'MON.spending'),
  ('HOB.social', 'REL.comm'),
  ('HOB.social', 'TRV.place'),
  ('CUL.book', 'EDU.reading'),
  ('CUL.book', 'EDU.academic'),
  ('CUL.media', 'TEC.sw'),
  ('CUL.show', 'TRV.place'),
  ('WRK.workplace', 'PER.colleague'),
  ('WRK.workplace', 'MON.income'),
  ('WRK.workplace', 'LAW.rights'),
  ('WRK.jobchange', 'MON.income'),
  ('WRK.cert', 'EDU.exam'),
  ('WRK.cert', 'EDU.online'),
  ('WRK.business', 'MON.income'),
  ('WRK.business', 'LAW.contract'),
  ('WRK.tool', 'TEC.sw'),
  ('WRK.tool', 'TEC.ai'),
  ('MON.income', 'LAW.tax'),
  ('MON.payment', 'LAW.tax'),
  ('MON.loan', 'LIV.housing'),
  ('MON.loan', 'LAW.contract'),
  ('MON.insurance', 'LAW.contract'),
  ('MON.invest', 'SOC.economy'),
  ('LAW.contract', 'LIV.housing'),
  ('LAW.rights', 'TEC.security'),
  ('LAW.statute', 'WRK.workplace'),
  ('LAW.admin', 'LIV.moving'),
  ('EDU.school', 'WRK.cert'),
  ('EDU.online', 'TEC.sw'),
  ('EDU.language', 'TRV.abroad'),
  ('TRV.domestic', 'FOD.restaurant'),
  ('TRV.domestic', 'HOB.outdoor'),
  ('TRV.domestic', 'NAT.weather'),
  ('TRV.abroad', 'FOD.restaurant'),
  ('TRV.abroad', 'SOC.international'),
  ('TRV.place', 'NAT.terrain'),
  ('NAT.animal', 'LIV.supply'),
  ('NAT.ecology', 'SOC.issue'),
  ('LIV.housing', 'MON.loan'),
  ('LIV.housing', 'LAW.contract'),
  ('LIV.appliance', 'TEC.hw'),
  ('LIV.appliance', 'TEC.sw'),
  ('LIV.moving', 'TRV.place'),
  ('TEC.ai', 'SOC.issue'),
  ('PER.colleague', 'WRK.workplace'),
  ('PER.org', 'WRK.workplace'),
  ('PER.family', 'REL.romance'),
  ('PER.friend', 'REL.comm'),
  ('REL.conflict', 'WRK.workplace'),
  ('REL.online', 'SOC.issue'),
  ('SOC.international', 'TRV.abroad'),
  ('SOC.politics', 'LAW.statute'),
  ('REG.practice', 'MND.coping'),
];

Map<String, List<String>> _buildAdjacentMap() {
  final result = <String, List<String>>{};
  for (final (a, b) in _adjacentPairs) {
    result.putIfAbsent(a, () => []).add(b);
    result.putIfAbsent(b, () => []).add(a);
  }
  return result;
}

final _defaultAdjacentMap = _buildAdjacentMap();

// ── DB helpers ───────────────────────────────────────────

Future<Map<String, int>> _matchStartNodes(
  Database db,
  List<String> keywords, {
  String question = '',
}) async {
  final matched = <String, int>{};
  final aliasResolvedNames = <String>{};

  // 0. Scan all aliases against question string
  if (question.isNotEmpty) {
    final rows = await db.rawQuery(
      "SELECT a.alias, n.id, n.name FROM aliases a "
      "JOIN nodes n ON n.id = a.node_id WHERE n.status = 'active'",
    );
    for (final r in rows) {
      final alias = r['alias'] as String;
      if (question.contains(alias)) {
        final name = r['name'] as String;
        final id = r['id'] as int;
        matched['$name#$id'] = id;
        aliasResolvedNames.add(name);
      }
    }
  }

  for (final kw in keywords) {
    // 1. Alias exact match
    if (!aliasResolvedNames.contains(kw)) {
      final row = await db.rawQuery(
        '''SELECT n.id, n.name FROM aliases a
           JOIN nodes n ON n.id = a.node_id
           WHERE a.alias = ? AND n.status = 'active' ''',
        [kw],
      );
      if (row.isNotEmpty) {
        final name = row.first['name'] as String;
        final id = row.first['id'] as int;
        matched['$name#$id'] = id;
        aliasResolvedNames.add(name);
        continue;
      }
    }

    // 2. Name exact match
    if (aliasResolvedNames.contains(kw)) continue;
    final nameRows = await db.rawQuery(
      "SELECT id, name FROM nodes WHERE name = ? AND status = 'active'",
      [kw],
    );
    if (nameRows.isNotEmpty) {
      for (final r in nameRows) {
        final id = r['id'] as int;
        if (!matched.containsValue(id)) {
          matched['${r['name']}#$id'] = id;
        }
      }
      continue;
    }

    // 3. Substring match
    final subRows = await db.rawQuery(
      "SELECT id, name FROM nodes WHERE name LIKE ? AND status = 'active' LIMIT 5",
      ['%$kw%'],
    );
    for (final r in subRows) {
      final name = r['name'] as String;
      final id = r['id'] as int;
      if (!aliasResolvedNames.contains(name) && !matched.containsValue(id)) {
        matched['$name#$id'] = id;
      }
    }
  }

  return matched;
}

/// v15: 같은 sentence 바구니 공출현 페어를 Triple(label=null)로 반환.
/// node_mentions JOIN으로 구한다.
Future<List<Triple>> _getTriples(Database db, Set<int> nodeIds) async {
  if (nodeIds.isEmpty) return [];
  final ph = List.filled(nodeIds.length, '?').join(',');
  final ids = nodeIds.toList();

  // 주어진 노드가 속한 sentence의 모든 공출현 페어를 조회.
  // m1.node_id < m2.node_id로 중복 페어 제거.
  final rows = await db.rawQuery(
    '''SELECT n1.id AS src_id, n1.name AS src,
              n2.id AS tgt_id, n2.name AS tgt,
              s.id AS sentence_id, s.text AS sentence_text
       FROM node_mentions m1
       JOIN node_mentions m2
            ON m1.sentence_id = m2.sentence_id AND m1.node_id < m2.node_id
       JOIN nodes n1 ON n1.id = m1.node_id
       JOIN nodes n2 ON n2.id = m2.node_id
       JOIN sentences s ON s.id = m1.sentence_id
       WHERE (m1.node_id IN ($ph) OR m2.node_id IN ($ph))
         AND n1.status='active' AND n2.status='active'
       ORDER BY s.created_at DESC
       LIMIT 200''',
    [...ids, ...ids],
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

Future<Set<int>> _getCategorySupplementNodes(
  Database db,
  Set<int> startNodeIds,
  Set<int> visitedIds, {
  Map<String, List<String>>? adjacencyMap,
}) async {
  if (startNodeIds.isEmpty) return {};

  final adjMap = adjacencyMap ?? _defaultAdjacentMap;
  final ph = List.filled(startNodeIds.length, '?').join(',');
  final rows = await db.rawQuery(
    'SELECT nc.category FROM node_categories nc WHERE nc.node_id IN ($ph)',
    startNodeIds.toList(),
  );

  // Only standard categories (3-letter uppercase + dot)
  final subcats = rows
      .map((r) => r['category'] as String)
      .where((c) => RegExp(r'^[A-Z]{3}\.').hasMatch(c))
      .toSet();
  if (subcats.isEmpty) return {};

  final adjacent = <String>{};
  for (final sub in subcats) {
    adjacent.addAll(adjMap[sub] ?? []);
  }
  adjacent.removeAll(subcats);
  if (adjacent.isEmpty) return {};

  final result = <int>{};
  for (final sub in adjacent) {
    final catRows = await db.rawQuery(
      "SELECT nc.node_id FROM node_categories nc "
      "JOIN nodes n ON n.id = nc.node_id "
      "WHERE nc.category = ? AND n.status='active' LIMIT 20",
      [sub],
    );
    for (final r in catRows) {
      final id = r['node_id'] as int;
      if (!visitedIds.contains(id)) result.add(id);
    }
  }
  return result;
}

// ── Main retrieve function ───────────────────────────────

Future<RetrieveResult> retrieve(
  Database db,
  InferenceEngine? engine,
  String question, {
  bool useLlm = true,
  int maxLayers = 5,
  Map<String, List<String>>? adjacencyMap,
}) async {
  final result = RetrieveResult();

  // 1. Keyword expansion
  List<String> keywords;
  if (useLlm && engine != null) {
    keywords = await retrieveExpand(engine, question);
  } else {
    keywords = question.split(' ');
  }

  // Merge raw tokens
  final rawTokens = question.split(' ');
  keywords = {...keywords, ...rawTokens}.toList();

  final startNodes = await _matchStartNodes(db, keywords, question: question);
  if (startNodes.isEmpty) {
    result.answer = '관련 정보를 찾을 수 없습니다.';
    return result;
  }

  result.startNodes.addAll(startNodes.keys);

  // 2. BFS (v15: _getTriples가 빈 리스트 반환 → BFS는 node_mentions 포팅 후 복원 예정)
  final visitedNodeIds = <int>{...startNodes.values};
  final contextTriples = <Triple>[];
  var currentNodeIds = Set<int>.from(startNodes.values);

  for (var layer = 0; layer < maxLayers; layer++) {
    final layerTriples = await _getTriples(db, currentNodeIds);
    if (layerTriples.isEmpty) break;

    List<Triple> filtered;
    if (useLlm && engine != null) {
      filtered = [];
      for (final t in layerTriples) {
        final text = t.sentenceText ?? t.toString();
        if (await retrieveFilterSentence(engine, question, text)) {
          filtered.add(t);
        }
      }
    } else {
      filtered = layerTriples;
    }

    contextTriples.addAll(filtered);

    final newIds = <int>{};
    for (final t in filtered) {
      newIds.add(t.srcId);
      newIds.add(t.tgtId);
    }
    newIds.removeAll(visitedNodeIds);
    if (newIds.isEmpty) break;
    visitedNodeIds.addAll(newIds);
    currentNodeIds = newIds;
  }

  // 3. Category supplement (v15: node_mentions 포팅 후 활성화 예정)
  if (useLlm && engine != null) {
    final catNodeIds = await _getCategorySupplementNodes(
      db,
      Set.from(startNodes.values),
      visitedNodeIds,
      adjacencyMap: adjacencyMap,
    );
    if (catNodeIds.isNotEmpty) {
      final catTriples = await _getTriples(db, catNodeIds);
      for (final t in catTriples) {
        final text = t.sentenceText ?? t.toString();
        if (await retrieveFilterSentence(engine, question, text)) {
          contextTriples.add(t);
        }
      }
    }
  }

  result.contextTriples.addAll(contextTriples);

  // 4. LLM answer
  if (useLlm && engine != null) {
    final seen = <String>{};
    final lines = <String>[];
    for (final t in contextTriples) {
      final txt = t.sentenceText ?? t.toString();
      if (seen.add(txt)) lines.add('- $txt');
    }
    final context = lines.join('\n');
    final userMsg = '알려진 사실:\n$context\n\n질문: $question';
    try {
      result.answer = await engine.chat(
        systemChat,
        userMsg,
        temperature: 0.3,
        maxTokens: 4096,
      );
    } catch (_) {
      result.answer = '[추론 실패] 인출된 문장 ${lines.length}개:\n$context';
    }
  } else {
    result.answer = contextTriples.isEmpty
        ? '관련 정보 없음'
        : contextTriples.map((t) => t.toString()).join('\n');
  }

  return result;
}

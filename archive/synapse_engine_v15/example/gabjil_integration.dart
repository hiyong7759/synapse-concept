/// gabjil integration example.
///
/// Shows how to:
///   1. Init engine with system categories (BFS) + user-defined categories (hierarchical)
///   2. Store structured character data via markdown
///   3. Process conversational venting
///   4. Detect recurring complaints → suggest character creation
///   5. Build character sheets combining both category types
///   6. Pipeline hooks for auto-tagging

import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/llamadart_backend.dart';

// ── System categories (BFS adjacency routing) ────────────

final gabjilCategories = CategoryMap({
  'CHR': Category('CHR', '인물', ['boss', 'coworker', 'friend', 'family']),
  'EPI': Category('EPI', '에피소드', ['conflict', 'gossip', 'praise', 'unfair']),
  'EMO': Category('EMO', '감정', ['anger', 'sad', 'frustration', 'relief']),
  'WKP': Category('WKP', '직장상황', ['meeting', 'overtime', 'review', 'order']),
  'TRT': Category('TRT', '특성', ['trait', 'habit', 'weakness', 'strength']),
});

final gabjilAdjacency = AdjacencyMap({
  'CHR.boss': ['EPI.conflict', 'EPI.unfair', 'EMO.anger', 'TRT.trait'],
  'CHR.coworker': ['EPI.gossip', 'EMO.frustration', 'TRT.habit'],
  'EPI.conflict': ['CHR.boss', 'CHR.coworker', 'EMO.anger'],
  'EPI.unfair': ['CHR.boss', 'EMO.frustration', 'WKP.order'],
  'EMO.anger': ['EPI.conflict', 'EPI.unfair', 'CHR.boss'],
  'WKP.overtime': ['EMO.frustration', 'CHR.boss'],
});

// ── Known persons DB (gabjil app side) ───────────────────

final _knownPersons = <String, String>{}; // name → role
final _complaintCount = <String, int>{};

// ── Event handlers ───────────────────────────────────────

/// v15: TripleAddedEvent → SentenceCommittedEvent. 문장 바구니에 타겟 인물이
/// 포함됐는지 확인하는 방식으로 변경.
void _onSentenceCommitted(SentenceCommittedEvent event) {
  for (final name in event.mentionedNodeNames) {
    if (name == '나') continue;
    _complaintCount[name] = (_complaintCount[name] ?? 0) + 1;
    if (_complaintCount[name] == 3) {
      print('  >> "$name" 불만 3회 누적! 캐릭터 생성 제안');
    }
  }
}

// ── Main ─────────────────────────────────────────────────

Future<void> main() async {
  // 1. Init engine with both category systems
  final engine = await SynapseEngine.create(
    EngineConfig(
      dataDir: '/tmp/gabjil_test',
      modelPath: '/Volumes/macex/models/gemma-4-E2B-it-Q4_K_M.gguf',
      adapterDir: '/Volumes/macex/workspace/claude-agentic-subagent-team/projects/synapse/archive/finetune/models/gguf',
      categories: gabjilCategories,
      adjacency: gabjilAdjacency,
      // Pipeline hook: auto-tag person nodes with hierarchical category
      onAfterExtract: (raw) async {
        for (final node in (raw['nodes'] as List)) {
          final name = node['name'] as String;
          final role = _knownPersons[name];
          if (role != null) {
            node['category'] = '인물.$role.$name';
          }
        }
        return raw;
      },
      // Customize AI friend persona
      onBuildChatPrompt: (defaultPrompt, context) {
        return '당신은 사용자의 찐친입니다. 직장 불만을 들어주고 격하게 공감해주세요.\n'
            '격하게 공감하되, 건설적인 조언도 한마디 해주세요.\n'
            '$defaultPrompt';
      },
    ),
    backend: LlamadartInferenceBackend(),
  );

  engine.onSentenceCommitted.listen(_onSentenceCommitted);
  engine.onNodeCreated.listen((e) {
    final cats = e.categories?.join(',') ?? '?';
    print('  [node] ${e.name} ($cats)');
  });

  // ── 2. Store structured character data (markdown) ──────

  print('=== Structured data via markdown ===');
  _knownPersons['김부장'] = '상사';

  await engine.ingest('''
# 인물.상사.김부장
## 약점
- 소심하다
- 윗사람 앞에서 꼬리 내린다
## 습관
- 퇴근 10분 전에 일 시킨다
- 회의에서 남 탓만 한다
''');
  print('  Structured data stored.');

  // ── 3. Conversational venting (natural language) ────────

  print('\n=== Conversational input ===');
  final messages = [
    '김부장이 또 야근시켰어',
    '김부장 진짜 짜증나 맨날 일 떠넘겨',
    '오늘도 김부장 때문에 회의에서 깨졌어',
  ];

  for (final msg in messages) {
    print('\nUser: $msg');
    final result = await engine.process(msg);
    print('  Nodes: ${result.saveResult.nodesAdded}');
    print('  Answer: ${result.retrieveResult.answer}');
  }

  // ── 4. Character sheet — both category types combined ──

  print('\n=== Character Sheet: 김부장 ===');

  // Structured data (markdown-entered, user-defined category)
  final weaknesses = await engine.query(HypergraphQuery(
    category: '인물.상사.김부장.약점',
  ));
  print('  Weaknesses (structured):');
  for (final t in weaknesses) {
    print('    $t');
  }

  final habits = await engine.query(HypergraphQuery(
    category: '인물.상사.김부장.습관',
  ));
  print('  Habits (structured):');
  for (final t in habits) {
    print('    $t');
  }

  // All edges (from conversation + structured)
  final allTriples = await engine.query(HypergraphQuery(nodeName: '김부장'));
  print('  All co-occurrences: ${allTriples.length}');

  // Recent episodes
  final recent = await engine.query(HypergraphQuery(
    nodeName: '김부장',
    lastDuration: Duration(days: 7),
  ));
  print('  Recent 7 days: ${recent.length} co-occurrences');

  // ── 5. Stats ───────────────────────────────────────────

  final stats = await engine.getStats();
  print('\n=== Stats ===');
  print('  Nodes: ${stats.nodesTotal} (active: ${stats.nodesActive})');
  print('  Categories: ${stats.categoriesTotal}');
  print('  Sentences: ${stats.sentencesTotal}');

  await engine.dispose();
}

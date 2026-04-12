# synapse_engine

On-device knowledge graph engine. LLM-powered extraction + BFS retrieval, fully offline.

## What it does

Text in → structured knowledge graph out. No server, no internet.

```
"나 쿠팡에서 물류 기획 담당하고 있어"
  → nodes: [나, 쿠팡, 물류, 기획]
  → edges: [나 ─(에서)→ 쿠팡, 나 ─(으로)→ 물류, ...]
  → categories: 쿠팡→[WRK.workplace], 물류→[WRK.role], ...
  (node_categories table — each node can have multiple categories)
```

Later, ask a question → BFS traversal finds related context → LLM answers from your personal graph.

## Quick Start

### 1. Add dependency

```yaml
# pubspec.yaml
dependencies:
  synapse_engine:
    path: ../synapse_engine  # or pub.dev when published
```

### 2. Initialize

```dart
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/llamadart_backend.dart';

final engine = await SynapseEngine.create(
  EngineConfig(
    dataDir: '/path/to/app/data',        // SQLite DB location
    modelPath: '/path/to/gemma-4-e2b.gguf',  // Base GGUF model
    adapterDir: '/path/to/adapters/',    // LoRA adapter directory
  ),
  backend: LlamadartInferenceBackend(),
);
```

### 3. Use

```dart
// Full pipeline: retrieve context → save to graph → generate answer
final result = await engine.process('나 스타벅스 안 좋아해');
print(result.saveResult.nodesAdded);      // [나, 스타벅스, 안, 좋아]
print(result.retrieveResult.answer);      // Context-aware response

// Save only (no answer generation)
final saved = await engine.ingest('허리디스크 L4-L5 진단받았어');

// Query only
final answer = await engine.retrieve('허리는 어때?');
print(answer.answer);

// Direct graph query
final triples = await engine.query(GraphQuery(
  nodeName: '스타벅스',
  lastDuration: Duration(days: 7),
));

// Cleanup
await engine.dispose();
```

## API Reference

### Core Pipeline

| Method | Description |
|--------|-------------|
| `process(text)` | Full pipeline: retrieve + save + answer |
| `ingest(text)` | Save only (no retrieve/answer) |
| `retrieve(query)` | Retrieve + answer only (no save) |
| `query(GraphQuery)` | Direct graph query (no LLM) |

### Graph Management

| Method | Description |
|--------|-------------|
| `addAlias(alias, nodeName)` | Register alias (e.g., "스벅" → "스타벅스") |
| `removeAlias(alias)` | Remove alias |
| `splitNode(nodeId, spec)` | Split homonym node |
| `deleteSentence(id)` | Delete sentence + connected edges |
| `updateSentence(id, text)` | Update sentence, re-extract |
| `rollback(edgeIds)` | Undo saved edges/nodes |
| `getStats()` | DB statistics |

### Event Streams

```dart
engine.onTripleAdded.listen((event) {
  print('New: ${event.triple}');
});

engine.onEdgeDeactivated.listen((event) {
  print('Deactivated: ${event.triple}');
});

engine.onNodeCreated.listen((event) {
  print('Node: ${event.name} (${event.category})');  // category assigned at creation time
});
```

### Custom Adapters

```dart
// Load domain-specific adapter at runtime
await engine.loadAdapter(AdapterSpec(
  name: 'my-extract',
  path: 'assets/adapters/my-extract.gguf',
  systemPrompt: mySystemPrompt,
  maxTokens: 512,
));

// Run custom adapter directly
final result = await engine.runAdapter('my-extract', inputText);
```

## Category System

Two independent category mechanisms:

### 1. System Categories (CategoryMap) — BFS routing

3-letter code + subcategory. Used by BFS to find related nodes when the graph is disconnected.

```
CHR.boss, EPI.conflict, EMO.anger   ← code-based, for adjacency routing
```

These are set via `EngineConfig` and define which categories are "adjacent" in BFS traversal.
Default: 17 Synapse categories (PER, BOD, MND, ...). Replaceable per app.

### 2. User-Defined Categories — hierarchical free-text paths

Unlimited depth, any language. Stored in the `node_categories` table (many-to-many).
A single node can have multiple categories — both system and user-defined.
Created via markdown headings or `ingest()` with structured input.

```
인물.상사.김부장.약점        ← hierarchical path, free-text
인물.동료.이대리.습관
에피소드.갑질.야근강요
```

These are **not** used for BFS adjacency — they're tags for organizing and querying.

### How they coexist

A single node can hold both types simultaneously via `node_categories` (many-to-many):

```dart
// "김부장" node has categories: [CHR.boss, 인물.상사.김부장]
// System category: BFS knows CHR.boss is adjacent to EPI.conflict
// User category: "인물.상사.김부장" tags structured data

// When you query by user category:
final traits = await engine.query(GraphQuery(
  category: '인물.상사.김부장.약점',
));

// When BFS runs, it uses system adjacency from ALL categories on the node:
// searching "김부장" → finds CHR.boss → supplements with EPI.conflict nodes
```

## Integration Guide: gabjil

### Step 1: Categories — System + User-Defined

```dart
// (A) System categories: define BFS adjacency for gabjil's domain
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

final engine = await SynapseEngine.create(EngineConfig(
  dataDir: appDocDir.path,
  modelPath: modelPath,
  adapterDir: adapterDir,
  categories: gabjilCategories,
  adjacency: gabjilAdjacency,
));
```

```dart
// (B) User-defined categories: store structured data via markdown
// Markdown headings become category paths on all nodes underneath.

await engine.ingest('''
# 인물.상사.김부장
## 약점
- 소심하다
- 윗사람 앞에서 꼬리 내린다
## 습관
- 퇴근 10분 전에 일 시킨다
- 회의에서 남 탓만 한다
''');
// Result (node_categories table, many-to-many):
//   노드 "소심하다"  → categories: ["인물.상사.김부장.약점"]
//   노드 "꼬리"      → categories: ["인물.상사.김부장.약점"]
//   노드 "퇴근"      → categories: ["인물.상사.김부장.습관"]
//   Same node can accumulate categories from different inputs.

// Query all of Kim's weaknesses:
final weaknesses = await engine.query(GraphQuery(
  category: '인물.상사.김부장.약점',
));

// Query everything about Kim:
final allAboutKim = await engine.query(GraphQuery(
  nodeName: '김부장',
));
```

### Step 2: Conversational Input (no markdown needed)

Normal chat messages go through the standard pipeline — LLM extracts nodes/edges automatically:

```dart
// User venting in chat — no markdown, just natural language
await engine.process('김부장이 또 야근시켰어');
// → nodes: [김부장, 야근], edges: [김부장 → 야근]
// → categories added: 김부장→WRK.overtime (accumulates with existing categories)

await engine.process('김부장 진짜 짜증나 맨날 일 떠넘겨');
// → nodes: [김부장, 짜증, 일], edges: [김부장 → 짜증, 김부장 → 일]
// → 김부장 now has categories: [CHR.boss, 인물.상사.김부장, WRK.overtime, ...]
```

### Step 3: Event-Driven Character Detection

```dart
final complaintCount = <String, int>{};

engine.onTripleAdded.listen((event) {
  final src = event.triple.src;
  if (src == '나') return;

  complaintCount[src] = (complaintCount[src] ?? 0) + 1;

  if (complaintCount[src] == 3) {
    suggestCharacterCreation(src);
  }
});
```

### Step 4: Character Sheet — Combine Both Category Types

```dart
Future<CharacterSheet> buildCharacterSheet(String personName) async {
  // All edges connected to this person
  final allTriples = await engine.query(GraphQuery(nodeName: personName));

  // Structured data (markdown-entered)
  final weaknesses = await engine.query(GraphQuery(
    category: '인물.상사.$personName.약점',
  ));
  final habits = await engine.query(GraphQuery(
    category: '인물.상사.$personName.습관',
  ));

  // Recent episodes (last 7 days, system category)
  final recentEpisodes = await engine.query(GraphQuery(
    nodeName: personName,
    lastDuration: Duration(days: 7),
  ));

  return CharacterSheet(
    name: personName,
    weaknesses: weaknesses,
    habits: habits,
    recentEpisodes: recentEpisodes,
    totalEdges: allTriples.length,
  );
}
```

### Step 5: Pipeline Hooks

```dart
final engine = await SynapseEngine.create(EngineConfig(
  // ...
  onAfterExtract: (raw) async {
    // Auto-tag person nodes with user-defined category (additive)
    for (final node in raw['nodes']) {
      final name = node['name'] as String;
      if (await isKnownPerson(name)) {
        final role = await getPersonRole(name); // "상사", "동료", etc.
        // categories accumulate — LLM category + hook category both saved
        node['categories'] = [
          if (node['category'] != null) node['category'],
          '인물.$role.$name',
        ];
      }
    }
    return raw;
  },
  onBuildChatPrompt: (defaultPrompt, context) {
    return '''당신은 사용자의 찐친입니다. 직장 불만을 들어주고 격하게 공감해주세요.
격하게 공감하되, 건설적인 조언도 한마디 해주세요.
$defaultPrompt''';
  },
));
```

### Step 6: Custom Extract Adapter (Optional)

```dart
await engine.loadAdapter(AdapterSpec(
  name: 'gabjil-extract',
  path: 'assets/adapters/gabjil-extract.gguf',
  systemPrompt: '''발언에서 인물, 에피소드, 감정을 추출하라.
JSON만 출력: {"character_updates": [...], "episode": {...}, "emotion": "..."}''',
  maxTokens: 512,
));

final result = await engine.runAdapter('gabjil-extract', inputText);
```

## Model Setup

### Base Model

Download GGUF base model (~2.9GB):
```bash
# via Python
python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download('unsloth/gemma-4-E2B-it-GGUF', 'gemma-4-E2B-it-Q4_K_M.gguf', local_dir='./models')
"
```

### Adapters

Required adapters (in `adapterDir/`):
- `extract.gguf` — Node/edge/category extraction
- `save-pronoun.gguf` — Pronoun/date resolution
- `retrieve-filter.gguf` — BFS relevance filtering
- `retrieve-expand.gguf` — Query keyword expansion

Each adapter is ~28MB. Base model runs without adapters but with lower quality.

### Converting MLX Adapters to GGUF

If you have MLX-trained adapters:
```bash
python3 scripts/convert_mlx_to_gguf.py --priority \
  --base-model /path/to/google/gemma-4-E2B-it
```

## Architecture

```
┌─────────────────────────────────────────┐
│  Consumer App (gabjil, synapse-app)     │
│  Flutter UI + Domain Logic              │
├─────────────────────────────────────────┤
│  synapse_engine                         │
│  ┌───────────────────────────────────┐  │
│  │ engine.dart — Public API          │  │
│  ├───────────────────────────────────┤  │
│  │ pipeline: retrieve → save → chat  │  │
│  ├──────────┬────────────────────────┤  │
│  │ save.dart│ retrieve.dart          │  │
│  ├──────────┴────────────────────────┤  │
│  │ inference.dart (llamadart)        │  │
│  │ db.dart (sqflite)                 │  │
│  └───────────────────────────────────┘  │
├─────────────────────────────────────────┤
│  llamadart → llama.cpp (C/C++)          │
│  sqflite → SQLite                       │
└─────────────────────────────────────────┘
```

## Testing Without LLM

For unit tests, use `StubInferenceBackend`:

```dart
final engine = await SynapseEngine.create(
  EngineConfig(
    dataDir: '/tmp/test',
    modelPath: '',
    adapterDir: '',
  ),
  // StubInferenceBackend is used by default when no backend specified
);

// Pipeline runs but LLM steps return empty — DB operations still work
final result = await engine.ingest('test text');
```

## Desktop CLI Testing

```bash
cd synapse_engine
dart run example/cli_test.dart /path/to/model.gguf /path/to/adapters/
```

## License

TBD

# Synapse Engine — 범용 온디바이스 지식 하이퍼그래프 패키지 설계

**최종 업데이트**: 2026-04-19 — 엔진 MVP 포팅 기준이 v15 스키마(node_mentions, node_categories, aliases, unresolved_tokens, **edges 테이블 폐기**, retention 폐기)로 확정. 의미 엣지 관련 구현(edge label 추출, edge JOIN 경로)은 모두 제거. 연결은 문장·카테고리·별칭 하이퍼엣지로만 표현. `/review` 런타임 제안 도출기(`suggestions.dart`)가 신규 추가. 자세한 배경은 `docs/DESIGN_PIPELINE.md` 참고.

## Context

Synapse를 모바일 앱이 아닌 **재사용 가능한 엔진 패키지**로 먼저 분리한다.
첫 소비자는 gabjil(찐친 카톡 앱), 두 번째는 Synapse 자체 모바일 앱.
엔진이 범용이어야 도메인 앱들이 `flutter pub add synapse_engine` 한 줄로 붙을 수 있다.

## 1. 패키지 구조

```
synapse_engine/               ← pub.dev 패키지 (또는 private)
├── lib/
│   ├── synapse_engine.dart   ← 단일 진입점. export만
│   ├── src/
│   │   ├── engine.dart       ← SynapseEngine 클래스 (유일한 공개 API)
│   │   ├── db.dart           ← SQLite 스키마 + CRUD (sqflite). v15
│   │   ├── inference.dart    ← llamadart 래퍼. 모델 로딩 + 어댑터 스왑
│   │   ├── save.dart         ← 자동 저장 파이프라인 (sentence + node + node_mentions + unresolved_tokens)
│   │   ├── retrieve.dart     ← BFS 인출 파이프라인 (node_mentions JOIN 기반)
│   │   ├── suggestions.dart  ← /review 런타임 제안 도출기 (쿼리 + LLM 호출, 저장 없음)
│   │   ├── pipeline.dart     ← 오케스트레이터 (retrieve→save→respond)
│   │   ├── typo.dart         ← 자모 거리 오타 의심 쌍 판정 (자동 교정 없음)
│   │   ├── markdown.dart     ← 마크다운 파싱 (heading 경로 + 항목 분리)
│   │   └── models/
│   │       ├── mention.dart          ← Mention(node_id, sentence_id) 모델
│   │       ├── save_result.dart
│   │       ├── retrieve_result.dart
│   │       ├── suggestion.dart       ← /review 섹션별 DTO
│   │       ├── engine_config.dart
│   │       └── engine_event.dart
│   └── src/internal/         ← 소비자에게 비공개
│       ├── regex_patterns.dart ← 날짜/대명사/부정부사 패턴
│       └── thinking_strip.dart ← gemma thinking 블록 제거
├── assets/                   ← 기본 어댑터 (선택적 번들)
├── test/
├── example/
├── pubspec.yaml
└── README.md
```

> v15 기준: **엣지 테이블 자체가 폐기**되어 `negation.dart`, 엣지 자동 생성, 엣지 label 추출 코드 모두 제거. 연결은 ① `node_mentions`(문장 바구니) ② `node_categories`(카테고리 바구니) ③ `aliases`(별칭 바구니) 세 하이퍼엣지로만 표현. 저장 파이프라인의 핵심은 `node_mentions` 채우기. 의미 관계(cause/avoid/similar) 해석은 외부 지능체 몫. `sentences.retention` 컬럼도 v13에서 폐기(모든 sentence 동등 보관).

핵심 원칙: `lib/src/` 아래는 전부 `src/` 내부. 소비자는 `synapse_engine.dart`를 통해서만 접근.

## 2. 공개 API — 6개 메서드 + 이벤트 스트림

```dart
/// 시냅스 온디바이스 지식 하이퍼그래프 엔진.
class SynapseEngine {

  // ── 생성 ──────────────────────────────────────
  /// 엔진 초기화. 모델 로딩 포함.
  static Future<SynapseEngine> create(EngineConfig config);

  /// 엔진 종료. 모델 언로드 + DB 커넥션 해제.
  Future<void> dispose();

  // ── 핵심 파이프라인 ────────────────────────────
  /// 텍스트 입력 → 저장 + 인출 + 응답 (전체 파이프라인).
  /// onProgress로 단계별 진행 콜백.
  Future<PipelineResult> process(
    String text, {
    void Function(PipelineStep step)? onProgress,
  });

  /// 저장만 (인출/응답 없이).
  Future<SaveResult> ingest(String text);

  /// 인출만 (저장 없이). 질문 응답용.
  Future<RetrieveResult> retrieve(String query);

  // ── 하이퍼그래프 직접 쿼리 ────────────────────
  /// 노드 기준 같은 바구니 멤버 조회. 필터 조건 지원.
  Future<List<SentenceContext>> query(HypergraphQuery query);

  // ── 하이퍼그래프 관리 ─────────────────────────
  /// 별칭 등록/삭제.
  Future<void> addAlias(String alias, String nodeName);
  Future<void> removeAlias(String alias);

  /// 노드 분리 (동음이의어).
  Future<void> splitNode(int nodeId, SplitSpec spec);

  /// 문장 삭제 (연결된 node_mentions 삭제, 고아 노드 보존).
  Future<void> deleteSentence(int sentenceId);

  /// 문장 수정 → 기존 node_mentions 삭제 후 재추출.
  Future<SaveResult> updateSentence(int sentenceId, String newText);

  /// 문장/노드 롤백.
  Future<void> rollback({List<int>? sentenceIds, List<int>? nodeIds});

  /// DB 통계.
  Future<EngineStats> getStats();

  // ── 이벤트 스트림 ─────────────────────────────
  /// 문장 커밋 이벤트 (sentence + 연관 node_mentions 한꺼번에).
  Stream<SentenceCommittedEvent> get onSentenceCommitted;

  /// 노드 비활성화 이벤트.
  Stream<NodeDeactivatedEvent> get onNodeDeactivated;

  /// 노드 생성 이벤트.
  Stream<NodeCreatedEvent> get onNodeCreated;
}
```

## 3. 설정 — EngineConfig

```dart
class EngineConfig {
  /// DB 파일 경로.
  final String dataDir;

  /// 베이스 모델 GGUF 경로.
  final String modelPath;

  /// 기본 어댑터 디렉토리 (extract, save-pronoun, retrieve-* 등).
  final String adapterDir;

  /// 커스텀 어댑터 목록 (도메인 앱이 추가 로드).
  final List<AdapterSpec> customAdapters;

  /// 카테고리 맵 (기본: 시냅스 17대분류. 도메인 앱이 교체 가능).
  final CategoryMap categories;

  /// 인접 카테고리 맵 (BFS 보완용. 카테고리와 함께 교체).
  final AdjacencyMap adjacency;

  /// 로케일 (어댑터 세트 전환. 기본: "ko").
  final String locale;

  /// 시스템 프롬프트 오버라이드 (태스크별).
  final Map<String, String>? systemPromptOverrides;

  /// max_tokens 오버라이드 (태스크별).
  final Map<String, int>? maxTokensOverrides;
}
```

### 카테고리 주입 예시

```dart
// 시냅스 기본 (17대분류)
final synapseCategories = CategoryMap.synapse(); // PER, BOD, MND, ...

// gabjil 도메인
final gabjilCategories = CategoryMap({
  'CHR': Category('CHR', '인물', ['boss', 'coworker', 'friend']),
  'EPI': Category('EPI', '에피소드', ['conflict', 'gossip', 'praise']),
  'EMO': Category('EMO', '감정', ['anger', 'sad', 'frustration']),
  'WKP': Category('WKP', '직장상황', ['meeting', 'overtime', 'review']),
  'TRT': Category('TRT', '특성', ['trait', 'habit', 'weakness']),
});

final gabjilAdjacency = AdjacencyMap({
  'CHR.boss': ['EPI.conflict', 'EMO.anger', 'TRT.trait'],
  'CHR.coworker': ['EPI.gossip', 'EMO.frustration'],
  // ...
});

final engine = await SynapseEngine.create(EngineConfig(
  dataDir: appDocDir.path,
  modelPath: 'assets/models/gemma-4-e2b.gguf',
  adapterDir: 'assets/adapters/',
  categories: gabjilCategories,
  adjacency: gabjilAdjacency,
));
```

## 4. 커스텀 어댑터

```dart
class AdapterSpec {
  final String name;       // "gabjil-extract"
  final String path;       // "assets/adapters/gabjil-extract.gguf"
  final String? systemPrompt; // 커스텀 시스템 프롬프트 (null이면 기본)
  final int maxTokens;     // 기본 512
  final double temperature; // 기본 0.0
}
```

어댑터 로드 타이밍:
- **기본 어댑터** (extract, save-pronoun, retrieve-filter, retrieve-expand): `SynapseEngine.create()` 시 등록
- **커스텀 어댑터**: `EngineConfig.customAdapters`로 등록, 또는 런타임에 `engine.loadAdapter()` 호출

```dart
// 런타임 어댑터 추가 로드
await engine.loadAdapter(AdapterSpec(
  name: 'gabjil-extract',
  path: 'assets/adapters/gabjil-extract.gguf',
  systemPrompt: gabjilExtractPrompt,
  maxTokens: 512,
));

// 커스텀 어댑터로 직접 추론
final result = await engine.runAdapter('gabjil-extract', inputText);
```

## 5. 이벤트 스트림

gabjil 같은 앱이 하이퍼그래프 변화를 실시간 구독:

```dart
class SentenceCommittedEvent {
  final int sentenceId;
  final String text;
  final List<int> mentionedNodeIds;   // 이 sentence 바구니의 멤버
  final DateTime timestamp;
}

class NodeDeactivatedEvent {
  final int nodeId;
  final String name;
  final String reason; // "상충" | "수동"
}

class NodeCreatedEvent {
  final String name;
  final List<String>? categories;
  final int nodeId;
}
```

gabjil 사용 예시:
```dart
engine.onSentenceCommitted.listen((event) async {
  // targetPerson 노드가 이 sentence 바구니에 들어갔는지 확인
  if (event.mentionedNodeIds.contains(targetPersonId)) {
    complaintCount++;
    if (complaintCount >= 3) suggestCharacterCreation(targetPersonId);
  }
});
```

## 6. 하이퍼그래프 직접 쿼리

BFS 파이프라인 외에 앱이 직접 하이퍼그래프를 조회:

```dart
class HypergraphQuery {
  final String? nodeName;       // 특정 노드 기준
  final int? nodeId;
  final String? category;       // 카테고리 필터
  final DateRange? dateRange;   // 기간 필터
  final int? limit;             // 최대 결과 수
  final bool includeInactive;   // 비활성 노드 포함 여부
}

// 사용 예: 특정 노드가 속한 문장 바구니들의 sentence 원문 + 같은 바구니 멤버들
final results = await engine.query(HypergraphQuery(
  nodeName: '김부장',
  dateRange: DateRange(last: Duration(days: 7)),
));
```

## 7. 파이프라인 확장 — 훅

소비자 앱이 파이프라인 중간에 개입할 수 있는 훅:

```dart
class EngineConfig {
  // ...

  /// extract 결과를 앱이 후처리할 수 있는 훅.
  /// 반환값이 최종 결과로 사용됨.
  final Future<ExtractResult> Function(ExtractResult raw)? onAfterExtract;

  /// save-pronoun 치환 전에 앱이 자체 치환 규칙 적용.
  final Future<String> Function(String text)? onBeforePronoun;

  /// 인출 결과(sentence 컨텍스트 목록)를 앱이 추가 필터링.
  final Future<List<SentenceContext>> Function(List<SentenceContext> sentences, String query)? onAfterRetrieve;

  /// 응답 생성 전 시스템 프롬프트 커스터마이징.
  final String Function(String defaultSystemPrompt, List<SentenceContext> context)? onBuildChatPrompt;
}
```

gabjil 사용 예시:
```dart
final engine = await SynapseEngine.create(EngineConfig(
  // ...
  onAfterExtract: (raw) async {
    // gabjil: extract 결과에서 인물 노드 감지 → 인물 DB 연동
    for (final node in raw.nodes) {
      if (node.category?.startsWith('CHR') == true) {
        await gabjilCharacterDb.upsert(node.name);
      }
    }
    return raw;
  },
));
```

## 8. 모델/어댑터 번들링 전략

```dart
class ModelManager {
  /// 번들된 모델 사용 (앱 assets에 포함).
  static ModelSource bundled(String assetPath);

  /// 첫 실행 시 다운로드.
  static ModelSource download(String url, {
    void Function(double progress)? onProgress,
  });

  /// 로컬 파일 직접 지정.
  static ModelSource file(String path);
}

// EngineConfig에서 사용
EngineConfig(
  modelSource: ModelManager.download(
    'https://hf.co/ggml-org/gemma-4-E2B-it-GGUF/...',
    onProgress: (p) => setState(() => downloadProgress = p),
  ),
  adapterSource: ModelManager.bundled('assets/synapse-adapters/'),
)
```

어댑터는 작음 (~2-5MB each) → 앱 번들에 포함.
베이스 모델은 큼 (~1.5GB) → 첫 실행 다운로드 권장.

## 9. 레이어 분리

```
┌─────────────────────────────────────────────┐
│  소비자 앱 (gabjil, synapse-app, ...)       │
│  Flutter UI + 도메인 로직                    │
├─────────────────────────────────────────────┤
│  synapse_engine (pub.dev 패키지)            │
│  ┌─────────────────────────────────────┐    │
│  │ engine.dart — 공개 API (6 메서드)   │    │
│  ├─────────────────────────────────────┤    │
│  │ pipeline.dart — 오케스트레이터      │    │
│  ├──────────┬──────────┬───────────────┤    │
│  │ save.dart│retrieve. │ query.dart    │    │
│  │          │ dart     │              │    │
│  ├──────────┴──────────┴───────────────┤    │
│  │ inference.dart — llamadart 래퍼     │    │
│  │ db.dart — sqflite                   │    │
│  └─────────────────────────────────────┘    │
├─────────────────────────────────────────────┤
│  llamadart (llama.cpp 바인딩)               │
│  sqflite (SQLite)                           │
├─────────────────────────────────────────────┤
│  llama.cpp (C/C++ NDK/Framework)            │
│  SQLite (OS 내장)                            │
└─────────────────────────────────────────────┘
```

소비자 앱 개발자가 건드리는 것: `SynapseEngine.create()` + `EngineConfig` + 6개 메서드.
네이티브 빌드, llama.cpp 컴파일, 플랫폼 채널 — 전부 패키지 내부에서 처리.

## 10. 포팅 우선순위 (gabjil 기준 반영)

### 필수 (엔진 MVP)
| 기능 | 원본 | 포팅 | gabjil |
|------|------|------|--------|
| 하이퍼그래프 저장 (nodes/node_mentions/node_categories/aliases/sentences/unresolved_tokens) | db.py, save.py | db.dart, save.dart | ★★★ |
| extract 어댑터 (v15: edges 출력 필드 제거, nodes/categories/aliases만) | llm.py extract | inference.dart | ★★★ |
| save-pronoun 어댑터 (tokens + unresolved 분리 반환) | llm.py save-pronoun | inference.dart | ★★★ |
| structure-suggest 어댑터 (평문 → 마크다운 초안) | llm.py | inference.dart | ★★ |
| BFS 인출 (node_mentions JOIN + node_categories 공유 + 인접 맵) + retrieve-filter | retrieve.py | retrieve.dart | ★★★ |
| retrieve-expand | retrieve.py | retrieve.dart | ★★★ |
| 부정부사 규칙 감지(노드화, 엣지 아님) | save.py | save.dart 내 규칙 | ★★★ |
| 자모 오타 의심 쌍 판정 (자동 교정 없음) | save.py | typo.dart | ★ |
| 마크다운 파싱 | markdown.py | markdown.dart | ★★ |
| 문장 삭제/수정 | save.py | save.dart | ★★ |
| /review 런타임 제안 도출기 | suggestions.py | suggestions.dart | ★★ |

### 확장점 (엔진 v1)
| 기능 | 설명 |
|------|------|
| 카테고리 주입 | CategoryMap + AdjacencyMap 외부 주입 |
| 커스텀 어댑터 | AdapterSpec으로 런타임 로드 |
| 이벤트 스트림 | onSentenceCommitted, onNodeDeactivated, onNodeCreated |
| 하이퍼그래프 쿼리 | HypergraphQuery로 직접 조회 |
| 파이프라인 훅 | onAfterExtract, onBeforePronoun 등 |

### 보류
| 기능 | 이유 |
|------|------|
| *-org 계열 | gabjil 불필요. 시냅스 앱에서만 사용 |
| security-* 계열 | gabjil 불필요 |
| routing | 분기 없음 |
| 다국어 어댑터 전환 | Phase 2 이후 |

## 11. 품질 기준 (DESIGN_MOBILE.md 섹션 5 그대로 적용)

엔진 패키지화해도 품질 기준은 동일. DESIGN_MOBILE.md의 "품질 기준선" 참조.
각 어댑터별 정확도 기준 미달 시 해당 어댑터 GGUF 재학습.

## 12. Phase 계획

### Phase 0: 모델 변환 + 검증 (3-4일)
DESIGN_MOBILE.md Phase 0과 동일. MLX→GGUF 변환 + 품질 검증.

### Phase 1: 엔진 MVP (7-10일)
- `synapse_engine` 패키지 스캐폴딩
- db.dart: 스키마 + CRUD
- inference.dart: llamadart 래퍼 + 어댑터 스왑
- save.dart: 저장 파이프라인 (pronoun → extract → negation → typo → DB)
- retrieve.dart: BFS + filter + category supplement
- engine.dart: `create()`, `dispose()`, `ingest()`, `retrieve()`, `process()`
- 단위 테스트 (use_llm: false 모드)
- 실기기 추론 통합 테스트

### Phase 2: 확장점 (4-5일)
- CategoryMap + AdjacencyMap 주입
- AdapterSpec + loadAdapter()
- 이벤트 스트림 (StreamController)
- GraphQuery
- 파이프라인 훅

### Phase 3: 패키지 퍼블리싱 (2-3일)
- pub.dev 또는 private 레지스트리 퍼블리싱
- example/ 앱 (최소 Chat UI로 엔진 시연)
- README + API 문서
- 모델 다운로드 / 번들 가이드

### Phase 4: 소비자 앱 (각자)
- gabjil: 커스텀 카테고리 + 어댑터 + 캐릭터 생성 로직
- synapse-app: 기존 웹앱의 모바일 버전

## 13. 핵심 파일 참조 (포팅 원본)
- `engine/save.py` → save.dart (자동 저장 + 문장 CRUD + split_node + merge_nodes). 엣지 생성 코드(조사·의미) 전체와 `_correct_typos` 자동 교정 코드는 포팅 대상 아님
- `engine/retrieve.py` → retrieve.dart (`node_mentions` JOIN + `node_categories` 공유 + 인접 맵)
- `engine/suggestions.py` → suggestions.dart (/review 런타임 도출기)
- `engine/llm.py` → inference.dart + 시스템 프롬프트
- `engine/db.py` → db.dart (v15 스키마 — edges 테이블 없음)
- `engine/markdown.py` → markdown.dart
- `api/mlx_server.py` → inference.dart (어댑터 스왑 패턴)

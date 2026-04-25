# synapse_engine — Dart 패키지 설계

> **연관 PLAN**: [`PLAN-20260425-SYN-flutter-rewrite.md`](../deliverables/SYN/20260425/user/PLAN-20260425-SYN-flutter-rewrite.md) §4 — 본 문서의 2 계층 API 가 PLAN 의 단일 출처.

## 0. 핵심 결정

- **Dart 패키지로 분리** — 시냅스 앱뿐 아니라 갑질(찐친 카톡) 같은 다른 도메인 앱도 `flutter pub add synapse_engine` 한 줄로 재사용.
- **풀 오프라인** — `sqflite` + `llamadart` (llama.cpp 바인딩) + `kiwi-nlp` (WASM). HTTP 서버·외부 API 일절 없음.
- **2 계층 API** — 시냅스 흐름(`SynapseFlow`)은 시냅스 앱 전용, 그래프·LLM 원자 작업(`GraphOps`/`LlmTasks`)은 도메인 무관. 갑질은 `SynapseFlow` 를 비활성화하고 하위 두 계층만 쓴다.
- **kind 유연성** — `posts.kind` CHECK 가 `allowedKinds` 컨스트럭터 인자로 동적 결정. `reservedKinds` 에 `synapse`·`insight` 가 있을 때만 `SynapseFlow` 활성.
- **저장 두 층 분리** — 자동저장(LLM 미사용) vs 의미 처리(사용자 명시 트리거). 원칙은 `DESIGN_PRINCIPLES.md §1 원칙 9·13·14`, 파이프라인은 `DESIGN_PIPELINE.md`.
- **`archive/synapse_engine_v15/`** — 검증된 인프라 코드 (llamadart 통합·LoRA 핫스왑) 참조용 보존.

---

## 1. 패키지 구조

```
synapse_engine/                ← Dart 패키지 (private 또는 pub.dev)
├── lib/
│   ├── synapse_engine.dart    ← 단일 진입점. export 만
│   ├── src/
│   │   ├── engine.dart        ← SynapseEngine 컨스트럭터 + DI 컨테이너
│   │   ├── config.dart        ← EngineConfig + allowedKinds/reservedKinds
│   │   ├── db/
│   │   │   ├── schema.dart    ← DDL (9 테이블 + CHECK 동적, `categories` 19 대분류 시드 INSERT 포함)
│   │   │   └── migrations.dart
│   │   ├── flow/
│   │   │   └── synapse_flow.dart  ← 상위 API (시냅스 앱 전용)
│   │   ├── llm/
│   │   │   ├── llamadart_backend.dart  ← 모델 로딩·LoRA 핫스왑
│   │   │   ├── tasks.dart     ← 하위 LlmTasks API
│   │   │   └── prompts/       ← 시스템 프롬프트 assets
│   │   ├── graph/
│   │   │   ├── ops.dart       ← 하위 GraphOps API
│   │   │   ├── bfs.dart       ← BFS 인출 알고리즘
│   │   │   └── typo.dart      ← 자모 거리 오타 후보
│   │   ├── kiwi/
│   │   │   ├── kiwi_wasm.dart ← kiwi-nlp WASM 바인딩
│   │   │   └── tokens.dart    ← KiwiToken 모델
│   │   ├── markdown/
│   │   │   └── parser.dart    ← heading 경로 + 항목 분리
│   │   └── models/
│   │       ├── post.dart
│   │       ├── sentence.dart
│   │       ├── mention.dart
│   │       ├── correction.dart
│   │       └── ...
│   └── src/internal/          ← 패키지 내부 전용
│       ├── regex.dart         ← 날짜·대명사·부정부사 패턴
│       └── thinking_strip.dart
├── assets/
│   ├── models/                ← 베이스 모델 GGUF (선택 번들)
│   ├── adapters/              ← retrieve-expand 어댑터 GGUF
│   ├── prompts/               ← 시스템 프롬프트
│   └── kiwi/                  ← kiwi-nlp WASM + 사전
├── test/
├── example/                   ← 최소 시연 앱
├── pubspec.yaml
└── README.md
```

`lib/src/` 아래는 전부 패키지 내부. 소비자 앱은 `synapse_engine.dart` 로만 접근.

---

## 2. 2 계층 API

```
┌────────────────────────────────────────┐
│  소비자 앱                              │
│  (시냅스 앱 / 갑질 앱 / ...)            │
└──────────────────┬─────────────────────┘
                   │
        ┌──────────┴────────────┐
        │                       │
┌───────▼─────────┐   ┌─────────▼────────┐
│ SynapseFlow     │   │ LlmTasks         │
│ (시냅스 앱 전용) │   │ GraphOps         │
│ reservedKinds   │   │ (모든 앱 공통)    │
│  활성화 시만    │   └─────────┬────────┘
└───────┬─────────┘             │
        └──────────┬────────────┘
                   │
            ┌──────▼──────┐
            │  내부 인프라 │
            │ llamadart   │
            │ sqflite     │
            │ kiwi-nlp    │
            └─────────────┘
```

상위는 도메인 흐름을 압축한 4 경로. 하위는 LLM 원자 태스크 6개·그래프 원자 작업 9개. 갑질처럼 시냅스 흐름이 필요 없는 앱은 상위를 비활성하고 하위만 자유 조합.

### 2.1 상위 — `SynapseFlow` (시냅스 앱 전용)

`reservedKinds` 에 `synapse` 와 `insight` 가 모두 있을 때만 활성. 없으면 `engine.flow` 가 `null` 이라 컴파일·런타임 모두 호출 불가.

```dart
class SynapseFlow {
  // /note 자동저장 — LLM 미사용. posts.source 만 갱신.
  Future<void> noteAutosave({
    required int postId,
    required String source,
  });

  // /note 의미 처리 — 사용자 명시 트리거 (⌘S / "정리").
  // sentences 재계산 + Kiwi 노드 + node_sentence_mentions + LLM 정정 후보.
  // 정정 카드는 반환만. 적용은 사용자 클릭 후 별도 호출.
  Future<NoteProcessResult> noteProcess({
    required int postId,
    required String source,
  });

  // /synapse 한 턴 — retrieve + 답변 + Q/A 누적.
  Future<SynapseTurnResult> synapseTurn({
    required String question,
    int? postId,  // 같은 시냅스 세션 이어쓰기 시
  });

  // /promote — 시냅스 메시지를 통찰로 승격 (Hebbian 일괄 연결).
  Future<InsightResult> promoteToInsight({
    required int sourceSentenceId,  // 승격할 synapse 메시지
    required List<int> snapshotNodeIds,  // 직전 retrieve 캐시 스냅샷
  });

  // post 목록·재진입·삭제 (시냅스 앱 사이드바 데이터 소스)
  Future<List<PostMeta>> listPosts({
    String? kind,            // null = 모든 kind
    int limit = 50,
    int offset = 0,
  });
  Future<PostDetail> getPost(int postId);
  Future<void> updatePostTitle(int postId, String title);
  Future<void> deletePost(int postId);
}
```

`NoteProcessResult` 에는 새로 만든 sentence 목록 + 정정 후보 목록 + 별칭 보호로 걸러진 토큰 목록이 함께 들어온다. UI 는 정정 카드를 인라인으로 그리고, [적용] 클릭 시 `GraphOps` 의 별칭 추가 + `update_sentence` 호출로 마무리.

### 2.2 하위 — `LlmTasks`

llamadart 호출의 단위 단위. 모든 앱이 자유 호출. 베이스 모델 + 어댑터 핫스왑은 내부에서 알아서.

```dart
class LlmTasks {
  // 지시어/대명사 치환 — "거기" → "스타벅스 강남점".
  Future<String> savePronoun(String text, {String? context});

  // 메타 대화 사전 필터 — "방금 그거 다시" 같은 메타 발화 식별.
  Future<List<bool>> metaFilter(List<String> texts);

  // 인출 키워드 확장 — "허리 어때?" → ["허리", "디스크", "통증"].
  Future<List<String>> retrieveExpand(String question);

  // 인출 결과 필터링 — 무관 문장 제거.
  Future<bool> retrieveFilter(String question, String sentence);

  // 시냅스 답변 생성 — 컨텍스트 sentences 기반 합성.
  Future<String> synapseAnswer({
    required String question,
    required List<ContextSentence> contexts,
  });

  // 정정 후보 생성 — 별칭 보호 + 자모 거리 사전 필터 통과한 토큰 대상.
  // 자동 적용 금지 (원칙 14-③), UI 카드로 노출.
  Future<List<Correction>> typoNormalize(
    String text, {
    required Set<String> protectedAliases,
  });

  // 어댑터 핫스왑 (내부 자동, 명시 호출도 가능)
  Future<void> swapAdapter(String adapterName);
}
```

### 2.3 하위 — `GraphOps`

sqflite + Kiwi 그래프 원자 작업. LLM 없이도 100% 동작 (원칙 11).

```dart
class GraphOps {
  // 노드 ────────────────────────────────────
  Future<int> upsertNode(String name);
  Future<List<Node>> findNodesByAlias(String alias);
  Future<void> splitNode(int nodeId, SplitSpec spec);
  Future<void> deleteNode(int nodeId);

  // 문장 바구니 ────────────────────────────
  Future<int> addSentence({
    required int postId,
    required String text,
    String role = 'user',
    String? origin,  // null/'user'/'insight'
  });
  Future<bool> addMention({
    required int nodeId,
    required int sentenceId,
    String origin = 'system',
  });
  Future<void> updateSentence(int sentenceId, String newText);
  Future<void> deleteSentence(int sentenceId);

  // 카테고리 바구니 ────────────────────────
  Future<int?> upsertCategoryPath(String? headingPath);  // 재귀 INSERT, 말단 id 반환
  Future<void> addSentenceCategory({
    required int sentenceId,
    required int categoryId,
    String origin = 'user',
  });
  Future<void> addCategoryMention({
    required int nodeId,
    required int categoryId,
    String origin = 'system',
  });

  // 별칭 바구니 ────────────────────────────
  Future<void> addAlias({
    required String alias,
    required int nodeId,
    String origin = 'user',
  });
  Future<void> removeAlias(String alias);

  // 인출 ──────────────────────────────────
  Future<List<Mention>> bfsRetrieve({
    required Set<int> startNodes,
    int maxLayers = 5,
  });

  // 오타 후보 (자모 거리, 자동 교정 없음)
  Future<List<TypoCandidate>> findSuspectedTypos();

  // 통계·디버깅
  Future<EngineStats> getStats();

  // Kiwi 노출 ─────────────────────────────
  Future<List<KiwiToken>> kiwiTokenize(String text);
  Future<List<String>> kiwiNouns(String text);  // lemma 정규화 적용
}
```

---

## 3. EngineConfig — kind 유연성

```dart
class EngineConfig {
  // 앱 식별 + kind 유연성
  final String appName;             // 'synapse_app' | 'gabjil_app' | ...
  final List<String> allowedKinds;  // posts.kind CHECK 동적 적용
  final List<String> reservedKinds; // SynapseFlow 활성 조건

  // 데이터 위치
  final String dbPath;              // sqflite DB 파일

  // LLM 자원 (모바일 번들 또는 데스크톱 다운로드 경로)
  final String modelPath;           // 베이스 GGUF
  final List<AdapterSpec> adapters;

  // Kiwi WASM
  final String kiwiAssetPath;       // 사전 + WASM 모듈

  // 카테고리 시드 (도메인 앱이 교체 가능)
  final CategorySeed categorySeed;

  // 시스템 프롬프트 오버라이드 (선택)
  final Map<String, String>? promptOverrides;
}
```

### 3.1 시냅스 앱 — 시냅스 흐름 활성

```dart
final engine = await SynapseEngine.create(EngineConfig(
  appName: 'synapse_app',
  allowedKinds: ['note', 'synapse', 'insight'],
  reservedKinds: ['synapse', 'insight'],  // SynapseFlow 활성
  dbPath: '${appDocDir.path}/synapse.db',
  modelPath: 'assets/models/gemma-4-e2b-q4.gguf',
  adapters: [
    AdapterSpec('retrieve-expand', 'assets/adapters/retrieve-expand.gguf'),
  ],
  kiwiAssetPath: 'assets/kiwi/',
  categorySeed: CategorySeed.synapse19(),  // 19 대분류
));

// SynapseFlow 사용 가능
await engine.flow!.noteAutosave(postId: 42, source: '...');
await engine.flow!.synapseTurn(question: '허리 어때?');
```

### 3.2 갑질 앱 — 시냅스 흐름 비활성

```dart
final engine = await SynapseEngine.create(EngineConfig(
  appName: 'gabjil_app',
  allowedKinds: ['message', 'thread', 'friend'],
  reservedKinds: [],  // SynapseFlow 비활성 — engine.flow == null
  dbPath: '${appDocDir.path}/gabjil.db',
  modelPath: 'assets/models/gemma-4-e2b-q4.gguf',
  adapters: [
    AdapterSpec('gabjil-extract', 'assets/adapters/gabjil-extract.gguf'),
  ],
  kiwiAssetPath: 'assets/kiwi/',
  categorySeed: CategorySeed.gabjil(),  // 인물·에피소드·감정·상황·특성
));

// LlmTasks + GraphOps 만 자유 호출
final tokens = await engine.graph.kiwiTokenize('김부장이 또...');
final nouns = await engine.graph.kiwiNouns('김부장이 또...');
final pid = await engine.graph.upsertNode('김부장');
final sid = await engine.graph.addSentence(postId: 7, text: '김부장이 또...');
await engine.graph.addMention(nodeId: pid, sentenceId: sid);

// 갑질 도메인 어댑터 직접 호출
final result = await engine.llm.runAdapter('gabjil-extract', '...');
```

### 3.3 CHECK 동적 적용

`allowedKinds` 가 컨스트럭터 단계에서 결정되므로 DB 생성 시점에 `posts.kind` CHECK 가 동적으로 빌드된다.

```dart
// schema.dart 가 EngineConfig 를 받아서 DDL 생성
String buildPostsDdl(List<String> allowedKinds) {
  final values = allowedKinds.map((k) => "'$k'").join(',');
  return '''
    CREATE TABLE posts (
      id          INTEGER PRIMARY KEY,
      kind        TEXT NOT NULL DEFAULT '${allowedKinds.first}'
                       CHECK(kind IN ($values)),
      title       TEXT,
      source      TEXT,
      created_at  TEXT DEFAULT (datetime('now')),
      updated_at  TEXT DEFAULT (datetime('now'))
    )
  ''';
}
```

마이그레이션 시에도 같은 함수로 CHECK 만 갈아끼움. 데이터는 보존.

---

## 4. Kiwi WASM 통합

모바일·데스크톱 모두 `kiwi-nlp` (WASM) 단일 사용. 서버용 `kiwipiepy` (C++) 는 본 패키지 범위 밖 (현재 Python 측 Frozen 환경에 남음).

```dart
class KiwiBackend {
  static Future<KiwiBackend> load(String assetPath);

  Future<List<KiwiToken>> tokenize(String text);
  Future<List<String>> nouns(String text);  // NNG/NNP/NR + lemma 정규화
  Future<String> lemma(String surface, String tag);

  void dispose();
}
```

토큰 경계·품사 태그·lemma 결과 스키마는 서버측 `kiwipiepy` 와 **동일하게 유지** (원칙 11) — 같은 시드 데이터·같은 노드 이름이 양 환경에서 재현되도록.

WASM 로드는 Flutter 의 `flutter_rust_bridge` 또는 `wasm_run` 같은 런타임 사용. `archive/synapse_engine_v15/` 의 통합 코드 참고.

---

## 5. llamadart 인프라

```dart
class LlamadartBackend {
  static Future<LlamadartBackend> load({
    required String modelPath,
    int contextSize = 4096,
    int gpuLayers = -1,  // -1 = 가능한 만큼
  });

  Future<void> applyAdapter(String name, String path);
  Future<void> swapAdapter(String name);  // 로드된 어댑터 간 핫스왑

  Future<String> chat({
    required String systemPrompt,
    required String userText,
    int maxTokens = 256,
    double temperature = 0.0,
  });

  Future<Stream<String>> chatStream({
    required String systemPrompt,
    required String userText,
    int maxTokens = 256,
  });

  void dispose();
}
```

베이스 모델 + LoRA 어댑터는 `archive/synapse_engine_v15/` 의 통합 코드를 인프라 (모델 로딩·핫스왑·thinking 블록 제거) 만 그대로 재사용.

### 어댑터 정책 — 단일 모델 고정

- **베이스 모델**: Gemma 4 E2B-it 4bit GGUF (~1.2GB). 앱 번들 고정. 모델 카탈로그·다운로드 인프라는 후속 PLAN.
- **어댑터**: `retrieve-expand` (GGUF, 52MB) 만 번들. `save-pronoun`/`meta-filter`/`typo-normalize`/`synapse-answer`/`retrieve-filter` 는 **베이스 + 시스템 프롬프트** 로 처리.
- **시스템 프롬프트**: `assets/prompts/` 에 `SAVE_PRONOUN_SYSTEMPROMPT.md`·`META_FILTER_SYSTEMPROMPT.md`·`TYPO_NORMALIZE_SYSTEMPROMPT.md` 등을 번들. `LlmTasks` 가 태스크별로 골라 사용.

---

## 6. 자동저장 vs 의미 처리 — `SynapseFlow` 구현 명세

| 동작 | API | DB 갱신 | LLM | UI 응답 |
|---|---|---|---|---|
| 자동저장 | `noteAutosave` | `posts.source` 만 | ❌ | <50ms (sqflite UPDATE) |
| 의미 처리 | `noteProcess` | sentences·node_sentence_mentions·sentence_categories·node_category_mentions·aliases·unresolved_tokens | ✅ | 0.5~3초 (llamadart 추론) |

`noteAutosave` 는 입력 1.5초 디바운스 + 페이지 이탈 (Flutter `WidgetsBindingObserver` 의 `didChangeAppLifecycleState` 또는 Navigator pop 시점) 때 호출. 손실 방지가 목적.

`noteProcess` 는 사용자 명시 트리거 — ⌘S, "정리" 버튼, 재진입 시 제안. 결과는 `NoteProcessResult` 로 반환되며 정정 후보는 UI 카드로 노출 (자동 적용 금지, 원칙 14-③).

원칙 9·13·14 와 파이프라인 세부는 `DESIGN_PRINCIPLES.md`·`DESIGN_PIPELINE.md` 참고.

---

## 7. 통찰 승격 — `promoteToInsight` 명세

원칙 15-2 (Hebbian 허브 형성) 의 구현. PLAN §4 의 SynapseFlow 4 경로 중 하나.

흐름:
1. UI 가 시냅스 세션의 메시지 하나에 `[⬆ 통찰로 승격]` 액션을 노출
2. 사용자 확인 → `engine.flow!.promoteToInsight(sourceSentenceId, snapshotNodeIds)` 호출
3. 엔진이 다음을 트랜잭션으로 처리:
   - 새 `posts` 행 (`kind='insight'`, `title=본문 첫 행`, `source=본문`)
   - 새 `sentences` 행 (`post_id=새 insight post`, `role='user'`, `origin='insight'`)
   - `snapshotNodeIds` 의 모든 노드와 `node_sentence_mentions` 일괄 INSERT
   - Kiwi 가 본체에서 추출한 노드도 같이 편입 (UNIQUE 충돌은 스킵)
4. `InsightResult` 반환 (새 post id + 연결된 노드 수)

`origin='insight'` sentence 는 `updateSentence` 가 거부 (API 레벨 강제). 삭제는 `/review` 승인 경로 (`DESIGN_REVIEW.md` insight_delete 섹션).

---

## 8. 이벤트 스트림 (선택)

소비자 앱이 그래프 변화를 실시간 구독:

```dart
class SynapseEngine {
  Stream<SentenceCommittedEvent> get onSentenceCommitted;
  Stream<NodeCreatedEvent> get onNodeCreated;
  Stream<InsightPromotedEvent> get onInsightPromoted;
}
```

갑질 앱 사용 예:
```dart
engine.onSentenceCommitted.listen((e) {
  if (e.mentionedNodeIds.contains(targetPersonId)) {
    complaintCount++;
    if (complaintCount >= 3) suggestCharacterCreation(targetPersonId);
  }
});
```

---

## 9. 갑질 재사용 시나리오 (구체)

갑질이 시냅스가 아닌데도 같은 `synapse_engine` 패키지를 쓰는 이유:
- **하이퍼그래프 본질이 같다** — 인물·에피소드·감정·상황을 노드로 잡고 공출현·카테고리로 연결.
- **온디바이스 LLM 인프라 공유** — llamadart·Kiwi WASM·시스템 프롬프트 메커니즘 전부 동일.
- **시냅스 특수 흐름은 분리** — `note`/`synapse`/`insight` 3 종 그릇·통찰 승격은 갑질에 무관 → `reservedKinds: []` 로 비활성.

갑질이 추가로 필요한 것:
- `gabjil-extract` 같은 도메인 특화 어댑터 (`AdapterSpec` 으로 등록)
- 인물·에피소드 카테고리 시드 (`CategorySeed.gabjil()`)
- 도메인 흐름 — "캐릭터 카드 자동 생성", "관계 강도 트래킹" 등은 갑질 앱 자체 코드. 엔진은 `LlmTasks`·`GraphOps` 만 제공하고 흐름은 갑질이 직접 조립.

---

## 10. 마이그레이션·롤백

- 패키지 단위 버전 관리 (`pubspec.yaml`).
- DB 마이그레이션은 `lib/src/db/migrations.dart` 의 단조 증가 버전 (v22 → v23 → ...).
- `archive/synapse_engine_v15/` 는 보존만, import 금지 (참고용 스냅샷).

---

## 11. 검증 (PLAN F1~F5 와 1:1)

| 마일스톤 | 본 문서 섹션 | 통과 조건 |
|---|---|---|
| F1 | §1 | `dart pub get` 성공, 빈 진입점 import 성공 |
| F2 | §3·DB | sqflite DB 생성 + 9 테이블 + 19 대분류 시드 + `posts.kind` CHECK 가 `allowedKinds` 반영 |
| F3 | §5 + §2.2 | `LlmTasks` 6 태스크 단위 호출 (베이스 + retrieve-expand 어댑터) |
| F4 | §4 + §2.3 | Kiwi WASM 토큰화 + `GraphOps` 원자 작업 + BFS 시나리오 (Python `engine/retrieve.py` 와 동등 결과) |
| F5 | §2.1 + §6·§7 | `SynapseFlow` 4 경로 단위 스모크 (Python 참조 구현의 M4 스모크 시나리오와 동등) |

---

## 12. 참고 자산

- `archive/synapse_engine_v15/` — Dart 엔진 인프라 참고 (llamadart·LoRA 핫스왑·thinking 블록 제거)
- `archive/app_react_v21/` — React 웹앱 UX 참고
- `engine/`, `api/` (Python) — 파이프라인 알고리즘 참조 구현 (frozen)
- `docs/DESIGN_PRINCIPLES.md` — 원칙 9·11·13·14·15 (저장 두 층 분리·지능체 분리·로컬 제약·UI 의무·통찰)
- `docs/DESIGN_HYPERGRAPH.md` — 스키마 (9 테이블)
- `docs/DESIGN_PIPELINE.md` — 자동저장·의미 처리·인출 파이프라인 세부
- `docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md` — note 단일 그릇 + LLM 호출 요약
- `docs/DESIGN_APP.md` — 비서 앱 + Flutter 기술 스택·디바이스 벤치마크·파이프라인 최적화·리스크
- `docs/DESIGN_CATEGORY.md` — 19 대분류 + 인접 맵
- `docs/DESIGN_REVIEW.md` — 통찰 삭제 (`insight_delete`) 승인 흐름
- `docs/CATEGORY_SYSTEMPROMPT.md`·`SAVE_PRONOUN_SYSTEMPROMPT.md`·`META_FILTER_SYSTEMPROMPT.md`·`RETRIEVE_EXPAND_SYSTEMPROMPT.md`·`RETRIEVE_FILTER_SYSTEMPROMPT.md` — assets 번들 후보

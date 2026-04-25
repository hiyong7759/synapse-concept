# PLAN-20260425-SYN-flutter-rewrite — Flutter 전환·재시작

**상태**: 승인 대기
**브랜치**: `feature/v22-rewrite` (이어서) 또는 `feature/flutter-rewrite` (분기, 결정 필요)
**작성일**: 2026-04-25
**선행 PLAN**: PLAN-20260424-SYN-v22rewrite (M1~M5 완료, Python 측 v22 1차안 구현 — git tracked 외, 로컬 보존)

---

## 1. 목표

v22 2차안 (note 단일 + 자동저장/의미 처리 분리 + LLM 정정 후보) 을 **Flutter** 로 처음부터 재구현한다.

- **모바일 우선** (iOS·Android) — 사용자 사용 빈도 1순위
- **데스크톱 통합** (macOS·Windows) — 같은 코드베이스로 부수적 따라옴
- **풀 오프라인** — `synapse_engine` Dart 패키지가 SQLite + llamadart + Kiwi WASM 모두 내장
- **`synapse_engine` 패키지 분리** — 시냅스 앱 외에도 갑질 등 다른 도메인 앱이 재사용 가능

기존 자산 처리:
- `archive/synapse_engine_v15/` — v15 시점 Dart 엔진 (참고용 보존, llamadart 통합·LoRA 핫스왑 코드 포함)
- `archive/app_react_v21/` — v21 React 웹앱 (참고용 보존)
- `engine/`, `api/` (Python) — v22 1차안에서 freeze, 학습·dogfood 환경 보존

## 2. 범위

### 포함
- **`synapse_engine` Dart 패키지** v22 2차안 신규 구현 — 2 계층 API (SynapseFlow / LlmTasks / GraphOps) + allowedKinds 유연성
- **시냅스 앱** Flutter (iOS·Android·macOS·Windows) — `/note`·`/synapse` 라우트
- **자동저장 vs 의미 처리** 분리 — 디바운스 자동저장 (LLM 미사용) + 사용자 명시 트리거 (⌘S / "정리") 의미 처리
- **LLM 정정 후보** 인라인 카드 — 별칭 보호 + 자모 거리 사전 필터 + 자동 적용 금지
- **통찰 승격** Hebbian 허브 연결
- **모바일 우선 반응형 UI** — 같은 위젯이 PC 데스크톱에서도 자연 확장
- **gstack 또는 Flutter integration_test** 로 각 M 종료 시 검증

### 제외 (후속 PLAN)
- 갑질 어댑터 6 개 audit (`PLAN-202604??-SYN-gabjil-adapter-audit`)
- 갑질 앱 v22 엔진 적용 (`PLAN-202604??-SYN-gabjil-v22-adoption`)
- `/review` 통찰 삭제 UI
- 온보딩 / 조직 모드 UI
- iOS·Android 앱스토어 배포 (코드 서명·공증 등)
- macOS notarization, Windows MSIX 패키징
- 베이스 모델 공유 폴더 최적화 (앱마다 번들 vs 공유)
- **첫 실행 모델 다운로드 인프라** (CDN·재개 가능 다운로드·진행률 UI) — 사용처 많아지거나 모델 카탈로그 도입 시점에 분리. v22 2차안은 앱 번들 고정
- **LLM 모델 갈아끼우기 + 모델 카탈로그 UI** — 시냅스 v22 2차안 dogfood 검증 후 별도 PLAN. 단일 모델 (Gemma 4 E2B) 고정 운영
- **다른 베이스용 어댑터 학습** (Qwen·Phi 등 retrieve-expand) — 모델 갈아끼우기 도입 시점에 함께

## 3. 마일스톤

| M | 내용 | 주요 산출물 | 검증 |
|---|---|---|---|
| **F0** | **Flutter 전환 설계 정합** — 선행 PLAN M5 (입력 모드 분리 폐지) 위에 Flutter·2 계층 API·풀 오프라인 결정 반영. **DESIGN_ENGINE.md 대수술** (2 계층 API: SynapseFlow / LlmTasks / GraphOps + `allowedKinds`·`reservedKinds` 유연성 + 갑질 재사용 시나리오 + Kiwi WASM 통합). **DESIGN_APP.md 통합** (DESIGN_MOBILE 흡수 — 모바일 우선·데스크톱 통합·디바이스 벤치마크·파이프라인 최적화·리스크). **DESIGN_INPUT_MODES_AND_RETRIEVAL.md 통합** (INPUT_GUIDE 흡수 — 작성자 가이드). **나머지 문서** (PRINCIPLES·HYPERGRAPH·PIPELINE·CATEGORY·REVIEW·FINETUNE·ORG·UI·OVERVIEW) 의 풀 오프라인·Flutter 위젯·HTTP 폐기 표현 정합 + 변경 이력 잡음 제거 | grep 으로 v22 1차안·"PC 데스크톱 기준"·"FastAPI" 등 잔재 0. 죽은 링크 0 |
| **F1** | `synapse_engine` Dart 패키지 scaffold | `pubspec.yaml`, `lib/synapse_engine.dart` 진입점, `lib/src/` 구조 (db, save, retrieve, llm, kiwi, models) | `dart pub get` 성공 + 빈 패키지 import 성공 |
| **F2** | DB 스키마 v22 2차안 (sqflite + ffi) | `lib/src/db.dart` — posts(kind/title/source) + sentences(post_id NOT NULL/origin) + nodes + node_sentence_mentions + categories + sentence_categories + node_category_mentions + aliases + unresolved_tokens. `allowedKinds` 컨스트럭터 유연성 | DB 생성 + 19 대분류 시드 + 스키마 덤프 검증 |
| **F3** | 하위 API — `LlmTasks` (llamadart 통합) | `lib/src/llm/llamadart_backend.dart` 모델 로딩·LoRA 핫스왑, `lib/src/llm/tasks.dart` (savePronoun, metaFilter, retrieveExpand, retrieveFilter, synapseAnswer, typoNormalize). `archive/synapse_engine_v15/` 의 인프라 코드 참고 가능 | 각 태스크 단위 호출 스모크 (모델 + GGUF 어댑터) |
| **F4** | 하위 API — `GraphOps` (그래프 작업) | `lib/src/graph/ops.dart` — upsertNode, addMention, addAlias, addCategoryMention, bfsRetrieve, findSuspectedTypos. Kiwi WASM 통합 (`lib/src/kiwi/`) | 단위 호출 스모크 + Kiwi 토큰화 검증 |
| **F5** | 상위 API — `SynapseFlow` (시냅스 흐름) | `lib/src/flow/synapse_flow.dart` — noteAutosave, noteProcess, synapseTurn, promoteToInsight | 4 경로 단위 스모크 (Python 측 M4 스모크 시나리오와 동등) |
| **F6** | Flutter 앱 scaffold | `app/` 신규 (Flutter), 라우트 `/note`·`/synapse`, 글로벌 토큰·반응형 레이아웃 (모바일 우선) | iOS 시뮬레이터 + Android 에뮬레이터 + macOS 빌드 빈 페이지 렌더 |
| **F7** | `/note` 페이지 구현 | 사이드바 post 목록 (✦ insight 구분), 단일 입력 영역, 자동저장 (디바운스 1.5초), ⌘S 의미 처리 트리거, 정정 카드 인라인, 재진입·이어쓰기, post 삭제, **해당 노트 그래프 패널** (지금 보고 있는 post 의 노드/하이퍼엣지만 시각화) | E2E (입력→자동저장→이탈→재진입→⌘S→정정 [적용]→source 갱신 + 그래프 패널 노드 반영) |
| **F8** | `/hypergraph` 페이지 구현 | 별도 라우트, **전체 누적 그래프** (모든 post 의 모든 노드/하이퍼엣지 통합 시각화), 허브 노드 강조, 노드 탭 → 같은 바구니 멤버 + 원문 sentence, `origin='insight'` 강조, 검색·필터·BFS 깊이 슬라이더 | post 3 개 이상 입력 후 전체 그래프 렌더 + 노드 탭 인터랙션 동작 |
| **F9** | `/synapse` 페이지 구현 | Q/A 스레드, 답변 카드 마크다운 렌더, `[⬆ 통찰로 승격]` 모달, 승격 후 `/note` 목록에 ✦ 표시, **해당 시냅스 세션 그래프 패널** (retrieve 캐시 노드만 시각화 — 답변이 어떤 노드에서 끌어왔는지 추적) | 시냅스 세션 → 승격 → 허브 연결 검증 + 그래프 패널이 retrieve 노드 반영 |
| **F10** | 3 라우트 E2E 통합 검증 | iOS·Android·macOS 빌드 각각에서 통합 시나리오 통과 (note → hypergraph 확인 → synapse → 통찰 승격 → hypergraph 허브 변화 확인) | 모든 Acceptance 항목 통과 |
| **F11** | 문서·CLAUDE.md 갱신 | `docs/index.md` 에 Flutter 전환 반영, `CLAUDE.md` 의 명령 섹션 갱신, README 업데이트 | 링크·참조 무결 |

각 M 종료 시 **커밋 → 진행 보고 → 사용자 승인 대기 → 다음 M 진입** (전역 CLAUDE.md 규칙).

## 4. `synapse_engine` 2 계층 API 설계 (v22 2차안 핵심)

### 상위 — `SynapseFlow` (시냅스 앱 전용)

```dart
class SynapseFlow {
  // /note 자동저장 — LLM 미사용, posts.source 만 갱신
  Future<void> noteAutosave({required int postId, required String source});

  // /note 의미 처리 — LLM 호출, sentences 재계산 + 정정 후보
  Future<NoteProcessResult> noteProcess({required int postId, required String source});

  // /synapse/turn — 한 턴 (retrieve + answer + Q/A 누적)
  Future<SynapseTurnResult> synapseTurn({required String question, int? postId});

  // /promote — 통찰 승격
  Future<InsightResult> promoteToInsight({required int sourceSentenceId, required List<int> nodeIds});

  // post 목록·재진입·삭제
  Future<List<PostMeta>> listPosts({String? kind, int limit = 50, int offset = 0});
  Future<PostDetail> getPost(int postId);
  Future<void> updatePostTitle(int postId, String title);
  Future<void> deletePost(int postId);
}
```

### 하위 — `LlmTasks` (모든 앱 자유 호출)

```dart
class LlmTasks {
  Future<String> savePronoun(String text, {String? context});
  Future<List<int>> metaFilter(List<String> texts);
  Future<List<String>> retrieveExpand(String question);
  Future<bool> retrieveFilter(String question, String sentence);
  Future<List<Correction>> typoNormalize(String text, {required List<String> aliases});
  Future<String> synapseAnswer({required String question, required List<ContextSentence> contexts});
}
```

### 하위 — `GraphOps` (모든 앱 자유 호출)

```dart
class GraphOps {
  Future<int> upsertNode(String name);
  Future<bool> addMention({required int nodeId, required int sentenceId, String origin = 'rule'});
  Future<void> addAlias({required String alias, required int nodeId, String origin = 'user'});
  Future<int?> upsertCategoryPath(String? path);
  Future<void> addCategoryMention({required int nodeId, required int categoryId, String origin = 'rule'});
  Future<List<Mention>> bfsRetrieve({required Set<int> startNodes, int maxLayers = 5});
  Future<List<TypoCandidate>> findSuspectedTypos();
  Future<List<KiwiToken>> kiwiTokenize(String text);
}
```

### kind 유연성 (Hybrid)

```dart
SynapseEngine(
  appName: 'synapse_app',
  allowedKinds: ['note', 'synapse', 'insight'],
  reservedKinds: ['synapse', 'insight'],  // 시냅스 핵심 (SynapseFlow 활성화 조건)
)

// 갑질
SynapseEngine(
  appName: 'gabjil_app',
  allowedKinds: ['message', 'thread', 'friend'],
  reservedKinds: [],  // SynapseFlow 비활성, LlmTasks·GraphOps 만
)
```

DB 의 `posts.kind` CHECK 는 컨스트럭터의 `allowedKinds` 로 동적 적용.

## 5. 자동저장 vs 의미 처리 — 동작 명세

| 동작 | 트리거 | 갱신 대상 | LLM | 응답 시간 | 비고 |
|---|---|---|---|---|---|
| **자동저장** | 입력 1.5초 디바운스 + 페이지 이탈 (`pagehide`/`visibilitychange` 상응 Flutter 이벤트) | `posts.source` 만 | ❌ | <50ms | sqflite UPDATE 한 줄 |
| **의미 처리** | 사용자 명시 (⌘S / "정리" 버튼 / 재진입 시 제안) | sentences 재계산 + Kiwi 노드 + LLM 정정 후보 | ✅ | 0.5~3초 | llamadart 추론 |

페이지 이탈 시 의미 처리는 **트리거만 + 백그라운드** (사용자 떠나는 순간 멈칫 없음).

## 6. LLM 모델·어댑터 번들 (모바일)

**v22 2차안 정책: 단일 모델 + 앱 번들 고정**. 모델 갈아끼우기·다운로드 인프라는 후속 PLAN (§2 제외 참고).

| 자원 | 사이즈 | 처리 |
|---|---|---|
| Gemma 4 E2B GGUF (4bit) | ~1.2GB | **iOS·Android·macOS·Windows 앱 번들** (다운로드 인프라 미도입) |
| 어댑터 `retrieve-expand` | 52MB | 앱 번들 (Gemma 4 E2B 종속) |
| 시스템프롬프트 (`SAVE_PRONOUN`, `META_FILTER`, `TYPO_NORMALIZE` 신설, `SYNAPSE_ANSWER`, `RETRIEVE_FILTER`) | ~30KB | 코드 임베드 또는 assets |

→ 모바일 앱스토어 다운로드는 ~1.25GB. 사용자가 받기 부담 있으나 v22 2차안 단일 사용처(시냅스 본인) 단계에선 인프라 부담 없는 게 우선. 사용처 늘거나 모델 카탈로그 필요해지면 다운로드 인프라 후속 PLAN 에서 분리.

`archive/synapse_engine_v15/` 의 GGUF 변환·LoRA 핫스왑 코드 그대로 참고 가능.

## 7. Acceptance 기준

| M | 통과 조건 |
|---|---|
| **F0** | 설계 문서 grep 으로 v22 1차안·`PC 데스크톱 기준`·`FastAPI`·`/chat`·`/compose`·변경 이력 박스 잔재 0. DESIGN_ENGINE 에 2 계층 API + `allowedKinds` + 갑질 재사용 시나리오 명기. DESIGN_APP 에 모바일·데스크톱 사양 통합. DESIGN_INPUT_MODES_AND_RETRIEVAL 에 작성자 가이드 통합. 죽은 링크 0 |
| **F1** | `dart pub get` 성공, 빈 진입점 import 성공 |
| **F2** | sqflite DB 생성 + 9 테이블 + 19 대분류 시드 (~133 개) + `posts.kind` CHECK 가 `allowedKinds` 반영 |
| **F3** | 5 LLM 태스크 단위 호출 성공 (베이스 + retrieve-expand 어댑터). MLX 의존성 제거 (llamadart 직접) |
| **F4** | Kiwi WASM 토큰화 + 9 GraphOps 단위 호출 + BFS 시나리오 (Python 측 retrieve.py 와 동등 결과) |
| **F5** | SynapseFlow 4 경로 (noteAutosave / noteProcess / synapseTurn / promoteToInsight) 단위 스모크 통과 |
| **F6** | Flutter 빈 앱이 iOS 시뮬레이터 + Android 에뮬레이터 + macOS 빌드 모두 기동 |
| **F7** | E2E 시나리오 통과 (입력→자동저장→이탈→재진입→⌘S→정정 카드 [적용]→토큰 치환 + alias 등록 + 해당 노트 그래프 패널이 새 노드 즉시 반영) |
| **F8** | post 3 개 이상 입력 후 `/hypergraph` 별도 라우트가 전체 누적 그래프 렌더 + 허브 노드 강조 + 노드 탭 → 같은 바구니 멤버 + 원문 sentence + `origin='insight'` 시각 강조 + 검색·필터·BFS 깊이 슬라이더 동작 |
| **F9** | 시냅스 세션 → 승격 → ✦ 통찰 post 표시 + `node_sentence_mentions` 편입 검증 + 시냅스 그래프 패널이 retrieve 캐시 노드 반영 |
| **F10** | 3 플랫폼 (iOS·Android·macOS) 통합 시나리오 30분 내 통과 (note → hypergraph → synapse → 통찰 승격 → hypergraph 허브 변화 확인) |
| **F11** | docs/index.md 링크 무결, CLAUDE.md 명령 섹션 갱신 완료 |

## 8. 리스크 & 완화

| 리스크 | 완화 |
|---|---|
| llamadart Kiwi-nlp WASM 통합 난이도 | `archive/synapse_engine_v15/` 코드 참고. 안 되면 Kiwi 결과를 Dart 네이티브 wrap 으로 임시 처리 |
| Flutter 데스크톱 (특히 Windows) 미세 폴리싱 부족 | macOS 우선 검증, Windows 는 F9 에서 동작 확인만 |
| GGUF 모델 1.2GB 앱 번들 사이즈 | 첫 실행 시 다운로드 옵션 검토 (네트워크 필요 1 회) |
| 모바일 LLM 추론 시간 (S22U 7.3초/호출) | 의미 처리는 사용자 명시 트리거이므로 지연 허용. 자동저장은 LLM 미사용이라 무관 |
| LLM 정정 거짓 양성 | 별칭 보호 + 자모 거리 사전 필터 + 사용자 [적용] 클릭 필수 |
| `archive/synapse_engine_v15/` 가 v15 스키마라 v22 2차안과 불일치 | 코드는 인프라(llamadart·LoRA 핫스왑) 만 참고, 데이터 흐름은 새로 |

## 9. 롤백

- `feature/v22-rewrite` 브랜치 단위. `git checkout main` 으로 복귀
- 각 F 별 독립 커밋 — `git revert` 가능
- archive 이동 자체도 `git mv` 로 추적 — 필요 시 되돌리기 가능

## 10. 일정 감

- F0 (설계 정합): 1 덩어리 (별도 세션 권장 — 8 문서 정합 작업)
- F1~F2 (패키지 scaffold + DB): 1 덩어리
- F3~F5 (LLM·Graph·Flow): 1 덩어리 (백엔드 완결)
- F6 (앱 scaffold): 1 덩어리
- F7~F9 (UI 페이지 3개 — /note · /hypergraph · /synapse): 각 M 후 승인
- F10~F11 (검증·마무리): 1 덩어리

## 11. 이 PLAN 의 성공 조건

**v22 2차안 Flutter 재시작 완료 시 사용자는:**
- iOS / Android 폰에서 시냅스 앱 사용 (풀 오프라인 LLM)
- 같은 앱이 macOS 데스크톱에서도 동작 (한 코드베이스)
- `/note` 에서 한 줄 메모도 긴 마크다운도 자유롭게 기록, 자동저장으로 손실 걱정 없음
- ⌘S 로 의미 처리 트리거 — AI 가 오타 정정 후보를 카드로 제안 (별칭 정감 보존)
- `/synapse` 에서 질문, 통찰 승격
- 앱 간 데이터 격리 (시냅스 ≠ 갑질) — `synapse_engine` 패키지만 공유

**시냅스의 본질** — "말하면 쌓이고, 물으면 엮이고, 엮인 것이 다시 재료가 된다" — 이 모바일·데스크톱 풀 오프라인으로 실현된 상태가 이 PLAN 의 종착점.

---

## 참고 문서

- `docs/DESIGN_PRINCIPLES.md` — 원칙 9 (note 단일·자동저장/의미처리 분리), 13·14·15
- `docs/DESIGN_HYPERGRAPH.md` — 스키마 v22 2차안 (kind 3값)
- `docs/DESIGN_PIPELINE.md` — 의미 처리 파이프라인 + 자동저장 명세
- `docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md` — 세션 그릇 3 종 + LLM 호출 요약
- `docs/DESIGN_UI.md` — 2 라우트 와이어프레임
- `docs/DESIGN_REVIEW.md` — `insight_delete` (후속 PLAN)
- `docs/DESIGN_ENGINE.md` — `synapse_engine` 패키지 구조 (v15 시점, 2 계층 API 로 갱신 예정)
- `docs/DESIGN_APP.md` — 비서 앱 사양 (Flutter + llamadart, 디바이스 벤치마크, 파이프라인 최적화, 리스크 흡수)
- `archive/synapse_engine_v15/` — v15 Dart 엔진 (인프라 참고용)
- `archive/app_react_v21/` — v21 React 웹앱 (UX 참고용)
- `engine/`, `api/` — Python v22 1차안 frozen (참조 구현)

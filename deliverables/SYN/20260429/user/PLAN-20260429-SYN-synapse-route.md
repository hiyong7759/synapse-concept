# PLAN-20260429-SYN-synapse-route — `/synapse` 라우트 1차 구현

## 1. 목표

`/synapse` 라우트를 F9 스텁([app/lib/src/pages/synapse_page.dart](../../../../app/lib/src/pages/synapse_page.dart))에서 **인출·융합 세션 + 통찰 즉시 승격**이 동작하는 1차 기능으로 끌어올린다.

본 PLAN 범위 외 (별 PLAN):
- D 세션 그래프 패널 — 8-3 시리즈 안정화 후
- F BFS 탐색 시각화 (`◌ 탐색 중...` + `[이 방향 제외하기]`)

## 2. 전제 — 엔진은 이미 완비

| API | 시그니처 | 위치 |
|---|---|---|
| 인출 한 턴 | `SynapseFlow.synapseTurn({question, postId?}) → SynapseTurnResult{postId, answer, retrievedNodeIds, ...}` | [synapse_engine/lib/src/flow/synapse_flow.dart:76](../../../../synapse_engine/lib/src/flow/synapse_flow.dart#L76) |
| 통찰 승격 | `SynapseFlow.promoteToInsight({body, snapshotNodeIds, title?}) → InsightResult` | [synapse_engine/lib/src/flow/synapse_flow.dart:197](../../../../synapse_engine/lib/src/flow/synapse_flow.dart#L197) |
| 사이드바 그룹화 | `kind='synapse'` / `kind='insight'` | [app/lib/src/widgets/post_sidebar.dart:217,299](../../../../app/lib/src/widgets/post_sidebar.dart#L217) |

→ 앱 측 = **상태 어댑터 + UI 위젯**. 엔진은 빈 상태 추천 칩용 helper 1개(`recentTopNodes`) 추가만.

## 3. 사용자 결정 사항 (사전 합의)

- 통찰 승격 후 **즉시** 시각화에 ✦ 표시 (사이드바 + retrieve 캐시 그래프)
- BFS 탐색 시각화는 **별 마일스톤 (F)** 으로 분리, 본 PLAN 외
- **더미 stub 단계 폐지** — 마일스톤 A 와 B 를 통합해 처음부터 `synapseTurn()` 실 호출로 동작
- **빈 상태 = 동적 추천 칩** — 0 메시지일 때 사용자 자기 데이터 기반으로 칩 자동 생성. 결정론적 SQL (최근 7일 mention top 노드) → 4 패턴에 1:1 매핑. LLM 호출 없음(즉시 표시). 노드 0 일 땐 가이드 카드. 클릭 시 입력창에 자동 채움 (즉시 전송 아님)
- **칩 패턴 4 종**: `{X} 어떻게 진행돼?` / `{X} 최근 정리해줘` / `{X} 와 {Y} 가 어떻게 연결돼?` / `{X} 에 대해 내가 한 결정은?`
- 마일스톤 진행 순서: **AB(통합) → C → E**

## 4. 마일스톤

### 마일스톤 AB — Q/A 스레드 + 인출 파이프라인 wiring

- **목적**: 중앙 컬럼에 입력창·메시지 리스트·Q/A 카드 렌더 + 입력 → `synapseTurn()` 실 호출 → 답변 카드 갱신. 더미 단계 없이 처음부터 실 동작
- **변경 파일**:
  - 신규: `app/lib/src/state/synapse_state.dart` — 활성 postId·메시지 리스트·loading 상태. [note_state.dart](../../../../app/lib/src/state/note_state.dart) + [note_process.dart](../../../../app/lib/src/state/note_process.dart) 패턴 추종 (Riverpod, copyWith). 새 post/insight 발생 시 `postListProvider.invalidate()` 표준 패턴 사용
  - 신규: `app/lib/src/widgets/synapse_thread.dart` — 메시지 리스트 + 하단 입력 바 + 빈 상태 추천 칩. 입력 바는 [note_editor.dart](../../../../app/lib/src/widgets/note_editor.dart) 의 `TextEditingController` 패턴 차용
  - 신규: `app/lib/src/widgets/q_card.dart`, `a_card.dart` — Q/A 카드. [correction_card.dart](../../../../app/lib/src/widgets/correction_card.dart) 의 Container + padding/border + 액션 패턴 차용. 액션 버튼은 기존 `SButton`, 배지는 `SBadge` 직접 사용. 답변 카드의 `[⬆ 통찰로 승격]`/`[재질문]`/`[복사]` 자리는 슬롯만, wire 는 마일스톤 C
  - 신규: `app/lib/src/widgets/suggestion_chips.dart` — 빈 상태 동적 추천 칩. `recentTopNodes` 호출 → 4 패턴 매핑. 노드 0 시 가이드 카드 fallback. 클릭 시 입력창 controller 에 텍스트 채움
  - 수정: `synapse_engine/lib/src/flow/synapse_flow.dart` — `recentTopNodes({limit, daysBack})` helper 추가 (결정론적 SQL, LLM 의존 0)
  - 수정: `app/lib/src/pages/synapse_page.dart` — `_SynapseStub` → `SynapseThread` 로 교체
- **응답성**: `synapseTurn()` 5~10초 블록. UI 는 `loading` 상태로 입력 비활성화 + 진행 indicator 표시. await 비동기 처리(Dart Future 기본)로 main isolate 멈춤 없음. BFS 탐색 시각화는 F 마일스톤
- **검증**:
  - 빈 DB → 추천 칩 표시. 칩 클릭 → 입력창 채움 (자동 전송 X)
  - 입력 → 전송 → DB `posts.kind='synapse'` 행 + Q/A sentence 2 개 확인
  - 같은 세션 follow-up → 동일 postId 에 sentence 누적
  - LLM 미주입 환경 → fallback 답변 정상 표시
  - 호출 중 입력창 lockout + indicator 노출, 사이드바·스크롤은 동작 유지
  - 데스크톱·모바일 양쪽 dogfood (스크린샷)
  - 기존 `/note`, `/hypergraph` 라우트 회귀 없음
  - `flutter analyze` 클린
- **회귀 리스크**: 약함 (synapse_page 외부 영향 없음, 신규 state)
- **롤백**: 신규 파일 삭제 + page revert

### 마일스톤 C — 통찰 즉시 승격

- **목적**: `[⬆ 통찰로 승격]` → 확인 모달 → `promoteToInsight()` → **즉시 ✦ 표시**
- **변경 파일**:
  - 신규: `app/lib/src/widgets/promote_dialog.dart` — 확인 모달 (DESIGN_UI.md §통찰 승격). Flutter 표준 `AlertDialog` + `SButton` 액션 (취소/승격) 재사용
  - 수정: A 카드 위젯에 `[⬆ 통찰로 승격]` 액션 + state 의 즉시 갱신 hook
  - 수정: post_sidebar — 새 insight post 즉시 노출. `postListProvider.invalidate()` 트리거만 (B 의 표준 패턴 동일)
- **검증**:
  - 승격 → DB `kind='insight'` post + Hebbian `node_sentence_mentions` 행 확인
  - 사이드바 ✦ 즉시 표시 (수동 새로고침 없이)
  - 본체 sentence 편집 시도 → 토스트 차단
- **회귀 리스크**: insight 본체 편집 차단 로직이 다른 sentence 편집 흐름에 영향 안 주는지 확인 필요
- **롤백**: 가능. 단 승격된 post 는 사용자 명시 클릭이라 보존

### 마일스톤 E — PostSidebar 시냅스 섹션 점검

- **목적**: 이미 그룹화 코드가 있으니 **A·B·C 후 visual QA** — 공백·정렬·아이콘 누락만 보완
- **검증**: 노트·시냅스 양 라우트에서 사이드바 정상 (회귀)
- **회귀 리스크**: 매우 약함

## 5. 외부 검증 트리거

외부 의존성 추가 없음 (엔진 내부 API 호출). WebSearch 불필요.

## 6. 일정·승인 루프

- 마일스톤별 커밋 → 진행 보고 → 사용자 승인 후 다음 진입
- 평균 마일스톤 1 개당 30~60 분 예상

## 7. 브랜치

`feature/synapse-route` (현 `feature/v22-rewrite` 에서 분기) — 8-3 그래프 작업과 머지 충돌 분리.

# PLAN-20260429-SYN-synapse-perf — `/synapse` 인출 속도 개선

## 1. 목표

`synapseTurn()` 한 턴의 **체감 시간을 1~2초 수준으로 단축**. 실제 시간 단축(병렬화) + 체감 단축(스트리밍·진행 표시) 콤보. dogfood/테스트 사이클이 빨라지는 게 핵심 가치.

## 2. 사용자 결정 사항 (사전 합의)

- 본 PLAN-synapse-route 의 마일스톤 C(통찰 승격) · E(PostSidebar 점검) 는 **보류**
- 머지는 AB + 속도개선까지 묶어서 한 번에
- 마일스톤 진행 순서: **F → B → A → C**
- 브랜치: 같은 `feature/synapse-route` 연장 (별 분기 X)

## 3. 마일스톤

### 마일스톤 F — 측정 (Stopwatch)

- **목적**: 단계별 실제 시간 데이터 확보. 추측 말고 데이터로 다음 단계 결정
- **변경 파일**:
  - 수정: `synapse_engine/lib/src/flow/synapse_flow.dart` 의 `synapseTurn` 에 단계별 `Stopwatch` + 로그 (retrieve-expand · 노드 매칭+BFS · retrieve-filter · synapse-answer · DB 저장 5 구간)
- **검증**: 1 턴 실행 후 콘솔에 단계별 ms 출력. 가장 큰 병목 확정
- **회귀 리스크**: 없음 (로깅만)
- **롤백**: 1 커밋 revert
- **예상 시간**: 10~20분

### 마일스톤 B — 단계 indicator UI

- **목적**: 사용자가 진행 단계 인지 → 5초도 짧게 느낌. 노력 대비 체감 효과 가장 큼
- **변경 파일**:
  - 수정: `synapse_engine/lib/src/flow/synapse_flow.dart` — `synapseTurn` 에 `onProgress` 옵션 콜백 인자 추가 (단계 enum/string 전달)
  - 수정: `app/lib/src/state/synapse_state.dart` — `synapseLoadingProvider` → `synapseProgressProvider` (enum: `idle / expanding / matching / filtering / answering`)
  - 수정: `app/lib/src/widgets/synapse_thread.dart` — `_LoadingIndicator` 가 단계 텍스트 표시 (`🔑 키워드 추출`, `🕸️ 관련 문장 찾기`, `✍️ 답변 생성`)
- **검증**: 1 턴 실행 시 indicator 단계별 갱신
- **회귀 리스크**: 약함. `onProgress` 옵션 콜백이라 미주입 시 기존 동작 유지
- **롤백**: 1 커밋 revert
- **예상 시간**: 30~60분

### 마일스톤 A — 스트리밍 답변

- **선결 확인**: `llamadart` inference backend 의 토큰 스트림 API 노출 여부. 공식 문서/코드 확인 (외부 의존성 검증 필수, 모델 추측 금지)
- **목적**: synapse-answer LLM 출력을 토큰 단위로 받아 답변 카드에 글자가 차오르듯 표시. 첫 글자 1~2초
- **변경 파일** (선결 확인 통과 시):
  - `synapse_engine/lib/src/llm/inference_backend.dart` — 스트림 API 추가
  - `synapse_engine/lib/src/llm/tasks.dart` — `LlmTasks.synapseAnswer()` 가 `Stream<String>` 또는 `onToken` 인자
  - `synapse_engine/lib/src/flow/synapse_flow.dart` — partial text 진행
  - `app/lib/src/state/synapse_state.dart` — partial answer 누적, finalize 시 `SynapseAnswer` commit
  - `app/lib/src/widgets/a_card.dart` — partial 표시 vs finalized 구분
- **검증**: 답변 카드에 글자가 흘러나옴 (스트림)
- **회귀 리스크**: 중간. LLM 호출 시그니처 변경 → 다른 호출처 영향
- **롤백**: 가능. 단 시그니처 변경 분리 커밋 권장
- **예상 시간**: 1~2시간 (백엔드 지원 여부에 따라)

### 마일스톤 C — retrieve-filter 병렬화

- **목적**: BFS 결과 sentence 의 LLM 관련성 평가가 직렬 N회 → `Future.wait` 로 동시 실행. **3~4초 → 1초** 실제 단축
- **변경 파일**:
  - 수정: `synapse_engine/lib/src/graph/bfs.dart` 또는 호출부의 filter 루프 → `Future.wait`
- **검증**: 마일스톤 F 의 stopwatch 로 실제 단축 확인 (retrieve-filter 3초 → 1초 이하)
- **회귀 리스크**: 약함. 단 LLM 동시 호출 시 backend 큐잉 동작 확인 필요
- **롤백**: 1 커밋 revert
- **예상 시간**: 30~60분

## 4. 본 PLAN 외 (보류)

- PLAN-synapse-route 의 마일스톤 C (통찰 승격) — 우선순위 ↓
- PLAN-synapse-route 의 마일스톤 E (PostSidebar 점검) — 우선순위 ↓
- D 그래프 패널 / F BFS 시각화 — 기존대로 별 PLAN
- `sentences.created_at` 인덱스 — 마이크로 마일스톤 후보

## 5. 외부 검증 트리거

- `llamadart` 토큰 스트리밍 API — 마일스톤 A 진입 직전 공식 문서/코드 확인 (시간 시그널 + 외부 의존 시그널)

## 6. 일정·승인 루프

마일스톤별 커밋 → 진행 보고 → 사용자 승인 후 다음

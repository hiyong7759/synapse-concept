# F5b 진입 프롬프트 — SynapseFlow 인출 + 통찰 승격

> 새 세션 시작 시 이 프롬프트를 그대로 입력.

---

PLAN-20260425-SYN-flutter-rewrite 의 F5b 마일스톤 진입한다 (F5 분할의 인출 절반).

## 현재 상태

- 브랜치: `feature/v22-rewrite`
- 작업 디렉토리: `/Volumes/macex/workspace/claude-agentic-subagent-team/projects/synapse`
- 최근 커밋: `0e75f61` (F5a — SynapseFlow note autosave/process + 마크다운 파서 + 인칭대명사 시드)
- F1·F2·F3·F4·F5a 완료. 단위 103 통과 + 통합 6 스킵 (LLM 4 + Kiwi 2)

## F5b 명세 (PLAN §3 F5 row 의 인출 절반)

| 항목 | 내용 |
|---|---|
| 산출물 | `lib/src/graph/seed_matching.dart` (3 경로 시드 매칭) + `lib/src/graph/bfs.dart` 확장 (path 2/3) + `lib/src/flow/synapse_flow.dart` 에 `synapseTurn` + `promoteToInsight` 추가 |
| 검증 | `synapseTurn` 단위 (시드 매칭·3 경로 BFS·retrieve-filter LLM·synapse-answer 합성). `promoteToInsight` 단위 (kind='insight' post 생성 + retrieve 캐시 노드 일괄 mention + Kiwi 본체 노드 편입). F4 회귀 통과 |

## 단일 출처 문서

- `docs/DESIGN_PIPELINE.md` §인출 파이프라인 (3 경로 + 시간 정렬 + synapse-answer)
- `docs/DESIGN_ENGINE.md` §2.1 (SynapseFlow API) + §7 (promoteToInsight)
- `docs/DESIGN_HYPERGRAPH.md` §하이퍼엣지 ④ (통찰 허브, origin='insight')
- `docs/DESIGN_CATEGORY.md` §인접 맵 + §목적 (3 경로 정의)

## 누적 결정 사항 (이전 세션 합의)

### 어댑터 정책
- **시냅스 v22 본체는 어댑터 0 개**. 모든 LLM 태스크 (metaFilter·retrieveExpand·retrieveFilter·synapseAnswer + 후속 typoNormalize) 가 베이스 + 시스템프롬프트
- 근거: `deliverables/SYN/20260426/user/REPORT-20260426-SYN-adapter-removal-h1.md` (PoC v3 시스템프롬프트가 어댑터 동등 또는 우수)
- 어댑터 핫스왑 인프라(`LlamadartInferenceBackend.registerAdapter`/`swapAdapter`) 는 재사용 앱(갑질 등)용으로 보존

### save-pronoun 폐기
- LlmTasks.savePronoun 메서드 + SAVE_PRONOUN 시스템프롬프트 폐기 (`docs/archive/v22_retired/`)
- 자연어 날짜 부사·ISO 날짜는 `lib/src/internal/date_normalize.dart` 결정론 모듈 (Kiwi EF/EC 절 분리 + 반복 마커 보존)
- 지시어는 `unresolved_tokens` 매커니즘이 흡수

### 파인튜닝 분리
- 시냅스 본체에서 파인튜닝/학습 책임 제거. `DESIGN_FINETUNE.md` archive
- 재사용 앱 (갑질 등) 이 자기 도메인 어댑터를 학습할 경우 그쪽 자체 책임

### F5 분할
- F5a 완료: `noteAutosave` + `noteProcess` 6 단계 + 마크다운 파서 + 인칭대명사 11 시드
- F5b 진행 (이번 마일스톤): `synapseTurn` + `promoteToInsight` + 3 경로 시드 매칭

### typoNormalize stub
- F3 부터 stub (UnimplementedError). 별도 후속 마일스톤
- F5a 의 `NoteProcessResult.corrections` 는 빈 배열로 시작

### 갑질-style reuse 컨피그
- `reservedKinds: []` + `CategorySeed.empty()` → `engine.flow == null`. 인칭대명사 시드도 비활성화

## 진행 룰 (전역 CLAUDE.md)

1. 사전 조사 → 결과 보고 → 결정 받기 → 본 작업 사전 고지 → 사용자 승인 → 작업 → 마일스톤 커밋 → 진행 보고 → "ㄱ"/"진행"/"계속" 대기
2. 문서·PLAN 정정 필요 시 별도 commit 으로 분리하거나 명시적 사전 고지 후 한 commit
3. 마일스톤 단위 커밋 메시지 한국어
4. 한국어 사전 보고 — 작업 직전 한국어로 뭘 할지 고지 후 승인

## 보고 형식

```
✅ 완료: ...
📁 변경 파일: ...
➡️ 다음 단계: ...
🔍 검토 체크리스트:
  - 완결성
  - 회귀 리스크
  - 원칙 준수
  - 롤백 가능성
```

## 작업 시작

먼저 F5b 사전 조사:
1. Python `engine/retrieve.py` 의 3 경로 시드 매칭 (`_match_start_nodes` / `_match_start_categories` / heading 재귀 CTE)
2. retrieve-filter 호출 위치 + 시간 정렬 + synapse-answer 컨텍스트 조립
3. `promoteToInsight` 의 retrieve 캐시 스냅샷 매커니즘
4. `seed_matching.dart` API 시그니처 결정 (단일 함수 vs 분리)

조사 후 사용자 결정 받고 본 작업 사전 고지 → 승인 → 들어간다.

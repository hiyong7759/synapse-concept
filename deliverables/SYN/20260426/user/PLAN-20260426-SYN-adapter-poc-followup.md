# PLAN-20260426-SYN-adapter-poc-followup — retrieve-expand 어댑터 제거 PoC 후속 정리

**상태**: 작성 — 사용자 결정 대기
**의존**: PLAN-20260425-SYN-adapter-removal-poc 완료 (커밋 `074f928`)
**스키마 변경**: 없음

---

## 본 PoC 결론 요약

retrieve-expand 어댑터 제거 가능성 입증 (H1).

- v3 단순 시스템프롬프트로 base(Gemma 4 E2B) 가 어댑터와 동등 또는 우수
- C 차별화 의미 다리 5/5 (치과·양도세·무릎·박사 학위·결산)
- base 노이즈 0/45 / 어댑터 어간 잔재 노이즈 8~10건 — 어댑터가 오히려 손해
- 어댑터가 v2 프롬프트로 base 와 거의 동일 출력 → 어댑터 고유 가치 사라짐

미검증: H2(LIKE 매칭) · H3(모델 갈아끼기 일관성) — 환경 종속이라 후속 분리.

---

## 후속 분기

### F1 — 어댑터 제거 PR (즉시 시작 가능)

**작업**:
- `engine/llm.py` 의 retrieve_expand 어댑터 호출 경로 제거 → base 모델 직접 호출로 전환
- `api/mlx_server.py` 어댑터 로딩 분기 정리 (해당 경로 있다면)
- `data/finetune/models/tasks/retrieve-expand` 정리: 가중치 단일 백업으로 묶고 본체 제거 (회귀 시 복구용)

**보존**:
- 학습 데이터 `data/finetune/tasks/retrieve-expand/` 그대로 유지 (회귀 시 재학습 가능)
- 시스템프롬프트 v2 (`docs/RETRIEVE_EXPAND_SYSTEMPROMPT.md`) — 본 PoC 산출 그대로 활용

**회귀 검증**:
- 본 PoC 의 `/tmp/retrieve_expand_poc_45.csv` 와 PR 후 출력 비교
- 1줄도 다르면 안 되는 게 아니라, 의미 다리·노이즈 수준이 동일 또는 우수면 통과

**산출**:
- `engine/llm.py` 어댑터 분기 제거 diff
- 회귀 검증 보고서 (1쪽)

**예상 비용**: 코드 수정 30분 + 회귀 검증 10분 (Mac 추론)

---

### F2 — LIKE 매칭 인출 통합 (트리거: v22 Flutter 통합 + 사용자 실데이터)

**작업**:
- 기존 `_narrow_by_like` / `_extract_original_phrase_tokens` ([engine/retrieve.py:327-370](engine/retrieve.py#L327-L370)) 재사용
- 호출 위치만 추가: BFS 시드 단계에서 LLM 출력 phrase 를 sentences LIKE 매칭

**검증** (사용자 실데이터에서):
- LIKE 매칭 시드 개수 (질문당 평균)
- retrieve-filter 통과율
- synapse-answer 정성 평가 (dogfood 5건)

**트리거 조건**:
- v22 Flutter 앱이 사용자 실데이터를 적재할 수 있는 상태가 됨
- 사용자가 일정 기간 사용해 그래프가 의미있는 크기 (노드 ≥ 500, 문장 ≥ 200)

**산출**:
- `engine/retrieve.py` LIKE 호출 경로 추가 PR
- 검증 보고서 (`/tmp/retrieve_expand_like_poc.csv` + 정성 평가)

---

### F3 — 모델 카탈로그 UI + 갈아끼기 일관성 검증 (트리거: HF 환경 정비)

**작업**:
- HF_TOKEN 등록 (사용자 huggingface 계정에서 read 토큰 발급 → `~/.cache/huggingface/token` 또는 환경변수)
- 본 PoC 의 `/tmp/eval_retrieve_expand_models.py` 그대로 재실행 (Gemma 4 E2B / Qwen3-1.7B / Llama-3.2-3B)
- 결과로 카탈로그에 포함할 모델 셋 결정 (시스템프롬프트 호환·노이즈·속도 기준)
- 모델 카탈로그 UI 설계 (사용자가 모델 선택·전환 가능)

**검증 지표** (본 PoC 의 합격 기준 그대로):
- C 차별화 의미 다리 ≥ 80% (각 모델별)
- 노이즈 (단일 일반어 단독) ≤ 5%
- 모델 일관성 — 후보 셋의 출력이 의미적으로 비슷
- 모바일 한도 — 모델 ≤ 3B / 첫 토큰 ≤ 2s / 메모리 ≤ 2.5GB

**트리거 조건**:
- HF 토큰 등록됨
- 모델 카탈로그 UI 설계가 v22 Flutter 로드맵에 들어옴

**산출**:
- 모델 교차 검증 결과 (`/tmp/retrieve_expand_models.csv`)
- 모델 카탈로그 UI 설계 (별도 PLAN 또는 DESIGN 문서)

---

## 우선순위

| 순위 | PLAN | 트리거 | 비용 |
|---|---|---|---|
| 1 | F1 어댑터 제거 PR | 즉시 | 40분 |
| 2 | F3 모델 갈아끼기 검증 | HF 환경 (5분 사용자 작업) | 30분 |
| 3 | F2 LIKE 매칭 통합 | v22 통합 + 실데이터 | 알 수 없음 (실데이터 적재 시점 종속) |

---

## 학습 데이터 보존 정책

- `data/finetune/tasks/retrieve-expand/` (train.jsonl, valid.jsonl): **보존**
- `data/finetune/eval/retrieve_expand_poc_45.jsonl`: 본 PoC 평가셋, **보존** (F3 재실행에 그대로 사용)
- `data/finetune/models/tasks/retrieve-expand` 가중치: F1 에서 단일 백업으로 묶고 본체 제거 (디스크 회수)
- `runpod_output/mlx_adapters/retrieve-expand*` 여러 버전: F1 에서 정리 검토 (가장 최신 1개만 백업, 나머지 제거)

---

## 다른 어댑터로의 확장 (별도 본 PoC 필요)

본 PoC 는 **retrieve-expand 한 개**만 검증. 다른 어댑터 (`retrieve-filter`, `save-pronoun`, `extract-core` 등)는 각자 분포·작업 특성이 달라 동일 결론 보장 안 됨. 같은 절차의 별도 PoC 필요:

1. 시스템프롬프트 정교화
2. 분포별 평가셋 (45 케이스 권장)
3. base + 시스템프롬프트 vs 어댑터 비교
4. 합격이면 어댑터 제거 PR

이건 사용자 우선순위 따라 결정. 본 PoC 의 결론을 다른 어댑터로 자동 일반화하지 않음.

---

## 다음 행동

사용자가 우선순위에서 시작하고 싶은 작업 결정 후 해당 작업의 별도 PLAN 으로 분기. F1 은 즉시 시작 가능.

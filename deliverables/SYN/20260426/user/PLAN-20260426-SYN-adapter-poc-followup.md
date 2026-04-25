# PLAN-20260426-SYN-adapter-poc-followup — retrieve-expand 어댑터 제거 PoC 후속

**상태**: 작성 — 사용자 결정 대기
**의존**: PLAN-20260425-SYN-adapter-removal-poc 완료 (커밋 `074f928`)
**스키마 변경**: 없음

---

## 본 PoC 결론

retrieve-expand 어댑터 제거 가능성 입증 (H1).

- v3 단순 시스템프롬프트로 base(Gemma 4 E2B) 가 어댑터와 동등 또는 우수
- C 차별화 의미 다리 5/5 / base 노이즈 0/45 / 어댑터 어간 잔재 노이즈 8~10건
- 어댑터가 v2 프롬프트로 base 와 거의 동일 출력 → 고유 가치 사라짐

미검증: H2(LIKE 매칭) · H3(모델 갈아끼기) — 환경 종속.

---

## 어댑터 사용 경로 (코드 확인됨)

| 파일·라인 | 내용 |
|---|---|
| [engine/llm.py:121-128](engine/llm.py#L121-L128) | `retrieve_expand(question)` 함수 — `mlx_chat("retrieve-expand", f"질문: {question}")` 호출, 예외 시 `question.split()` 폴백 |
| [api/mlx_server.py:35-38](api/mlx_server.py#L35-L38) | `TASKS = ["retrieve-expand", "retrieve-expand-org"]` 리스트 |
| [api/mlx_server.py:29-30](api/mlx_server.py#L29-L30) | `ADAPTER_BASE = data/finetune/models/tasks` (`SYNAPSE_ADAPTER_BASE` 환경변수로 변경 가능) |
| [api/mlx_server.py:53-66](api/mlx_server.py#L53-L66) | `switch_adapter(task)` — `task=None` 이면 base 로드, 아니면 `ADAPTER_BASE/task` 어댑터 로드 |

가중치 디렉터리:
- `data/finetune/models/tasks/retrieve-expand/` — **MLX 서버가 실제 로드하는 곳** (약 120MB: adapter_config.json + 체크포인트 4개)
- `data/finetune/models/peft/retrieve-expand/` — peft 형식 변환본 (서버 미사용)
- `runpod_output/mlx_adapters/retrieve-expand`, `retrieve-expand-org`, `retrieve-expand_v1_noaug` — runpod 학습 산출물 여러 버전 (서버 미사용)
- `runpod_output/adapters/retrieve-expand`, `retrieve-expand-org` — 다른 형식 (서버 미사용)

학습 데이터:
- `data/finetune/tasks/retrieve-expand/{train,valid}.jsonl` — 회귀 시 재학습용

PoC 산출물:
- `data/finetune/eval/retrieve_expand_poc_45.jsonl` — 평가셋
- `docs/RETRIEVE_EXPAND_SYSTEMPROMPT.md` v2 — 본 PoC 산출 시스템프롬프트
- `docs/RETRIEVE_EXPAND_SYSTEMPROMPT.v1.md` — v1 백업

---

## 후속 분기

### F1 — 어댑터 제거 PR (즉시 시작 가능)

**코드 변경**:

1. `engine/llm.py:124` 의 `mlx_chat("retrieve-expand", ...)` 를 어댑터 없이 호출하도록 변경
   - `mlx_chat` 시그니처 확인 필요 (task=None 호출이 가능한지) — 본 PLAN 작성 시점엔 미확인
2. `api/mlx_server.py:35-38` `TASKS` 리스트에서 `"retrieve-expand"` 제거 (`"retrieve-expand-org"` 처리는 별도 결정)

**가중치 정리 (사용자 결정)**:

| 디렉터리 | 크기 | 권장 |
|---|---|---|
| `data/finetune/models/tasks/retrieve-expand/` | ~120MB | 단일 백업으로 묶고 본체 제거, 또는 그대로 두기 |
| `data/finetune/models/peft/retrieve-expand/` | 미확인 | 제거 후보 |
| `runpod_output/mlx_adapters/retrieve-expand*` 3개 | 미확인 | 정리 (가장 최신 1개만 백업) |
| `runpod_output/adapters/retrieve-expand*` 2개 | 미확인 | 정리 |

학습 데이터 (`data/finetune/tasks/retrieve-expand/`) 와 PoC 산출물은 **그대로 보존**.

**회귀 검증**:
- 본 PoC 의 `/tmp/retrieve_expand_poc_45.csv` 와 PR 후 출력 비교 — 의미 다리·노이즈 동일 또는 우수면 통과
- 비교 스크립트는 `/tmp/eval_retrieve_expand_poc.py` 그대로 사용

---

### F2 — LIKE 매칭 인출 통합 (트리거: v22 통합 + 사용자 실데이터)

**작업**:
- 기존 `_narrow_by_like` / `_extract_original_phrase_tokens` ([engine/retrieve.py:327-370](engine/retrieve.py#L327-L370)) 재사용
- 호출 위치만 추가: BFS 시드 단계에서 LLM 출력 phrase 를 sentences LIKE 매칭

**검증** (사용자 실데이터에서):
- LIKE 매칭 시드 개수 (질문당)
- retrieve-filter 통과율 (어댑터 제거 후 기준)
- synapse-answer 정성 평가

**트리거 조건**:
- v22 Flutter 앱이 사용자 실데이터를 적재할 수 있는 상태
- 사용자 그래프가 의미있는 크기로 누적됨

---

### F3 — 모델 카탈로그 UI + 갈아끼기 검증 (트리거: HF 환경 정비)

**HF 환경 문제**: 본 PoC 의 M5 단계에서 비인증 다운로드 rate limit 으로 Llama 3.2 3B / Qwen 3 1.7B 다운로드가 stuck. `HF_TOKEN` 환경변수 또는 `~/.cache/huggingface/token` 미설정 상태.

**작업**:
- HF 토큰 등록 (사용자 huggingface 계정 settings/tokens 에서 read 토큰 발급)
- 본 PoC 의 `/tmp/eval_retrieve_expand_models.py` 그대로 재실행 (Gemma 4 E2B / Qwen 3 1.7B / Llama 3.2 3B)
- 결과로 카탈로그에 포함할 모델 셋 결정
- 모델 카탈로그 UI 설계 (별도 PLAN)

**검증 지표**: 본 PoC 합격 기준 그대로 (C 의미 다리 ≥80% / 노이즈 ≤5% / 모델 일관성 / 모바일 한도 ≤3B).

---

## 다른 어댑터로의 확장 (별도 본 PoC 필요)

본 PoC 는 **retrieve-expand 한 개**만 검증. 코드에서 발견된 다른 어댑터 후보:

| 어댑터 | 위치 | 본 PoC 결론 적용? |
|---|---|---|
| retrieve-expand-org | `data/finetune/models/tasks/retrieve-expand-org/` (TASKS 에 등록), `runpod_output/.../retrieve-expand-org` | retrieve-expand 의 변형. 같이 정리 검토 |
| retrieve-filter | `runpod_output/.../retrieve-filter*` 여러 버전. `engine/llm.py:retrieve_filter_sentence` 에서 호출 | ❌ 자동 일반화 금지 — 별도 PoC 필요 |
| save-pronoun | `data/finetune/models/peft/save-pronoun/`, `data/finetune/tasks/save-pronoun/`(추정) | ❌ 별도 PoC 필요 |
| extract-* | `runpod_output/.../extract-*` 여러 종류, `data/finetune/models/peft/extract*` | ❌ 별도 PoC 필요 |

각 어댑터의 작업 분포·요구가 retrieve-expand 와 다를 수 있어 같은 결론 보장 안 됨. 같은 절차의 별도 PoC 가 필요:
1. 시스템프롬프트 정교화
2. 분포별 평가셋
3. base + 시스템프롬프트 vs 어댑터 비교
4. 합격이면 제거 PR

---

## 학습 데이터 보존 정책

- `data/finetune/tasks/retrieve-expand/{train,valid}.jsonl` — **보존**
- `data/finetune/eval/retrieve_expand_poc_45.jsonl` — **보존** (F3 재실행 그대로 사용)
- 가중치 디렉터리들 — F1 단계에서 사용자 결정 (단일 백업 정책)

---

## 다음 행동

사용자가 우선순위에서 시작할 작업 결정 후 해당 분기의 별도 PLAN 으로. F1 은 즉시 시작 가능.

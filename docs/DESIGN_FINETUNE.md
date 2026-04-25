# Synapse 설계 — 파인튜닝

## 작업 규칙 (이 문서의 모든 작업 전 필독)

**작업 원칙은 `docs/DESIGN_PRINCIPLES.md §7 파인튜닝 작업 원칙` 참고.**
(추측 금지 · MLX 우선/RunPod 폴백 · 환경 매번 검증 · 100 iters 소규모 검증 · 하이퍼파라미터 임의 변경 금지)

아래는 원칙을 실제 작업에 적용하는 체크리스트다.

### 실행 환경: MLX 우선, RunPod 폴백

기본 학습 환경은 **Mac M4 + MLX LoRA (로컬)**. 다음 경우에만 RunPod 사용:

| RunPod 폴백이 정당화되는 조건 | 이유 |
|---|---|
| 8B+ 모델 학습 | MLX 통합 메모리로 불가 또는 매우 느림 |
| 장시간(>24h) 학습 | 로컬 머신 점유 부담 |
| MLX 비호환 연산 필요 | 일부 커스텀 kernel, 분산 학습 |
| 대규모 병렬 실험 | 여러 GPU 동시 필요 |

MLX에서 먼저 시도 → 막히면 RunPod으로 이관. 반대 방향은 기본값이 아님.

### Phase 0: 설계 파악 (반드시 읽기)

- 이 문서(`DESIGN_FINETUNE.md`) — 태스크 구조, 하이퍼파라미터, 데이터 현황
- `scripts/mlx/train_all.py` — **MLX 학습 설정 (기본 경로)**
- `scripts/runpod/train_all.py` — RunPod 폴백 시에만 (TaskConfig 클래스)
- `scripts/runpod/README.md` — RunPod 사용법 (폴백 시)

### Phase 1: 환경 검증 루틴 (실행 전 필수)

문서의 설정이 현재 환경에서 유효한지 **매번** 확인. 하루만 지나도 바뀔 수 있다.

**MLX 환경 (기본):**
```
[ ] MLX 라이브러리 버전 확인
    - pip show mlx mlx-lm → MLX 업데이트 주기가 짧아 API 변경 잦음
    - 버전이 문서/스크립트 작성 시점과 다르면 changelog 확인
[ ] 모델/토크나이저 확인
    - 베이스 모델 HF 캐시 존재 여부
    - chat_template 변경 여부
[ ] 데이터 파일 존재 + 건수 확인
    - wc -l data/finetune/tasks/*/train.jsonl
    - 빈 파일, 0건 데이터 체크
[ ] 통합 메모리 여유 확인 (MLX)
    - 다른 프로세스의 메모리 점유량 (특히 MLX 서버가 이미 떠 있는지)
    - 활성 모니터 또는 vm_stat
[ ] 디스크 여유 확인
    - df -h ~
[ ] 기존 어댑터 백업
    - 재학습 전 _backup 또는 타임스탬프 보존
```

**RunPod 폴백 환경 (예외 시):**
```
[ ] 폴백 조건에 해당하는지 재확인 (위 표)
[ ] 라이브러리 버전 확인
    - pip show unsloth peft transformers trl
    - unsloth, trl은 API가 자주 바뀜 (deprecated 파라미터, 클래스 이동)
[ ] GPU/VRAM 확인
    - nvidia-smi (할당된 GPU 종류와 VRAM)
    - 이전 프로세스 잔류 VRAM 점유 여부
[ ] 디스크 여유
    - df -h /workspace
```

### Phase 2: 소규모 검증 (첫 실행 필수)

새 환경, 새 라이브러리 버전, 새 데이터에서는 반드시 **1개 태스크 100 iters**로 먼저 돌린다.

```
[ ] 100 iters 테스트 실행 (가장 작은 태스크)
[ ] train_loss 정상 감소 확인
[ ] eval_loss 트렌드 확인 (↓이면 정상, →이면 과적합 조짐)
[ ] 출력 포맷 확인 (MLX 추론 또는 GGUF 변환 후 실제 프롬프트 1건)
[ ] 문제 있으면 → 전체 학습 진행하지 말고 원인 분석
```

---

## 전제

- 모델: google/gemma-4-E2B (확정)
- 런타임 (학습): MLX (Mac M4 로컬, `unsloth/gemma-4-E2B-it-UD-MLX-4bit`)
- 런타임 (모바일·데스크톱 추론): llamadart 인프로세스 (Gemma 4 E2B-it 4bit GGUF)
- 런타임 (Python frozen 추론·dogfood): MLX 서버 (`api/mlx_server.py`, localhost:8765)
- 파인튜닝 도구: MLX LoRA
- 단일 모델 + 앱 번들 고정 정책. 학습된 어댑터를 GGUF 변환해 모바일·데스크톱 앱 번들 (`synapse_engine` 패키지의 `assets/adapters/`) 에 포함.

## 현행 태스크 처리 방식

Gemma 4 E2B-it + `enable_thinking=False` + 학습 데이터 system 메시지를 시스템 프롬프트로 주입하는 방식으로, 여러 태스크가 베이스 모델만으로 실용 수준 정확도에 도달함을 확인 (상세: `docs/DESIGN_PIPELINE.md` §"Gemma 4 thinking 모드 OFF").

| 태스크 | 처리 방식 | 용도 |
|--------|-----------|------|
| meta-filter | 베이스 + `docs/META_FILTER_SYSTEMPROMPT.md` | 게시물 단위 메타 대화 idx 판정 |
| save-pronoun | 베이스 + `docs/SAVE_PRONOUN_SYSTEMPROMPT.md` | 지시어·시간부사·주어 치환 |
| typo-normalize | 베이스 + `docs/TYPO_NORMALIZE_SYSTEMPROMPT.md` | LLM 정정 후보 생성 — 별칭 보호 + 자모 거리 사전 필터 통과 토큰 검증 |
| retrieve-filter | 베이스 + `docs/RETRIEVE_FILTER_SYSTEMPROMPT.md` | 인출된 문장의 질문 관련성 |
| retrieve-expand | 파인튜닝 어댑터 | 질문 → BFS 탐색 노드 후보 |
| synapse-answer | 베이스 + `docs/SYNAPSE_ANSWER_SYSTEMPROMPT.md` | 시냅스 한 턴 답변 합성 |
| category (백그라운드 워커) | 베이스 + `docs/CATEGORY_SYSTEMPROMPT.md` | 노드 카테고리 자동 분류 |

**현행 파인튜닝 어댑터 (학습·번들 활성)**: `retrieve-expand` 1 종.

---

## 데이터셋 설계

### 포맷 (Ollama fine-tune 기준)

```jsonl
{"messages": [
  {"role": "system", "content": "..."},
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
]}
```

### retrieve-expand: 인출 확장 (노드 후보 생성)

**시스템 프롬프트:**
```
당신은 지식 하이퍼그래프 검색 엔진입니다.
질문을 보고 하이퍼그래프에서 검색해야 할 관련 노드 후보를 생성하세요.
형태소 단위로 쪼개진 노드 이름으로 나열하세요.
출력 형식: ["노드1", "노드2", ...]
```

**예시 데이터:**
```jsonl
{"messages": [
  {"role": "system", "content": "당신은 지식 하이퍼그래프 검색 엔진입니다. 질문을 보고 검색해야 할 노드 후보를 형태소 단위로 나열하세요. 출력 형식: [\"노드1\", \"노드2\", ...]"},
  {"role": "user", "content": "질문: 언제 아팠지?"},
  {"role": "assistant", "content": "[\"허리\", \"아프\", \"감기\", \"두통\", \"병원\", \"낫\"]"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 하이퍼그래프 검색 엔진입니다. 질문을 보고 검색해야 할 노드 후보를 형태소 단위로 나열하세요. 출력 형식: [\"노드1\", \"노드2\", ...]"},
  {"role": "user", "content": "질문: 내가 좋아하는 음식 뭐야?"},
  {"role": "assistant", "content": "[\"좋아하\", \"음식\", \"먹\", \"맛있\", \"자주\"]"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 하이퍼그래프 검색 엔진입니다. 질문을 보고 검색해야 할 노드 후보를 형태소 단위로 나열하세요. 출력 형식: [\"노드1\", \"노드2\", ...]"},
  {"role": "user", "content": "질문: 지금 어디 살아?"},
  {"role": "assistant", "content": "[\"살\", \"이사\", \"집\", \"주소\", \"거주\"]"}
]}
```

---

## 학습 설정 (MLX)

학습된 어댑터는 GGUF 변환 (`scripts/convert_adapters.py`) 후 모바일·데스크톱 앱 번들에 포함. 모바일·데스크톱은 학습하지 않음 (재학습은 항상 MLX 환경에서).

### 공통 하이퍼파라미터 (모든 어댑터 동일)

| 파라미터 | 값 | 비고 |
|---------|-----|------|
| base model | unsloth/gemma-4-E2B-it-UD-MLX-4bit | MLX 4bit QLoRA |
| rank | 16 | |
| scale (alpha/rank) | 32.0 | |
| lora_dropout | 0.05 | |
| keys | self_attn.{q,k,v,o}_proj | attention only |
| num_layers | 8 | last 8 layers |
| batch_size | 1 | |
| grad_accumulation_steps | 4 | effective batch = 4 |
| learning_rate | 2e-4 | |
| max_seq_length | 2048 | |
| grad_checkpoint | true | |
| mask_prompt | true | 응답 토큰에만 loss |
| val_batches | 25 | |
| steps_per_report | 20 | |
| steps_per_eval | 100 | |
| save_every | 200 | |

설정 파일: `configs/mlx/_base.yaml`

### iters (어댑터별 자동 계산)

```
iters = max(150, (n_train × 3 epochs) // effective_batch)
      = max(150, (n_train × 3) // 4)
```

`scripts/mlx/train_all.py`의 `compute_iters()`가 각 task의 `train.jsonl` 건수로 계산.

| 어댑터 | n_train | iters |
|---|---|---|
| retrieve-expand | 468 | 351 |

### LoRA 파라미터는 공통, iters만 어댑터별

과거 실험에서 rank·scale·dropout 조정 시 전반적으로 성능 차이가 작거나 오히려 악화. **iters를 데이터 크기에 맞춰 자동 계산**하는 것이 가장 단순하고 효과적.

스크립트: `scripts/mlx/train_all.py`
어댑터 출력: `runpod_output/mlx_adapters/<task>/`
로그: `runpod_output/mlx_logs/<task>.log`
GGUF 변환: `scripts/convert_adapters.py` (MLX safetensors → HF PEFT 키 리매핑 → llama.cpp `convert_lora_to_gguf.py`)

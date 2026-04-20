# PLAN-20260420-SYN-001 — extract 어댑터 폐기 + 베이스 모델 + 시스템 프롬프트 전환

**상태**: 준비 완료, 실행 대기 (다른 세션용 핸드오프)

## 배경 — 왜 전환하는가

### 파인튜닝 실험 결과 (실패)

extract-core 어댑터를 v15 포맷으로 재학습 시도. 결과 요약:

| 시점 | Val loss | 72건 골드셋 정답률 |
|---|---|---|
| 100 iters (smoke) | 0.681 | 79.2% |
| 1278 iters (full) | 0.189 | **58.3%** ← 더 나빠짐 |
| 체크포인트 sweep (200/400/600/800/1000/1200) | — | 80.6% / 23.6% / 65.3% / 31.9% / 9.7% / **84.7%** |

**문제점:**
1. **학습이 춤춤** — 200 iters마다 정답률이 9.7% ~ 84.7%로 왕복. 일반적 수렴 곡선 아님
2. **Val loss와 실제 성능 미스매치** — Val 최저(0.104 @ 1200)였는데 58.3%로 하락
3. **데이터 재라벨 실험도 실패** — 빈 nodes 143건 보정 후 70.8%로 하락
4. **평가 골드셋 72건 자체가 작아 변동 노이즈 큼**

### 베이스 모델 + 시스템 프롬프트 전환 (성공)

Gemma 4 E2B 4bit 베이스 모델에 시스템 프롬프트만 주입해서 평가:

| 카테고리 | 파인튜닝 최고 (84.7%) | **베이스 + 프롬프트 (94.4%)** |
|---|---|---|
| FOD | 62.5% | **100%** |
| PER | 75% | **100%** |
| BOD | 50% | **100%** |
| HOB | 50% | **100%** |
| TRV | 100% | 100% |
| CUL | 100% | 100% |
| 1인칭 | 100% | 83.3% |
| 부정 | 50% | **100%** |
| **MND** | **0%** | **100%** |
| LAW | 75% | **100%** |
| WRK | 20% | 40% |
| MON | 0% | **100%** |
| 날짜 | 50% | **100%** |
| TEC | 83% | **100%** |
| **TOTAL** | **84.7%** | **94.4%** (**+9.7%p**) |

**결론**: 파인튜닝 완전 불필요. 베이스 + 시스템 프롬프트 + thinking 제거 파싱으로 **9.7%p 더 정확**.

### Gemma 4 특이사항

Gemma 4는 `<|channel>thought ... <channel|>{JSON}` 형태로 reasoning 블록을 먼저 출력한 뒤 JSON을 내놓는다. 파싱 시 thinking 블록 제거 후 마지막 `{...nodes...}` 패턴을 뽑아야 한다. (`scripts/mlx/eval_base_prompt.py`의 `extract_json` 로직 참고)

## 확정된 산출물

### 1) 시스템 프롬프트 (이미 커밋됨)

**경로**: `docs/EXTRACT_SYSTEMPROMPT.md`

WRK 약점(㈜ 법인 접두어, A프로젝트 고유명사)과 1인칭 통일(내/저/제 → "나") 규칙이 강화된 버전.

### 2) 평가 스크립트 (이미 커밋됨)

**경로**: `scripts/mlx/eval_base_prompt.py`

- max_tokens=1024
- thinking 블록 제거 후 JSON 추출
- `eval_extract_core.py`의 CASES 재사용
- 80건 기준 94.4% 확인됨 (실제 72건 골드셋)

## 다음 세션이 해야 할 작업 체크리스트

### A. 엔진 코드 수정

- [ ] **`engine/llm.py` — `llm_extract()` 수정**
  - 어댑터 호출(`mlx_chat("extract", ...)`) → 베이스 모델 호출(`mlx_chat("chat", ...)`)로 전환
  - 시스템 프롬프트는 `docs/EXTRACT_SYSTEMPROMPT.md` 파일을 읽어 주입
  - thinking 블록 제거 파싱 추가 (`eval_base_prompt.py`의 `extract_json` 참고)
  - max_tokens=1024로 상향
  - deactivate 필드는 별도로 `extract-state` 어댑터 유지 (이건 아직 파인튜닝)

- [ ] **`api/mlx_server.py` TASKS 정리**
  - `extract`는 제거 (베이스 모델로 처리)
  - `extract-state`는 유지

- [ ] **시스템 프롬프트 주입 방식 통일**
  - `CATEGORY_SYSTEMPROMPT.md`, `EXTRACT_SYSTEMPROMPT.md` 같은 프롬프트 파일을 어떻게 읽어들일지 공통 헬퍼 도입 권장
  - 후보: `engine/prompts.py`에 로더 함수 추가

### B. 데이터·어댑터 정리

- [ ] **`data/finetune/tasks/extract-core/` → `archive/finetune/tasks/extract-core/`** 이동 (git mv)
  - train.jsonl, valid.jsonl, *.pre-v15-backup, *.pre-relabel-backup, *.relabeled 모두 이관
  - save-state 이동(A1)과 같은 방식

- [ ] **`runpod_output/mlx_adapters/extract-core*` 정리**
  - `extract-core_pre-v15-backup-20260419`, `extract-core_v15-v1`, `extract-core`(현재 = 재라벨 100iter) 등
  - 운영에선 불필요. 로컬 보존하고 싶으면 별도 backup 경로로 묶음

- [ ] **`scripts/mlx/train_all.py`의 태스크 discover 로직**
  - `extract-core/` 디렉토리가 archive로 빠지면 자동으로 대상에서 제외됨 (별도 수정 불요)

- [ ] **`scripts/mlx/relabel_empty_nodes.py`, `scripts/mlx/convert_extract_core_v15.py`** — 실험 흔적 정리
  - 유지해도 무해. 이력 문서화를 위해 보존 권장

### C. 설계 문서 갱신

- [ ] **`docs/DESIGN_FINETUNE.md`** — extract 관련 섹션
  - Task 6A (extract-core) 섹션을 "**폐기** — 베이스 모델 + 시스템 프롬프트로 전환"으로 정리
  - 근거: 파인튜닝 실패·베이스 94.4% 결과 요약 삽입
  - 데이터셋 summary 표에서 extract-core 표시 업데이트 (archive로 이동 명시)

- [ ] **`docs/DESIGN_PIPELINE.md`** — 저장 파이프라인
  - "`[synapse/extract]` 어댑터 호출" 섹션을 "**베이스 모델 + `docs/EXTRACT_SYSTEMPROMPT.md`** 주입"으로 변경
  - 어댑터 구성표 업데이트: `synapse/extract`를 제거하고 "extract는 베이스 모델로 처리" 노트 추가

- [ ] **`docs/DESIGN_HYPERGRAPH.md`** — 필요 시 업데이트
  - 어댑터 의존성 언급이 있으면 현행화

- [ ] **`docs/DESIGN_ENGINE.md`** — 엔진 포팅 설계
  - `extract-core` 어댑터 참조를 베이스 모델 프롬프트 방식으로 수정

### D. 검증

- [ ] **엔진 수정 후 `eval_extract_core.py` 또는 `eval_base_prompt.py` 재실행**으로 94% 대 유지 확인
- [ ] **WRK 보강된 프롬프트(EXTRACT_SYSTEMPROMPT.md)로 실제 재평가** — 현재 94.4%는 보강 전 프롬프트 기준. 보강 후 96~98% 기대
- [ ] **실제 사용 플로우 E2E 테스트** — 문장 입력 → engine.cli 또는 API로 저장 → DB에 노드가 정확히 들어가는지

### E. 커밋 정책 (다른 세션 참고)

- 코드 수정은 `feature/extract-prompt-transition` 같은 별도 브랜치에서
- 문서 수정은 main에 직접 가능
- 이 PLAN 문서는 실행 시작 시 `deliverables/SYN/20260420/agent/` 쪽에 진행 보고용 파일 생성해서 상태 추적

## 현재 상태 (2026-04-20 기준)

- `main` 브랜치: 최신 커밋 이미 push됨
- 시스템 프롬프트 파일: `docs/EXTRACT_SYSTEMPROMPT.md` 커밋됨
- 평가 스크립트: `scripts/mlx/eval_base_prompt.py` 커밋됨
- 파인튜닝 어댑터: 로컬 `runpod_output/mlx_adapters/`에만 존재 (git 외)
- 학습 데이터: `data/finetune/tasks/extract-core/`에 v15 포맷(재라벨된 상태로) 커밋됨

## 성공 기준

- 엔진 수정 후 동일 72건 골드셋에서 **94% 이상** 유지
- WRK 도메인 50% 이상 (현재 40%에서 프롬프트 보강으로 개선)
- 저장 → 인출 → 응답 전체 플로우에서 노드가 의도대로 추출됨
- 실행 시간 허용 수준 (샘플당 4~8초, 필요 시 후속 최적화)

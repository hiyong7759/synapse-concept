# PLAN-20260425-SYN-adapter-removal-poc — retrieve-expand 어댑터 제거 검증 PoC

**상태**: 작성 중 (사용자 승인 대기)
**의존**: 없음 (현행 retrieve-expand 어댑터·BFS 인프라 그대로 시작)
**스키마 변경**: 없음

---

## 배경 — 왜 어댑터를 빼려는가

**원칙 11 (지능체는 분리되어 있다)** 에 충실하려면 시냅스가 특정 모델/어댑터에 고정돼서는 안 된다. 사용자는 Gemma·Qwen·Phi·Claude API 등을 자유롭게 갈아 끼울 수 있어야 한다. 어댑터가 있으면 모델 바뀔 때마다 재학습이 필요하고, 결과 시냅스의 운영 부담·모델 이식성이 모두 떨어진다.

**2026-04-25 분포별 비교 결과** (스크립트: `/tmp/eval_retrieve_expand_distribution.py`, 산출: `/tmp/retrieve_expand_dist.csv`)

| 구간 | base + 시스템프롬프트 | 어댑터 |
|---|---|---|
| A — in-distribution (5건) | 토큰 분리 위주, 도메인 확장 약함 | 도메인 확장 양호 |
| B — 아주 일반 (5건) | 키워드 폭발(15~18개) | 절제 + 조사 노이즈 |
| C — 아주 차별화 (5건) | **의미 다리 압승** (충치·보철·임플란트·재무제표·심박수) | **입력 토큰 형태소 분해 + 약한 확장** |

치과 예시 직격: "이가 시려서 그러는데 치과 어디가 좋아"
- base: `…, 임플란트, 보철, 충치 치료` ✓ (사용자가 원한 다리)
- adapter: `이가, 시리, 치과, 치료, 통증, 어디` ✗ (입력 분해)

**가설**: 베이스 모델의 의미 확장 + 시스템프롬프트 정교화 + LIKE 매칭으로 어댑터 대체 가능.

---

## 인출 파이프라인 (PoC 제안)

```
질문
  ↓
[1] LLM base + 정교화 시스템프롬프트 (의미 확장, 자연어 noun phrase 허용)
  ↓
[2] LLM 출력 그대로 sentences.text LIKE 매칭          ← kiwi 분해 미사용
      "충치 치료" → sentences LIKE '%충치 치료%' → 그 문장에 언급된 노드를 시드
  ↓
[3] BFS 인출 (aliases 자동 매칭, engine/retrieve.py:89-114 이미 작동)
```

**kiwi 분해를 의도적으로 빼는 이유**: "충치 치료" → ["충치", "치료"] 처럼 자르면 "치료" 가 너무 일반적이라 무관한 노드까지 끌어옴. 의미가 강한 noun phrase 가 그대로 보존돼야 인출이 정확하다. LIKE 매칭은 `engine/retrieve.py:319` 에 후처리 메커니즘으로 이미 존재 — 메인 경로로 승격시키는 그림.

---

## 가설

| ID | 가설 | 검증 마일스톤 |
|---|---|---|
| H1 | 시스템프롬프트 + few-shot 으로 base 노이즈(과잉 확장·영어 혼재·고유명사 폭주)를 어댑터 수준으로 절제 가능 | M1·M3 |
| H2 | LLM 출력을 그대로 sentences LIKE 매칭하면 kiwi 분해 없이 BFS 시드로 충분 | M4 |
| H3 | 2~3 개 모델(Gemma·Qwen·Phi)에서 일관 품질 — 모델 자유 가능성 | M5 |

---

## 마일스톤

### M1 — 시스템프롬프트 정교화

- `docs/RETRIEVE_EXPAND_SYSTEMPROMPT.md` v2 작성
- few-shot 7건: in-distribution 2 + 일반 2 + 차별화(치과·법률·마라톤) 3
- **모델 자유 극대화 원칙** — 그래프가 자연 필터. 출력 cap·한국어 강제·고유명사 금지·변형 반복 금지 모두 제거
- 남은 규칙 두 줄: ①자연어 명사구 출력 ②단음절 일반어 단독 출력 금지(복합어 OK)
- 산출: `docs/RETRIEVE_EXPAND_SYSTEMPROMPT.md` v2 (백업: `RETRIEVE_EXPAND_SYSTEMPROMPT.v1.md`)

### M2 — PoC 평가셋 확장 (15 + 30 = 45)

- 기존 15건: A/B/C 5건씩 (2026-04-25 실험에서 사용)
- 신규 30건: 도메인 다양화
  - 의료 5 (이가 시리다·두통·운동 부상 등)
  - 법률·세무 5 (퇴직금·연차·세금공제 등)
  - 금융·회계 5 (결산·대출·재무 등)
  - 운동·건강 5 (마라톤·헬스·식단 등)
  - 학습·진로 5 (양자컴퓨터·자격증·이직 등)
  - 일상·여행 5 (여행·취미·가족 등)
- 산출: `data/finetune/eval/retrieve_expand_poc_45.jsonl`

### M3 — base + 새 프롬프트 vs 현 어댑터 비교

- 동일 시스템프롬프트 v2 로 base / 어댑터 모두 돌림 (어댑터에 새 프롬프트 적용 시 영향도 같이 측정)
- 출력 비교 + 정성 평가 (눈으로 합격/불합격)
- 산출: `/tmp/retrieve_expand_poc_45.csv` (질문·base_list·adapter_list·judgement)

### M4 — LIKE 매칭 인출 PoC (보류 — 후속 PLAN 으로 분리)

**보류 사유**: M4 검증의 핵심(LIKE 매칭 시드 개수·retrieve-filter 통과율·synapse-answer dogfood)은 모두 사용자 그래프 데이터에 종속. 현재 v22 마이그레이션으로 DB 비어 있고, 인위적 시드는 사용자 도메인을 모방 못해 검증 신뢰도 낮음. 어댑터 제거 결정의 본질은 "LLM 출력 자체가 충분한가" 인데 M3 에서 이미 입증.

**후속 PLAN 으로 미루는 작업**:
- 기존 `_narrow_by_like` 재사용해서 LLM phrase 를 BFS 시드 단계에 LIKE 매칭 추가
- 사용자 실데이터 적재 후 시드 개수·retrieve-filter 통과율·dogfood 측정
- 트리거: v22 Flutter 통합 + 사용자 사용 시작

### M5 — 모델 교차 검증 — **보류 (HF 환경 문제 + 사용자 결정)**

**보류 사유**: HF 비인증 다운로드 rate limit 으로 Llama 3.2 3B / Qwen 3 1.7B 다운로드가 반복적으로 stuck. 환경 정비(HF_TOKEN 등) 필요. 사용자 결정으로 본 PoC 의 핵심 목적인 "어댑터 제거 가능성" 만 결론 짓고 모델 갈아끼기 검증은 분리.

**부분 결과**:
- Gemma 4 E2B 단독 출력 확보 (`/tmp/retrieve_expand_models.csv`) — M3 와 동일 결과 재확인
- Llama·Qwen 미수행

**후속 PLAN 으로 분리**: HF 환경 정비 후 모델 카탈로그 UI 설계 단계에서 같이 검증. 검증 자체는 사용자 환경(토큰)이 갖춰지면 본 PoC 스크립트 (`/tmp/eval_retrieve_expand_models.py`) 그대로 재사용 가능.

### M6 — 결정: **어댑터 제거 합격 (H1 단독 입증)**

**결정 근거 (M3 결과)**:
- v3 시스템프롬프트로 base(Gemma 4 E2B) 가 어댑터와 동등 또는 우수
  - C(차별화) 의미 다리 5/5 (치과 → 충치·보철·시린이, 양도세 → 취득가액·양도가액·비과세, 무릎 → 정형외과·인대 손상 등)
  - 노이즈 0/45 (단일 일반어 단독 출력 없음)
- **어댑터에 어간 잔재 노이즈 8~10건** (`먹·올리·따·아프·결림·키우`) — 학습 분포의 형태소 패턴이 살아남은 부작용. 어댑터가 오히려 해로움 증명
- 어댑터가 v2 프롬프트로 base 와 거의 동일 출력 → 어댑터 고유 가치 사라짐

**합격 후 액션**:
- retrieve-expand 어댑터 제거 PR 가능 (`engine/llm.py` 어댑터 호출 경로 제거, `data/finetune/models/tasks/retrieve-expand` 정리)
- 학습 데이터 `task4_retrieval_expand.jsonl` 은 **보존** (회귀 시 복구용)
- LIKE 매칭 인출 통합 PoC (M4 보류분) 후속 PLAN
- 모델 카탈로그 UI + 모델 갈아끼기 검증 (M5 보류분) 후속 PLAN

**미검증 항목 (후속)**:
- H2 (LIKE 매칭) — v22 통합 + 사용자 실데이터 후
- H3 (모델 갈아끼기 일관성) — HF 환경 정비 후

---

## 합격 기준

**품질**

| 항목 | 임계 |
|---|---|
| C(차별화) 구간 의미 다리 잡힘 비율 | ≥ 80% (15건 중 12건) |
| 노이즈(단음절·단일 일반어 단독 출력 — 방법·것·정도 등) | ≤ 5% (45건 중 2건) |
| 모델 일관성 | ⏳ 보류 (M5 HF 환경 문제) — 후속 PLAN |

**모바일 (Mac M4 대리 측정) — ⏳ 보류 (M5 와 함께 후속)**

| 항목 | 임계 |
|---|---|
| 모델 크기 | ≤ 3B (4bit 양자화 후 모델 파일 ≤ 2GB) |
| 첫 토큰 응답 | Mac M4 기준 ≤ 2s |
| 출력 완료 | Mac M4 기준 ≤ 5s (45 케이스 중앙값) |
| 메모리 점유 | 모델 + 컨텍스트 RAM ≤ 2.5GB |

Gemma 4 E2B 단독 측정값: 로드 3.6s · 추론 중앙값 1.3s/건 (45 케이스) · 빈 출력 0건.

---

## 산출물 목록

- `docs/RETRIEVE_EXPAND_SYSTEMPROMPT.md` v2 (+v1 백업)
- `data/finetune/eval/retrieve_expand_poc_45.jsonl`
- `engine/retrieve.py` 의 LIKE 호출 경로 추가 (기존 `_narrow_by_like` 재사용, 신규 함수 X)
- `/tmp/retrieve_expand_poc_45.csv` (M3 비교)
- `/tmp/retrieve_expand_like_poc.csv` (M4 LIKE 비교)
- `/tmp/retrieve_expand_poc_models.csv` (M5 모델 교차)
- 의사결정 보고서 (`deliverables/SYN/20260425/user/REPORT-...md`) — 합격/불합격 + 근거 + 다음 단계

---

## 범위 명시 — 이 PoC가 검증하지 않는 것

- **다른 어댑터 제거** (retrieve-filter, save-pronoun, sensitivity 등)는 이 PLAN 범위 외. 이번 PoC 결과를 보고 별도 PLAN 으로 다룬다.
- **모델 카탈로그 UI 구현**도 범위 외. 합격 시 트리거되는 후속 PLAN.
- **GGUF 변환·Ollama 통합**도 범위 외. 현재는 MLX 기준으로 검증.

---

## 위험 요소

- **베이스 모델이 한국어 noun phrase 를 일관되게 못 뽑을 수 있음** — M3 에서 드러나면 시스템프롬프트 추가 정교화로 대응
- **LIKE 매칭이 너무 좁아서 시드가 거의 안 잡힐 수 있음** — M4 에서 빈 결과 비율이 높으면 폴백 (phrase LIKE 빈 결과 → word-level LIKE 또는 alias 매칭) 추가 검토
- **모델별 출력 형식 일관성 부족** — Qwen·Phi 가 JSON 배열 출력을 안 따를 수 있음. 시스템프롬프트에 형식 강제 + 파서 견고성 보강

---

## 다음 행동 — 사용자 승인 후

M1 부터 순차 진행. 마일스톤마다 보고 후 "ㄱ"·"진행"·"계속" 받으면 다음 단계.

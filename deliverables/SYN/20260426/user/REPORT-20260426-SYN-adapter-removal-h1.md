# REPORT-20260426-SYN-adapter-removal-h1 — H1 검증 결과

**대상 PLAN**: PLAN-20260425-SYN-adapter-removal-poc
**관련 커밋**: f5c6390 (M1·시스템프롬프트 v2) · a27ed25 (M2·평가셋 45) · 074f928 (M6 결정)
**작성일**: 2026-04-26

---

## 가설 H1

> **시스템프롬프트 + few-shot 으로 베이스 출력의 노이즈(과잉 확장·영어 혼재·고유명사 폭주)를 어댑터 수준으로 절제 가능 — 즉 retrieve-expand 어댑터를 시스템프롬프트로 대체할 수 있다.**

검증 목적: 어댑터 없이 base + 시스템프롬프트만으로 시냅스 retrieve-expand 작동 가능한가.

---

## 검증 방법

**모델**:
- base: Gemma 4 E2B (`unsloth/gemma-4-E2B-it-UD-MLX-4bit`, MLX 4bit)
- adapter: 같은 base + retrieve-expand LoRA (`data/finetune/models/tasks/retrieve-expand/`)

**시스템프롬프트** (`docs/RETRIEVE_EXPAND_SYSTEMPROMPT.md` v2):
- 규칙 두 줄: ① 자연어 명사·명사구 출력(형태소 분해 X) ② 단음절 일반어 단독 출력 금지(복합어 OK)
- few-shot 7건 (in-distribution 2 + 일반 2 + 차별화 3)

**평가셋** (`data/finetune/eval/retrieve_expand_poc_45.jsonl`):
- 9 bucket × 5 케이스 = 45건
- A in-distribution / B 일반 / C 차별화(기존 PoC) / D 의료 / E 법률·세무 / F 금융 / G 운동 / H 학습·진로 / I 일상·여행

**스크립트**:
- 분포별 비교 (구간 A/B/C 15건): `/tmp/eval_retrieve_expand_distribution.py` → `/tmp/retrieve_expand_dist.csv`
- 확장 비교 (45건, v2 프롬프트 통일): `/tmp/eval_retrieve_expand_poc.py` → `/tmp/retrieve_expand_poc_45.csv`

---

## 결과

### 정량 지표

| 지표 | base + v2 프롬프트 | adapter + v2 프롬프트 |
|---|---|---|
| C 차별화 (구간 C) 의미 다리 잡힘 | 5/5 | 5/5 |
| 단일 일반어 단독 출력 노이즈 (전체 45건) | 0건 | — (어간 잔재 노이즈 별도) |
| 어간 잔재 노이즈 (`먹·올리·따·아프·결림·키우` 등) | 0건 | 8~10건 |
| 출력 개수 분포 (45건) | 5~11 | 5~8 |
| 빈 출력 | 0/45 | — |

### 주요 출력 비교 (인용 — `/tmp/retrieve_expand_poc_45.csv`)

| 질문 | base | adapter |
|---|---|---|
| 이가 시려서 그러는데 치과 어디가 좋아 | `치과·충치·보철·치아·시린이·치료` | `치과·시린이·치료·보철·충치·통증` |
| 마라톤 풀코스 처음 뛰는데 페이스 조절 어떻게 해 | `마라톤·풀코스·페이스·페이스조절·페이스감각·달리기·훈련·심박수` | `마라톤·풀코스·페이스·페이스조절·달리기·훈련·심박수·초반` |
| 부동산 양도세 계산 어떻게 하지 | `부동산·양도세·계산·세금·취득가액·양도가액·비과세·장기보유특별공제·세금 계산 방법` | `양도세·부동산·계산·세금·취득·보유·양도·비과세` |
| 헬스 처음인데 3대 운동부터 해야 해 | `헬스·운동·3대 운동·스쿼트·벤치프레스·데드리프트·초보자·운동 루틴·근력 운동·자세` | `헬스·3대 운동·스쿼트·벤치프레스·데드리프트·초보` |
| 위염인 것 같은데 뭐 먹으면 안 돼 | `위염·음식·피해야 할 음식·식단·소화·자극적인 음식·기름진 음식·맵고 짠 음식·산성 음식·과일·채소` | `위염·먹·음식·피해야 할·음식·자극` |

### 어댑터 어간 잔재 노이즈 (구체 사례)

`/tmp/retrieve_expand_poc_45.csv` 의 adapter_list 에서 발견:
- "오늘 점심 뭐 먹지?" → `…먹…` (단음절 어간)
- "신용점수 올리려면 뭐부터 해야 해" → `…올리…`
- "AWS 자격증 어떤 거부터 따야 해" → `…따…`
- "무릎이 자주 아픈데 어디 가야 해" → `…아프…`
- "어깨가 결리는데 운동으로 풀 수 있나" → `…결림…`
- "강아지 처음 키우는데 준비물 뭐 있어" → `…키우…`
- "위염인 것 같은데 뭐 먹으면 안 돼" → `…먹·피해야 할…` (조각 형태소)

base 의 동일 케이스에서는 모두 자연어 명사구로 출력 (형태소 조각 없음).

---

## 핵심 발견

1. **단순화된 v2 프롬프트로 base 노이즈가 잡힘** — cap·한국어 강제·고유명사 금지 같은 추가 규칙 없이 "자연어 명사구" + "단일 일반어 단독 금지" 두 줄로 충분.
2. **base 가 의미 다리를 일관되게 잡음** — C 차별화 + D~I 6 도메인 (의료·법률·금융·운동·학습·일상) 모두에서 도메인 키워드(LTV·DTI·키토시스·항히스타민제·취득가액·SAA-C03 등) 자연스럽게 출력.
3. **어댑터의 학습 분포 부작용** — v3 프롬프트로도 어간 잔재 노이즈가 살아남음. 학습 시 "형태소 단위 노드" 패턴이 박혀서 자연어 명사구 지시를 완전히 따르지 못함. 어댑터가 base 보다 손해.
4. **동등 케이스도 다수** — 도커·마라톤 등 in-distribution 케이스에서 base 와 어댑터 출력이 거의 동일 → 어댑터 고유 가치 사라짐.

---

## 결정

**H1 합격 — retrieve-expand 어댑터 제거 가능.**

근거:
- 합격 기준 (PLAN 합격 기준 표):
  - C 차별화 의미 다리 잡힘 비율 ≥ 80% → base 5/5 = 100% ✓
  - 노이즈(단음절·단일 일반어 단독 출력) ≤ 5% → base 0/45 = 0% ✓
- 추가 발견: 어댑터 유지가 오히려 어간 잔재 노이즈로 손해

---

## 한계 — 본 보고서가 검증하지 않은 것

- **H2 (LIKE 매칭 인출)**: 사용자 실데이터에 LLM 출력 phrase 를 LIKE 매칭한 시드 개수·통과율·dogfood 미검증. 본 PoC 는 v22 마이그레이션으로 DB 비어 있어 보류, 후속 PLAN 으로 분리.
- **H3 (모델 갈아끼기 일관성)**: HF 비인증 다운로드 rate limit 으로 Llama 3.2 3B / Qwen 3 1.7B 다운로드 실패, 본 보고서는 Gemma 4 E2B 단독 결과. 후속 PLAN 으로 분리.
- **다른 어댑터 (retrieve-filter, save-pronoun, extract-* 등)**: 본 보고서 결론은 retrieve-expand 한 개에만 적용. 자동 일반화 금지.

---

## 다음 단계

PLAN-20260426-SYN-adapter-poc-followup 의 분기 참고:
- **F1 어댑터 제거 PR** (즉시 시작 가능)
- F2 LIKE 매칭 통합 (v22 통합 + 사용자 실데이터 후)
- F3 모델 카탈로그 + 갈아끼기 검증 (HF 환경 정비 후)

---

## 산출물 (재현 가능)

| 항목 | 위치 |
|---|---|
| 시스템프롬프트 v2 | `docs/RETRIEVE_EXPAND_SYSTEMPROMPT.md` (커밋 f5c6390 + 096b75b) |
| 시스템프롬프트 v1 백업 | `docs/RETRIEVE_EXPAND_SYSTEMPROMPT.v1.md` |
| 평가셋 45건 | `data/finetune/eval/retrieve_expand_poc_45.jsonl` (커밋 a27ed25) |
| 비교 스크립트 | `/tmp/eval_retrieve_expand_poc.py` |
| 비교 결과 (45건) | `/tmp/retrieve_expand_poc_45.csv` |
| 분포별 비교 (15건, 초기) | `/tmp/retrieve_expand_dist.csv` |
| 어댑터 가중치 | `data/finetune/models/tasks/retrieve-expand/` |
| 학습 데이터 | `data/finetune/tasks/retrieve-expand/{train,valid}.jsonl` |

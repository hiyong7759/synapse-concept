# Synapse 설계 — 파인튜닝

## 전제

- 모델: google/gemma-4-E2B (확정)
- 런타임: MLX 서버 (로컬, api/mlx_server.py — localhost:8765)
- 파인튜닝 도구: MLX LoRA (unsloth/gemma-4-E2B-it-UD-MLX-4bit)
- 목적: 한국어 형태소 기반 트리플 판단에서 2B 모델의 한계를 보정

## 파인튜닝 타겟 (7개)

대화 페르소나는 시스템 프롬프트로 제공. 파인튜닝 불필요.
별칭 제안은 일반 모델로 충분. 파인튜닝 불필요.

| # | 태스크 | 입력 | 출력 | 목표 수량 |
|---|--------|------|------|-----------|
| ~~1~~ | ~~상태 변경 감지~~ | — | — | **폐기** — Task 6 deactivate 필드로 통합 |
| 2 | 대명사/부사/지시어 구체화 | 입력 텍스트 + 대화 맥락 | 치환된 텍스트 or 사용자 질문 | 500건 |
| 3 | 인출 필터 | 관계(source—label—target) + 질문 | pass / reject | 800건 |
| 4 | 인출 확장 | 질문 | 관련 노드 후보 목록 | 400건 |
| 5A | 관계 민감도 마킹 | 관계 하나 | safe / sensitive:\<카테고리\> | 500건 |
| 5B | 컨텍스트 민감도 판단 | 질문 + 전체 관계(5A 마킹 포함) | safe / confirm:\<메시지\> | 400건 |
| **6** | **노드/엣지/카테고리/상태변경/보관유형 추출** | **한국어 문장 + 인출 맥락** | **{"retention":"memory\|daily", "nodes":[...], "edges":[...], "deactivate":[...]}** | **재학습 필요** |

Task 6은 저장 파이프라인의 핵심: Kiwi 형태소 분석 제거 → LLM 단독 추출 + 상태변경 통합.

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

---

### ~~태스크 1: 상태 변경 감지~~ (폐기)

> Task 6의 `deactivate` 필드로 통합됨. 별도 어댑터 불필요.
> 기존 데이터(`task1_*.jsonl`)는 Task 6 학습 데이터 보강에 참고 가능.

---

### 태스크 2: 대명사/부사/지시어 구체화

**시스템 프롬프트:**
```
당신은 지식 그래프 저장 엔진입니다.
텍스트에서 대명사와 부사를 구체적인 값으로 치환하세요.
대화 맥락이 제공되면 활용하세요.
치환 불가능하면 {"question": "질문 내용"}을 반환하세요.
출력 형식: {"text": "치환된 텍스트"} 또는 {"question": "..."}
```

**예시 데이터:**
```jsonl
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 저장 엔진입니다. 텍스트에서 대명사와 부사를 구체적인 값으로 치환하세요. 출력 형식: {\"text\": \"치환된 텍스트\"} 또는 {\"question\": \"...\"}"},
  {"role": "user", "content": "입력: 오늘 병원 갔어\n날짜: 2026-04-04"},
  {"role": "assistant", "content": "{\"text\": \"2026-04-04 병원 갔어\"}"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 저장 엔진입니다. 텍스트에서 대명사와 부사를 구체적인 값으로 치환하세요. 출력 형식: {\"text\": \"치환된 텍스트\"} 또는 {\"question\": \"...\"}"},
  {"role": "user", "content": "입력: 거기서 밥 먹었어\n맥락: 이전 발화 없음"},
  {"role": "assistant", "content": "{\"question\": \"어디서 밥 드셨나요?\"}"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 저장 엔진입니다. 텍스트에서 대명사와 부사를 구체적인 값으로 치환하세요. 출력 형식: {\"text\": \"치환된 텍스트\"} 또는 {\"question\": \"...\"}"},
  {"role": "user", "content": "입력: 그거 별로야\n맥락: 직전 대화 - 사용자: 스타벅스 신메뉴 먹어봤어?"},
  {"role": "assistant", "content": "{\"text\": \"스타벅스 신메뉴 별로야\"}"}
]}
```

---

### 태스크 3: 인출 필터

> **v2 변경**: 판단 단위가 트리플 문자열 → 원본 문장(sentence_text)으로 변경됨.
> 트리플은 추적 구조. 판단은 엣지가 속한 실제 문장으로 한다.

**시스템 프롬프트:**
```
당신은 지식 그래프 인출 필터입니다.
질문과 문장을 보고, 이 문장이 질문과 관련 있는지 판단하세요.
불확실하면 pass로 판단하세요 (제외보다 포함이 안전).
출력: pass 또는 reject (한 단어만)
```

**예시 데이터:**
```jsonl
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 인출 필터입니다. 질문과 문장을 보고 관련 있는지 판단하세요. 불확실하면 pass. 출력: pass 또는 reject"},
  {"role": "user", "content": "질문: 언제 허리 아팠지?\n문장: 허리디스크 L4-L5 진단받았어"},
  {"role": "assistant", "content": "pass"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 인출 필터입니다. 질문과 문장을 보고 관련 있는지 판단하세요. 불확실하면 pass. 출력: pass 또는 reject"},
  {"role": "user", "content": "질문: 언제 허리 아팠지?\n문장: 스타벅스 신메뉴 맛있어"},
  {"role": "assistant", "content": "reject"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 인출 필터입니다. 질문과 문장을 보고 관련 있는지 판단하세요. 불확실하면 pass. 출력: pass 또는 reject"},
  {"role": "user", "content": "질문: 언제 허리 아팠지?\n문장: 허리 다 나았어"},
  {"role": "assistant", "content": "pass"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 인출 필터입니다. 질문과 문장을 보고 관련 있는지 판단하세요. 불확실하면 pass. 출력: pass 또는 reject"},
  {"role": "user", "content": "질문: 좋아하는 음식 뭐야?\n문장: 나 삼성에서 일하고 있어"},
  {"role": "assistant", "content": "reject"}
]}
```

---

### 태스크 4: 인출 확장 (노드 후보 생성)

**시스템 프롬프트:**
```
당신은 지식 그래프 검색 엔진입니다.
질문을 보고 그래프에서 검색해야 할 관련 노드 후보를 생성하세요.
형태소 단위로 쪼개진 노드 이름으로 나열하세요.
출력 형식: ["노드1", "노드2", ...]
```

**예시 데이터:**
```jsonl
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 검색 엔진입니다. 질문을 보고 검색해야 할 노드 후보를 형태소 단위로 나열하세요. 출력 형식: [\"노드1\", \"노드2\", ...]"},
  {"role": "user", "content": "질문: 언제 아팠지?"},
  {"role": "assistant", "content": "[\"허리\", \"아프\", \"감기\", \"두통\", \"병원\", \"낫\"]"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 검색 엔진입니다. 질문을 보고 검색해야 할 노드 후보를 형태소 단위로 나열하세요. 출력 형식: [\"노드1\", \"노드2\", ...]"},
  {"role": "user", "content": "질문: 내가 좋아하는 음식 뭐야?"},
  {"role": "assistant", "content": "[\"좋아하\", \"음식\", \"먹\", \"맛있\", \"자주\"]"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 검색 엔진입니다. 질문을 보고 검색해야 할 노드 후보를 형태소 단위로 나열하세요. 출력 형식: [\"노드1\", \"노드2\", ...]"},
  {"role": "user", "content": "질문: 지금 어디 살아?"},
  {"role": "assistant", "content": "[\"살\", \"이사\", \"집\", \"주소\", \"거주\"]"}
]}
```

---

---

### 태스크 5A: 관계 민감도 마킹

**시스템 프롬프트:**
```
당신은 지식 그래프 보안 엔진입니다.
관계(source—label—target) 하나를 보고 민감정보 여부를 판단하세요.
출력 형식: safe 또는 sensitive:<카테고리>
카테고리: health_detail | financial | location_precise | relationship_private | schedule_combined
```

**민감도 카테고리:**
- `health_detail` — 구체적 병명, 처방약, 진단명, 수술 내역
- `financial` — 연봉, 계좌, 자산, 대출
- `location_precise` — 구체적 주소 (시/구 이하)
- `relationship_private` — 연애, 이혼, 사망, 가족 사생활
- `schedule_combined` — 특정 날짜+장소+행동 조합

**예시 데이터:**
```jsonl
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 보안 엔진입니다. 관계(source—label—target) 하나를 보고 민감정보 여부를 판단하세요. 출력 형식: safe 또는 sensitive:<카테고리>"},
  {"role": "user", "content": "관계: 허리 → 아프"},
  {"role": "assistant", "content": "safe"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 보안 엔진입니다. 관계(source—label—target) 하나를 보고 민감정보 여부를 판단하세요. 출력 형식: safe 또는 sensitive:<카테고리>"},
  {"role": "user", "content": "관계: 약 → 세레콕시브"},
  {"role": "assistant", "content": "sensitive:health_detail"}
]}
{"messages": [
  {"role": "system", "content": "당신은 지식 그래프 보안 엔진입니다. 관계(source—label—target) 하나를 보고 민감정보 여부를 판단하세요. 출력 형식: safe 또는 sensitive:<카테고리>"},
  {"role": "user", "content": "관계: 연봉 → 8000"},
  {"role": "assistant", "content": "sensitive:financial"}
]}
```

---

### 태스크 5B: 컨텍스트 전체 민감도 판단

**시스템 프롬프트:**
```
당신은 지식 그래프 보안 엔진입니다.
질문과 인출된 전체 트리플 컨텍스트(각 트리플의 5A 마킹 포함)를 보고,
답변에 민감정보가 포함되는지 종합 판단하세요.
출력 형식: {"result": "safe"} 또는 {"result": "confirm", "message": "사용자에게 보여줄 확인 메시지"}
```

**종합 판단 원칙:**
- 5A에서 하나라도 sensitive → 대부분 confirm
- 5A 전부 safe여도 조합 효과로 confirm 가능 (날짜+장소+행동, 여러 건강 트리플 패턴 등)
- 5A 전부 safe + 조합 효과 없음 → safe

**파이프라인 내 위치:**
```
BFS → Task 3 (관련성 필터)
      ↓
   Task 5A (트리플 단위 마킹) ← 각 트리플에 태그
      ↓
   Task 5B (전체 컨텍스트 판단) ← 마킹 포함 전체 컨텍스트
      ↓
   safe → 답변 LLM
   confirm → 사용자 확인 요청
```

---

---

## 조직(Org) 파인튜닝 설계

### 핵심 패러다임

개인 vs 조직 **모드 전환이 아님**. 개인 질문에 조직 맥락이 자연스럽게 augment되는 구조.

```
사용자 질문
  ↓
[Task 0-org] augment 필요?
  ├── personal_only → 개인 그래프만
  └── augment_org  → 개인 + 조직 그래프 병렬 탐색
                       ↓
                    컨텍스트 merge
                       ↓
                    [Task 5A/5B-org] 권한 기반 민감도 게이트
                       ↓
                    답변 LLM
```

개인 그래프는 **항상** 탐색. 조직 그래프는 관련 있을 때만 augment.

---

### 권한 레벨

```
employee    — 일반 직원 (본인 업무 정보만)
team_lead   — 팀장 (팀원 업무·성과)
hr          — HR 담당자 (인사·연봉 전체)
executive   — 임원 (전략·영업비밀)
admin       — 시스템 관리자 (전체)
```

---

### Task 0-org: Augment 필요 여부 판단

**입력:** 사용자 질문  
**출력:** `personal_only` / `augment_org`

| 질문 | 출력 |
|------|------|
| "허리 언제 나았지?" | `personal_only` |
| "좋아하는 음식 뭐야?" | `personal_only` |
| "오늘 뭐 해야 해?" | `augment_org` |
| "요즘 힘들어?" | `augment_org` |
| "이번 프로젝트 어때?" | `augment_org` |
| "우리 팀 회의 언제야?" | `augment_org` |

목표 수량: **300건** (personal_only 50% / augment_org 50%)

---

### Task 1-org: 상태 변경 감지 (주어 추적)

개인 Task 1과 구조 동일. **차이: 주어가 명시됨.**

```
입력: "김대리 개발팀으로 이동했어"
      기존 트리플:
      - 김대리 —[소속]→ 마케팅팀
      - 김대리 —[직급]→ 대리
출력: {"inactive": [{"source": "김대리", "target": "마케팅팀"}]}
```

조직 상태 변경 유형: 인사이동, 직급 변경, 퇴사/입사, 프로젝트 종료/중단, 고객사 계약 해지, 담당자 교체

목표 수량: **400건**

---

### Task 2-org: 주어 해소 (Subject Resolution)

개인 Task 2(대명사 구체화)와 **성격이 다름**. 조직에서는 "누가"가 핵심.

**출력 3가지:**
- `{"question": "..."}` — 주어 불명확, 사용자에게 질문
- `{"subject": "...", "text": "..."}` — 주어 추론 성공
- `{"text": "..."}` — 주어 없어도 되는 발화

```
입력: "팀 이동했대"  맥락: 없음
출력: {"question": "누가 팀 이동했나요?"}

입력: "걔 승진했대"  맥락: 직전 - "김팀장 얘기 들었어?"
출력: {"subject": "김팀장", "text": "김팀장 승진했대"}

입력: "A프로젝트 완료됐어"  맥락: 없음
출력: {"text": "A프로젝트 완료됐어"}
```

목표 수량: **400건** (question 40% / subject 추론 40% / 주어 불필요 20%)

---

### Task 3-org: 인출 필터 (조직 도메인)

구조 동일. **doc_mode 트리플 포함이 핵심.**

```
질문: "연차가 며칠이야?"
트리플: 35조 → 유급휴가              → pass
트리플: 35조① → 출근율              → pass  (관련 조항)
트리플: 35조 —[항, seq=1]→ 35조①   → pass  (구조 트리플)
트리플: 김팀장 —[소속]→ 개발팀       → reject
```

목표 수량: **600건** (pass 60% / reject 40%)

---

### Task 4-org: 인출 확장 (조직 도메인)

```
질문: "연차 며칠이야?"
출력: ["연차", "유급휴가", "취업규칙", "35조", "출근율", "일수"]

질문: "A프로젝트 담당자 누구야?"
출력: ["A프로젝트", "담당", "책임자", "팀", "배정"]
```

목표 수량: **300건**

---

### Task 5A-org: 트리플 민감도 마킹 (최소 열람 권한 포함)

**출력:** `safe` / `sensitive:<카테고리>:<최소권한>`

| 카테고리 | 설명 | 최소 권한 |
|----------|------|-----------|
| `personal_info` | 직원 연봉·주소·건강·가족 | `hr` |
| `performance` | 성과 평가·등급 | `team_lead` |
| `trade_secret` | 계약금액·내부 단가·기술 노하우 | `executive` |
| `internal_decision` | 미발표 인사·전략 계획 | `executive` |
| `client_confidential` | 고객사 기밀·미공개 프로젝트 | `executive` |
| `legal_risk` | 계약 분쟁·규정 위반 내역 | `hr` |

```
트리플: 김민수 → 개발팀        → safe
트리플: 김민수 → 연봉          → sensitive:personal_info:hr
트리플: 김민수 → 성과등급      → sensitive:performance:team_lead
트리플: 전략계획 → 2027        → sensitive:internal_decision:executive
```

목표 수량: **500건** (safe 55% / sensitive 45%)

---

### Task 5B-org: 컨텍스트 민감도 판단 (권한 기반)

**입력:** 질문 + **질의자 권한** + 전체 트리플(5A 마킹 포함)  
**출력 3가지:** `safe` / `confirm` / `reject`

권한 판단 매트릭스:

| 트리플 최소권한 | 질의자 권한 | 결과 |
|----------------|-------------|------|
| safe | 누구나 | safe |
| :team_lead | employee | reject |
| :team_lead | team_lead 이상 | confirm |
| :hr | team_lead 이하 | reject |
| :hr | hr 이상 | confirm |
| :executive | executive 미만 | reject |
| :executive | executive | confirm |

```
입력: 질문: 김민수 연봉 얼마야?
      질의자 권한: employee
      컨텍스트:
      - [sensitive:personal_info:hr] 김민수 → 연봉
      - [safe] 김민수 → 개발팀
출력: {"result": "reject", "message": "해당 정보는 HR 담당자 이상만 열람 가능합니다."}

입력: 질문: 우리 팀원 성과 어때?
      질의자 권한: team_lead
      컨텍스트:
      - [sensitive:performance:team_lead] 김민수 → 성과등급
출력: {"result": "confirm", "message": "팀원 성과 정보가 포함됩니다. 열람하시겠습니까?"}
```

목표 수량: **300건** (safe 35% / confirm 35% / reject 30%)

---

### Org 데이터 총계

| 태스크 | 수량 |
|--------|------|
| 0-org Augment 판단 | 300건 |
| 1-org 상태 변경 | 400건 |
| 2-org 주어 해소 | 400건 |
| 3-org 인출 필터 | 600건 |
| 4-org 인출 확장 | 300건 |
| 5A-org 트리플 마킹 | 500건 |
| 5B-org 컨텍스트 판단 | 300건 |
| **합계** | **2,800건** |

저장 경로: `archive/finetune/data/org/`

---

## 태스크 6: 노드/엣지/카테고리/상태변경 추출

**배경**: Kiwi 형태소 분석 기반 저장 파이프라인의 한계.
- 형태소 단위 노드 파편화 → 개념 추론 불가
- 카테고리 없이 BFS 탐색 → 연관 노드 도달 실패
- 상태변경 감지가 별도 LLM 호출 → 통합으로 단순화
- LLM이 한 번에 노드·엣지·카테고리·상태변경을 추출하도록 재학습

**시스템 프롬프트 (v2.1 — 문장 컨텍스트):**
```
한국어 문장에서 지식 그래프의 노드, 엣지, 카테고리, 상태변경, 보관 유형을 추출하라.
JSON만 출력. 다른 텍스트 금지.

출력 형식:
{"retention":"memory|daily","nodes":[{"name":"노드명","category":"대분류.소분류"}],"edges":[{"source":"노드명","label":"조사","target":"노드명"}],"deactivate":[{"source":"노드명","target":"노드명"}]}

규칙:
- 노드는 원자. 하나의 개념 = 하나의 노드.
- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출. 문장에 없는 1인칭 추가 금지.
- 3인칭 주어는 원문 그대로 노드 추출.
- 엣지 label = 원문의 조사 그대로. 조사 없으면 null.
- "알려진 사실:"이 제공된 경우: 현재 입력과 상충되는 기존 문장을 파악해 deactivate에 포함. 없으면 [].
- retention: 잘 변하지 않는 사실/상태/이력 → "memory". 순간적 활동/감정/일상 → "daily".
- 저장 불필요한 대화 → {"retention":"daily","nodes":[],"edges":[],"deactivate":[]}
```

**입력 형식**: 현재 발화 + "알려진 사실:" 섹션 (retrieve에서 가져온 원본 문장들)
```
허리 다 나았어
알려진 사실:
- 나는 허리디스크 L4-L5 진단받았어
- 허리 너무 아파서 병원 다니고 있어
```

**출력 규칙:**
- 노드는 원자. 하나의 개념 = 하나의 노드.
- 개인 모드: 1인칭이 문장에 있으면 "나" 노드 추출. 없으면 미생성 + 엣지에도 미사용.
- 조직 모드: 1인칭 → 사용자 이름 노드로 치환
- 3인칭 주어는 원문 그대로 노드 추출
- 엣지 label = 원문의 조사 (에서, 으로, 의, 에, 를/을, 와/과 등). 조사 없으면 null.
- `deactivate`: 상태변경으로 비활성화할 기존 엣지. 없으면 빈 배열.
- 저장 불필요한 일상 대화 → `{"nodes":[],"edges":[],"deactivate":[]}`

**조사 라벨 예시 (개인 모드):**
```
"더나은에서 웹기획자로 일하고 있어"
→ 더나은 —(에서)→ 웹기획자  (1인칭 없으므로 "나" 미생성)

"나 더나은에서 웹기획자로 일하고 있어"
→ 나 —(에서)→ 더나은  (1인칭 명시 → "나" 노드 생성)

"박지수가 개발팀장으로 승진했어"
→ 박지수 —(으로)→ 개발팀장

"허리디스크 L4-L5 진단받았어"
→ 허리디스크 → L4-L5 (null)  (1인칭 없으므로 "나" 미생성)

"맥북 프로 M4 샀어"
→ 맥북 프로 M4  (단독 노드, 1인칭 없으므로 "나" 미생성)
```

**상태변경 예시:**
```
입력: "허리 다 나았어"
인출 맥락: 허리 → 아프 (active)
→ deactivate: [{"source": "허리", "target": "아프"}]

입력: "회사 그만뒀어"
인출 맥락: 삼성 → 재직 (active)
→ deactivate: [{"source": "삼성", "target": "재직"}]
```

**카테고리 코드 (17개 대분류, ~95개 소분류):**
```
PER BOD MND FOD LIV MON WRK TEC EDU LAW TRV NAT CUL HOB SOC REL REG
```
→ 상세 목록: `docs/DESIGN_CATEGORY.md`

**데이터 현황:**

| 파일 | 내용 | 건수 | 상태 |
|------|------|------|------|
| task6_extract_category.jsonl | 초기 균형 세트 | 500건 | 구버전 (트리플 컨텍스트) |
| task6_sup_a~d.jsonl | 카테고리별 보강 | 1,177건 | 구버전 (트리플 컨텍스트) |
| **task6_v2_a.jsonl** | PER/BOD/MND | — | **재생성 중 (v2.1)** |
| **task6_v2_b.jsonl** | WRK/MON/TEC/EDU | — | **재생성 중 (v2.1)** |
| **task6_v2_c.jsonl** | FOD/LIV/HOB/TRV/CUL | — | **재생성 중 (v2.1)** |
| **task6_v2_d.jsonl** | LAW/NAT/SOC/REL/REG | — | **재생성 중 (v2.1)** |
| **task6_v2_e.jsonl** | doc_mode (조직 문서) | — | **재생성 중 (v2.1)** |

v2.1 변경: `current_graph`(트리플) → `context_sentences`(원본 문장) 포맷. deactivate 학습 정확도 향상 목적.

---

## 전체 데이터셋 summary

| 구분 | 태스크 | 총 건수 | 상태 |
|------|--------|---------|------|
| Personal | 2~4, 5A, 5B (Task 1 폐기) | ~2,600건 | 완료 |
| Personal | Task 6 (재학습) | 1,677건 기반 | **재학습 필요** |
| Org | 0~4, 5A, 5B | 2,800건 | 예정 |

**mlx_train 현황 (Task 6 재학습 전 기준):**
- 전체: 4,811건 (중복 제거)
- train: 4,329건 / valid: 482건
- 저장 경로: `archive/finetune/data/mlx_train/`

> Task 6 재학습 이후 수치 업데이트 필요.

---

## 다음 세션 할 일

1. task6_v2 a~e 생성 완료 → validate_task6.py 전수검사 → 오류 제거 → 커밋
2. Task 6 파인튜닝 재실행 (MLX LoRA, gemma4:e2b, task6_v2 데이터)
3. eval: 추출 정확도 + deactivate 정확도 측정
4. Org 데이터셋 생성 스크립트 작성

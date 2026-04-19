# Synapse 설계 — 파인튜닝

## 작업 규칙 (이 문서의 모든 작업 전 필독)

**추측하지 마라. 검색해라. 실행 전에 검증해라.**

학습/파인튜닝 관련 작업 시 일반적인 ML 지식으로 추측하여 진행하지 말 것.
이 프로젝트에는 확정된 설계·하이퍼파라미터·실패 기록·성공 패턴이 이미 문서화되어 있다.

### Phase 0: 설계 파악 (반드시 읽기)

- 이 문서(`DESIGN_FINETUNE.md`) — 태스크 구조, 하이퍼파라미터, 데이터 현황, 실패 기록
- `scripts/runpod/train_all.py` — 확정된 학습 설정 (TaskConfig 클래스)
- `scripts/runpod/README.md` — RunPod 사용법, 태스크 목록

### Phase 1: 환경 검증 루틴 (실행 전 필수)

문서의 설정이 현재 환경에서 유효한지 **매번** 확인. 하루만 지나도 바뀔 수 있다.

```
[ ] 라이브러리 버전 확인
    - pip show unsloth peft transformers trl → 버전이 문서/스크립트 작성 시점과 다르면 변경사항 검색
    - 특히 unsloth, trl은 API가 자주 바뀜 (deprecated 파라미터, 클래스 이동 등)
[ ] 모델/토크나이저 확인
    - 베이스 모델 접근 가능한지 (HF 캐시 또는 다운로드)
    - chat_template이 변경되지 않았는지
[ ] 데이터 파일 존재 + 건수 확인
    - wc -l data/finetune/tasks/*/train.jsonl
    - 빈 파일, 0건 데이터 체크
[ ] GPU/VRAM 확인
    - nvidia-smi (RunPod이면 할당된 GPU 종류와 VRAM)
    - 이전 프로세스 잔류 VRAM 점유 여부
[ ] 디스크 여유 확인
    - df -h /workspace (RunPod 볼륨 용량)
[ ] 기존 어댑터 백업
    - 재학습 시 기존 결과 덮어쓰기 전 _backup 또는 타임스탬프 보존
```

### Phase 2: 소규모 검증 (첫 실행 필수)

새 환경, 새 라이브러리 버전, 새 데이터에서는 반드시 **1개 태스크 100 iters**로 먼저 돌린다.

```
[ ] 100 iters 테스트 실행 (가장 작은 태스크)
[ ] train_loss 정상 감소 확인
[ ] eval_loss 트렌드 확인 (↓이면 정상, →이면 과적합 조짐)
[ ] 출력 포맷 확인 (GGUF 변환 후 실제 프롬프트로 추론 1건)
[ ] 문제 있으면 → 전체 학습 진행하지 말고 원인 분석
```

### 금지 사항

- 하이퍼파라미터(lr, layers, alpha, batch 등)를 임의로 정하지 말 것 — 이미 확정된 값이 있음
- 이전에 실패한 접근(전체 레이어 LoRA, alpha=160 등)을 반복하지 말 것
- 환경을 가정하지 말 것 — RTX3080 없음, RunPod 사용, MLX는 로컬 테스트용
- "설정 완료"를 동작 확인 전에 말하지 말 것 — 실제 1회 실행으로 검증 후 보고
- 에러 발생 시 로그 일부만 보고 판단하지 말 것 — 성공/실패 케이스 비교 후 판단

---

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
| **6** | **노드/상태변경 추출 (v13)** | **한국어 문장 + 인출 맥락** | **{"nodes":[...], "deactivate":[...]}** | **재학습 필요** |

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

### 태스크 2: 대명사/부사/지시어 구체화 (v12)

**핵심 변경**:
- **세션리스** — 직전 대화 맥락 주입 제거
- **인칭대명사 치환 금지** — "나/내/저/제"는 건드리지 않음
- **출력 구조 단순화** — 치환 성공 토큰만 `tokens[]`에 담는다. 치환 실패한 지시어/부사는 원문에 그대로 두고 LLM은 따로 표기하지 않음 (save.py가 규칙 기반 정규식으로 감지 → `unresolved_tokens` INSERT)
- **카테고리 규칙 기반 분명한 것만** — 시간/장소/인물/사물/부정 등 명확히 분류되는 것만 `category` 부여, 모호하면 생략

**출력 스키마:**
```json
{"text": "치환된 문장",
 "tokens": [{"name": "노드명", "category": "시간|장소|인물|사물|부정|..."}]}
// 또는 — 저장 자체가 불가능한 완전 모호 케이스
{"question": "되묻기 메시지"}
```

**시스템 프롬프트:**
```
당신은 지식 그래프 저장 엔진입니다.
입력 문장에서 치환 가능한 부분만 치환합니다.

규칙:
- 인칭대명사(나/내/저/제)는 절대 치환하지 않습니다.
- 날짜 관련 부사(오늘/어제/내일/이번 주/지난달 등)는 "날짜:" 값 기준으로 계산하여 치환.
- 치환 성공한 고정 토큰은 tokens[]에 {name, category?}로 담기. category는 규칙 기반 분명할 때만 (시간/장소/인물/사물/부정 등).
- 치환할 수 없는 지시어(이거/그거/걔/그때/거기 등)는 그대로 원문에 남깁니다. LLM이 따로 표기하지 않습니다.
- 저장 자체가 불가능한 완전 모호 케이스만 {"question": "..."} 단독 반환.

출력 형식:
{"text": "...", "tokens": [...]}
또는 {"question": "..."}
```

**예시 데이터:**
```jsonl
{"messages": [
  {"role": "system", "content": "..."},
  {"role": "user", "content": "입력: 오늘 병원 갔어\n날짜: 2026-04-04"},
  {"role": "assistant", "content": "{\"text\": \"2026-04-04 병원 갔어\", \"tokens\": [{\"name\": \"2026-04-04\", \"category\": \"시간\"}]}"}
]}
{"messages": [
  {"role": "system", "content": "..."},
  {"role": "user", "content": "입력: 그거 별로야\n날짜: 2026-04-04"},
  {"role": "assistant", "content": "{\"text\": \"그거 별로야\", \"tokens\": []}"}
]}
{"messages": [
  {"role": "system", "content": "..."},
  {"role": "user", "content": "입력: 나 오늘 이거 시작했어\n날짜: 2026-04-04"},
  {"role": "assistant", "content": "{\"text\": \"나 2026-04-04 이거 시작했어\", \"tokens\": [{\"name\": \"2026-04-04\", \"category\": \"시간\"}]}"}
]}
{"messages": [
  {"role": "system", "content": "..."},
  {"role": "user", "content": "입력: 그 동네 살기 좋아\n날짜: 2026-04-04"},
  {"role": "assistant", "content": "{\"question\": \"어떤 동네인가요?\"}"}
]}
```

**엔진 측 unresolved 감지 (save.py 책임)**: 저장 파이프라인에서 LLM 출력의 `text`를 받은 후, 엔진이 한정된 사전(지시대명사·지시부사·시간 모호 부사·장소부사)을 정규식으로 스캔하여 치환되지 않은 지시어를 찾고 `unresolved_tokens`에 INSERT. 빈도/정도 부사(자주/많이 등)는 지시적 의미가 없어 제외한다.

**맥락 의존 케이스 폐기**: v12 이전에는 "직전 대화 - 사용자: 스타벅스 신메뉴 먹어봤어?" 같은 맥락으로 "그거"를 "스타벅스 신메뉴"로 치환했으나, 세션리스 전환으로 **더 이상 맥락을 받지 않음**. 해당 케이스는 원문 `text`로 그대로 반환하고 `/review`에서 해소한다.

---

### 태스크 3: 인출 필터 (v12)

> **v12 변경**:
> - 판단 단위: 트리플 문자열 → **원본 문장** (sentence_text)
> - 조사 엣지 폐기에 따라 트리플 개념 자체가 인출 컨텍스트에서 제거됨
> - 구 데이터(트리플 기계 변환)는 품질 불균형으로 전량 폐기, Claude CLI(opus)로 완전 재생성
> - 노이즈 필터(조사 라벨 엣지 / 형태소 단편 노드) + `scripts/mlx/build_retrieve_filter_aug.py` 전체 재생성

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

저장 경로: `data/finetune/org/`

---

## 태스크 6: 추출 — extract-core + extract-state 분리

**배경**: Kiwi 형태소 분석 기반 저장 파이프라인의 한계.
- 형태소 단위 노드 파편화 → 개념 추론 불가
- 카테고리 없이 BFS 탐색 → 연관 노드 도달 실패

### 분리 근거

기존 Task 6은 5가지 인지 작업(retention, nodes, edges, category, deactivate)을 단일 어댑터에서 수행.
2B 모델에서 deactivate(상태 무효화)는 **한 번도 정상 동작한 적 없음**:
- nodes/edges/category: 패턴 매칭 (입력 문장에서 구조 추출)
- deactivate: 추론 (입력 vs 기존 N개 사실 비교 → 만료된 사실 탐지)

2B 모델이 한 어댑터에서 패턴 매칭과 추론을 동시에 수행하는 것은 무리.
분리 비용(추론 시 LLM 호출 1→2회, ~0.5초 추가)은 미미.

### v13 추가 정리 (2026-04-18)
- edges 필드 폐기 (v12): 조사 기반 엣지는 사용자 승인 기반 의미 엣지로 전환
- **retention 필드 폐기 (v13)**: "daily → 빈 nodes" 과적합 원인이라 제거. `{nodes, deactivate}`만.
- category 필드: LLM 추론 결과는 저장 대상 아님 (규칙 기반 + heading 경로만). extract 어댑터에서 제거.
- 결과: extract-core는 **순수 노드 이름 추출**에만 집중

---

### Task 6A: extract-core (노드 추출, v13)

**시스템 프롬프트:**
```
한국어 문장에서 지식 그래프의 노드를 추출하라.
JSON만 출력. 다른 텍스트 금지.

출력 형식:
{"nodes":[{"name":"노드명"}]}

규칙:
- 노드는 원자. 하나의 개념 = 하나의 노드.
- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출. 문장에 없는 1인칭 추가 금지.
- 3인칭 주어는 원문 그대로 노드 추출.
- 부정부사(안, 못)는 독립 노드다. 예: "스타벅스 안 좋아" → 노드 [스타벅스, 안, 좋아].
- 추출할 노드가 없는 대화도 {"nodes":[]} (비어있어도 반환)
```

**입력**: 현재 발화 (알려진 사실 없음 — core는 구조 추출만 담당)
**출력**: `{"nodes":[...]}`

v12 이전에는 edges/category/retention 필드를 함께 반환했으나 각각 폐기:
- edges: 사용자 승인 기반 의미 엣지로 전환 (v12)
- category: 규칙 기반 + heading 경로만 저장 (LLM 추론 결과 불채택)
- retention: 분류 자체를 폐기, 모든 sentence 동등 보관 (v13)

**조사 라벨 예시:**
```
"더나은에서 웹기획자로 일하고 있어"
→ 더나은 —(에서)→ 웹기획자  (1인칭 없으므로 "나" 미생성)

"나 더나은에서 웹기획자로 일하고 있어"
→ 나 —(에서)→ 더나은  (1인칭 명시 → "나" 노드 생성)

"박지수가 개발팀장으로 승진했어"
→ 박지수 —(으로)→ 개발팀장
```

**데이터**: `data/finetune/tasks/extract-core/`
- train: 1,798건, valid: 200건
- 기존 task6_v2 전체 데이터에서 deactivate 필드 + 알려진 사실 입력 제거

---

### Task 6B: extract-state (모순 탐지)

**시스템 프롬프트:**
```
알려진 사실 목록에서 현재 입력으로 인해 더 이상 유효하지 않은 문장을 찾아 sentence_id를 반환하라.
JSON만 출력. 다른 텍스트 금지.

출력 형식:
{"deactivate":[sentence_id, ...]}

규칙:
- 각 알려진 사실에는 [번호]가 붙어 있다.
- 현재 입력이 기존 사실을 무효화하면 해당 번호를 deactivate에 포함.
- 무효화할 사실이 없으면 {"deactivate":[]}.
- 무효화 판단 기준: 동일 주체의 상태/소속/위치/습관 등이 바뀐 경우.
```

**입력**: 현재 발화 + "알려진 사실:" 섹션 (각 문장에 `[sentence_id]` 포함)
```
허리 다 나았어
알려진 사실:
- [434] 나는 허리디스크 L4-L5 진단받았어
- [435] 허리 너무 아파서 병원 다니고 있어
```

**출력**: `{"deactivate": [434, 435]}`

**데이터**: `data/finetune/tasks/extract-state/`
- train: 490건, valid: 52건
- 알려진 사실이 있는 데이터만 필터링 (없는 건 판단 불가 → 제외)
- 양성(deactivate 있음) 79%, 음성(모순 없음) 21%

**파이프라인 호출 순서**: save.py에서 extract-core → extract-state 순차 호출.

---

### 카테고리 코드 (17개 대분류, ~55개 소분류)

```
PER BOD MND FOD LIV MON WRK TEC EDU LAW TRV NAT CUL HOB SOC REL REG
```
→ 상세 목록: `docs/DESIGN_CATEGORY.md`

**원본 데이터 (v2.1):**

| 파일 | 내용 | 건수 |
|------|------|------|
| task6_v2_a.jsonl | PER/BOD/MND | 350 |
| task6_v2_b.jsonl | WRK/MON/TEC/EDU | 350 |
| task6_v2_c.jsonl | FOD/LIV/HOB/TRV/CUL | 350 |
| task6_v2_d.jsonl | LAW/NAT/SOC/REL/REG | 350 |
| task6_v2_e.jsonl | doc_mode (조직 문서) | 350 |
| task6_v2_supp_*.jsonl | 보충 (생년, 명령, 질문) | 248 |
| **합계** | | **1,998** |

---

## 전체 데이터셋 summary (v12 기준)

| 구분 | 태스크 | 총 건수 | 상태 |
|------|--------|---------|------|
| Personal | Task 2 save-pronoun (v12) | 720건 (train 660 / valid 60) | ✅ 재생성 완료 |
| Personal | Task 3 retrieve-filter (v12) | 1,400건 (train 1,269 / valid 131) | 🔄 Claude CLI 재생성 진행 |
| Personal | Task 4 retrieve-expand | 468건 (train) | 완료 (변동 없음) |
| Personal | Task 5A/5B security | ~900건 | 완료 (변동 없음) |
| Personal | Task 6A extract-core (v12) | 1,998건 (train 1,798 / valid 200) | ✅ 재생성 완료 (edges 드롭) |
| Personal | Task 6B extract-state | 542건 (train 490 / valid 52) | 완료 (변동 없음) |
| Org | 0~4, 5A, 5B | 2,800건 | 예정 |

---

## 학습 설정 (MLX — 2026-04-18 현행화)

RunPod은 운영 불안정(디스크·드라이버·스케줄 문제)으로 폐기. 어댑터별 하이퍼파라미터를 MLX 기준으로 재조정한 뒤 아래 값으로 수렴.

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
| extract-core | 1798 | 1348 |
| extract-state | 490 | 367 |
| retrieve-filter | 1269 | 951 |
| save-pronoun | 660 | 495 |
| retrieve-expand | 468 | 351 |
| routing | 265 | 198 |
| save-state-personal | 438 | 328 |
| security-personal | 495 | 371 |
| security-context | 415 | 311 |
| security-access | 319 | 239 |
| ... | ... | ... |

### LoRA 파라미터는 공통, iters만 어댑터별

과거 실험(v1~v5)에서 rank·scale·dropout 조정 시 전반적으로 성능 차이가 작거나 오히려 악화. **iters를 데이터 크기에 맞춰 자동 계산**하는 것이 가장 단순하고 효과적이라고 판단.

스크립트: `scripts/mlx/train_all.py`
어댑터 출력: `runpod_output/mlx_adapters/<task>/`
로그: `runpod_output/mlx_logs/<task>.log`

---

## v12 재학습 진행 현황 (2026-04-18)

| # | 어댑터 | 데이터 전환 | 학습 | Val loss |
|---|---|---|---|---|
| M1 | extract-core | ✅ edges 필드 드롭 | ✅ iters=1348 완료 | **0.086** (1.606 → 0.086) |
| M4/M4.1 | save-pronoun | ✅ 출력 `{text, tokens}` / question. 세션리스, 인칭 치환 금지, 규칙 기반 시간부사 치환 | 🔄 진행 중 (iters=495) | — |
| M5/M5.1 | retrieve-filter | 🔄 Claude CLI 전체 재생성 (노이즈 필터 후 부족분 보충) | 대기 | — |

### 백업된 pre-v12 어댑터
- `runpod_output/mlx_adapters/extract-core_pre_v12/`
- `runpod_output/mlx_adapters/save-pronoun_pre_v12/`
- `runpod_output/mlx_adapters/extract_backup_20260418/` (구 통합 어댑터)
- `runpod_output/mlx_adapters/save-pronoun_backup_20260418/`
- `runpod_output/mlx_adapters/retrieve-filter_backup_20260418/`

### 변환/생성 스크립트
- `scripts/drop_edges_extract_core.py` — extract-core edges 드롭
- `scripts/convert_save_pronoun_v12.py` — save-pronoun 스키마 전환 + 시간부사 규칙 치환
- `scripts/convert_retrieve_filter_v12.py` — retrieve-filter 트리플→문장 + 노이즈 필터
- `scripts/mlx/build_retrieve_filter_aug.py` — Claude CLI(opus) v12 완결형 문장 증강

---

## 다음 세션 할 일

1. retrieve-filter 학습 (iters=951, Claude CLI 재생성 병합 후)
2. 세 어댑터 추론 검증 — GGUF 변환 + MLX 서버 로딩 + 실제 프롬프트 반응
3. Org 데이터셋 생성 (후순위)

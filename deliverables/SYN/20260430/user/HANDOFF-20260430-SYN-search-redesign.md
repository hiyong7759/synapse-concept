# HANDOFF — 검색·저장 모델 재설계 (진행 중단)

작성일: 2026-04-30
브랜치: `main` (직접 작업, 워크트리 없음)
상태: **코드 작업 중단 — 사용자 요청. 미완료. 테스트 3개 fail.**

---

## 핵심 결정 (사용자 합의 완료)

1. **BFS 공출현 확장 → 폐기**, 직접 lookup 으로 전환 (3 경로: 문장/카테고리/heading)
2. **sentence-단위 retrieve-filter → 폐기**, **keyword-단위 filter** 로 전환 (불순물 사전 제거)
3. **heading 분리자**: `.` = 단계, `/` `,` 등 공백 치환. List<String> 으로 보관 (join/split 왕복 X)
4. **표 입력 자동 인식**: `# col1\tcol2\t...` heading + `- val1\tval2\t...` row → 한 sentence 로 zip
5. **표 row 저장 포맷**: `key:: val key:: val key:: val` (공백 구분 — `/` `,` 같은 모호 구분자 X. heading 의 특수문자 공백 치환 정책과 일관)
6. **synapse-answer 빈 컨텍스트**: LLM 호출 안 하고 `"기록 없어요."` 결정론 반환

---

## 완료된 변경

### 설계서 (M1 완료)
- `docs/DESIGN_PIPELINE.md` — 인출 파이프라인 재작성 (BFS 폐기, keyword filter, heading 분리자)
- `docs/DESIGN_HYPERGRAPH.md` — BFS 표현 → lookup 으로 갱신
- `docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md` — heading 정규화 규칙 + synapse 흐름

### 저장 측 코드 (M2 완료)
- `synapse_engine/lib/src/markdown/parser.dart`
  - heading 특수문자 공백 치환 (`/` `|` `\` `·` `,` `;` `&` `+` `~` `→`)
  - `.` 단계 분리자 처리
  - **표 모드 자동 인식** (heading 에 tab 있으면 column header 로, row 들 zip)
- `synapse_engine/lib/src/graph/ops.dart`
  - `upsertCategoryPath(String)` → `upsertCategoryPath(List<String>)` 시그니처 변경
  - `bfsRetrieve` → `mentionsForNodes` (path 1 직접 lookup 으로 단순화)
- `synapse_engine/lib/src/flow/note_pipeline.dart` — `headingPath.join('/')` 제거

### 검색 측 코드 (M3 완료)
- **신규** `synapse_engine/lib/src/graph/lookup.dart`
  - `matchStartCategories(db, keywords)` — 카테고리 직접 매칭
  - `collectMentionsForNodes` — path 1
  - `collectMentionsByCategorySharing` — path 2
  - `collectMentionsByHeadingSubtree` — path 3 (재귀 CTE)
  - `categoriesForNodes` — 헬퍼
- **신규** `synapse_engine/lib/src/flow/retrieve.dart`
  - `retrieveForQuestion()` 오케스트레이터
  - keyword expand → keyword filter LLM → 3경로 lookup → context 빌드
- **삭제** `synapse_engine/lib/src/graph/bfs.dart` (280줄)
- **삭제** `synapse_engine/test/graph/bfs_typo_test.dart`
- `synapse_engine/lib/src/flow/synapse_flow.dart` — `bfsRetrieve` → `retrieveForQuestion`
- `synapse_engine/lib/src/graph/seed_matching.dart` — `headingSubtreeSeeds`/`sameCategoryNodes` 폐기 (lookup.dart 로 이전), `matchStartNodes` 만 유지
- `synapse_engine/lib/src/config.dart` / `engine.dart` — `retrieveStopwordThreshold` 제거
- `synapse_engine/lib/synapse_engine.dart` — exports 정비

### 필터 위치 전환 (M3.5 완료)
- **신규** `docs/KEYWORD_FILTER_SYSTEMPROMPT.md` + `synapse_engine/assets/prompts/KEYWORD_FILTER_SYSTEMPROMPT.md`
- **삭제** `RETRIEVE_FILTER_SYSTEMPROMPT.md` (양쪽)
- `synapse_engine/lib/src/llm/tasks.dart` — `retrieveFilter(question, sentences)` → `filterKeywords(question, candidates)` 의미 전환
- `synapse_engine/lib/src/prompts/loader.dart` — `PromptKey.retrieveFilter` → `keywordFilter`
- `synapse_engine/lib/src/flow/retrieve.dart` — sentence 필터 제거, expand 직후 keyword filter 호출
- 안전망: 모델이 키워드 다 떨어뜨려도 원본 candidates 그대로 사용 (zero-match 회귀 차단)

### 답변 품질 패치 (M3.6 일부 완료)
- `docs/SYNAPSE_ANSWER_SYSTEMPROMPT.md` 다시 씀
  - 시작 군더더기 금지 ("알려진 사실에 따르면", "사용자님의 비서입니다", "네, ", "음, ")
  - 훈련 지식 보충 금지
  - 예시 4개 (직답·인용·기록 없음·시간 충돌)
- `synapse_engine/lib/src/llm/tasks.dart::synapseAnswer`
  - **빈 contexts → LLM 호출 없이 `"기록 없어요."` 직반환** (작은 모델이 시스템 프롬프트 paraphrase 하는 회귀 차단)
  - 비빈 경우 user prompt: `[사실]\n- ...\n\n질문: ...`
- `synapse_engine/lib/src/flow/synapse_flow.dart::_fallbackAnswer` — `"기록 없어요."` 로 통일

---

## ⚠️ 미완료·문제 — 다음 세션에서 우선 처리

### A. 테스트 3개 fail (`tasks_stub_test.dart`)

전체: **+157 ~8 -3**. 실패 위치 [synapse_engine/test/llm/tasks_stub_test.dart:128, 148, 158](synapse_engine/test/llm/tasks_stub_test.dart#L128).

원인: M3.6 에서 prompt 형식 + 빈 컨텍스트 분기 변경. 테스트는 옛날 형식(`알려진 사실 (시간 순):`) 기대 + 옛날 빈 컨텍스트 분기 (LLM 호출 → `(관련 사실 없음)` placeholder) 기대.

**수정**:
1. canned key 를 새 형식(`[사실]\n- ...\n\n질문: ...`)으로 변경 (라인 132~133, 149)
2. 빈 컨텍스트 테스트 (라인 158~166) → LLM 호출 없이 `"기록 없어요."` 반환 확인으로 변경

### B. 사용자 dogfood 검증 결과 (M4 미시작)

마지막 dogfood (2026-04-30):
| 질의 | 답변 | 진단 |
|---|---|---|
| 슬램덩크 몇권? | "1부터 26까지의 제목이 기록되어 있어요" (12권 데이터인데 환각) | 환각 — 권수 분포(1,2,5,6,7,8,13,15,19,23,24,26) 보고 모델이 "1~26" 으로 잘못 추론 |
| 정윤수가 산 책 | "규칙을 이해했습니다..." | Gemma 4 E2B 가 instruction-heavy 프롬프트에 ack 응답. 또는 contexts 가 진짜 비어서 (`기록 없어요.` 가드 hot-reload 안 됐을 가능성) |
| 본사에 있는 만화책 | "본사에 있는 만화책이 있습니다" (질문 paraphrase) | 동일한 모델 한계 + 데이터 구조 문제 |

**근본 원인 분석 (사용자 dogfood 후 합의)**:
- books.md 가 sentence-level 로 쪼개짐 (`- 제목:: ...`, `- 구매자:: ...` 가 각각 별도 sentence)
- "정윤수" 노드 매칭 → `구매자:: 정윤수` 만 컨텍스트로 옴, 같은 책의 제목·저자 못 가져옴
- → **표 모드 자동 인식 (M3.7) 의 도입 동기**

### C. M3.7 표 모드 — 코드는 작성, 검증 미완료

`synapse_engine/lib/src/markdown/parser.dart` 수정 + 테스트 6개 추가됨. parser 단위 테스트는 통과. 다만:

- DB 재인입 안 됨 — 사용자가 books.md 를 표 형식으로 변환해서 재입력해야 효과 검증 가능
- books.md 변환 스크립트 없음 — 사용자가 수동 또는 `convert.py` (이미 있음) 변경해야 함

`deliverables/SYN/20260429/user/books.md` 는 현재 `- key:: value` 줄들 형식. 표 모드로 받으려면:
```
# 제목\t저\t출판사\t정가\t구매가\t구매일\t구매자\t위치
- 꿈돌이의 FUSION360 1st 입문편\t권경범\t청담북스\t30000원\t27000원\t2018-05-03\t조용희\t본사
- ...
```

`deliverables/SYN/20260429/user/books_raw.tsv` 가 이미 TSV 라 거기서 헤더 + 데이터를 그대로 markdown 으로 변환하면 됨.

---

## 인수인계 요청

다음 세션에서 진행할 일 (우선순위 순):

### 1. 즉시: 테스트 3개 fix
파일: `synapse_engine/test/llm/tasks_stub_test.dart` 라인 128~166. canned key 형식 + 빈 컨텍스트 분기 갱신.

### 2. 사용자 dogfood 재실행
- DB 초기화 → books.md 를 표 형식으로 재입력 (M3.7 검증)
- 7가지 회귀 질의 재실행 (HANDOFF-20260429 표)

### 3. 답변 품질 추가 진단 (필요 시)
- 디버그 로그 (`[retrieve] kw_in=X kw_out=Y ...`) 콘솔에서 확인
- "정윤수가 산 책" 에서 lookup 결과가 비었는지, 컨텍스트는 채워졌는지, 모델만 헛소리하는지 분리

### 4. M3.7 보강 가능성
표 모드가 제대로 작동해도 답변 품질 안 잡히면:
- 카테고리 path 를 컨텍스트에 prefix `[A > B > C] sentence` 로 넘기는 옵션 (사용자가 한번 제안한 안)
- 컨텍스트 sentence 수 cap 더 낮춰 노이즈 줄이기

---

## 사용자 피드백 — 다음 세션 주의

- **사용자는 UI/UX 기획자, 비개발자.** 영어 용어·기술 jargon 쓰지 말 것 (`sentinel`, `worktree` 등). 한국어로 풀어 설명.
- **간결·직접.** 옵션 A/B/C 길게 늘어놓지 말고 추천 1개로 결정 후 진행.
- **사용자가 "그냥 X로 해" 라고 하면 즉시 그대로.** 이유 추가 설명 금지.
- **사용자가 멈추라 하면 멈춤.** 추가 작업 제안 금지.
- **이미 결정한 정책은 다시 묻지 말 것.** parser 의 특수문자 공백 치환 정책은 이미 M2 에서 결정됨. 표 row 구분자도 그 정책과 일관(공백)이어야 했음.

---

## 참고 자료

- 작업 시작 핸드오프: `projects/synapse/deliverables/SYN/20260429/user/HANDOFF-20260429-SYN-search-redesign.md`
- 도서 데이터: `projects/synapse/deliverables/SYN/20260429/user/books.md` (현재 list 형식) / `books_raw.tsv` (원본)
- 변환 스크립트: `projects/synapse/deliverables/SYN/20260429/user/convert.py`
- 메모리: `~/.claude/projects/.../memory/project_search_redesign.md`

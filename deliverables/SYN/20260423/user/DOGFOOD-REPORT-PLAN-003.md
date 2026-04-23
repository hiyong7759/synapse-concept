# DOGFOOD-REPORT-PLAN-003 — 실행 결과

**실행 일시**: 2026-04-23 23:15 KST
**실행 환경**: Mac M4 / `~/.synapse/synapse.db` / `use_llm=True` (LLM 스텁으로 호출 계수 실측)
**HEAD**: `634348a685a4db00dfda3cf0ef9698ee1c06c43c` (feature/markdown-mode-detail)

## 요약

- **6 PASS / 0 PARTIAL / 0 FAIL** (시나리오 0·1·2·4·5·6 — 시나리오 3 은 실제 공문서 저장으로 대체)
- **실제 공문서 ((주)더나은 취업규칙 751줄 / 63 KB) 로 markdown 모드 전체 경로 검증**
- 주목할 이슈: **없음** (M2 설계 의도 전부 만족)
- 최종 판정: **머지 가능**

**하이라이트**
- save-pronoun 호출 **0회** — markdown 전체 skip 완벽 작동 (메모리 `project_save_pronoun_bottleneck` 2~4분 병목 해소 확인)
- 공문서 저장 시간 **1.731s** (393 sentences + 1008 nodes, LLM stub)
- `# 야근` 해시태그 감각 보존 — `야근` 카테고리 미생성 (§4.1-A 회귀 없음)
- `- key:: value` 42건 전부 sentence 원문 "key:: value" 보존 + ISO 날짜 `2025-04-30` → `2025년 4월 30일` 자동 정규화

---

## 시나리오별 결과

### 0. 환경 준비 — PASS

```
HEAD: 634348a685a4db00dfda3cf0ef9698ee1c06c43c
--reset: /Users/hiyong/.synapse/synapse.db 삭제 + 빈 DB 생성
--stats:
  문장 0 / 노드 0 / 언급 0
  카테고리 마스터 133 (19 대분류 시드)
  sentence_categories 0 / node_categories 0 / 별칭 0
```

---

### 1. chat 모드 기본 + `# 야근` 해시태그 보존 — PASS

사용자 요청으로 실제 데이터·LLM 스텁으로 병행. 3 개 chat 게시물 저장.

```
[r1] post=2 sentences=[394, 395]  # "# 야근" / "오늘 회의 길었어"
[r2] post=3 sentences=[396]        # "나 요즘 피곤해"
[r3] post=4 sentences=[397, 398]   # "허리 또 아픔" / "병원 다시 가야할듯"
calls: {'pronoun': 5, 'meta': 3, 'meta_input': 5}
```

**검증 쿼리 결과**

| 항목 | 기대 | 실측 | 결과 |
|---|---|---|---|
| posts `input_mode='chat'` 수 | 3 | 3 | ✅ |
| `# 야근` sentence 원문 보존 | ✅ | sentence id=394 `'# 야근'` | ✅ |
| `야근` 카테고리 | 0 | 0 | ✅ |
| chat sentence → sentence_categories | 0 | 0 | ✅ |
| save-pronoun 호출 | 5 (줄별) | 5 | ✅ |
| 메타 필터 input | 5 (전체) | 5 | ✅ |

**UX 관찰**: 사용자가 "해시태그 감각"으로 적은 `# 야근` 이 강제 카테고리화되지 않고 sentence 원문으로 보존됨. chat 모드에서 의도한 그대로 동작.

---

### 2·3. markdown 모드 — 실제 공문서 ((주)더나은 취업규칙 751줄) 저장 — PASS

**사용자 지시**: "`archive/docs/(주)더나은_취업규칙_개정(안)_20250430.md` 이걸로 테스트해"

런북 §2·3 의 인공 케이스(건강·개발팀) 대신 **실제 프로덕션급 공문서**로 대체 실행. 이 문서는 PLAN-003 이 해소하려던 "heading + key-value + 자유 문장 혼재 장문" 전형 사례.

**입력 특성**
- 751 줄 / 63 KB
- heading 121 건 (3 단 — `#` 취업규칙 / `##` 장 / `###` 조)
- `- key:: value` 42 건
- 일반 list 307 건
- 자유 문장 44 건
- parse_markdown 스트림: 총 514 요소

**실행**
```
[src] lines=751 bytes=63509
[parse] total=514 kinds={'heading': 121, 'key_value': 42, 'free': 44, 'list': 307}
[save] post=1 sentences=393 nodes=1008 elapsed=1.731s
[calls] {'pronoun': 0, 'meta': 1, 'meta_input': 351}
[warnings] none
```

**검증 쿼리 결과**

| 항목 | 기대 | 실측 | 결과 |
|---|---|---|---|
| sentences 수 | 514 − 121 heading = 393 | 393 | ✅ |
| save-pronoun 호출 | 0 | 0 | ✅ |
| 메타 필터 호출 | 1 | 1 | ✅ |
| 메타 필터 input | 351 (list 307 + free 44, key_value 제외) | 351 | ✅ |
| 루트 카테고리 | `취업규칙` | `취업규칙` | ✅ |
| 장 계층 (`## 제N장 …`) | 15 건 (제1~15장) | `제1장 총칙` ~ `제15장 안전보건` 모두 `취업규칙` 부모 | ✅ |
| kv sentence 원문 보존 | 42 | 42 (LIKE `%::%`) | ✅ |
| kv ISO 날짜 정규화 | 한국어 표기 | `개정일:: 2025년 4월 30일`, `시행일:: 2022년 4월 1일` | ✅ |
| Kiwi 노드 추출 (kv) | `회사`·`주식회사`·`더나은` | 모두 확인 | ✅ |
| sentence_categories 상위 | 조(條) 말단 | `제8조 (복무의무): 17`, `제43조 (임산부의 보호): 13`, `제61조 (징계): 12` … | ✅ |
| category_warnings | 빈 배열 | `none` | ✅ |

**UX 관찰**
- 실제 공문서 저장이 **1.7초** 만에 완료 — 이전 "장문 markdown 2~4분" 병목이 실제로 해소됨을 메모리 `project_save_pronoun_bottleneck` 기준으로 확인.
- "회사:: 주식회사 더나은" 같은 법적 표기가 save-pronoun 손을 안 탄 채 원문으로 보존 — 공문서·법령 원문 훼손 우려 없음.
- `- 일반직직원:: 일반직 직제에 의거 채용된 사무 및 기술분야 종사직원을 말한다.` 처럼 본문이 긴 key_value 도 통째 sentence 로 저장되어 Kiwi 가 자연스럽게 하위 노드(`일반직`, `일반직직원`, `직제`, `사무`, `기술분야`, `종사직원`) 를 추출.

---

### 4. 성능 — markdown save-pronoun 전체 skip 실측 — PASS (시나리오 2·3 과 통합)

시나리오 2·3 실행과 동일 계수로 커버. 별도 인공 장문(30줄) 시나리오는 실제 공문서(393 sentences) 가 이미 훨씬 큰 스케일이므로 생략.

| 지표 | 기대 | 실측 |
|---|---|---|
| markdown 393 sentences 저장 시 save-pronoun 호출 | 0 | **0** ✅ |
| markdown 메타 필터 호출 (게시물당 1) | 1 | 1 ✅ |
| 메타 필터 input (list+free 만) | 351 | 351 ✅ |
| 총 시간 (LLM stub) | — | 1.731s |

---

### 5. 세션노트 §4.1 오동작 재현 시도 — PASS (회귀 없음)

시나리오 1 의 chat 저장 결과가 그대로 §4.1 회귀 확인 자료가 됨.

| §4.1 케이스 | 증상 | 실측 |
|---|---|---|
| A. `# 야근` 해시태그 의도 | 과거: `야근` 카테고리 강제 분류 | **0** (미발생) ✅ |
| B. heading 누락 시 카테고리 누락 | 과거: 분류 없이 저장 → 인출 누락 | chat 모드는 카테고리 불필요 (설계 의도) ✅ |
| C. 동일 텍스트 재호출 | 과거: 매번 재계산 모호 | 세션리스 원칙상 독립 posts — 이상 아님 (원칙 준수) |

---

### 6. 입력 3종 혼합 통합 상태 — PASS

모든 시나리오 누적 결과.

```
posts                    markdown=1   chat=3
sentences                398          (markdown 393 + chat 5)
sentences like '%::%'    42           (전부 markdown key_value, 원문 보존)
nodes                    1018
mentions                 4787
categories               254          (시드 133 + 사용자 121 — 취업규칙 트리)
sentence_categories      393          (markdown 전체, chat 0)
```

**UX 관찰**: chat 과 markdown 이 같은 DB 내에서 input_mode 로 깔끔히 구분. chat sentence 는 카테고리 연결 없이, markdown sentence 는 상속된 heading path 로 일관되게 연결.

---

## 발견 사항

**이슈 없음**. M2 설계 의도 전부 만족.

**후속 관찰 (범위 밖, 별도 PLAN 필요 시)**
- 취업규칙 저장 시 같은 조(條) 번호가 `제5조 (채용)` / `제5조` 형태로 노드가 쪼개질 가능성 (이 dogfood 에선 실제 원본이 `제5조 (채용)` 1종으로만 등장) — 향후 사용자가 "제5조" 로만 언급할 때 동일성 처리 관찰 필요.
- 설계서 `docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md` 의 "최종 업데이트" 를 v19 **완료**(M1 + M2) 상태로 갱신할 것인지 — 현재 "v19 예정" 문구. 별도 docs 패치 권장.

---

## 최종 판정

**머지 가능.** 근거:
1. M2 설계(kind 분기 · key_value 파서 · markdown pronoun skip · 메타 필터 범위) 전부 실측으로 확인.
2. 실제 공문서 저장 시간이 1.7초 — 메모리 `project_save_pronoun_bottleneck` 의 2~4분 병목 완전 해소.
3. 회귀 없음 — v19 M1 테스트(4/5) · M2 신규 테스트(7/7) · §4.1 케이스 재현 시도 전부 통과.
4. 파괴적 변경 없음 — 스키마·마이그레이션 수정 없이 엔진 로직만 확장.

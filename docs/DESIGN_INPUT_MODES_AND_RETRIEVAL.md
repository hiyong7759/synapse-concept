# Synapse 설계 — 입력 모드 & 인출 관계

**관련 문서**: `DESIGN_PRINCIPLES.md` §1 원칙 9 · `DESIGN_PIPELINE.md` 저장 파이프라인 · `DESIGN_HYPERGRAPH.md` 스키마 · `DESIGN_UI.md` 와이어프레임

---

## 세션 그릇 정의 (3 종)

| kind | UI 라우트 | API `kind` 값 | 주된 용도 |
|---|---|---|---|
| **note** | `/note` | `'note'` | **모든 지식 축적** — 한 줄 메모도 긴 마크다운도 같은 그릇. heading·`::`·list·평문 자유 혼재. heading 있으면 카테고리 등록, 없으면 free 처리. |
| **synapse** | `/synapse` | `'synapse'` | 지식 활용·융합 — 축적된 지식 사이의 새 연결 발화. 질문·답이 역사로 기록되며 노드 편입 없음 |
| **insight** | 승격 전용 | `'insight'` | 사용자가 synapse 메시지를 "통찰"로 승격 → 고유 post 1 개 = 본체 sentence 1 개. 편집 불가·허브 연결 |

**API 계약** — `note` 는 사용자가 `/note` 화면에 진입해 입력하면 자동 생성. 사용자가 모드를 명시하지 않음. `synapse` 는 `/synapse` 진입 + 첫 질문 시 자동 생성. `insight` 는 `POST /promote` 전용 (일반 save 경로에서 생성 불가).

**저장 두 층 분리 (`note` 그릇 적용)**:
- **자동저장** — `posts.source` 만 갱신 (입력 1.5초 디바운스 + 페이지 이탈). LLM 호출 없음.
- **의미 처리** — sentences·노드·LLM 정정 후보 생성 (사용자 명시 트리거: ⌘S / "정리" 버튼). 자동저장과 한 트랜잭션으로 source 동기화 후 진행.

**모드 인식 UI** — 라우트 두 개(`/note`·`/synapse`) 만 있어 사용자가 모드를 인지·선택하지 않음.

---

# 작성자 가이드

> 시냅스에 글을 저장하는 입력 담당자를 위한 실전 가이드.

**한 줄 요약** — `/note` 에 무엇이든 자유롭게 쓰되, 구조화된 글일 때는 딱 **4가지 요소**(`#`, `- key:: value`, `- value`, 자유 문장)만 기억하세요. 평문은 평문대로 받습니다.

---

## `/note` 단일 그릇

모든 입력은 `/note` 라우트의 단일 입력 영역으로 받습니다. 모드 선택 없음.

| 입력 성격 | 어떻게 쓰면 되는지 |
|---|---|
| 한 줄·몇 줄 즉흥 메모, 감정 기록 | 그냥 평문으로 적기 |
| 제목·항목·표가 있는 구조화된 글 | 아래 4 가지 요소 활용 |
| 공문서·법령·규정·매뉴얼 원문 | 4 가지 요소 + 템플릿 활용 |
| 레시피·체크리스트·업무 일지 | 템플릿 활용 |
| 회의록·학습 정리 | 템플릿 활용 |

**핵심**: 평문이든 마크다운이든 같은 그릇 (`note` post). heading 이 있으면 의미 처리 단계가 카테고리로 등록하고, 없으면 자유 문장으로 처리 — 사용자가 모드를 선택하지 않습니다.

---

## 4 가지 요소 판단표 ⭐

| 내용 성격 | 쓰는 법 | 예시 | 저장 결과 |
|---|---|---|---|
| 분류·주제 제목 (여러 줄) | `# 제목`, `## 소제목` | `## 제4장 인사` | **카테고리 경로** 등록 (문장 저장 안 됨) |
| 분류 경로 한 줄 입력 | `# 분류1.분류2.분류3` | `# 취업규칙.제1장 총칙.제1조` | 여러 단계 **한번에** 등록 |
| 용어 = 정의 | `- key:: value` | `- 보직:: 직원의 자질에 따라...` | 용어·정의가 **묶여서** 한 문장으로 |
| 속성 = 값 | `- key:: value` | `- 개정일:: 2025-04-30` | 메타데이터 문장 |
| 병렬 나열 (2개 이상) | `- value` | `- 이력서 1통`<br>`- 자기소개서 1통` | 각 줄이 **독립 문장** |
| 단일 문장·문단 | 그냥 쓰기 | `이 규칙은 ... 목적으로 한다.` | 문단 단위 문장 |

**핵심 포인트 4 개**
- `::` **두 개**여야 key-value 로 인식 — `:` 하나는 일반 문장으로 떨어짐
- 항목이 **1개뿐**이면 `- ` 없이 그냥 문장
- 조항·섹션 제목처럼 "그 아래 문장들이 소속되는" 표시는 **반드시 heading** (`##`, `###`)으로
- 한 줄 경로에서 **`.` 은 단계 구분자** — 분류 이름에 `.` 은 넣지 않기

---

## heading 단계

**기준** — 이 제목 **아래 여러 줄**이 같은 분류에 속하는가?

- ✅ heading: 장·절·조, 챕터, 주제 단위
- ❌ 자유 문장: 한 번만 등장하는 강조, 단일 문장 전환

| 단계 | 용도 | 예시 |
|---|---|---|
| `#` | 문서 전체 주제 | `# 취업규칙` |
| `##` | 장·큰 묶음 | `## 제1장 총칙` |
| `###` | 절 | `### 제1절 인사위원회` |
| `####` | 조항 | `#### 제13조 (구성)` |

### 한 줄 경로 입력 (점 구분자)

여러 줄로 쓰는 대신 **`.` 로 단계 구분**해서 한 줄에 경로를 지정할 수 있습니다.

```markdown
# 취업규칙.제1장 총칙.제1조 (목적)
이 규칙은 ... 목적으로 한다.
```

→ 저장되는 경로는 `취업규칙 > 제1장 총칙 > 제1조 (목적)` 3단계로 자동 분해.

**동작 규칙**
- `.` 만나면 경로가 새로 세팅됨 (이전 heading 맥락 리셋)
- `#` 개수는 **무시**됨 — `# A.B.C` 와 `### A.B.C` 결과 동일
- 뒤에 이어지는 `##` 등은 점 경로에 맞춰 덮어쓰기

**`.` 은 단계 구분자 — 분류 이름에 `.` 넣지 않기**

```markdown
❌  # Ver 1.0       → "Ver 1" > "0" 2단계로 쪼개짐 (원치 않는 해석)
✅  # Ver 1-0        → 단일 분류 "Ver 1-0"
✅  ## Ver 1.0       → 여러 줄 heading 이면 점이 있어도 한 단계로 취급
```

점이 포함된 이름(버전·날짜)을 분류로 쓰고 싶으면 **여러 줄 heading**을 쓰거나 **하이픈(`-`)·언더스코어(`_`)** 로 대체.

---

## 자주 하는 실수 ⚠️

UI 실시간 린터 슬롯 → 빨간 밑줄 + 마우스오버 툴팁

### 실수 1 — 콜론을 하나만 씀

```markdown
❌  - 보직: 직원의 자질에 따라 ...     일반 리스트로 강등 (파서 매칭 실패)
✅  - 보직:: 직원의 자질에 따라 ...    용어-정의로 저장
```

### 실수 2 — 조항·섹션 제목을 자유 문장으로 흘려둠

```markdown
❌  ## 제1장 총칙
    제1조 (목적)
    이 규칙은 ...

✅  ## 제1장 총칙
    ### 제1조 (목적)
    이 규칙은 ...
```
이유 — 자유 문장으로 두면 "제1조" 분류가 생기지 않아 조항 경계가 뭉개집니다.

### 실수 3 — 같은 줄에 제목과 본문 섞기

```markdown
❌  ## 제1조 (목적) 이 규칙은 ... 목적으로 한다.

✅  ## 제1조 (목적)
    이 규칙은 ... 목적으로 한다.
```

### 실수 4 — 분류 이름에 `.` 넣기

```markdown
❌  # Ver 1.0        → "Ver 1" 과 "0" 두 단계로 쪼개져 저장됨
✅  # Ver 1-0         → 단일 분류 "Ver 1-0"
```

### 실수 5 — 연속 점 `..` 또는 시작·끝 점

```markdown
❌  # A..B            → "A" > "" > "B" 중간에 빈 분류 생성
❌  # .A.B            → 첫 단계가 빈 이름
❌  # A.B.            → 마지막 단계가 빈 이름
✅  # A.B             → 깔끔하게 두 단계
```

### 실수 6 — `- key::` 뒤 값이 비어있음

```markdown
❌  - 개정일::         → key-value 인식 실패, 일반 리스트로 강등
✅  - 개정일:: 미정     → 값이 있어야 key-value 로 저장됨
✅  - 개정일:: (미정)   → 괄호로 "아직 없음" 명시
```

---

## 의미 처리 전 체크리스트 (구조화된 글일 때만)

UI 의미 처리 트리거 (⌘S / "정리") 직전에 필요할 때 노출. 평문 메모는 체크 불필요.

- [ ] `#`/`##`/`###` 제목이 **분류로서 의미**가 있는가?
- [ ] 용어 정의·속성은 모두 `::` **두 개**로 썼는가?
- [ ] 조항·섹션 제목을 자유 문장으로 흘리지 않았는가?

자동저장은 항상 백그라운드로 진행되므로 손실 걱정은 없습니다 — 위 체크는 LLM 정정 후보 품질을 위한 것.

---

## 헷갈리는 경계 사례 (FAQ)

**Q1. 자유 문장도 `- ` 붙여 리스트로 해야 하나?**
A. 불필요. 단일 문단은 그대로 두세요. `- ` 는 **병렬 나열 2개 이상**일 때만.

**Q2. `- key:: value` 의 value 로 긴 문장 넣어도 되나?**
A. OK. value 길이·형태 제한 없음.

**Q3. 일반 문장 vs `- key:: value` 결과 차이?**
A. 파이프라인 관점 차이는 **메타 필터 skip 여부** 하나. key-value 는 "용어 = 정의" 가 **명시적으로 결속**되어 인출이 더 정확합니다.

**Q4. 평문 메모에 `#` 를 해시태그처럼 써도 되나?**
A. 됩니다. 의미 처리 시 `#` 로 시작하는 줄이 있으면 카테고리 등록 후보가 되고, 없으면 평문으로 처리됩니다.

**Q5. 원본에 `①②③` 같은 번호가 있으면?**
A. 번호는 **떼고** `- value` 리스트로 변환. 시냅스는 순서보다 의미 연결이 중요.

**Q6. 표(`|...|...|`)는 어떻게 처리되나?**
A. 현재 파이프라인은 표를 **자유 문장 묶음**으로 처리. 구조적 의미는 보존되지 않음. 표 내용이 중요하면 `- key:: value` 시리즈로 풀어 쓰는 걸 권장.

---

## 문서 유형별 템플릿

### 법령·규정·정책

```markdown
# 취업규칙

- 회사:: 주식회사 더나은
- 개정일:: 2025-04-30
- 시행일:: 2022-04-01

## 제1장 총칙

### 제1조 (목적)

이 규칙은 ... 을 정함을 목적으로 한다.

### 제2조 (적용범위)

- 이 규칙은 ... 에 적용한다.
- 다만, ... 의 경우에는 제외한다.
```

### 회의록

```markdown
# 2026-04-23 카테고리 재설계 회의

- 일시:: 2026-04-23 14:00
- 참석자:: 김지원, 박진호, 이수민
- 안건:: 카테고리 단일 매핑 전환

## 논의 내용

### 1안 — 단일 매핑

`node_category_mentions` 단일 매핑이면 ... 한계가 있다. 분리하면 ...

## 결정 사항

- 1안 채택
- 박진호가 M1 구현, 다음 주까지 완료
```

### 레시피

```markdown
# 김치찌개

- 조리시간:: 30분
- 인분:: 2인분

## 재료

- 김치:: 200g
- 돼지고기:: 150g
- 두부:: 반 모

## 조리 순서

- 팬에 기름을 두르고 돼지고기를 볶는다.
- 김치를 넣고 5분간 볶는다.
- 물 500ml를 붓고 끓인다.
```

### 일지

```markdown
# 2026-04-23 업무 일지

- 날씨:: 맑음
- 기분:: 보통

## 한 일

- 카테고리 재설계 리뷰
- 취업규칙 마크다운 변환

## 배운 것

분류가 의미 있게 쪼개져 있으면 인출 정확도가 올라간다.
```

---

# 파이프라인 명세

> 작성자가 친 입력이 엔진 안에서 어떻게 처리되는지의 단일 출처.

## 마크다운 문법 (파서 동작)

`/note` 입력은 평문일 수도 있고, 4 가지 마크다운 요소로 구성될 수도 있다. 사용자는 인지·선택하지 않으며, 의미 처리 시점에 `parse_markdown` 이 자동 분기. heading 이 있으면 카테고리 경로 상속, 없으면 모든 줄을 free 로 처리. 각 요소는 저장 파이프라인에서 서로 다른 경로를 탄다.

### 1) heading
```markdown
# 건강
## 허리
```
- 저장 효과: 카테고리 경로(`건강 > 허리`) 등록. 이후 요소는 이 경로를 **상속**한다.
- sentence INSERT **안 함**. (heading 자체는 문장 아님.)
- 카테고리 origin: `user`.

**heading name 정규화 규칙** (파서가 자동 적용)
- 분리 의도 특수문자 → 공백 치환: `/` `|` `\` `·` `,` `;` `&` `+` `~` `→`
  - 예: `## 만화/라이트노벨` → 카테고리 이름 `만화 라이트노벨`
- 보존 (이름 일부로 그대로): `-` `_` `()` `[]` `{}` `"` `'` `:` `?` `!`
- `.` 은 단계 분리자로 별도 해석 (한 줄 경로 입력 — 위 §heading 단계 참고)
- 헤딩 단계는 List<String> 으로 보관·DB 저장. 문자열 join/split 왕복 없음 — 분리자 충돌 자체가 발생하지 않음

### 2) `- key:: value` (Obsidian Dataview 스타일)
```markdown
- 팀장:: 박지수
```
- 저장 효과: sentence 로 **통째 저장**(`text="팀장:: 박지수"`). 별도 속성 테이블 신설 안 함.
- Kiwi 형태소 분석은 **통째 문장 대상**으로 실행 → `팀장`, `박지수` 같은 노드가 자연스럽게 뽑힘.
- save-pronoun **skip** (구조화 — 지시어 가능성 낮음).
- 메타 필터 **제외**.

파서 정규식: `^-\s+(.+?)\s*::\s+(.+)$` — key 와 value 양쪽 공백은 trim. 둘 중 하나라도 비면 매칭 실패 → 일반 list 로 강등.

### 3) `- value` (일반 list)
```markdown
- 오늘 피곤함
```
- 저장 효과: sentence INSERT. 일반 자유 문장과 동일 취급.
- 메타 필터 대상 · save-pronoun 호출 (지시어 치환).

### 4) 자유 문장 (paragraph)
```markdown
어제보다 훨씬 나아졌다.
```
- 저장 효과: sentence INSERT.
- 메타 필터 대상 · save-pronoun 호출.

### 상속 규칙

heading 뒤에 오는 모든 요소(2·3·4)는 **가장 가까운 heading 경로** 를 `category_path` 로 상속한다. heading 간 깊이 변화는 마크다운 표준대로 — `#` → `##` → `###` 누적, 같은 레벨은 덮어쓰기.

---

## 저장 파이프라인 — 단일 경로 (`note` 그릇)

`parse_markdown` 이 heading 유무를 자동 판단해 카테고리 등록 또는 free 처리. 의미 처리 트리거 시점에만 호출 (자동저장은 source UPDATE 만).

### note 그릇 — heading 없는 입력 (평문)

```
사용자 입력 (단일 줄 또는 여러 줄 평문)
  ↓ 자동저장: posts.source UPDATE   ← 1.5초 디바운스, LLM 미사용
  ────────────────────
  사용자 ⌘S / "정리" 버튼:
  ↓ 의미 처리 호출
  ↓ posts.source UPDATE (자동저장 미발화분 flush)
  ↓ 기존 sentences DELETE (post_id CASCADE)
  ↓ parse_markdown — heading 없음 → 모든 줄 (category_path=None, kind='free', text)
  ↓ [메타 필터 — 게시물 단위 1회 LLM]
     모든 줄 대상
  ↓ 줄별 (메타 idx 제외):
     ① save-pronoun (LLM) — 지시어·날짜 치환
     ② ISO 날짜 정규화 (규칙)
     ③ unresolved 감지 (규칙)
     ④ sentence INSERT (category_path=None, role='user')
     ⑤ Kiwi 형태소 분석
     ⑥ 날짜 분할 (규칙)
     ⑦ 노드 upsert + node_sentence_mentions
        — sentence_categories 등록 없음 (상속할 heading 없음)
  ↓ LLM 정정 후보 생성 (자모 거리 사전 필터 + 별칭 보호 + 캐싱)
  ↓ 응답: { post_id, sentence_ids, nodes_added, correction_candidates: [...] }
```

### note 그릇 — heading 포함 입력 (구조화)

```
사용자 입력 (heading + key-value + list + 자유 문장 혼재)
  ↓ 자동저장: posts.source UPDATE   ← 1.5초 디바운스, LLM 미사용
  ────────────────────
  사용자 ⌘S / "정리" 버튼:
  ↓ 의미 처리 호출
  ↓ posts.source UPDATE (자동저장 미발화분 flush)
  ↓ 기존 sentences DELETE (post_id CASCADE)
  ↓ parse_markdown — (category_path, md_kind, text) 튜플 스트림
                      md_kind ∈ {'heading', 'key_value', 'list', 'free'}
  ↓ [메타 필터] — 자유 문장·list 만 대상 (heading·key_value 제외)
  ↓ 요소별:
     [heading]
        — sentence INSERT 안 함
        — 카테고리 path 등록 (categories 마스터 테이블)
     [key_value]
        ② ISO 날짜 정규화
        ③ unresolved 감지
        ④ sentence INSERT (text="key:: value", category_path 상속)
        ⑤ Kiwi 형태소 분석
        ⑥ 날짜 분할
        ⑦ 노드 upsert + node_sentence_mentions + sentence_categories
        — save-pronoun skip (구조화 — 지시어 가능성 낮음)
     [list / free]
        ① save-pronoun (LLM) — 지시어·날짜 치환
        ② ISO 날짜 정규화
        ③ unresolved 감지
        ④ sentence INSERT (category_path 상속)
        ⑤ Kiwi 형태소 분석
        ⑥ 날짜 분할
        ⑦ 노드 upsert + node_sentence_mentions + sentence_categories
  ↓ LLM 정정 후보 생성 (자모 거리 사전 필터 + 별칭 보호 + 캐싱)
  ↓ 응답: { post_id, sentence_ids, nodes_added, correction_candidates: [...] }
```

### synapse 모드

```
사용자 질문 입력
  ↓ posts 행이 없으면 새로 생성 (kind='synapse', title=첫 질문 첫 행, source=질문)
     있으면 기존 synapse post 이어서
  ↓ sentence INSERT (role='user', origin=NULL)
  ↓ source 에 "> user: {질문}" 라인 append
  ↓ retrieve() — 키워드 후보(형태소 + retrieve-expand LLM)
                  → filter-keywords LLM 1배치로 불순물 제거
                  → 노드/카테고리 직접 lookup
                  → 세 경로(문장 바구니 + 카테고리 공유 + 사용자 heading) sentence 수집
                  현재 synapse post 의 이전 질문·답도 LLM 프롬프트 맥락으로 주입
                  상세는 DESIGN_PIPELINE §인출 파이프라인
  ↓ answer 생성 (LLM 이 마크다운 포맷으로 재조합 응답)
  ↓ sentence INSERT (role='assistant', origin=NULL, text=answer)
  ↓ source 에 "< assistant: {answer}" 라인 append
  ↓ ❌ node_sentence_mentions 편입 안 함 (원칙 15-1)
  ↓ ❌ sentence_categories 편입 안 함
  ↓ ❌ aliases 편입 안 함
  ↓ 결과적으로 synapse post 의 sentence 는 "역사 기록" 으로만 남는다
```

### insight 모드 (승격 전용)

```
사용자가 /synapse 세션 메시지의 [⬆ 통찰로 승격] 클릭
  ↓ promote_to_insight(source_sentence_id, snapshot_node_ids) 호출
  ↓ 새 posts 행 (kind='insight',
                  title=해당 메시지 첫 행,
                  source=해당 메시지 본문)
  ↓ 본체 sentence INSERT
       (post_id=새 insight post, role='user',
        origin='insight', text=해당 메시지 본문)
  ↓ Kiwi 형태소 분석 (본체 sentence text 대상)
     + 스냅샷 노드 id 합집합
  ↓ node_sentence_mentions 일괄 INSERT (허브 자동 연결)
     — 본문 언급 여부 무관 (원칙 15-2, Hebbian)
  ↓ (선택) 사용자가 19 대분류 통찰 카테고리 지정 시 node_category_mentions
  ↓ ❌ 본체 sentence 는 이후 update_sentence API 에서 거부됨 (편집 불가)
  ↓ ❌ 삭제는 /review 승인 경로 (원칙 8)
```

---

## 한 눈 비교표

| 처리 | note (heading 없음) | note (heading 포함) | synapse | insight |
|---|:---:|:---:|:---:|:---:|
| sentence INSERT (user) | ✅ | ✅ (heading 제외) | ✅ 질문 | ✅ 본체 1개 |
| sentence INSERT (assistant) | — | — | ✅ 답 | — |
| category_path 상속 | — | ✅ | — | — |
| 메타 필터 | ✅ 전체 | 자유문장·list만 | ❌ | ❌ |
| save-pronoun | ✅ list/free | ✅ list/free (key_value skip) | ❌ | ❌ |
| ISO 날짜 정규화 | ✅ | ✅ | — | ✅ |
| unresolved 감지 | ✅ | ✅ | — | — |
| Kiwi 형태소 | ✅ | ✅ | ❌ | ✅ |
| 날짜 분할 | ✅ | ✅ | — | ✅ |
| node_sentence_mentions 편입 | ✅ | ✅ | **❌** | ✅ + **세션 retrieve 노드 허브** |
| sentence_categories 편입 | ❌ | ✅ (heading 있으면) | ❌ | 옵션 (사용자 지정) |
| aliases 자동 | ✅ | ✅ | ❌ | ✅ |
| source 에 누적 | ✅ 자동저장 + 의미 처리 시 동기화 | ✅ 동일 | ✅ Q/A 로그 | 본체 1 줄 |
| LLM 정정 후보 | ✅ 의미 처리 시점 | ✅ 의미 처리 시점 | ❌ | ❌ |
| 편집 가능 | ✅ source 재로드 | ✅ source 재로드 | ✅ 개별 sentence | **❌ 본체 불변** |

### 공통 전처리

**어느 그릇이든 거치는 단계** — ISO 날짜 정규화·unresolved 감지·Kiwi 형태소·날짜 분할. 이는 그릇과 무관한 **기계적·결정론적** 변환이라 origin 이 `system` 으로 남는다.

---

## LLM 호출 요약

| LLM 태스크 | note (의미 처리) | synapse | insight |
|---|:---:|:---:|:---:|
| 메타 필터 (의미 처리 1회) | ✅ 자유 문장·list | ❌ | ❌ |
| save-pronoun (list/free 줄별) | ✅ | ❌ | ❌ |
| LLM 정정 후보 생성 | ✅ 의미 처리 끝부분 | ❌ | ❌ |
| retrieve-expand / filter-keywords | — | **✅ (핵심)** | — |
| 답 생성 (LLM 재조합·마크다운 포맷) | — | **✅** | — |
| 카테고리 분류 워커 (백그라운드) | ✅ | ❌ | 옵션 |
| Wikidata 별칭 워커 (백그라운드) | ✅ | ❌ | ✅ |

**LLM 호출은 자동저장 시점엔 0회** — 사용자 명시 의미 처리 트리거에서만 호출되어 모바일 배터리·발열·네트워크 부담 통제됨 (원칙 13 정합).

key_value 줄에서 save-pronoun 을 skip 하는 근거:
- 구조화된 속성이라 지시어 존재 가능성 자체가 낮음
- 호출량 절감 — 장문 노트에서 key_value 줄별 호출은 불필요

---

## synapse 세션이 지켜야 할 것

- 질문·답 sentence 는 저장되지만 `node_sentence_mentions` 편입 **안 함**. 질문은 "사실 언급" 이 아니므로 (원칙 1).
- 사용자가 명시적으로 "통찰" 로 승격시키기 전까지 하이퍼그래프에 영향 없음.
- 답 형식은 LLM 이 **마크다운으로 재조합** (단순 원문 나열 금지). 사용자 후속 발화로 정제·심화.
- 세션 단위 재진입 가능 — 과거 synapse post 를 목록에서 열어 이어서 질문·심화.
- 맥락 누적 — 세션 내 직전 질문·답이 다음 retrieve 의 LLM 프롬프트 맥락으로 주입됨.

---

## 호출자 (환경별)

**Python frozen 환경** (학습·dogfood·참조 구현):

| 호출부 | 동작 |
|---|---|
| `engine.cli` 대화형 | `kind='note'` (입력은 단일 그릇) |
| `api/routes/graph.py` `POST /note` | 새 note post 생성 + 첫 source 저장 |
| `api/routes/graph.py` `PATCH /posts/{id}` | 자동저장 — `posts.source` 만 갱신 (LLM 호출 없음) |
| `api/routes/graph.py` `POST /posts/{id}/process` | 의미 처리 — sentences 재계산 + LLM 정정 후보 생성 (사용자 명시 트리거) |
| `api/routes/graph.py` `POST /synapse/turn` | `kind='synapse'`. retrieve + answer + 세션 기록 전용 |
| `api/routes/graph.py` `POST /promote` | `kind='insight'` post 생성. source sentence_id + node_ids 받음 |

**Flutter 환경** (모바일·데스크톱):

| 호출부 | 동등 동작 |
|---|---|
| `synapse_engine.SynapseFlow.noteAutosave` | `posts.source` UPDATE (LLM 미사용, <50ms) |
| `synapse_engine.SynapseFlow.noteProcess` | sentences 재계산 + LLM 정정 후보 (사용자 명시 트리거, ⌘S / "정리") |
| `synapse_engine.SynapseFlow.synapseTurn` | `kind='synapse'` post — retrieve + answer + 세션 기록 |
| `synapse_engine.SynapseFlow.promoteToInsight` | `kind='insight'` post 생성 + retrieve 캐시 노드 일괄 허브 연결 |
| `synapse_engine.SynapseFlow.listPosts/getPost/...` | post 목록·재진입·삭제 |

엔진 패키지 API 세부는 `DESIGN_ENGINE.md §2`.

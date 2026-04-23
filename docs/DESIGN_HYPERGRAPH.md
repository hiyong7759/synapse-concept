# Synapse 설계 — 하이퍼그래프 모델

**최종 업데이트**: 2026-04-23 (v20 계획 — PLAN-004 "카테고리 재설계" · `categories` · `sentence_categories` 신설, `node_categories` 를 19 대분류 태깅용으로 재정의 (`major_category TEXT`). 선행 v19: `posts.input_mode` 신설. v18: 상태 레이어 제거 / `sentences.status` · `extract-state` 폐기. v17: Kiwi-first + 메타 필터 + origin `rule→system`)

## 핵심 설계 원칙

하이퍼그래프 모델에 적용되는 원칙은 **`docs/DESIGN_PRINCIPLES.md`**로 이전·통합되었다.

- **§1 시스템 관통 원칙** (존재론·구조·저장·동작) — 노드/하이퍼엣지/문장의 정의와 저장 규칙
- **§2 개인 / 조직 모드 원칙** — 1인칭 처리, 주어 명시 규칙

이 문서는 스키마·구현·예시에 집중하며, 위 원칙은 단일 출처인 `DESIGN_PRINCIPLES.md`를 참조한다.

---

## 왜 하이퍼그래프인가 (지식 바구니 은유)

전통적인 그래프는 `A — B` 같은 **선(엣지)**으로 두 노드를 잇는다. 하지만 실제 기억은 "A와 B가 함께 떠올랐다"는 **공동 활성화**에 가깝다. Synapse는 이걸 다음과 같이 표현한다:

- **바구니 = 하이퍼엣지** — 여러 노드를 동시에 묶는 그릇
- **문장 바구니**: 같은 sentence에 등장한 노드들 전부를 하나의 하이퍼엣지로 묶음
- **카테고리 바구니**: 같은 분류를 공유하는 노드들을 묶음
- **별칭 바구니**: 같은 개념의 다른 표기들을 묶음

같은 바구니 안에 있으면 연결된 것. 선을 따로 저장하지 않고, **바구니 자체가 연결 정보**다. 이게 생물학적 시냅스의 본질인 "함께 활성화되는 경향"(Hebbian)과 동형이다.

---

## 스키마 (v20 계획 · v19 현재)

> v19 → v20 변경 (PLAN-004): **카테고리 재설계** — 단일 `node_categories` 가 담던 두 역할(사용자 heading 계층 + 19 대분류 의미 태깅)을 두 축으로 분리.
> - **신설 `categories`** — 사용자 heading 계층 마스터 (adjacency list, `parent_id` FK). 19 대분류 시드 루트 + 사용자 정의 루트 공존.
> - **신설 `sentence_categories`** — 문장 ↔ 사용자 카테고리 연결 (주 매핑). heading 말단 카테고리만 등록, `origin` 유지.
> - **재정의 `node_categories`** — 19 대분류 의미 태깅 전용. `category TEXT` → `major_category TEXT` 로 의미 축소, 값은 `CATEGORY_SYSTEMPROMPT.md` 코드 상수(100 개 고정). CATEGORY 백그라운드 워커만 생성. heading 경로(`"건강.2026-04-10"` 등)는 더 이상 들어가지 않는다.
> 기존 v19 `node_categories` 는 마이그레이션: `category` 문자열이 heading path 이면 `categories` 분해 INSERT + `sentence_categories` 로 재배선, 19 대분류 코드면 `major_category` 로 유지.
> 상세는 `docs/DESIGN_CATEGORY.md` + `PLAN-20260422-SYN-004`.
>
> v18 → v19 변경 (PLAN-003 M1): **`posts.input_mode` 컬럼 신설** + `CHECK (input_mode IN ('chat','markdown'))`.
> 기존 v18 posts 는 `has_heading(markdown)` 결과로 backfill — heading 포함이면 `'markdown'`, 아니면 `'chat'`.
> 저장 모드가 "자동 판정" 에서 "사용자 명시" 로 이행된다. 상세는 `docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md`.
>
> v17 → v18 변경: **`sentences.status` 컬럼 삭제**. 관련 인덱스(`idx_sentences_status`)
> 와 `extract-state` LLM 판정 경로 전부 제거. 상태 레이어 자체 폐기 — 모든 sentence 는
> 영구 기록이며 시점 해석은 인출 LLM 이 `created_at` 기반 최근성 판단으로 처리한다.
> 기존 v17 DB 는 컬럼 제거 마이그레이션 또는 폐기·재생성.
>
> v16 → v17: origin CHECK 갱신 — `('user','ai','rule','external')` → `('user','ai','system','external')`.
> `rule` 은 수단(규칙)이지 데이터 생성 주체가 아니며, 시스템 엔진이 주체 — `system` 이 정확.
>
> v15 → v16: 스키마 동일. Kiwi 도입은 엔진 로직 수준 변경.
> v14 → v15 마이그레이션 정책은 `engine/db.py` 의 자동 백업 로직 참고.

```sql
posts:                               -- 게시물 = 맥락 그룹 (원본 마크다운 보관)
  id          INTEGER PRIMARY KEY
  markdown    TEXT NOT NULL           -- 사용자가 확정한 최종 마크다운 (heading + 본문)
  input_mode  TEXT NOT NULL DEFAULT 'chat'     -- v19 신설 (PLAN-003 M1). chat | markdown
                                               -- CHECK (input_mode IN ('chat','markdown'))
                                               -- 모드는 UI 입력창 선택으로 결정. 자동 판정 없음.
  created_at  TEXT DEFAULT (datetime('now'))
  updated_at  TEXT DEFAULT (datetime('now'))

sentences:                           -- 문장 하이퍼엣지의 실체 (post 에 속한 한 줄)
  id          INTEGER PRIMARY KEY
  post_id     INTEGER REFERENCES posts(id) ON DELETE CASCADE   -- NULL = assistant 응답
  position    INTEGER DEFAULT 0       -- post 내 순서 (0-based)
  text        TEXT NOT NULL           -- 치환·정규화 후 본문 (원형은 posts.markdown)
  role        TEXT DEFAULT 'user'     -- user | assistant
  created_at  TEXT DEFAULT (datetime('now'))
  updated_at  TEXT DEFAULT (datetime('now'))
  -- v18: status 컬럼 폐기. 모든 sentence 영구 기록.

nodes:
  id          INTEGER PRIMARY KEY
  name        TEXT NOT NULL          -- UNIQUE 아님. 동명이인/동명이의어 허용
  status      TEXT DEFAULT 'active'  -- active | inactive
  created_at  TEXT DEFAULT (datetime('now'))
  updated_at  TEXT DEFAULT (datetime('now'))

node_mentions:                       -- 문장 하이퍼엣지의 멤버십
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  sentence_id INTEGER REFERENCES sentences(id) ON DELETE CASCADE
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (node_id, sentence_id)

categories:                          -- 사용자 heading 계층 마스터 (v20 신설, adjacency list)
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  name        TEXT NOT NULL           -- 경로 한 세그먼트 ("개발팀", "2026-04-10")
  parent_id   INTEGER REFERENCES categories(id) ON DELETE CASCADE  -- NULL = 루트
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
  UNIQUE (parent_id, name)
  -- INDEX idx_categories_parent (parent_id)
  -- origin 컬럼 없음: 삭제 경로가 UI 에 없어 시드 보호는 애플리케이션 상수로 처리

sentence_categories:                 -- 문장 ↔ 사용자 카테고리 (v20 신설, 주 매핑)
  sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE
  category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE
  origin      TEXT NOT NULL DEFAULT 'user'
                       CHECK(origin IN ('user','ai','system','external'))
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
  PRIMARY KEY (sentence_id, category_id)
  -- INDEX idx_sentence_categories_cat (category_id)

node_categories:                     -- 노드 ↔ 19 대분류 (v20 재정의, LLM 워커 전용)
  node_id        INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  major_category TEXT NOT NULL       -- CATEGORY_SYSTEMPROMPT.md 코드 상수 (예: "BOD.medical")
  origin         TEXT NOT NULL DEFAULT 'ai'
                         CHECK(origin IN ('user','ai','system','external'))
  created_at     TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (node_id, major_category)
  -- v20: 이전 category TEXT → major_category TEXT 로 리네이밍, heading 경로 저장 금지
  -- FK 불필요: major_category 값은 100 개 고정 코드 상수, 애플리케이션에서 validation

aliases:                             -- 별칭 하이퍼엣지. 자동 저장 + origin 추적
  alias       TEXT PRIMARY KEY
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  origin      TEXT NOT NULL          -- user | ai | system | external   (v17: rule→system)
  created_at  TEXT DEFAULT (datetime('now'))

unresolved_tokens:                   -- 치환 실패 지시어 (유일한 승인 대기)
  sentence_id INTEGER REFERENCES sentences(id) ON DELETE CASCADE
  token       TEXT NOT NULL
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (sentence_id, token)
```

**설계 결정:**
- **엣지 테이블 폐기(v15)**: 별도 `edges` 테이블 없음. 노드 간 연결은 sentence·category·alias 세 종류의 하이퍼엣지로만 표현된다. 의미 관계(cause/avoid/similar 등)는 `sentences.text` 원문에 이미 있고, 해석은 외부 지능체(원칙 11) 몫.
- **posts = 맥락 그룹**: 사용자 저장 1회 = `save()` 1회 = posts 1행. 마크다운 heading 과 본문을 통째로 보관해 ① UI 렌더링 편의, ② 지시어·날짜 치환 이전 원본 보존, ③ 부분 수정 시 diff base 로 사용.
- **sentences.post_id**: NULL 이면 assistant 응답(`save_response()` 경로). user 입력은 항상 post 에 속한다.
- **sentences.text vs posts.markdown**: sentences 는 저장 파이프라인의 지시어 치환(`save-pronoun`) · ISO→한국어 날짜 변환을 거친 후 버전. 사용자가 **진짜로 친 원형**은 posts.markdown 쪽에만 보존된다.
- **세션리스**: sessions 테이블 없음. 하이퍼그래프가 영속 메모리, sentences가 대화 기록. 매 입력마다 BFS가 독립적으로 맥락 인출.
- **자동 저장 + origin**: `sentence_categories` / `node_categories` / `aliases`는 전부 자동 저장되며, `origin` 컬럼(`user` / `ai` / `system` / `external`)으로 출처를 식별한다(`categories` 마스터는 origin 없음 — 삭제 경로 부재). 사용자는 UI·`/review`에서 origin 필터로 검수·수정·삭제할 수 있다. 파괴적 작업(노드 병합 등)만 `/review` 승인을 거친다. (v17: 이전의 `rule` 값을 `system` 으로 리네이밍 — 출처는 데이터 생성 "주체"이며 규칙은 수단이기 때문)
- **retention 폐기(v13)**: `sentences.retention` 컬럼 제거. 모든 sentence 동등하게 영구 보관.
- **sentences.status 폐기(v18)**: 상태 레이어 자체 제거. 모든 sentence 는 영구 기록·영구 조회 대상. "무효화" 는 사용자가 `update_sentence` / `delete_sentence` 로 직접 처리. 시점 해석은 인출 LLM 이 `created_at` 순으로 읽고 최근 사실을 우선 반영. 근거: 2026-04-21~23 실측(114쌍 골든셋)에서 자동 판정 F1=0.46~0.81 로 모델·사람 공통 애매, 저장 시점 판정이 원칙 7(저장은 순수 기록)·8(파괴적 작업만 승인)·10(도메인은 관찰)·11(지능체 분리) 과 어긋남.
- **posts.input_mode 신설(v19 계획 — PLAN-003 M1)**: 저장 모드를 사용자 명시(UI 입력창 선택)로 기록. `'chat'` 은 메신저 스타일 평문, `'markdown'` 은 구조화된 전체 에디터. 저장 파이프라인은 이 값을 보고 save-pronoun 호출 여부·메타 필터 대상 범위·parse_markdown 분기를 결정한다. 내용 기반 `has_heading()` 자동 분기 제거. 상세는 `docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md`.
- **카테고리 재설계(v20 계획 — PLAN-004)**: 단일 `node_categories` 가 혼용하던 두 역할을 두 축으로 분리. (a) **사용자 heading 계층** → `categories`(adjacency list 마스터) + `sentence_categories`(문장 단위 주 매핑). (b) **19 대분류 의미 태깅** → `node_categories`(노드 단위, `major_category TEXT`, CATEGORY 백그라운드 워커 전용). 과포함(heading 하위 **모든** Kiwi 노드에 경로 부여 → 용언·서술어까지 오염) 해소 + FK 기반 계층 검증 가능. 저장 흐름은 heading 말단 카테고리만 `sentence_categories` 로 등록하고, `node_categories` 는 워커가 노드 의미로 분류한다. 상세는 `docs/DESIGN_CATEGORY.md`.
- **node_mentions**: "노드↔문장" 역참조. 시간·장소·부정 같은 특수 노드도 별도 취급 없이 여기만 참조.
- **unresolved_tokens**: 치환 실패한 지시어 기록. 저장 시점 일회성 이벤트라 런타임 재생성 불가 → 유일한 "승인 대기" 저장 예외. origin 불필요(사용자 답만 들어옴).
- **nodes·node_mentions·sentences는 origin 없음**: 원문 추출·자동 인덱스 성격이라 출처 식별이 `sentences.role`로 충분.
- `domain`, `source`, `weight`, `safety`, `filters`, `nodes.category`, `edges`(테이블 자체) 컬럼 없음.

### origin 값 의미

| 값 | 생성 경로 | 예시 |
|----|----------|------|
| `user` | 사용자가 직접 명시 | 마크다운 heading 경로, 수동 별칭 등록 |
| `ai` | LLM 추론 | 카테고리 분류 워커(베이스 모델 + 시스템 프롬프트) |
| `system` | 결정론적 엔진 규칙 (v17 리네이밍 — 이전 `rule`) | Kiwi lemma 정규화, 날짜 정규화(`2026-04-18` → `2026년`+`4월`+`18일`), 부정부사(`안/못`) 감지, 인칭대명사 별칭 시드 |
| `external` | 외부 API | Wikidata altLabel API로 가져온 별칭 |

UI·`/review`에서는 `origin='ai'` / `'system'` / `'external'` 필터를 제공해 "AI 추론 오류 검수", "엔진 규칙 오류 추적", "외부 데이터 오염 검수"가 각각 가능하다.

---

## 노드

**Kiwi 단독 추출 (v17)** — LLM extract/merge 는 폐기. Kiwi 형태소 분석만으로 노드를 결정한다. 자세한 흐름은 `docs/DESIGN_PIPELINE.md`. (v16 의 2-step LLM 병합은 dogfood 에서 수량·조항 수치를 대거 버리는 범인으로 확인 — 2026-04-22 세션 참조)

| 노드 종류 | 예시 | 비고 |
|-----------|------|------|
| 인물·조직 | 조용희, 강남세브란스, 삼성 | 개인 모드: 1인칭 명시 시 "나" 노드 / 조직 모드: 주어 명시 |
| 개념·사물 | 허리디스크, 식기세척기, ChatGPT | |
| 장소 | 진천, 강남역, L4-L5 | |
| 수치·날짜 | 50살, 2026년, 4월, 18일, 30만원 | 날짜는 한국어 표기 단위로 분리 (아래 참조) |
| 상태·행위 | 번아웃, 퇴사, **다녀오**, **아프** | 동사·형용사도 개념이면 노드. **Kiwi lemma(원형)** 으로 저장 |
| 부정부사 | 안, 못 | Kiwi `MAG` 태그. 독립 노드. 일반 노드와 동일하게 `node_mentions`로 참조 |

### 노드 정체성 — lemma 정규화 · Kiwi 쪼갬 수용 (v17)

같은 개념은 반드시 같은 노드로 수렴해야 BFS 가 제대로 작동한다. 규칙:

- **한국어 용언은 Kiwi lemma** — `아파서 / 아프 / 아팠어` 모두 `아프` 로 정규화해 upsert. 활용형 파편화 방지.
- **외래어·영문·복합명사는 Kiwi 쪼갬 수용 (v17 변경)** — `React Native` 는 `React`, `Native` 두 노드로 저장. 두 노드가 같은 sentence 에 공출현하므로 원칙 4(문장 바구니) 로 연결이 창발한다. LLM 원형 복원 단계 없음. 다국어 표기 변형은 `aliases`(예: Wikidata `external`)로 연결.
- **대소문자·공백 무시** — `FastAPI` / `fastapi` 는 같은 노드(기존 규칙 유지).
- **부정부사 예외** — `안 / 못` 은 Kiwi `MAG` 태그이지만 독립 노드로 유지(원칙 2).

### 날짜 노드 — 한국어 표기로 통일

ISO(`2026-04-18`)로 입력돼도 본문 sentence와 노드 모두 **한국어 표기**(`2026년`, `4월`, `18일`)로 정규화. 노드 = 사용자가 일상에서 말하는 단위와 일치해야 한다는 원칙.

식별 규칙: 명시적 키워드(`년/월/일`) 또는 ISO 구분자(`-`)가 있을 때만 날짜로 판단. 단독 4자리 숫자(`2026`)는 오탐 위험으로 노드화하지 않음.

쿼리 예:
- "4월에 뭐 있었지?" → `4월` 노드 → mentions → 4월의 모든 sentence
- "2026-04-18 기록" → `2026년 4월 18일` 노드 + `2026년` ∩ `4월` ∩ `18일` 교집합으로 좁힘 가능

---

## 하이퍼엣지 ①: 문장 바구니 (node_mentions)

같은 sentence에 등장한 모든 노드가 하나의 **문장 하이퍼엣지**로 묶인다. 멤버십은 `node_mentions` 테이블이 담는다. BFS는 `node_mentions` JOIN으로 "같은 문장에 함께 언급된 노드"를 이웃으로 삼는다.

```
"스타벅스 안 좋아"
→ sentence: "스타벅스 안 좋아"  (하이퍼엣지 하나)
→ 노드: 스타벅스, 안, 좋아 (각각 독립)
→ node_mentions: (스타벅스, sid), (안, sid), (좋아, sid)  (멤버십)

BFS("스타벅스") → 같은 sentence 하이퍼엣지 안의 멤버 탐색
              → {스타벅스, 안, 좋아} 전부 인접 노드로 도달
```

선 형태의 엣지 없이도 BFS 연결성은 보장된다. 문장이 곧 "함께 활성화된 노드들의 묶음"이기 때문.

의미 관계(cause/avoid/similar)는 sentence 원문에 이미 담겨 있고, 필요 시 외부 지능체가 해석한다 (원칙 11).

---

## 하이퍼엣지 ②: 카테고리 바구니 (두 축 — v20)

v20 에서 카테고리 바구니는 **두 축**으로 분리된다. 과거(v19 이하) 단일 `node_categories` 가 혼용하던 역할을 쪼갠 결과.

### 축 A — 사용자 heading 계층 (`categories` + `sentence_categories`)

사용자가 마크다운 heading 으로 명시한 경로. adjacency list 마스터(`categories`) + 문장 주 매핑(`sentence_categories`).

- 저장 대상: **문장 단위**. heading **말단 카테고리**만 `sentence_categories` 에 들어간다.
- 예: `# 더나은\n## 개발팀\n- 민지가 프로젝트 맡음` → `categories` upsert `(더나은, NULL)=1`·`(개발팀, 1)=2`, `sentence_categories` INSERT `(sentence_id, 2, 'user')`. 노드(`민지`·`프로젝트`)는 등록되지 않음.
- 계층 확장: "더나은 전체" 질의는 `categories` 재귀 CTE 로 하위 id 를 한꺼번에 수집 → `sentence_categories` JOIN.
- origin: `sentence_categories` 는 `user|ai|system|external`. `categories` 마스터엔 origin 없음 (삭제 경로 부재).

| 생성 경로 | 저장 주체 | origin |
|---|---|---|
| 마크다운 heading 경로 | `save.py` | `user` |
| 규칙 기반 자동 분류 (향후) | 엔진 규칙 | `system` |

### 축 B — 19 대분류 의미 태깅 (`node_categories`)

노드 의미를 19 대분류 코드(`CATEGORY_SYSTEMPROMPT.md`, 약 100 개 고정)로 태깅. 저장은 **노드 단위**, 생성은 **CATEGORY 백그라운드 워커 전용**.

- 저장 대상: **노드 단위**. `major_category TEXT`.
- 예: 위 문장 저장 직후 워커가 `민지 → PER.individual`, `프로젝트 → WRK.role` 등록.
- heading 경로 문자열(`"건강.2026-04-10"`) 은 저장 금지 — 축 A 로 분리됐다.
- origin: `ai`(워커) 기본. 사용자 수동 교정은 `user`, 규칙 기반은 `system`.

| 생성 경로 | 저장 주체 | origin |
|---|---|---|
| CATEGORY 워커 LLM 분류 | `engine/workers.py` | `ai` |
| 사용자 수동 교정 | `/review` UI | `user` |
| 결정론적 규칙 (예: 날짜 노드 → `TIM.*`) | 엔진 규칙 | `system` |

### 두 축의 협력

질의 `"건강 관련 병원 언제?"` 처리 시 두 축이 병렬로 시드 확장에 쓰인다:
- 축 B: 후보 `병원` 노드 → `node_categories.major_category='BOD.medical'` 확인 → `BOD.medical` 전체 노드를 시드로 `node_mentions` BFS.
- 축 A: `건강` 이 사용자 `categories` 루트와 일치하면 서브트리 수집 → `sentence_categories` 로 sentences 확장.

**용도**: ① 문장 바구니 공출현을 뛰어넘는 개념적 연결, ② 사용자 계층 전체 스캔(`더나은 전체 보여줘`), ③ 인접 맵 기반 한 홉 확장(`BOD.medical ↔ MON.insurance` 등). 잘못된 분류·자동 등록 카테고리는 `/review` 의 AI·시스템 목록 뷰에서 즉시 제거.

분류체계 전체 · 인접 맵 · 두 축 상세 → `docs/DESIGN_CATEGORY.md` 참고

---

## 하이퍼엣지 ③: 별칭 바구니 (aliases)

같은 개념의 다른 표기들을 하나로 묶는 **별칭 하이퍼엣지**. 인출 정확도의 핵심. **자동 저장 + `origin` 추적**.

v15에서 별칭 생성 방식이 바뀌었다. 기존에는 LLM(extract 어댑터)이 추론했지만, 품질·비용 문제로 **외부 지식베이스(Wikidata altLabel API)**로 전환. LLM 추론은 별칭에선 사용하지 않는다.

| origin | 생성 경로 | 예시 |
|--------|-----------|------|
| `user` | 직접 등록 ("스벅은 스타벅스야") | `스벅` → 스타벅스 |
| `external` | **Wikidata altLabel API** (백그라운드 별칭 워커가 호출) | `React Native` 노드에 `리액트 네이티브` · `RN` 자동 등록 |
| `system` | 인칭대명사 시드(엔진 내장) + 자모 거리 기반 오타 후보 사용자 확정 (v17 — 이전 `rule`) | `나/내/저/제` 등 11개 · `스타벅스` ← `스타벅시` (병합 시 별칭 보존) |

- `ai` origin은 **별칭에선 사용하지 않음** (카테고리와 달리 LLM 추론을 안 씀).
- Wikidata 매칭이 없는 노드엔 `external` 별칭이 생성되지 않음 (skip). 사용자는 `user` origin으로 직접 보완 가능.
- 잘못된 별칭은 사용자가 노드 상세 화면에서 즉시 제거. `/review`의 `origin='external'` 목록 뷰로 일괄 검수 가능.

인출 매칭 우선순위: `aliases 정확 매칭 → 노드명 직접 매칭 → 노드명 substring 매칭`

---

## 개인 / 조직 모드

| | 개인 모드 | 조직 모드 |
|---|---|---|
| 1인칭 처리 | 문장에 있을 때만 "나" 노드 | 사용자 이름으로 치환 (주어 명시) |
| 주어 생략 | 그대로 저장 | LLM이 사용자에게 질문 |
| doc_mode | 거의 사용 안 함 | 주 사용 (취업규칙, 법령 등) |
| 목적 | 개인 지식 하이퍼그래프 | 조직 날리지 관리 |

### doc_mode (조직 모드 특화)

정규식으로 자동 감지하여 조항 구조 보존:

```python
DOC_PATTERN = re.compile(
    r'제\s*\d+\s*조'         # 제N조
    r'|[①②③④⑤⑥⑦⑧⑨⑩]'    # 원문자 항
    r'|\d+\s*호\b'           # N호
    r'|제\s*\d+\s*항'        # 제N항
)
```

doc_mode=True이면 조항 식별자(`제N조`, `제N항`, `N호`)를 노드로 두고, 같은 sentence 내 `node_mentions`로 본문 노드와 연결. 계층은 마크다운 heading 경로와 동일하게 축 A(`categories` + `sentence_categories`, origin='system')로 표현한다 — v20 전환으로 `node_categories` 에는 들어가지 않는다.

상세 흐름 → `docs/DESIGN_ORG.md` / `docs/DESIGN_PIPELINE.md`

---

## 허브 → 도메인 부상

도메인은 사전에 정의하지 않는다. 관찰하는 것이다.

```
초기: 허리, 감기, 두통, 병원, 약 노드가 각각 존재
      ↓ 문장 바구니 공출현 + 카테고리 바구니 공유 축적
허브 감지: 특정 노드의 mention degree + category 공유 수가 임계값 초과
      ↓
도메인 부상: 해당 노드가 클러스터의 대표 허브로 기능
```

- 허브 노드는 UI 하이퍼그래프 뷰에서 시각적으로 강조
- 도메인 부상은 노드/하이퍼엣지 구조를 바꾸지 않음 (관찰값)

---

## 파이프라인 요약

모든 테이블 자동 저장. `sentence_categories` / `node_categories` / `aliases`는 `origin` 컬럼으로 출처(user/ai/system/external)가 식별됨 (`categories` 마스터는 origin 없음 — 삭제 경로 부재). `/review`는 (1) `unresolved_tokens`(애매한 지시어) 해소 + (2) AI·시스템·외부 생성물 목록 검수 + (3) 파괴적 작업(노드 병합) 승인 세 가지만 담당.

저장·인출·검토 상세는:
- `docs/DESIGN_PIPELINE.md` — 저장/인출/응답 파이프라인 세부
- `docs/DESIGN_REVIEW.md` — `/review` 섹션별 런타임 제안 도출 및 승인 흐름
- `docs/DESIGN_ENGINE.md` — 엔진 패키지 구조
- `docs/DESIGN_CATEGORY.md` — 카테고리 분류체계

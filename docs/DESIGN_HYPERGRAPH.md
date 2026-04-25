# Synapse 설계 — 하이퍼그래프 모델

## 핵심 설계 원칙

하이퍼그래프 모델에 적용되는 원칙은 **`docs/DESIGN_PRINCIPLES.md`** 가 단일 출처.

- **§1 시스템 관통 원칙** (존재론·구조·저장·동작) — 노드/하이퍼엣지/문장의 정의와 저장 규칙
- **§2 개인 / 조직 모드 원칙** — 1인칭 처리, 주어 명시 규칙

이 문서는 스키마·구현·예시에 집중한다.

---

## 왜 하이퍼그래프인가 (지식 바구니 은유)

전통적인 그래프는 `A — B` 같은 **선(엣지)** 으로 두 노드를 잇는다. 하지만 실제 기억은 "A와 B가 함께 떠올랐다"는 **공동 활성화**에 가깝다. Synapse 는 이걸 다음과 같이 표현한다:

- **바구니 = 하이퍼엣지** — 여러 노드를 동시에 묶는 그릇
- **문장 바구니**: 같은 sentence에 등장한 노드들 전부를 하나의 하이퍼엣지로 묶음
- **카테고리 바구니**: 같은 분류를 공유하는 노드들을 묶음
- **별칭 바구니**: 같은 개념의 다른 표기들을 묶음

같은 바구니 안에 있으면 연결된 것. 선을 따로 저장하지 않고, **바구니 자체가 연결 정보**다. 이게 생물학적 시냅스의 본질인 "함께 활성화되는 경향"(Hebbian)과 동형이다.

---

## 스키마

```sql
posts:                               -- 세션 그릇 (3 종)
  id          INTEGER PRIMARY KEY
  kind        TEXT NOT NULL DEFAULT 'note'
                  CHECK(kind IN ('note','synapse','insight'))
                                               -- note: 지식 축적 (뉴런 재료, /note 화면)
                                               -- synapse: 인출·융합 세션 (발화 순간)
                                               -- insight: 승격된 통찰 고유 그릇 (허브)
  title       TEXT                              -- 목록 표시용 제목.
                                               -- 기본값: 첫 sentence 의 첫 행 자동.
                                               -- 사용자 편집 가능. NULL 허용.
  source      TEXT                              -- 세션 전체 원본을 모드별 형식으로 누적:
                                               --  note: 사용자가 친 원문 (자동저장 갱신)
                                               --  synapse: Q/A 로그
                                               --  insight: 본체 한 줄
  created_at  TEXT DEFAULT (datetime('now'))
  updated_at  TEXT DEFAULT (datetime('now'))   -- 메시지 append·편집 시 갱신

sentences:                           -- 문장 하이퍼엣지의 실체 (post 에 반드시 속함)
  id          INTEGER PRIMARY KEY
  post_id     INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE
                                               -- assistant 응답도 그 대화가 일어난 post 에
                                               -- role='assistant' 로 귀속. 미아 sentence 없음.
  position    INTEGER NOT NULL DEFAULT 0       -- post 내 순서 (0-based)
  text        TEXT NOT NULL                     -- 치환·정규화 후 본문 (원형은 posts.source)
  role        TEXT NOT NULL DEFAULT 'user'     -- user | assistant
  origin      TEXT                              -- NULL|'user'|'insight'.
                                               -- 'insight' = 시냅스 세션에서 승격된 통찰
                                               -- 본체. 본문 편집 불가 (API·UI 레벨 강제).
                                               -- 삭제는 /review 승인 경로.
  created_at  TEXT DEFAULT (datetime('now'))
  updated_at  TEXT DEFAULT (datetime('now'))

nodes:
  id          INTEGER PRIMARY KEY
  name        TEXT NOT NULL          -- UNIQUE 아님. 동명이인/동명이의어 허용
  created_at  TEXT DEFAULT (datetime('now'))
  updated_at  TEXT DEFAULT (datetime('now'))

node_sentence_mentions:              -- 문장 하이퍼엣지의 멤버십
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  sentence_id INTEGER REFERENCES sentences(id) ON DELETE CASCADE
  origin      TEXT NOT NULL DEFAULT 'system'
                       CHECK(origin IN ('user','ai','system','external'))
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (node_id, sentence_id)

node_category_mentions:              -- 노드 ↔ 카테고리 단일 매핑
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE
  origin      TEXT NOT NULL DEFAULT 'system'
                       CHECK(origin IN ('user','ai','system','external'))
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (node_id, category_id)
  -- AI 워커는 19 대분류 시드 카테고리 id 로 매핑 (origin='ai').
  -- 저장 파이프라인의 _upsert_category_path 가 heading 을 Kiwi 로 토큰화해
  -- heading 노드 id 로 자동 매핑 (origin='system').

categories:                          -- 카테고리 마스터 (adjacency list)
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  name        TEXT NOT NULL           -- 경로 한 세그먼트 ("개발팀", "2026-04-10")
  parent_id   INTEGER REFERENCES categories(id) ON DELETE CASCADE  -- NULL = 루트
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
  UNIQUE (parent_id, name)
  -- INDEX idx_categories_parent (parent_id)
  -- 19 대분류 시드 루트 (~133 개) + 사용자 heading 노드 공존
  -- origin 컬럼 없음: 삭제 경로가 UI 에 없어 시드 보호는 애플리케이션 상수로 처리

sentence_categories:                 -- 문장 ↔ 사용자 heading 카테고리 (주 매핑)
  sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE
  category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE
  origin      TEXT NOT NULL DEFAULT 'user'
                       CHECK(origin IN ('user','ai','system','external'))
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
  PRIMARY KEY (sentence_id, category_id)
  -- INDEX idx_sentence_categories_cat (category_id)

aliases:                             -- 별칭 하이퍼엣지. 자동 저장 + origin 추적
  alias       TEXT PRIMARY KEY
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  origin      TEXT NOT NULL          -- user | ai | system | external
  created_at  TEXT DEFAULT (datetime('now'))

unresolved_tokens:                   -- 치환 실패 지시어 (유일한 승인 대기)
  sentence_id INTEGER REFERENCES sentences(id) ON DELETE CASCADE
  token       TEXT NOT NULL
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (sentence_id, token)
```

**설계 결정:**
- **엣지 테이블 없음**: 별도 `edges` 테이블 없음. 노드 간 연결은 sentence·category·alias 세 종류의 하이퍼엣지로만 표현된다. 의미 관계(cause/avoid/similar 등)는 `sentences.text` 원문에 이미 있고, 해석은 외부 지능체(원칙 11) 몫.
- **posts = 세션 그릇**: 한 개의 `posts` 행은 사용자 활동의 **세션 그릇**. 3 종 (`note`·`synapse`·`insight`) 공통. 그 안에 `sentences`가 누적되며, user·assistant 메시지가 `role` 로만 구분된다. post 는 사용자가 **명시적으로 나갈 때까지 열려있고** 목록에서 재진입·편집·이어서 쓰기 가능. 시간 기반 자동 경계 없음 (원칙 9 참조).
- **posts.source**: 세션 전체 원본 누적 보관. 모드별 형식이 다르지만 공통 목적은 ① UI 재편집 시 원형 그대로 로드, ② 지시어·날짜 치환 이전 원본 보존, ③ sentences 가 파싱·정규화된 가공본임을 감안한 **진짜로 친 원형**의 단일 출처. sentences 만으로 복원 불가능한 정보(heading·치환 전 표현)가 여기에만 있다.
- **sentences.post_id NOT NULL**: 모든 sentence 는 어떤 post 에 반드시 속한다. assistant 응답도 같은 대화의 사용자 메시지 post 에 귀속된다.
- **sentences.origin**: 기본 NULL 또는 `'user'`. 통찰 승격 sentence 는 `'insight'` 로 표식되며, 본문 편집 불가 (API/UI 레벨 강제). 원칙 15-2 참조. 삭제는 `/review` 승인 경로.
- **sentences.text vs posts.source**: sentences 는 저장 파이프라인의 지시어 치환(`save-pronoun`) · ISO→한국어 날짜 변환을 거친 후 버전. 사용자가 **진짜로 친 원형**은 posts.source 쪽에만 보존된다.
- **세션리스**: `sessions` 테이블 없음. post 가 세션 그릇 역할을 수행한다. 하이퍼그래프가 영속 메모리, sentences 가 대화 기록. 매 입력마다 BFS가 독립적으로 맥락 인출.
- **자동 저장 + origin**: `sentence_categories` / `node_category_mentions` / `aliases` / `sentences` 는 전부 자동 저장되며, `origin` 컬럼으로 출처를 식별한다 (`categories` 마스터는 origin 없음 — 삭제 경로 부재). 사용자는 UI·`/review`에서 origin 필터로 검수·수정·삭제할 수 있다. 파괴적 작업(노드 병합, 통찰 삭제 등)만 `/review` 승인을 거친다.
- **posts.kind 사용자 명시**: 그릇 종류를 사용자 액션으로 결정. 사용자는 입력 형식(평문 vs 마크다운)을 인지·선택하지 않으며, `kind` 는 `/note` (자동 생성), `/synapse` (자동 생성), `/promote` (사용자 명시) 액션으로만 결정. 내용 기반 자동 분기 없음.
- **카테고리 단일 매핑**: 19 대분류 시드 루트 + 사용자 heading 계층이 같은 `categories` 마스터에 공존. 노드 ↔ 카테고리는 `node_category_mentions` 단일 매핑. `sentence_categories` 는 사용자 heading 계층 문장 매핑. 상세는 `docs/DESIGN_CATEGORY.md`.
- **node_sentence_mentions**: "노드↔문장" 역참조. 시간·장소·부정 같은 특수 노드도 별도 취급 없이 여기만 참조.
- **unresolved_tokens**: 치환 실패한 지시어 기록. 저장 시점 일회성 이벤트라 런타임 재생성 불가 → 유일한 "승인 대기" 저장 예외. origin 불필요(사용자 답만 들어옴).
- `domain`, `weight`, `safety`, `filters`, `nodes.category`, `nodes.status`, `sentences.status`, `edges`(테이블 자체) 컬럼 없음.

### origin 값 의미

| 값 | 생성 경로 | 예시 |
|----|----------|------|
| `user` | 사용자가 직접 명시 | 마크다운 heading 경로, 수동 별칭 등록 |
| `ai` | LLM 추론 | 카테고리 분류 워커(베이스 모델 + 시스템 프롬프트) |
| `system` | 결정론적 엔진 규칙 | Kiwi lemma 정규화, 날짜 정규화(`2026-04-18` → `2026년`+`4월`+`18일`), 부정부사(`안/못`) 감지, 인칭대명사 별칭 시드 |
| `external` | 외부 API | Wikidata altLabel API로 가져온 별칭 |
| `insight` | (`sentences.origin` 전용) 사용자 승격 통찰 본체 | 시냅스 세션에서 `[⬆ 통찰로 승격]` 클릭 시 새 sentence |

UI·`/review`에서는 `origin='ai'` / `'system'` / `'external'` 필터를 제공해 "AI 추론 오류 검수", "엔진 규칙 오류 추적", "외부 데이터 오염 검수"가 각각 가능하다.

---

## 노드

**Kiwi 단독 추출.** Kiwi 형태소 분석만으로 노드를 결정한다. 자세한 흐름은 `docs/DESIGN_PIPELINE.md`.

| 노드 종류 | 예시 | 비고 |
|-----------|------|------|
| 인물·조직 | 조용희, 강남세브란스, 삼성 | 개인 모드: 1인칭 명시 시 "나" 노드 / 조직 모드: 주어 명시 |
| 개념·사물 | 허리디스크, 식기세척기, ChatGPT | |
| 장소 | 진천, 강남역, L4-L5 | |
| 수치·날짜 | 50살, 2026년, 4월, 18일, 30만원 | 날짜는 한국어 표기 단위로 분리 (아래 참조) |
| 상태·행위 | 번아웃, 퇴사, **다녀오**, **아프** | 동사·형용사도 개념이면 노드. **Kiwi lemma(원형)** 으로 저장 |
| 부정부사 | 안, 못 | Kiwi `MAG` 태그. 독립 노드. 일반 노드와 동일하게 `node_sentence_mentions` 로 참조 |

### 노드 정체성 — lemma 정규화 · Kiwi 쪼갬 수용

같은 개념은 반드시 같은 노드로 수렴해야 BFS 가 제대로 작동한다. 규칙:

- **한국어 용언은 Kiwi lemma** — `아파서 / 아프 / 아팠어` 모두 `아프` 로 정규화해 upsert. 활용형 파편화 방지.
- **외래어·영문·복합명사는 Kiwi 쪼갬 수용** — `React Native` 는 `React`, `Native` 두 노드로 저장. 두 노드가 같은 sentence 에 공출현하므로 원칙 4(문장 바구니) 로 연결이 창발한다. 다국어 표기 변형은 `aliases`(예: Wikidata `external`)로 연결.
- **대소문자·공백 무시** — `FastAPI` / `fastapi` 는 같은 노드.
- **부정부사 예외** — `안 / 못` 은 Kiwi `MAG` 태그이지만 독립 노드로 유지(원칙 2).

### 날짜 노드 — 한국어 표기로 통일

ISO(`2026-04-18`)로 입력돼도 본문 sentence와 노드 모두 **한국어 표기**(`2026년`, `4월`, `18일`)로 정규화. 노드 = 사용자가 일상에서 말하는 단위와 일치해야 한다는 원칙.

식별 규칙: 명시적 키워드(`년/월/일`) 또는 ISO 구분자(`-`)가 있을 때만 날짜로 판단. 단독 4자리 숫자(`2026`)는 오탐 위험으로 노드화하지 않음.

쿼리 예:
- "4월에 뭐 있었지?" → `4월` 노드 → mentions → 4월의 모든 sentence
- "2026-04-18 기록" → `2026년 4월 18일` 노드 + `2026년` ∩ `4월` ∩ `18일` 교집합으로 좁힘 가능

---

## 하이퍼엣지 ①: 문장 바구니 (node_sentence_mentions)

같은 sentence에 등장한 모든 노드가 하나의 **문장 하이퍼엣지**로 묶인다. 멤버십은 `node_sentence_mentions` 테이블이 담는다. BFS는 `node_sentence_mentions` JOIN으로 "같은 문장에 함께 언급된 노드"를 이웃으로 삼는다.

```
"스타벅스 안 좋아"
→ sentence: "스타벅스 안 좋아"  (하이퍼엣지 하나)
→ 노드: 스타벅스, 안, 좋아 (각각 독립)
→ node_sentence_mentions: (스타벅스, sid), (안, sid), (좋아, sid)  (멤버십)

BFS("스타벅스") → 같은 sentence 하이퍼엣지 안의 멤버 탐색
              → {스타벅스, 안, 좋아} 전부 인접 노드로 도달
```

선 형태의 엣지 없이도 BFS 연결성은 보장된다. 문장이 곧 "함께 활성화된 노드들의 묶음"이기 때문.

의미 관계(cause/avoid/similar)는 sentence 원문에 이미 담겨 있고, 필요 시 외부 지능체가 해석한다 (원칙 11).

---

## 하이퍼엣지 ②: 카테고리 바구니 (categories + sentence_categories + node_category_mentions)

`categories` 마스터가 19 대분류 시드 루트 + 사용자 heading 계층을 동시에 담는다. `node_category_mentions` 가 노드 ↔ 카테고리 단일 매핑을 처리.

### `categories` + `sentence_categories` (사용자 heading 계층)

사용자가 마크다운 heading 으로 명시한 경로. adjacency list 마스터(`categories`) + 문장 주 매핑(`sentence_categories`).

- 저장 대상: **문장 단위**. heading **말단 카테고리**만 `sentence_categories` 에 들어간다.
- 예: `# 더나은\n## 개발팀\n- 민지가 프로젝트 맡음` → `categories` upsert `(더나은, NULL)=1`·`(개발팀, 1)=2`, `sentence_categories` INSERT `(sentence_id, 2, 'user')`. 노드(`민지`·`프로젝트`)는 `node_sentence_mentions` 에 별도 등록.
- 계층 확장: "더나은 전체" 질의는 `categories` 재귀 CTE 로 하위 id 를 한꺼번에 수집 → `sentence_categories` JOIN.

| 생성 경로 | 저장 주체 | origin |
|---|---|---|
| 마크다운 heading 경로 | 저장 파이프라인 | `user` |
| 규칙 기반 자동 분류 (doc_mode 등) | 엔진 규칙 | `system` |

### `node_category_mentions` (노드 ↔ 카테고리 단일 매핑)

노드 ↔ 카테고리 단일 매핑. `(node_id, category_id, origin)`. AI 워커는 19 대분류 시드 루트로, heading Kiwi 토큰화·사용자 수동 교정은 임의 카테고리로 매핑.

- 저장 대상: **노드 단위**. `category_id` 는 `categories` 의 어떤 행이든 가능 — 19 대분류 시드 루트일 수도, 사용자 heading 노드일 수도 있다.
- 예: CATEGORY 워커가 `민지 → PER.individual` 시드 카테고리 id, `프로젝트 → WRK.role` 시드 카테고리 id 등록 (`origin='ai'`). heading Kiwi 토큰화는 `(민지, 개발팀.id, 'system')` 자동 매핑.

| 생성 경로 | 저장 주체 | origin |
|---|---|---|
| CATEGORY 워커 LLM 분류 | 백그라운드 워커 | `ai` |
| Kiwi heading 토큰화 자동 매핑 | 저장 파이프라인 | `system` |
| 사용자 수동 교정 | `/review` UI | `user` |
| 결정론적 규칙 (예: 날짜 노드 → `TIM.*`) | 엔진 규칙 | `system` |

### 두 매핑의 협력

질의 `"건강 관련 병원 언제?"` 처리 시 두 매핑이 병렬로 시드 확장에 쓰인다:
- `node_category_mentions`: 후보 `병원` 노드 → `BOD.medical` 시드 카테고리 id 확인 → `BOD.medical` 에 매핑된 모든 노드를 시드로 `node_sentence_mentions` BFS.
- `sentence_categories` + `categories` 재귀 CTE: `건강` 이 사용자 `categories` 루트와 일치하면 서브트리 수집 → `sentence_categories` JOIN 으로 sentences 확장.

**용도**: ① 문장 바구니 공출현을 뛰어넘는 개념적 연결, ② 사용자 계층 전체 스캔(`더나은 전체 보여줘`), ③ 인접 맵 기반 한 홉 확장(`BOD.medical ↔ MON.insurance` 등). 잘못된 분류·자동 등록 카테고리는 `/review` 의 AI·시스템 목록 뷰에서 즉시 제거.

분류체계 전체 · 인접 맵 · 단일 매핑 상세 → `docs/DESIGN_CATEGORY.md`

---

## 하이퍼엣지 ③: 별칭 바구니 (aliases)

같은 개념의 다른 표기들을 하나로 묶는 **별칭 하이퍼엣지**. 인출 정확도의 핵심. **자동 저장 + `origin` 추적**.

별칭 생성은 외부 지식베이스(Wikidata altLabel API)로 처리. LLM 추론은 별칭에선 사용하지 않는다.

| origin | 생성 경로 | 예시 |
|--------|-----------|------|
| `user` | 직접 등록 ("스벅은 스타벅스야") | `스벅` → 스타벅스 |
| `external` | **Wikidata altLabel API** (백그라운드 별칭 워커가 호출) | `React Native` 노드에 `리액트 네이티브` · `RN` 자동 등록 |
| `system` | 인칭대명사 시드(엔진 내장) + 자모 거리 기반 오타 후보 사용자 확정 | `나/내/저/제` 등 11개 · `스타벅스` ← `스타벅시` (병합 시 별칭 보존) |

- `ai` origin은 **별칭에선 사용하지 않음** (카테고리와 달리 LLM 추론을 안 씀).
- Wikidata 매칭이 없는 노드엔 `external` 별칭이 생성되지 않음 (skip). 사용자는 `user` origin으로 직접 보완 가능.
- 잘못된 별칭은 사용자가 노드 상세 화면에서 즉시 제거. `/review`의 `origin='external'` 목록 뷰로 일괄 검수 가능.

인출 매칭 우선순위: `aliases 정확 매칭 → 노드명 직접 매칭 → 노드명 substring 매칭`

---

## 하이퍼엣지 ④: 통찰 허브

시냅스 세션에서 사용자가 "통찰" 로 승격시킨 sentence 는 **그 순간 함께 발화한 모든 노드의 공통 허브** 가 된다. 다른 바구니와 구조가 같지만 생성 방식·의미·편집 정책이 특별하다.

### 생성 방식

1. 사용자가 `kind='synapse'` post 의 메시지 하나를 UI 액션(예: `[⬆ 통찰로 승격]`) 으로 승격
2. 엔진이 다음을 수행:
   - 새 `posts` 행 생성 (`kind='insight'`, `title=승격된 메시지 첫 행`, `source=승격된 본문`)
   - 승격된 메시지 내용을 새 `sentences` 행으로 복제 (`post_id=새 insight post`, `origin='insight'`, `role='user'`)
   - **해당 synapse 세션에서 직전 retrieve 로 당겨진 모든 노드 id 목록** 을 스냅샷하여 `node_sentence_mentions` 에 일괄 INSERT. 본문 토큰 외 노드도 포함됨 — "함께 발화한" 것이 전부 엮이는 Hebbian 구현.
   - Kiwi 가 본체 sentence 에서 추출하는 노드도 같이 편입 (중복은 UNIQUE 로 스킵).

### 편집 정책

- `origin='insight'` sentence 는 **본문 편집 불가**. `update_sentence` API 가 거부.
- 통찰에 덧붙이는 "참조" 는 구조적 append 가 아니라, 다른 post 의 sentence 가 같은 노드·카테고리를 공유할 때 원칙 4의 창발 규칙으로 자연스럽게 연결되는 것.
- 삭제는 `/review` 승인 경로 (파괴적 작업이므로 원칙 8).

### 인출 가중치

`retrieve()` 시 `origin='insight'` sentence 와 그에 연결된 노드는 **우선 점화** — 다음 시냅스 세션의 중력으로 작용. 구체 가중치 수치는 `docs/DESIGN_PIPELINE.md` 의 retrieve 점수 계산 섹션 참조.

### 시각화

- `/hypergraph` 뷰에서 통찰 노드·sentence 는 **허브 크기 +** 와 앰버 링으로 강조
- `/note` 목록에서 통찰 post 는 ✦ 아이콘과 앰버 보더로 구분
- `/synapse` 세션에서 과거 통찰이 인출되면 답변 카드에 "이 통찰을 참고함" 태그 노출

자세한 원칙 배경 → `DESIGN_PRINCIPLES.md §1 원칙 15`

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

doc_mode=True 이면 조항 식별자(`제N조`, `제N항`, `N호`)를 노드로 두고, 같은 sentence 내 `node_sentence_mentions` 로 본문 노드와 연결. 계층은 마크다운 heading 경로와 동일하게 사용자 heading 계층 (`categories` + `sentence_categories`, origin='system')로 표현한다.

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

모든 테이블 자동 저장. `sentence_categories` / `node_category_mentions` / `aliases` 는 `origin` 컬럼으로 출처(user/ai/system/external)가 식별됨 (`categories` 마스터는 origin 없음 — 삭제 경로 부재). `/review`는 (1) `unresolved_tokens`(애매한 지시어) 해소 + (2) AI·시스템·외부 생성물 목록 검수 + (3) 파괴적 작업(노드 병합·통찰 삭제) 승인 세 가지만 담당.

저장·인출·검토 상세는:
- `docs/DESIGN_PIPELINE.md` — 저장/인출/응답 파이프라인 세부
- `docs/DESIGN_REVIEW.md` — `/review` 섹션별 런타임 제안 도출 및 승인 흐름
- `docs/DESIGN_ENGINE.md` — 엔진 패키지 구조
- `docs/DESIGN_CATEGORY.md` — 카테고리 분류체계

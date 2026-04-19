# Synapse 설계 — 그래프 모델

**최종 업데이트**: 2026-04-19 (v13 — retention 폐기 + node_mentions + 의미 엣지)

## 핵심 설계 원칙

그래프 모델에 적용되는 원칙은 **`docs/DESIGN_PRINCIPLES.md`**로 이전·통합되었다.

- **§1 시스템 관통 원칙** (존재론·구조·저장·동작) — 노드/엣지/문장의 정의와 저장 규칙
- **§2 개인 / 조직 모드 원칙** — 1인칭 처리, 주어 명시 규칙

이 문서는 스키마·구현·예시에 집중하며, 위 원칙은 단일 출처인 `DESIGN_PRINCIPLES.md`를 참조한다.

---

## 스키마 (v13)

```sql
sentences:
  id          INTEGER PRIMARY KEY
  text        TEXT NOT NULL           -- 원본 문장(user) 또는 응답(assistant)
  role        TEXT DEFAULT 'user'     -- user | assistant
  created_at  TEXT DEFAULT (datetime('now'))

nodes:
  id          INTEGER PRIMARY KEY
  name        TEXT NOT NULL          -- UNIQUE 아님. 동명이인/동명이의어 허용
  status      TEXT DEFAULT 'active'  -- active | inactive
  created_at  TEXT DEFAULT (datetime('now'))
  updated_at  TEXT DEFAULT (datetime('now'))

node_mentions:                       -- 노드↔문장 역참조 (모든 노드 공통)
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  sentence_id INTEGER REFERENCES sentences(id) ON DELETE CASCADE
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (node_id, sentence_id)

node_categories:                     -- 사용자 승인된 카테고리만 (다대다)
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  category    TEXT NOT NULL          -- 사용자 지정 경로 또는 LLM 제안 승인값
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (node_id, category)

edges:                               -- 의미 엣지만. 사용자 승인으로만 삽입
  id              INTEGER PRIMARY KEY
  source_node_id  INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  target_node_id  INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  label           TEXT NOT NULL      -- similar | cooccur | cause | contain | …
  sentence_id     INTEGER REFERENCES sentences(id) ON DELETE SET NULL
  created_at      TEXT DEFAULT (datetime('now'))
  last_used       TEXT

aliases:
  alias       TEXT PRIMARY KEY
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE

unresolved_tokens:                   -- 치환 실패 지시어 (승인 대기)
  sentence_id INTEGER REFERENCES sentences(id) ON DELETE CASCADE
  token       TEXT NOT NULL
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (sentence_id, token)
```

**설계 결정:**
- **세션리스**: sessions 테이블 없음. 그래프가 영속 메모리, sentences가 대화 기록. 매 입력마다 BFS가 독립적으로 맥락 인출.
- **retention 폐기(v13)**: `sentences.retention` 컬럼 제거. 모든 sentence 동등하게 영구 보관. "daily → 빈 nodes" 과적합 + 오분류 리스크 + 실제 미사용 — 세 가지 이유로 제거.
- **node_mentions**: 조사 엣지 폐기로 끊긴 "노드↔문장" 경로를 대체하는 핵심 구조. 시간·장소·부정 같은 특수 노드도 별도 취급 없이 여기만 참조.
- **nodes.category 컬럼 제거**: 카테고리는 `node_categories` 다대다 테이블로 이전. 노드당 복수 카테고리 허용 (예: `더나은.개발팀` + `BOD.disease`).
- **edges.label**: 의미 관계만 (`similar / cooccur / cause / contain / …`). 조사 저장 금지. `status`·`origin` 컬럼 없음 — 삽입된 것은 곧 승인된 것.
- **unresolved_tokens**: 치환 실패한 지시어 기록. 저장 시점 일회성 이벤트라 런타임 재생성 불가 → 유일한 "승인 대기" 저장 예외.
- `domain`, `source`, `weight`, `safety`, `filters`, `nodes.category`, `edges.status/origin` 컬럼 없음.

---

## 노드

LLM(파인튜닝 모델)이 문장에서 개념 단위로 직접 추출. 형태소 분석기 없음.

| 노드 종류 | 예시 | 비고 |
|-----------|------|------|
| 인물·조직 | 조용희, 강남세브란스, 삼성 | 개인 모드: 1인칭 명시 시 "나" 노드 / 조직 모드: 주어 명시 |
| 개념·사물 | 허리디스크, 식기세척기, ChatGPT | |
| 장소 | 진천, 강남역, L4-L5 | |
| 수치·날짜 | 50살, 2026년, 4월, 18일, 30만원 | 날짜는 한국어 표기 단위로 분리 (아래 참조) |
| 상태·행위 | 번아웃, 퇴사, 다녀왔 | 동사/형용사도 개념이면 노드 |
| 부정부사 | 안, 못 | 독립 노드. 일반 노드와 동일하게 `node_mentions`로 참조 |

### 날짜 노드 — 한국어 표기로 통일

ISO(`2026-04-18`)로 입력돼도 본문 sentence와 노드 모두 **한국어 표기**(`2026년`, `4월`, `18일`)로 정규화. 노드 = 사용자가 일상에서 말하는 단위와 일치해야 한다는 원칙.

식별 규칙: 명시적 키워드(`년/월/일`) 또는 ISO 구분자(`-`)가 있을 때만 날짜로 판단. 단독 4자리 숫자(`2026`)는 오탐 위험으로 노드화하지 않음.

쿼리 예:
- "4월에 뭐 있었지?" → `4월` 노드 → mentions → 4월의 모든 sentence
- "2026-04-18 기록" → `2026년 4월 18일` 노드 + `2026년` ∩ `4월` ∩ `18일` 교집합으로 좁힘 가능

---

## node_mentions — 저장 파이프라인의 핵심

같은 sentence에 등장한 모든 노드가 `node_mentions`로 묶인다. BFS는 `node_mentions` JOIN으로 "같은 문장에 함께 언급된 노드"를 이웃으로 삼는다.

```
"스타벅스 안 좋아"
→ sentence: "스타벅스 안 좋아"
→ 노드: 스타벅스, 안, 좋아 (각각 독립)
→ node_mentions: (스타벅스, sid), (안, sid), (좋아, sid)

BFS("스타벅스") → sentence 탐색 → {스타벅스, 안, 좋아} 전부 인접 노드로 도달
```

조사 엣지가 없어도 BFS 연결성 유지. 의미 해석은 `/review`에서 사용자 승인으로 `edges`에 추가.

---

## 엣지 (의미 관계)

사용자 승인으로만 생성되는 의미 관계 테이블.

| 구성요소 | 설명 |
|----------|------|
| source_node_id | 출발 노드 |
| target_node_id | 도착 노드 |
| label | `similar` / `cooccur` / `cause` / `contain` / `avoid` / … |
| sentence_id | 관계가 도출된 대표 문장 (nullable) |

생성 흐름:
```
/review 호출
  → node_mentions self-JOIN으로 공출현 노드 쌍 도출
  → LLM이 관계 label 후보 제안 (similar/cooccur/cause/contain…)
  → 사용자 선택 → edges INSERT
```

문장 내 문법 관계(주어-조사-목적어)는 `sentences.text` 원문에 이미 있으므로 재저장하지 않는다.

---

## node_categories

`대분류.소분류` 또는 사용자 지정 경로(마크다운 heading, 예: `더나은.개발팀`) 형식. 다대다 관리, 노드당 복수 카테고리 허용.

- **사용자 명시**: 마크다운 heading 경로는 즉시 `node_categories` INSERT (명시 = 승인)
- **LLM 제안**: `/review`에서 옵션 제시 → 사용자 승인 시만 INSERT
- **용도**: BFS 검색 범위 필터, 뷰 태깅

분류체계 전체 및 인접 맵 → `docs/DESIGN_CATEGORY.md` 참고

---

## Aliases

노드의 다른 이름/변형. 인출 정확도의 핵심. **사용자 승인으로만 등록**.

- 사용자 수동 등록: "스벅은 스타벅스야"
- 노드 상세 화면에서 "별칭 추천" 요청 시 LLM 호출 → 제안 → 사용자 승인 → `aliases` INSERT
- missing 기반: 인출 실패 키워드를 `/review`에서 연결 제안

인출 매칭 우선순위: `aliases 정확 매칭 → 노드명 직접 매칭 → 노드명 substring 매칭`

---

## 개인 / 조직 모드

| | 개인 모드 | 조직 모드 |
|---|---|---|
| 1인칭 처리 | 문장에 있을 때만 "나" 노드 | 사용자 이름으로 치환 (주어 명시) |
| 주어 생략 | 그대로 저장 | LLM이 사용자에게 질문 |
| doc_mode | 거의 사용 안 함 | 주 사용 (취업규칙, 법령 등) |
| 목적 | 개인 지식 그래프 | 조직 날리지 관리 |

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

doc_mode=True이면 조항 식별자(`제N조`, `제N항`, `N호`)를 노드로 두고, 같은 sentence 내 node_mentions로 본문 노드와 연결. 계층은 사용자 승인 시 의미 엣지(`contain`)로 반영.

상세 흐름 → `docs/DESIGN_ORG.md` / `docs/DESIGN_PIPELINE.md`

---

## 허브 → 도메인 부상

도메인은 사전에 정의하지 않는다. 관찰하는 것이다.

```
초기: 허리, 감기, 두통, 병원, 약 노드가 각각 존재
      ↓ 연결(node_mentions 공출현 + 승인된 edges) 축적
허브 감지: 특정 노드의 mention/edge degree가 임계값 초과
      ↓
도메인 부상: 해당 노드가 클러스터의 대표 허브로 기능
```

- 허브 노드는 UI 그래프 뷰에서 시각적으로 강조
- 도메인 부상은 노드/엣지 구조를 바꾸지 않음 (관찰값)

---

## 파이프라인 요약

자동 저장은 sentence + 노드 + node_mentions + unresolved_tokens까지. 카테고리·엣지·별칭·병합은 `/review` 승인 후 반영.

저장·인출·검토 상세는:
- `docs/DESIGN_PIPELINE.md` — 저장/인출/응답 파이프라인 세부
- `docs/DESIGN_REVIEW.md` — `/review` 섹션별 런타임 제안 도출 및 승인 흐름
- `docs/DESIGN_ENGINE.md` — 엔진 패키지 구조
- `docs/DESIGN_CATEGORY.md` — 카테고리 분류체계

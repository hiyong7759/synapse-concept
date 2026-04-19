# Synapse 설계 — 하이퍼그래프 모델

**최종 업데이트**: 2026-04-19 (v15 — 엣지 테이블 폐기, 연결은 sentence·category 하이퍼엣지로 창발)

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

## 스키마 (v15)

```sql
sentences:                           -- 문장 하이퍼엣지의 실체
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

node_mentions:                       -- 문장 하이퍼엣지의 멤버십
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  sentence_id INTEGER REFERENCES sentences(id) ON DELETE CASCADE
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (node_id, sentence_id)

node_categories:                     -- 카테고리 하이퍼엣지의 멤버십
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  category    TEXT NOT NULL          -- 대분류.소분류 또는 사용자 지정 경로
  origin      TEXT NOT NULL          -- user | ai | rule | external
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (node_id, category)

aliases:                             -- 별칭 하이퍼엣지. 자동 저장 + origin 추적
  alias       TEXT PRIMARY KEY
  node_id     INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  origin      TEXT NOT NULL          -- user | ai | rule | external
  created_at  TEXT DEFAULT (datetime('now'))

unresolved_tokens:                   -- 치환 실패 지시어 (유일한 승인 대기)
  sentence_id INTEGER REFERENCES sentences(id) ON DELETE CASCADE
  token       TEXT NOT NULL
  created_at  TEXT DEFAULT (datetime('now'))
  PRIMARY KEY (sentence_id, token)
```

**설계 결정:**
- **엣지 테이블 폐기(v15)**: 별도 `edges` 테이블 없음. 노드 간 연결은 sentence·category·alias 세 종류의 하이퍼엣지로만 표현된다. 의미 관계(cause/avoid/similar 등)는 `sentences.text` 원문에 이미 있고, 해석은 외부 지능체(원칙 11) 몫.
- **세션리스**: sessions 테이블 없음. 하이퍼그래프가 영속 메모리, sentences가 대화 기록. 매 입력마다 BFS가 독립적으로 맥락 인출.
- **자동 저장 + origin**: `node_categories / aliases`는 전부 자동 저장되며, `origin` 컬럼(`user` / `ai` / `rule` / `external`)으로 출처를 식별한다. 사용자는 UI·`/review`에서 origin 필터로 검수·수정·삭제할 수 있다. 파괴적 작업(노드 병합 등)만 `/review` 승인을 거친다.
- **retention 폐기(v13)**: `sentences.retention` 컬럼 제거. 모든 sentence 동등하게 영구 보관.
- **node_mentions**: "노드↔문장" 역참조. 시간·장소·부정 같은 특수 노드도 별도 취급 없이 여기만 참조.
- **unresolved_tokens**: 치환 실패한 지시어 기록. 저장 시점 일회성 이벤트라 런타임 재생성 불가 → 유일한 "승인 대기" 저장 예외. origin 불필요(사용자 답만 들어옴).
- **nodes·node_mentions·sentences는 origin 없음**: 원문 추출·자동 인덱스 성격이라 출처 식별이 `sentences.role`로 충분.
- `domain`, `source`, `weight`, `safety`, `filters`, `nodes.category`, `edges`(테이블 자체) 컬럼 없음.

### origin 값 의미

| 값 | 생성 경로 | 예시 |
|----|----------|------|
| `user` | 사용자가 직접 명시 | 마크다운 heading 경로, 수동 별칭 등록 |
| `ai` | LLM 추론 | 카테고리 분류 워커(베이스 모델 + 시스템 프롬프트) |
| `rule` | 결정론적 규칙 | 날짜 정규화(`2026-04-18` → `2026년`+`4월`+`18일`), 부정부사(`안/못`) 감지, 인칭대명사 별칭 시드 |
| `external` | 외부 API | Wikidata altLabel API로 가져온 별칭 |

UI·`/review`에서는 `origin='ai'` / `'rule'` / `'external'` 필터를 제공해 "AI 추론 오류 검수", "규칙 오류 추적", "외부 데이터 오염 검수"가 각각 가능하다.

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

## 하이퍼엣지 ②: 카테고리 바구니 (node_categories)

`대분류.소분류` 또는 사용자 지정 경로(마크다운 heading, 예: `더나은.개발팀`) 형식. 같은 카테고리를 공유하는 노드들이 하나의 **카테고리 하이퍼엣지**. 다대다 관리, 노드당 복수 카테고리 허용. **모두 자동 저장**, `origin`으로 출처 구분.

| origin | 생성 경로 | 예시 |
|--------|-----------|------|
| `user` | 마크다운 heading 경로 (명시 입력) | `# 더나은\n## 개발팀` → `더나은.개발팀` |
| `ai` | extract 어댑터가 노드 의미로부터 추론 | `허리디스크` → `BOD.disease` |
| `rule` | 결정론적 분류 | `4월` → `TIM.month`, `안/못` → 부정부사 노드 |

**용도**: 문장 바구니를 뛰어넘는 개념적 연결. 스타벅스 노드만 언급한 문장에서도 같은 `FOD.cafe` 카테고리의 투썸·커피빈 관련 문장을 끌어올 수 있다. 인접 맵으로 한 홉 더 확장 가능. 잘못된 분류는 `/review`의 AI·규칙 목록 뷰에서 즉시 제거.

분류체계 전체 및 인접 맵 → `docs/DESIGN_CATEGORY.md` 참고

---

## 하이퍼엣지 ③: 별칭 바구니 (aliases)

같은 개념의 다른 표기들을 하나로 묶는 **별칭 하이퍼엣지**. 인출 정확도의 핵심. **자동 저장 + `origin` 추적**.

v15에서 별칭 생성 방식이 바뀌었다. 기존에는 LLM(extract 어댑터)이 추론했지만, 품질·비용 문제로 **외부 지식베이스(Wikidata altLabel API)**로 전환. LLM 추론은 별칭에선 사용하지 않는다.

| origin | 생성 경로 | 예시 |
|--------|-----------|------|
| `user` | 직접 등록 ("스벅은 스타벅스야") | `스벅` → 스타벅스 |
| `external` | **Wikidata altLabel API** (백그라운드 별칭 워커가 호출) | `React Native` 노드에 `리액트 네이티브` · `RN` 자동 등록 |
| `rule` | 인칭대명사 시드(엔진 내장) + 자모 거리 기반 오타 후보 사용자 확정 | `나/내/저/제` 등 11개 · `스타벅스` ← `스타벅시` (병합 시 별칭 보존) |

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

doc_mode=True이면 조항 식별자(`제N조`, `제N항`, `N호`)를 노드로 두고, 같은 sentence 내 `node_mentions`로 본문 노드와 연결. 계층은 마크다운 heading 경로와 동일하게 `node_categories`(origin='rule')로 표현한다.

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

모든 테이블 자동 저장. `node_categories / aliases`는 `origin` 컬럼으로 출처(user/ai/rule/external)가 식별됨. `/review`는 (1) `unresolved_tokens`(애매한 지시어) 해소 + (2) AI·규칙·외부 생성물 목록 검수 + (3) 파괴적 작업(노드 병합) 승인 세 가지만 담당.

저장·인출·검토 상세는:
- `docs/DESIGN_PIPELINE.md` — 저장/인출/응답 파이프라인 세부
- `docs/DESIGN_REVIEW.md` — `/review` 섹션별 런타임 제안 도출 및 승인 흐름
- `docs/DESIGN_ENGINE.md` — 엔진 패키지 구조
- `docs/DESIGN_CATEGORY.md` — 카테고리 분류체계

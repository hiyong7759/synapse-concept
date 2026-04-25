# Synapse 설계 — /review 검토 편입

## 배경

카테고리·별칭은 **자동으로 저장**되며, 각 레코드는 `origin`(`user` / `ai` / `system` / `external`) 컬럼으로 출처가 식별된다. 노드 간 연결은 별도 테이블이 아니라 sentence·category·alias 세 종류의 **하이퍼엣지**로만 표현된다. "사용자가 인지하지 못한 채 쌓이는 것"을 막는 대신, **"사용자가 언제든 찾아서 고칠 수 있게 한다"**.

`/review`는 이 모델에서 **세 가지 역할**만 담는다:

1. **`unresolved_tokens` 해소** — 치환 실패 지시어(유일한 승인 대기 테이블)
2. **AI·시스템 생성물 검토 뷰** — `origin='ai'` / `'system'` 필터 목록에서 잘못된 항목 즉시 삭제
3. **파괴적 작업 승인** — 노드 병합·아카이브·통찰 삭제 등 되돌릴 수 없는 작업

---

## 핵심 설계 원칙

`/review` 검토 흐름의 5개 원칙은 **`docs/DESIGN_PRINCIPLES.md §3`** 참고.
(자동 저장 + origin 추적 · unresolved_tokens만 승인 대기 · 파괴적 작업만 승인 · AI/시스템 목록 뷰 · LLM 없이도 동작)

---

## 유일한 승인 대기 테이블: unresolved_tokens

```sql
CREATE TABLE unresolved_tokens (
  sentence_id  INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
  token        TEXT NOT NULL,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (sentence_id, token)
);
CREATE INDEX idx_unresolved_sentence ON unresolved_tokens(sentence_id);
```

**왜 이것만 승인 대기인가?**

치환 실패는 **저장 시점에만 발생하는 이벤트**다. 사용자가 "요즘 허리 아파"를 입력하면 `_preprocess`가 "요즘"을 치환 시도하고 실패한다. 이 시점이 지나면 `sentences` 테이블에는 원문 그대로 남고, 그 "요즘"이 아직 해소 대기 중인지 사용자가 이미 닫은 건지는 어디에도 흔적이 남지 않는다. 즉 **런타임 재생성 불가** → 별도 저장 필수.

AI·규칙 생성물은 이미 `node_category_mentions / aliases`에 `origin`과 함께 저장되어 있으므로 "대기 테이블"이 필요 없다. 조회만 하면 된다.

---

## 섹션별 도출기

알고리즘 명세는 환경 무관. Python frozen 환경의 단일 출처는 `engine/suggestions.py`, Flutter 환경의 단일 출처는 `synapse_engine` 의 `lib/src/review/suggestions.dart` 가 같은 알고리즘을 재현. 호출 인터페이스만 환경별로 노출.

### unresolved — 미해결 지시어 (승인 대기 해소)

```python
def unresolved() -> list[Suggestion]:
    # SELECT sentence_id, token FROM unresolved_tokens
    # 각 토큰의 종류에 따라 옵션 구성:
    #   시간 지시어("요즘", "최근", "그때"): 최근 언급 날짜 노드 + 표준 시간 범위 + 자유 입력
    #   장소·사물·인물 지시어: 사용자의 해당 카테고리 노드 중 최근 언급 상위 N개 + 자유 입력
    #   사용자 카테고리가 비면: 직전 문장 맥락에서 후보 추출 → 그것도 없으면 자유 입력만
```

승인 흐름: 사용자가 옵션 선택 → `POST /review/apply type=token` → `nodes` upsert + `node_sentence_mentions` INSERT + `unresolved_tokens` DELETE. "알 수 없음" 선택은 `type=token_dismiss`로 `unresolved_tokens` DELETE만.

### ai_generated — AI 생성물 검수

```python
def ai_generated(kind: str, limit: int) -> list[Suggestion]:
    # kind = 'category'  (ai 출처는 카테고리만. aliases 는 external)
    # node_category_mentions WHERE origin='ai'
    # 각 항목에 원문 sentence·노드 컨텍스트를 함께 반환 (사용자가 판단 가능하도록)
```

**액션**: 각 항목마다 `유지` / `삭제` 버튼. 삭제는 해당 테이블 DELETE.

### external_generated — 외부 API 생성물 검수 (Wikidata 별칭)

```python
def external_generated(kind: str, limit: int) -> list[Suggestion]:
    # kind = 'alias'  (external 출처는 별칭만. Wikidata altLabel)
    # aliases WHERE origin='external'
    # 각 항목에 원 노드명과 Wikidata altLabel 둘 다 표시 (매핑 정확성 확인용)
```

**액션**: `유지` / `삭제`. Wikidata 가 잘못 매핑한 경우(동명이인·동의어 충돌) 사용자가 즉시 제거.

### system_generated — 시스템 생성물 검수 (엔진 규칙 오류 추적용)

```python
def system_generated(kind: str, limit: int) -> list[Suggestion]:
    # kind in ('category', 'alias')
    # node_category_mentions / aliases WHERE origin='system'
    # 사용자가 "잘못 분류됐네" 발견 시 해당 엔진 규칙을 이후 수정하기 위한 추적 경로
```

**액션**: `유지` / `삭제`. 같은 규칙이 반복 오류 내면 엔지니어에게 규칙 수정 신호.

### suspected_typos — 오타 의심 쌍 (파괴적 작업 승인)

```python
def suspected_typos() -> list[Suggestion]:
    # 자모 Levenshtein 거리 == 1 쌍을 후보로 한다.
    # Kiwi lemma 동일 쌍 자동 제외 (활용형 차이 — 예: "배고파/배고프")
    # 옵션: "같음 (병합)", "별칭으로만", "다르지만 관련 (카테고리 공유)", "다름 (무시)"
```

병합(`merge_nodes`)은 되돌릴 수 없어 **자동 저장 대상 아님** — 사용자 승인 유지.

승인 흐름:
- "같음" → `type=merge` (`merge_nodes(keep_id, remove_id)` 호출)
- "별칭으로만" → `type=alias` (aliases INSERT, origin='user')
- "다르지만 관련" → `type=category` (양 노드에 공통 사용자 정의 카테고리 INSERT, origin='user')
- "다름" → 무시 (이 쌍을 다음 번 도출에서 제외하는 상태는 별도 필요 시 추가)

### stale_nodes(days) — 노드 생존 (아카이브 승인)

```python
def stale_nodes(days: int) -> list[Suggestion]:
    # nodes.updated_at 기준 N일 이상 미갱신 + 최근 참조 없음
    # 아카이브 = 물리 DELETE (FK CASCADE)
    # 옵션: "유지", "아카이브 (물리 삭제)"
```

아카이브는 물리 DELETE 이므로 확실히 파괴적. 사용자가 모르게 삭제되면 복구 불가이므로 승인 유지.

승인 흐름: `POST /review/apply type=archive` / 유지는 카드만 닫기.

### insight_delete — 통찰 삭제 (파괴적 작업 승인)

```python
def insight_delete_candidates() -> list[Suggestion]:
    # posts.kind='insight' 전체 목록. 자동 도출 아님 —
    # 사용자가 /hypergraph 또는 /note 에서 특정 insight post 선택 후 삭제 요청 시
    # 여기서 파괴성 확인 승인 후 실행.
    # 옵션: "삭제 (허브 연결도 CASCADE)", "유지"
```

통찰은 본체 sentence 가 `origin='insight'` 로 편집 불가. 삭제만이 변경 수단이며, 삭제는 **시냅스 세션에서 축적된 허브 연결(노드 스냅샷 전체)까지 함께 사라지므로** 파괴적. 승인 필수.

승인 흐름: `POST /review/apply type=insight_delete` + `{post_id}` → post 행 DELETE → FK CASCADE 로 본체 sentence + `node_sentence_mentions` + `node_category_mentions` 자동 정리. 고아 노드(해당 통찰만 참조하던 노드) 도 rollback 로직처럼 정리.

### daily(date) — 일일 회고 (정보 뷰)

```python
def daily(date: str) -> list[Suggestion]:
    # 해당 날짜 sentences를 노드별로 그룹핑
    # 옵션 없음 (회고 뷰). 사용자가 읽는 용도
    # 부족한 내용을 이어 쓰려면 기본 입력 흐름으로
```

### gaps() — 기록 공백 (정보 뷰)

```python
def gaps() -> list[Suggestion]:
    # sentences.created_at 분석해 N일 이상 기록 없는 구간 감지
    # 옵션: "그 기간 기록 추가", "알 수 없음"
```

승인 시 사용자 입력 창 열림 → 기본 저장 플로우로.

---

## API

Python frozen 환경: `api/routes/graph.py` (FastAPI) — REST 인터페이스. Flutter 환경: `synapse_engine` 의 동등 메서드 (`getReview()`·`applyReview(...)` 등). 두 환경의 응답 스키마는 동일.

### GET /review

현재 시점의 모든 섹션을 JSON으로 반환. 섹션 필터 지원:

```
GET /review
GET /review?sections=unresolved,ai_generated
GET /review?sections=ai_generated&kind=category&limit=20
```

응답 예시:
```json
{
  "unresolved": [
    {"sentence_id": 42, "token": "요즘",
     "question": "'요즘'은 언제부터 언제까지인가요?",
     "options": ["2026-04-10~04-17", "이번 달", "최근 7일", "직접 입력"]}
  ],
  "ai_generated": {
    "category": [
      {"node_id": 17, "node_name": "허리디스크", "category": "BOD.disease",
       "created_at": "..."}
    ]
  },
  "external_generated": {
    "alias": [
      {"node_id": 42, "node_name": "React Native", "alias": "리액트 네이티브",
       "source": "wikidata", "created_at": "..."}
    ]
  },
  "system_generated": { "category": [...], "alias": [...] },
  "suspected_typos": [...],
  "stale_nodes": [...],
  "insight_delete": [...],
  "daily": [...],
  "gaps": [...]
}
```

### GET /review/count

사이드바 배지용 집계 (쿼리만, LLM 없음):
```json
{
  "unresolved": 2,
  "ai_generated": {"category": 8},
  "external_generated": {"alias": 3},
  "system_generated": {"category": 9, "alias": 0},
  "suspected_typos": 1,
  "stale_nodes": 1,
  "insight_delete": 0
}
```

### POST /review/apply

제안 수락·처리. body:
```json
{"type": "merge", "params": {"keep_id": 17, "remove_id": 42}}
```

| type | params | 동작 |
|------|--------|------|
| `token` | `{sentence_id, token, value}` | `nodes` upsert + `node_sentence_mentions` INSERT + `unresolved_tokens` DELETE |
| `token_dismiss` | `{sentence_id, token}` | `unresolved_tokens` DELETE (하이퍼그래프 변경 없음) |
| `merge` | `{keep_id, remove_id}` | `merge_nodes` 호출 (파괴적, 물리 DELETE) |
| `archive` | `{node_id}` | `nodes` 물리 DELETE (FK CASCADE) |
| `category` (수동 추가) | `{node_id, category_id}` | `node_category_mentions` INSERT, origin='user' |
| `alias` (수동 추가) | `{node_id, alias}` | `aliases` INSERT, origin='user' |
| `insight_delete` | `{post_id}` | `posts` 행 DELETE → FK CASCADE 로 본체 sentence + `node_sentence_mentions` 자동 정리 |

### DELETE — 자동 저장물 제거

검토 목록에서 잘못된 항목을 제거하는 API (이미 저장된 것 삭제):

| 엔드포인트 | 동작 |
|-----------|------|
| `DELETE /nodes/{id}/categories/{category_id}` | 카테고리 멤버십 제거 (`node_category_mentions` 한 행) |
| `DELETE /aliases/{alias}` | 별칭 제거 |

Flutter 환경에서는 같은 동작이 `synapse_engine.GraphOps` 의 `removeAlias` · `removeCategoryMention` 으로 노출.

---

## 프론트

`/review` 라우트 신규 구현은 [`PLAN-20260425-SYN-flutter-rewrite.md`](../deliverables/SYN/20260425/user/PLAN-20260425-SYN-flutter-rewrite.md) §2 "범위 외 (후속 PLAN)" 의 통찰 삭제 UI 항목으로 분리되어 있다. 본 섹션의 동작 사양은 신규 구현의 단일 출처.

공통 동작 사양:
- 페이지 로드 시 `GET /review` 호출 → 섹션별 리스트 렌더
- **`ai_generated` 섹션**: 기본 확장, 각 항목에 `[삭제]` 버튼 + 원문 컨텍스트 툴팁
- **`system_generated` 섹션**: 기본 접힘, 사용자가 펼쳐서 훑어볼 때만 부하 발생
- **`unresolved` 섹션**: 질문형 카드. 옵션 선택 시 `POST /review/apply type=token`
- **`suspected_typos` / `stale_nodes` / `insight_delete`**: 파괴적이므로 확인 모달 포함
- 사이드바 배지: `GET /review/count`로 섹션별 카운트 표시. `ai_generated` 배지는 "검수 대기 건수"로 기능
- 삭제 직후 목록에서 해당 항목 제거 (optimistic update)

---

## 독립 동작 (`--no-llm`)

LLM 없이도 모든 검토 섹션이 작동한다:

- **쿼리만으로 완결**: `unresolved`(옵션 구성 제외), `ai_generated`, `system_generated`, `suspected_typos`, `stale_nodes`, `insight_delete`, `daily`, `gaps`
- **LLM 호출은 저장 시점에만** — 백그라운드 카테고리 분류 워커만 LLM 을 사용해 `origin='ai'` 카테고리를 자동 생성한다. 별칭은 Wikidata(`origin='external'`)로 생성되어 LLM 추론 안 씀. 이후 검토는 LLM 없이 가능.

사용자는 여전히 카테고리·별칭을 자유 입력으로 직접 추가할 수 있다 (`origin='user'`).

---

## 편집 — 언제든 수정·삭제

자동 저장된 카테고리·별칭은 하이퍼그래프 뷰 / `/review` / 노드 상세 화면에서 **언제든** 수정·삭제 가능:

- `POST /nodes/{id}/categories` — 추가 (origin='user')
- `DELETE /nodes/{id}/categories/{category_id}` — 삭제
- `DELETE /aliases/{alias}` — 별칭 삭제

핵심 가정: **"자동 저장은 완벽하지 않다. 사용자가 쉽게 고칠 수 있으면 된다."** origin 컬럼 + 검수 뷰 + 편집 API 세 가지가 이 가정을 뒷받침한다.

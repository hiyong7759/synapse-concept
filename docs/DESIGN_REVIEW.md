# Synapse 설계 — /review 검토 편입

**최종 업데이트**: 2026-04-17

## 배경

시냅스는 **저장과 합성을 분리**한다. 자동 저장되는 것은 원문 sentence + 노드 + 노드↔문장 역참조(`node_mentions`)까지이고, 그 외의 모든 의미 합성(카테고리 부여·엣지 생성·별칭 등록·노드 병합)은 **사용자 승인**을 거쳐야 DB에 반영된다. 근거: "사용자가 인지하지 못한 채 쌓이는 지식은 사용자의 지식이 아니다. 승인 과정의 읽기/판단 행위가 곧 사고 확장."

`/review`는 이 승인 과정을 담는 화면이다. 게임화된 편입 경로로서 "짝짓기 / 묶기 / 체인 / 생존 / 일일 / 공백" 같은 유형의 검토 작업을 제공한다.

---

## 핵심 설계 원칙

1. **승인 대기 전용 테이블을 만들지 않는다** — 유일한 예외 `unresolved_tokens` 하나
2. **제안은 요청 시점에 런타임 도출** — `GET /review`가 호출될 때 `engine/suggestions.py`가 DB 쿼리 + 필요 시 LLM 호출로 리스트 생성. 결과를 DB에 쓰지 않음
3. **승인 즉시 최종 테이블에 반영** — `edges / node_categories / aliases`에는 승인된 것만 존재
4. **LLM 없이도 동작** — 규칙 기반 섹션은 LLM 의존 없이 쿼리만으로 채워짐

이 설계는 "DB에 있는 것은 전부 승인된 것" 원칙을 `edges`, `node_categories`, `aliases` 전반에 일관되게 적용한 결과다. `status / origin / kind / action` 같은 중간 분류 컬럼은 모두 불필요하다.

---

## 유일한 저장 예외: unresolved_tokens

```sql
CREATE TABLE unresolved_tokens (
  sentence_id  INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
  token        TEXT NOT NULL,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (sentence_id, token)
);
CREATE INDEX idx_unresolved_sentence ON unresolved_tokens(sentence_id);
```

**왜 이것만 저장하는가?**

치환 실패는 **저장 시점에만 발생하는 이벤트**다. 사용자가 "요즘 허리 아파"를 입력하면 `_preprocess`가 "요즘"을 치환 시도하고 실패한다. 이 시점이 지나면 `sentences` 테이블에는 원문 그대로 남고, 그 "요즘"이 아직 해소 대기 중인지 사용자가 이미 닫은 건지는 어디에도 흔적이 남지 않는다. 즉 **런타임 재생성 불가** → 별도 저장 필수.

다른 제안(공출현 쌍·오타 의심·미분류·LLM 추론)은 전부 `nodes / node_mentions / node_categories`에서 쿼리로 재생성 가능하므로 저장이 필요 없다.

---

## 섹션별 도출기 (engine/suggestions.py)

각 함수는 DB 쿼리 + 필요 시 LLM 호출로 제안 리스트를 반환한다. **DB에 쓰지 않는다.**

### unresolved — 미해결 지시어

```python
def unresolved() -> list[Suggestion]:
    # SELECT sentence_id, token FROM unresolved_tokens
    # 각 토큰의 종류에 따라 옵션 구성:
    #   시간 지시어("요즘", "최근", "그때"): 최근 언급 날짜 노드 + 표준 시간 범위 + 자유 입력
    #   장소·사물·인물 지시어: 사용자의 해당 카테고리 노드 중 최근 언급 상위 N개 + 자유 입력
    #   사용자 카테고리가 비면: 직전 문장 맥락에서 후보 추출 → 그것도 없으면 자유 입력만
```

승인 흐름: 사용자가 옵션 선택 → `POST /review/apply type=token` → `nodes` upsert + `node_mentions` INSERT + `unresolved_tokens` DELETE. "알 수 없음" 선택은 `type=token_dismiss`로 `unresolved_tokens` DELETE만.

### uncategorized — 미분류 노드

```python
def uncategorized() -> list[Suggestion]:
    # SELECT n.id, n.name
    #   FROM nodes n
    #   LEFT JOIN node_categories nc ON nc.node_id = n.id
    #   WHERE nc.node_id IS NULL AND n.status = 'active'
    # 각 노드에 대해:
    #   기존 사용자 정의 경로 목록 상위 N개를 옵션에 포함
    #   선택적으로 synapse/chat(base)에 분류 제안 요청 → 옵션에 추가
```

승인 흐름: `POST /review/apply type=category` → `node_categories` INSERT.

### cooccur_pairs — 공출현 노드 쌍

```python
def cooccur_pairs(limit: int) -> list[Suggestion]:
    # node_mentions self-JOIN으로 같은 sentence_id에 속한 노드 쌍 수집
    # 이미 edges에 존재하는 쌍은 제외
    # 상위 limit개 반환
    # 관계 종류 옵션(similar/cooccur/cause/contain/...)은
    #   synapse/chat(base)에 관련 sentence 텍스트를 함께 전달해 추천
```

승인 흐름: `POST /review/apply type=edge` → `edges` INSERT.

### suspected_typos — 오타 의심 쌍

```python
def suspected_typos() -> list[Suggestion]:
    # engine/save.py의 find_suspected_typos 재사용
    # 자모 Levenshtein 거리 == 1 쌍을 후보로
    # 옵션: "같음 (병합)", "별칭으로만", "다르지만 관련 (엣지)", "다름 (무시)"
```

승인 흐름: 사용자 선택에 따라 `type=merge` / `type=alias` / `type=edge` / `type=token_dismiss`로 분기.

### alias_suggestions(node_id) — 별칭 제안 (사용자 요청 시에만)

```python
def alias_suggestions(node_id: int) -> list[Suggestion]:
    # 사용자가 그래프 뷰 노드 상세에서 "별칭 추천" 버튼 클릭 시 호출
    # synapse/chat(base)에 노드 이름 → 줄임말·영어 원문·다국어 표기·흔한 오타 요청
    # 결과를 옵션으로 제시
```

승인 흐름: `POST /review/apply type=alias` → `aliases` INSERT.

### stale_nodes(days) — 노드 생존

```python
def stale_nodes(days: int) -> list[Suggestion]:
    # nodes.updated_at 기준 N일 이상 미갱신 + edges.last_used 참조 없음
    # 옵션: "유지", "아카이브 (status=inactive)"
```

승인 흐름: `POST /review/apply type=archive` / 유지는 그냥 카드만 닫기.

### daily(date) — 일일 회고

```python
def daily(date: str) -> list[Suggestion]:
    # 해당 날짜 sentences를 노드별로 그룹핑
    # 옵션 없음 (회고 뷰). 사용자가 읽는 용도
    # 부족한 내용을 이어 쓰려면 기본 입력 흐름으로
```

### gaps() — 기록 공백

```python
def gaps() -> list[Suggestion]:
    # sentences.created_at 분석해 N일 이상 기록 없는 구간 감지
    # 옵션: "그 기간 기록 추가", "알 수 없음"
```

승인 시 사용자 입력 창 열림 → 기본 저장 플로우로.

---

## API (api/routes/graph.py)

### GET /review

현재 시점의 모든 섹션 제안을 JSON으로 반환. 섹션 필터 지원:

```
GET /review
GET /review?sections=unresolved,uncategorized
```

응답 예시:
```json
{
  "unresolved": [
    {"sentence_id": 42, "token": "요즘",
     "question": "'요즘'은 언제부터 언제까지인가요?",
     "options": ["2026-04-10~04-17", "이번 달", "최근 7일", "직접 입력"]}
  ],
  "uncategorized": [
    {"node_id": 17, "node_name": "허리디스크",
     "question": "'허리디스크'는 어떤 분류에 속하나요?",
     "options": ["건강.질병", "BOD.disease"], "allow_free_input": true}
  ],
  "cooccur_pairs": [...],
  "suspected_typos": [...],
  "stale_nodes": [...],
  "daily": [...],
  "gaps": [...]
}
```

응답 구조는 섹션별로 다르다. UI는 섹션 이름으로 렌더링 분기.

### GET /review/count

사이드바 배지용 집계:
```json
{"total": 12, "unresolved": 2, "uncategorized": 5, "cooccur_pairs": 3, "suspected_typos": 1, "stale_nodes": 1}
```
간단 쿼리만 사용 (LLM 호출 없음).

### POST /review/apply

제안 수락. body:
```json
{"type": "edge", "params": {"source_id": 17, "target_id": 42, "label": "cause"}}
```

| type | params | 동작 |
|------|--------|------|
| `edge` | `{source_id, target_id, label}` | `edges` INSERT |
| `category` | `{node_id, category}` | `node_categories` INSERT |
| `alias` | `{node_id, alias}` | `aliases` INSERT |
| `merge` | `{keep_id, remove_id}` | `merge_nodes` 호출 |
| `archive` | `{node_id}` | `nodes.status='inactive'` |
| `token` | `{sentence_id, token, value}` | `nodes` upsert + `node_mentions` INSERT + `unresolved_tokens` DELETE |
| `token_dismiss` | `{sentence_id, token}` | `unresolved_tokens` DELETE (그래프 변경 없음) |

---

## 프론트 (app/src/pages/ReviewPage.tsx)

- 페이지 로드 시 `GET /review` 호출 → 섹션별로 리스트 렌더
- 각 제안은 `{question, options}` 구조. 옵션 버튼 클릭 시 `POST /review/apply` 호출 + 클라이언트 상태에서 해당 제안 제거
- 승인된 결과는 그래프 뷰로 전환했을 때 애니메이션으로 강조 (새 엣지/노드/카테고리 칩 1.5초 하이라이트)
- 사이드바 배지: `GET /review/count`로 열린 제안 수 표시
- LLM 호출이 있는 섹션(`cooccur_pairs`의 관계 종류 옵션 등)은 사용자가 섹션을 펼칠 때만 지연 로드 (페이지 초기 로딩 부담 완화)

### 게임 모드

사용자 결정사항의 6가지 게임 유형은 **같은 데이터를 섹션별로 다르게 시각화하는 UI 뷰일 뿐, 백엔드 스키마는 동일**:

- 관계 짝짓기 → `cooccur_pairs`
- 묶기 게임 → `cooccur_pairs` + `uncategorized`를 클러스터로 묶어 표시
- 체인 채우기 → `cooccur_pairs` 중 2-hop 연결 후보
- 노드 생존 → `stale_nodes`
- 일일 그래프 → `daily(today)`
- 공백 채우기 → `gaps`

LLM 역할은 옵션 후보 생성만. 최종 결정은 항상 사용자.

---

## 독립 동작 (`--no-llm`)

LLM 없이도 대부분의 섹션은 작동한다:

- **쿼리만으로 동작**: `unresolved`, `uncategorized`(LLM 제안 옵션 제외), `cooccur_pairs`(관계 종류 옵션 없이 쌍만), `suspected_typos`, `stale_nodes`, `daily`, `gaps`
- **빈 결과**: `alias_suggestions(node_id)` (LLM 필수)

사용자는 여전히 카테고리·엣지·별칭을 자유 입력으로 직접 추가할 수 있다.

---

## 승인 이후 편집

승인된 카테고리·엣지·별칭은 Phase 4의 편집 API로 **언제든 수정·삭제 가능**하다:

- `POST /nodes/{id}/categories` — 추가
- `DELETE /nodes/{id}/categories/{category}` — 삭제
- `PUT /nodes/{id}/categories` body `{from, to}` — 이름 변경
- `DELETE /edges/{id}` — 엣지 삭제
- `DELETE /aliases/{alias}` — 별칭 삭제

"승인된 것은 틀릴 수 없다"는 아니다. 사용자의 판단은 변할 수 있고 그래프도 그에 맞춰 업데이트된다.

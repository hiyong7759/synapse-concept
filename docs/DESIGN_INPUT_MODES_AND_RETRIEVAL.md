# Synapse 설계 — 입력 모드 & 인출 관계

**관련 문서**: `DESIGN_PRINCIPLES.md` §1 원칙 9 · `DESIGN_PIPELINE.md` 저장 파이프라인 · `DESIGN_HYPERGRAPH.md` 스키마 · `INPUT_GUIDE.md` 작성자용 실전 가이드

---

## 세션 그릇 정의 (3 종)

| kind | UI 라우트 | API `kind` 값 | 주된 용도 |
|---|---|---|---|
| **note** | `/note` | `'note'` | **모든 지식 축적** — 한 줄 메모도 긴 마크다운도 같은 그릇. heading·`::`·list·평문 자유 혼재. heading 있으면 카테고리 등록, 없으면 free 처리. |
| **synapse** | `/synapse` | `'synapse'` | 지식 활용·융합 — 축적된 지식 사이의 새 연결 발화. 질문·답이 역사로 기록되며 노드 편입 없음 |
| **insight** | 승격 전용 | `'insight'` | 사용자가 synapse 메시지를 "통찰"로 승격 → 고유 post 1 개 = 본체 sentence 1 개. 편집 불가·허브 연결 |

**API 계약** — `note` 는 사용자가 `/note` 화면에 진입해 입력하면 자동 생성. 사용자가 모드를 명시하지 않음. `synapse` 는 `/synapse` 진입 + 첫 질문 시 자동 생성. `insight` 는 `POST /promote` 전용 (일반 save 경로에서 생성 불가).

**저장 두 층 분리 (`note` 그릇 적용)**:
- **자동저장** — `posts.source` 만 갱신 (입력 1.5초 디바운스 + 페이지 이탈). LLM 호출 없음. 모바일 친화.
- **의미 처리** — sentences·노드·LLM 정정 후보 생성 (사용자 명시 트리거: ⌘S / "정리" 버튼). 자동저장과 한 트랜잭션으로 source 동기화 후 진행.

**모드 인식 UI (원칙 14)** — 라우트 두 개(`/note`·`/synapse`) 만 있어 사용자가 모드를 인지·선택하지 않음. 대신 `/note` 상단에 **자동저장 상태** (`변경됨 / 저장 중… / ✓ 저장됨`) + **의미 처리 상태** (`⚙ 정리 중… / ✦ 정리됨`) 를 명확히 표시.

---

## 마크다운 문법 명세 (`note` 그릇 안에서 — 선택적 사용)

`note` 입력은 평문일 수도 있고, 아래 네 가지 마크다운 요소로 구성될 수도 있다. 사용자는 인지·선택하지 않으며, 의미 처리 시점에 `parse_markdown` 이 자동 분기. heading 이 있으면 카테고리 경로 상속, 없으면 모든 줄을 free 로 처리한다. 각 요소는 저장 파이프라인에서 서로 다른 경로를 탄다.

### 1) heading
```markdown
# 건강
## 허리
```
- 저장 효과: 카테고리 경로(`건강.허리`) 등록. 이후 요소는 이 경로를 **상속**한다.
- sentence INSERT **안 함**. (heading 자체는 문장 아님.)
- 카테고리 origin: `user`.

### 2) `- key:: value` (Obsidian Dataview 스타일)
```markdown
- 팀장:: 박지수
- 모델:: Gemma 4 E2B
```
- 저장 효과: sentence 로 **통째 저장**(`text="팀장:: 박지수"`). 별도 속성 테이블 신설 안 함.
- Kiwi 형태소 분석은 **통째 문장 대상**으로 실행 → `팀장`, `박지수` 같은 노드가 자연스럽게 뽑힘.
- save-pronoun **skip** (공문서·고유 표기 보존 — note 그릇 안에서 key_value 형식이 감지되면 이 줄만 skip).
- 메타 필터 **제외** (구조화된 기록이므로 "메타 대화" 가능성 없음).

파서 정규식: `^-\s+(.+?)\s*::\s+(.+)$` — key 와 value 양쪽 공백은 trim. 둘 중 하나라도 비면 매칭 실패 → 일반 list 로 강등.

### 3) `- value` (일반 list)
```markdown
- 오늘 피곤함
- 회의 3시간
```
- 저장 효과: sentence INSERT. 일반 자유 문장과 동일 취급.
- 메타 필터 대상 · save-pronoun 호출 (지시어 치환).

### 4) 자유 문장 (paragraph)
```markdown
어제보다 훨씬 나아졌다.
오늘은 회의가 세 개 연속.
```
- 저장 효과: sentence INSERT.
- 메타 필터 대상 · save-pronoun skip.

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
  ↓ retrieve() — 전체 하이퍼그래프 대상 BFS + retrieve-expand/filter
                  현재 synapse post 의 이전 질문·답도 LLM 프롬프트 맥락으로 주입
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

### 한 눈 비교표

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
| retrieve-expand / retrieve-filter | — | **✅ (핵심)** | — |
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

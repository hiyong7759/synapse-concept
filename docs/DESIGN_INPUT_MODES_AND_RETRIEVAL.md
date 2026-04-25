# Synapse 설계 — 입력 모드 & 인출 관계

**최종 업데이트**: 2026-04-25 (v22 2차안 — 입력 모드 분리 폐지로 **세션 그릇 3 종** (`note`/`synapse`/`insight`). 축적 그릇 `note` 단일로 chat·markdown 통합. 사용자는 입력 형식을 인지·선택하지 않음. 자동저장(원본만)과 의미 처리(사용자 명시 트리거) 두 층 분리. 선행 v22 1차안: 4 모드 안. v19: `posts.input_mode` 컬럼 신설 / `- key:: value` 파서 / save-pronoun 모드별 분기)

**관련 문서**: `DESIGN_PRINCIPLES.md` §1 원칙 9 · `DESIGN_PIPELINE.md` 저장 파이프라인 · `DESIGN_HYPERGRAPH.md` 스키마 · `INPUT_GUIDE.md` 작성자용 실전 가이드

---

## 배경 — 왜 입력 모드 분리를 폐지하나 (v22 2차안)

v18 까지는 입력의 `has_heading()` 결과로 **자동 분기**했고, v19 에서 사용자 명시 분리(`chat`/`markdown`)로 격상했다. v22 1차안은 그 분리를 그대로 유지하면서 `synapse`·`insight` 를 추가했다.

**2026-04-25 본질 검토** — 사용자가 "메모장에 적는다" 라는 단일 정신모델로 시냅스를 인지하는 게 자연스럽고, chat/markdown 분리는:
- 사용자가 매번 "이건 chat? markdown?" 선택해야 하는 인지 부하
- 엔진 차이는 사실상 save-pronoun 호출 여부 + heading 처리뿐 — 단일 경로에서 문장 kind(heading/key_value/list/free) 분기로 충분히 흡수 가능
- 별도 라우트 두 개 유지 비용 (UI · 모드 배지 · 전환 유도 등)

→ **입력 모드 분리 폐지**. 축적은 `note` 단일 그릇. heading 이 있으면 카테고리 등록, 없으면 free 처리 — 사용자는 인지하지 않는다.

원칙 11(지능체는 분리)·원칙 13(로컬 모델 제약 → 사용자 명시 우선) 정합성도 더 강해진다 — 모드 결정 자체를 폐기했으므로 모델·규칙·사용자 어느 누구도 "이건 어떤 종류 글" 을 판정하지 않는다.

---

## 세션 그릇 정의 (v22 2차안 — 3 종)

| kind | UI 라우트 | API `kind` 값 | 주된 용도 |
|---|---|---|---|
| **note** | `/note` | `'note'` | **모든 지식 축적** — 한 줄 메모도 긴 마크다운도 같은 그릇. heading·`::`·list·평문 자유 혼재. heading 있으면 카테고리 등록, 없으면 free 처리. |
| **synapse** | `/synapse` | `'synapse'` | 지식 활용·융합 — 축적된 지식 사이의 새 연결 발화. 질문·답이 역사로 기록되며 노드 편입 없음 |
| **insight** | 승격 전용 | `'insight'` | 사용자가 synapse 메시지를 "통찰"로 승격 → 고유 post 1 개 = 본체 sentence 1 개. 편집 불가·허브 연결 |

**API 계약** — `note` 는 사용자가 `/note` 화면에 진입해 입력하면 자동 생성. 사용자가 모드를 명시하지 않음. `synapse` 는 `/synapse` 진입 + 첫 질문 시 자동 생성. `insight` 는 `POST /promote` 전용 (일반 save 경로에서 생성 불가).

**저장 두 층 분리 (v22 2차안 신설, `note` 그릇 적용)**:
- **자동저장** — `PATCH /posts/{id}` 가 `posts.source` 만 갱신 (입력 1.5초 디바운스 + 페이지 이탈). LLM 호출 없음. 모바일 친화.
- **의미 처리** — `POST /posts/{id}/process` 가 sentences·노드·LLM 정정 후보 생성 (사용자 명시 트리거: ⌘S / "정리" 버튼). 자동저장과 한 트랜잭션으로 source 동기화 후 진행.

**모드 인식 UI (원칙 14 갱신)** — 라우트 두 개(`/note`·`/synapse`) 만 있어 사용자가 모드를 인지·선택하지 않음. 대신 `/note` 상단에 **자동저장 상태** (`변경됨 / 저장 중… / ✓ 저장됨`) + **의미 처리 상태** (`⚙ 정리 중… / ✦ 정리됨`) 를 명확히 표시.

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
- 저장 효과: sentence 로 **통째 저장**(`text="팀장:: 박지수"`). 별도 속성 테이블 신설 안 함 (세션노트 §2.3).
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

> v22 2차안 — 입력 모드 분리 폐지로 단일 경로. `parse_markdown` 이 heading 유무를 자동 판단해 카테고리 등록 또는 free 처리. 의미 처리 트리거 시점에만 호출 (자동저장은 source UPDATE 만).

### note 그릇 — heading 없는 입력 (평문)
```
사용자 입력 (단일 줄 또는 여러 줄 평문)
  ↓ 자동저장: PATCH /posts/{id} { source: "..." }   ← 1.5초 디바운스, LLM 미사용
  ────────────────────
  사용자 ⌘S / "정리" 버튼:
  ↓ POST /posts/{id}/process
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
  ↓ 자동저장: PATCH /posts/{id} { source: "..." }   ← 1.5초 디바운스, LLM 미사용
  ────────────────────
  사용자 ⌘S / "정리" 버튼:
  ↓ POST /posts/{id}/process
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

### synapse 모드 (v22 신설)
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

### insight 모드 (v22 신설 — 승격 전용)
```
사용자가 /synapse 세션 메시지의 [⬆ 통찰로 승격] 클릭
  ↓ promote_to_insight(source_sentence_id) 호출
  ↓ 새 posts 행 (kind='insight',
                  title=해당 메시지 첫 행,
                  source=해당 메시지 본문)
  ↓ 본체 sentence INSERT
       (post_id=새 insight post, role='user',
        origin='insight', text=해당 메시지 본문)
  ↓ 해당 synapse 세션의 retrieve 캐시에서 "당겨진 노드 id 전부" 스냅샷
  ↓ Kiwi 형태소 분석 (본체 sentence text 대상)
     + 스냅샷 노드 id 합집합
  ↓ node_sentence_mentions 일괄 INSERT (허브 자동 연결)
     — 본문 언급 여부 무관 (원칙 15-2, Hebbian)
  ↓ (선택) 사용자가 19 대분류 통찰 카테고리 지정 시 node_category_mentions
  ↓ ❌ 본체 sentence 는 이후 update_sentence API 에서 거부됨 (편집 불가)
  ↓ ❌ 삭제는 /review 승인 경로 (원칙 8)
```

> note — `sentence_categories` 는 **PLAN-004(카테고리 재설계)** 에서 도입된 테이블. `node_sentence_mentions` 는 v21 에서 `node_mentions` 리네임. v22 는 그 위에 synapse/insight 모드를 얹는다.

### 한 눈 비교표 (v22 2차안 — 3 종)

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
| LLM 정정 후보 (v22 2차안) | ✅ 의미 처리 시점 | ✅ 의미 처리 시점 | ❌ | ❌ |
| 편집 가능 | ✅ source 재로드 | ✅ source 재로드 | ✅ 개별 sentence | **❌ 본체 불변** |

### 공통 전처리

**어느 그릇이든 거치는 단계** — ISO 날짜 정규화·unresolved 감지·Kiwi 형태소·날짜 분할. 이는 그릇과 무관한 **기계적·결정론적** 변환이라 origin 이 `system` 으로 남는다.

---

## LLM 호출 요약 (v22 2차안)

| LLM 태스크 | note (의미 처리) | synapse | insight |
|---|:---:|:---:|:---:|
| 메타 필터 (의미 처리 1회) | ✅ 자유 문장·list | ❌ | ❌ |
| save-pronoun (list/free 줄별) | ✅ | ❌ | ❌ |
| **LLM 정정 후보 생성** (v22 2차안) | ✅ 의미 처리 끝부분 | ❌ | ❌ |
| retrieve-expand / retrieve-filter | — | **✅ (핵심)** | — |
| 답 생성 (LLM 재조합·마크다운 포맷) | — | **✅** | — |
| 카테고리 분류 워커 (백그라운드) | ✅ | ❌ | 옵션 |
| Wikidata 별칭 워커 (백그라운드) | ✅ | ❌ | ✅ |

**LLM 호출은 자동저장 시점엔 0회** — 사용자 명시 의미 처리 트리거에서만 호출되어 모바일 배터리·발열·네트워크 부담 통제됨 (원칙 13 정합).

key_value 줄에서 save-pronoun 을 skip 하는 근거:
- 구조화된 속성이라 지시어 존재 가능성 자체가 낮음
- 호출량 절감 — 장문 노트에서 key_value 줄별 호출은 불필요

---

## v19→v22 — 인출이 1급 모드가 되다

v19 까지는 "저장 2-모드" 와 "인출 세션 일회성" 의 비대칭 구조였다. v22 에서 인출 행위 자체를 1급 모드(`synapse`)로 격상해 다음 3 가지가 가능해진다:

1. **세션 단위 재진입** — 과거 synapse post 를 목록에서 열어 이어서 질문·심화 가능
2. **맥락 누적** — 세션 내 직전 질문·답이 다음 retrieve 의 LLM 프롬프트 맥락으로 주입됨 ("그중에 2026년 것만")
3. **통찰 승격 경로** — synapse 세션의 답에서 인사이트가 나왔을 때 `insight` 모드로 승격시켜 **허브 형태로 DB 에 편입** (원칙 15-2)

### synapse 세션이 지켜야 할 것
- 질문·답 sentence 는 저장되지만 `node_sentence_mentions` 편입 **안 함**. 질문은 "사실 언급" 이 아니므로 (원칙 1).
- 사용자가 명시적으로 "통찰" 로 승격시키기 전까지 하이퍼그래프에 영향 없음.
- 답 형식은 LLM 이 **마크다운으로 재조합** (단순 원문 나열 금지). 사용자 후속 발화로 정제·심화.

### 질문 자체의 처리
- 사용자 질문 형태(한 줄 "나 요즘 어때?" vs 구조화된 다중 조건)는 **프롬프트 레벨**에서 retrieve-expand 가 흡수.
- 긴 질문이라도 markdown 문법으로 저장되지는 않음 — `kind='synapse'` post 는 조합 목적이지 구조 등록 목적이 아님.

---

## 마이그레이션 (v21 → v22)

### 전략: DB 리셋 (ALTER 없음)

v22 는 앱 재작성과 병행되며, 다음 이유로 **DB 리셋**이 기본 전략:
- `posts.kind` CHECK 제약 확장(2값 → 4값) · `posts.markdown` → `posts.source` 리네임 · `posts.title` 신설은 SQLite 에서 테이블 재생성(copy+drop+rename) 이 필요함
- `sentences.post_id NOT NULL` 강제로 기존 `post_id=NULL` 인 assistant 응답은 그대로 이관 불가
- 기존 v21 이하 DB 는 PLAN-v22-rewrite 의 축적 데이터와 무관 (개인 DB 기준)

### 실 구현 (M3, 2026-04-25)

`engine/db.py` 의 `_is_current_schema` 가 v22 요건(`posts.kind`·`posts.title`·`posts.source` + `sentences.origin` + `sentences.post_id NOT NULL` + CHECK 확장)을 점검하고, 미일치 시 **자동 백업(`.backup-<timestamp>`) → 파일 삭제 → v22 재생성** 경로를 탄다. 사용자가 별도로 ALTER 를 실행할 필요 없음.

### 호출자 영향

**Python frozen 환경** (v22 1차안에서 구현·freeze 됨, 학습·dogfood·참조 구현 용도):

| 호출부 | 변경 |
|---|---|
| `engine.cli` 대화형 (Python frozen) | `kind='note'` (입력은 단일 그릇) |
| `api/routes/graph.py` `POST /note` | 새 note post 생성 + 첫 source 저장 |
| `api/routes/graph.py` `PATCH /posts/{id}` | 자동저장 — `posts.source` 만 갱신 (LLM 호출 없음) |
| `api/routes/graph.py` `POST /posts/{id}/process` | 의미 처리 — sentences 재계산 + LLM 정정 후보 생성 (사용자 명시 트리거) |
| `api/routes/graph.py` `POST /synapse/turn` | `kind='synapse'`. retrieve + answer + 세션 기록 전용 |
| `api/routes/graph.py` `POST /promote` | `kind='insight'` post 생성. source sentence_id + node_ids 받음 |
| 테스트 | 각 테스트 의도에 맞는 `kind` 명시 |

**Flutter 환경** (v22 2차안, [`PLAN-20260425-SYN-flutter-rewrite.md`](../deliverables/SYN/20260425/user/PLAN-20260425-SYN-flutter-rewrite.md) F1~F10 에서 신규 구현):

| 호출부 | 동등 동작 |
|---|---|
| `synapse_engine.SynapseFlow.noteAutosave` | `posts.source` UPDATE (LLM 미사용, <50ms) |
| `synapse_engine.SynapseFlow.noteProcess` | sentences 재계산 + LLM 정정 후보 (사용자 명시 트리거, ⌘S / "정리") |
| `synapse_engine.SynapseFlow.synapseTurn` | `kind='synapse'` post — retrieve + answer + 세션 기록 |
| `synapse_engine.SynapseFlow.promoteToInsight` | `kind='insight'` post 생성 + retrieve 캐시 노드 일괄 허브 연결 |
| `synapse_engine.SynapseFlow.listPosts/getPost/...` | post 목록·재진입·삭제 |

엔진 패키지 API 세부는 `DESIGN_ENGINE.md §2`.

---

## 구현 경계 — 두 PLAN 의 분담

### PLAN-v22-rewrite (v22 1차안, Python — M1~M5 완료, freeze)

**완료된 범위**:
- `posts` 스키마 변경 (kind 리네임·3값 enum·title·source 리네임). M3·M3.1
- `sentences.post_id NOT NULL` 강제 + `origin` 신설. M3
- `save()` 단일 경로 (mode 인자 폐지). M4·M4.1
- `/note`, `/synapse` 라우트 (`/chat`·`/compose` 통합)
- 자동저장 vs 의미 처리 두 층 분리 + 정정 후보 생성. M6
- `/promote` API 및 `promote_to_insight()` 엔진 함수. M4
- synapse retrieve 결과 노드 캐시 (승격 시 참조). M4
- 설계 문서 8 개 v22 2차안 정합. M5

이 작업은 학습·dogfood·참조 구현 환경으로 freeze. Flutter 측 구현이 알고리즘을 그대로 가져간다.

### PLAN-flutter-rewrite (v22 2차안, Flutter — F0~F10 진행 중)

**범위 내** ([`PLAN-20260425-SYN-flutter-rewrite.md`](../deliverables/SYN/20260425/user/PLAN-20260425-SYN-flutter-rewrite.md) 참조):
- `synapse_engine` Dart 패키지 신규 (2 계층 API: SynapseFlow / LlmTasks / GraphOps). F1~F5
- DB 스키마 v22 2차안 (`allowedKinds` 컨스트럭터 유연성). F2
- llamadart 인프로세스 + LoRA 핫스왑 + Kiwi WASM. F3·F4
- 시냅스 Flutter 앱 `/note`·`/synapse` (모바일 우선·데스크톱 통합). F6~F8
- iOS·Android·macOS 통합 검증. F9
- 설계 정합 + 문서 갱신. F0·F10

**범위 외 (후속 PLAN)**:
- 갑질 어댑터 6 개 audit · 갑질 v22 엔진 적용
- 하이퍼그래프 뷰 (`/hypergraph`)
- `/review` 통찰 삭제 UI
- 온보딩 / 조직 모드 UI
- 첫 실행 모델 다운로드 인프라 + 모델 카탈로그 UI
- 다른 베이스용 어댑터 학습 (Qwen·Phi 등)
- LLM 정정 프롬프트 정교화 (실측 후 별도 PLAN)

---

## 참고

- 이 문서의 이전 기초: `PLAN-20260422-SYN-003-input-modes.md` (v19 — 2-모드 시작)
- v21 통합: `PLAN-20260423-SYN-007-hyperedge-unify.md` (node_mentions 리네임)
- 세션노트 `SESSION-NOTES-20260421-input-and-retrieval.md` §10·§11·§12
- `project_save_pronoun_bottleneck` 메모리

# Synapse 설계 — 입력 모드 & 인출 관계

**최종 업데이트**: 2026-04-24 (v22 계획 — 2 모드 → **4 모드** 로 확장. `posts.input_mode` → `kind`. 인출·융합 모드 `synapse` 1급화. 사용자 승격 통찰 `insight` 1급화. 선행 v19: PLAN-003 "마크다운 입력 체계 + 모드 분리" — `posts.input_mode` 컬럼 신설 / `- key:: value` 파서 / save-pronoun 모드별 분기)

**관련 문서**: `DESIGN_PRINCIPLES.md` §1 원칙 9 · `DESIGN_PIPELINE.md` 저장 파이프라인 · `DESIGN_HYPERGRAPH.md` 스키마 · `INPUT_GUIDE.md` 작성자용 실전 가이드

---

## 배경 — 왜 모드를 나누나

v18 까지 `save()` 는 입력의 `has_heading()` 결과로 **자동 분기**했다. `structure-suggest` 를 v17 에서 폐기한 뒤에도 모드 결정은 "텍스트에 heading 이 있나" 라는 **내용 기반 자동 판정**에 의존. 이 판정이 흔들리는 경우:

| 시나리오 | 자동 판정 | 사용자 의도 | 결과 |
|---|---|---|---|
| `# 야근\n오늘 회의 길었어` | markdown | chat (해시태그 감각) | `야근` 카테고리로 강제 분류 |
| markdown 쓰려다 heading 누락 | chat | markdown | 카테고리 없이 저장 → 인출 누락 |
| 같은 문장 재호출 | 매번 재계산 | 동일성 기대 | 모호 |

**2026-04-22 합의** — UI 진입점부터 모드를 분리한다. 자동 판정 의존 제거. 모드는 사용자가 **입력창 선택**으로 명시한다.

> 시냅스의 원칙 11(지능체는 분리)·원칙 10(도메인은 관찰)에 비추어도, 저장 시점에 "이건 어떤 종류의 글인가" 를 모델·규칙이 판정하는 단계 자체가 불필요.

---

## 모드 정의 (v22 — 4 모드)

| 모드 | UI 라우트 | API `kind` 값 | DB `posts.kind` | 주된 용도 |
|---|---|---|---|---|
| **chat** | `/chat` | `'chat'` | `'chat'` | 지식 축적 — 메신저 스타일 평문, 즉흥 기록 |
| **markdown** | `/compose` | `'markdown'` | `'markdown'` | 지식 축적 — 구조화된 기록, 공문서·법령 원문, 구조·키값 포함 글 |
| **synapse** | `/synapse` | `'synapse'` | `'synapse'` | 지식 활용·융합 — 축적된 지식 사이의 새 연결 발화. 질문·답이 역사로 기록되며 노드 편입 없음 |
| **insight** | 승격 전용 | `'insight'` | `'insight'` | 사용자가 synapse 메시지를 "통찰"로 승격 → 고유 post 1 개 = 본체 sentence 1 개. 편집 불가·허브 연결 |

**중간 전환 금지** — post 안에서 모드 전환되지 않는다. chat 입력창에서 `#` 을 쳐도 `#야근` 은 단순 텍스트. 모드는 **라우트 진입 시 한 번** 결정되고, 저장 파이프라인은 그 결정을 따른다.

**API 계약** — `kind` 파라미터 **기본값 없음**. 호출자가 반드시 4 값 중 하나 명시. `'insight'` 는 `POST /posts/{id}/sentences/{sid}/promote` 전용 (일반 save 경로에서 생성 불가).

**모드 인식 UI (원칙 14)** — 각 라우트 상단에 모드 배지 상시 표시, 채팅 입력창에서 마크다운 문법(heading·`::`·긴 paste)이 감지되면 `/compose` 전환 유도. 자연어→마크다운 핫키는 `/compose` 에서만 제공.

---

## 마크다운 문법 명세 (markdown 모드)

markdown 모드 입력은 아래 네 가지 요소로 구성된다. 각 요소는 저장 파이프라인에서 서로 다른 경로를 탄다.

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
- save-pronoun **skip** (공문서·고유 표기 보존).
- 메타 필터 **제외** (구조화된 기록이므로 "메타 대화" 가능성 없음).

파서 정규식: `^-\s+(.+?)\s*::\s+(.+)$` — key 와 value 양쪽 공백은 trim. 둘 중 하나라도 비면 매칭 실패 → 일반 list 로 강등.

### 3) `- value` (일반 list)
```markdown
- 오늘 피곤함
- 회의 3시간
```
- 저장 효과: sentence INSERT. 일반 자유 문장과 동일 취급.
- 메타 필터 대상 · save-pronoun skip (markdown 모드 전체 skip).

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

## 저장 파이프라인 — 모드별 비교

### chat 모드
```
사용자 입력 (단일 줄 또는 여러 줄 평문)
  ↓ posts INSERT (input_mode='chat', markdown=원문)
  ↓ parse_markdown  — heading 없음 → 모든 줄 (category_path=None, kind='free', text)
  ↓ [메타 필터 — 게시물 단위 1회 LLM]
     모든 줄 대상
  ↓ 줄별 (메타 idx 제외):
     ① save-pronoun (LLM) — 지시어·날짜 치환
     ② ISO 날짜 정규화 (규칙)
     ③ unresolved 감지 (규칙)
     ④ sentence INSERT (category_path=None)
     ⑤ Kiwi 형태소 분석
     ⑥ 날짜 분할 (규칙)
     ⑦ 노드 upsert + node_mentions
        — sentence_categories 등록 없음 (상속할 heading 없음)
```

### markdown 모드
```
사용자 입력 (heading + key-value + list + 자유 문장 혼재)
  ↓ posts INSERT (kind='markdown', source=원문)
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
        — save-pronoun skip
     [list / free]
        ② ISO 날짜 정규화
        ③ unresolved 감지
        ④ sentence INSERT (category_path 상속)
        ⑤ Kiwi 형태소 분석
        ⑥ 날짜 분할
        ⑦ 노드 upsert + node_sentence_mentions + sentence_categories
        — save-pronoun skip
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

### 한 눈 비교표 (v22 — 4 모드)

| 처리 | chat | markdown | synapse | insight |
|---|:---:|:---:|:---:|:---:|
| sentence INSERT (user) | ✅ | ✅ (heading 제외) | ✅ 질문 | ✅ 본체 1개 |
| sentence INSERT (assistant) | 옵션 | — | ✅ 답 | — |
| category_path 상속 | — | ✅ | — | — |
| 메타 필터 | ✅ 전체 | 자유문장·list만 | ❌ | ❌ |
| save-pronoun | ✅ | ❌ | ❌ | ❌ |
| ISO 날짜 정규화 | ✅ | ✅ | — | ✅ |
| unresolved 감지 | ✅ | ✅ | — | — |
| Kiwi 형태소 | ✅ | ✅ | ❌ | ✅ |
| 날짜 분할 | ✅ | ✅ | — | ✅ |
| node_sentence_mentions 편입 | ✅ | ✅ | **❌** | ✅ + **세션 retrieve 노드 허브** |
| sentence_categories 편입 | ❌ | ✅ (heading 있으면) | ❌ | 옵션 (사용자 지정) |
| aliases 자동 | ✅ | ✅ | ❌ | ✅ |
| source 에 누적 | ✅ 메시지 라인 | ✅ 사용자 저장 시 원본 | ✅ Q/A 로그 | 본체 1 줄 |
| 편집 가능 | ✅ sentence 단위 | ✅ source 재로드 | ✅ 개별 sentence | **❌ 본체 불변** |

### 공통 전처리

**어느 모드든 거치는 단계** — ISO 날짜 정규화·unresolved 감지·Kiwi 형태소·날짜 분할. 이는 모드와 무관한 **기계적·결정론적** 변환이라 origin 이 `system` 으로 남는다.

---

## 모드별 LLM 호출 요약 (v22)

| LLM 태스크 | chat | markdown | synapse | insight |
|---|---|---|---|---|
| 메타 필터 (게시물 단위 1회) | ✅ 전체 | ✅ 자유 문장·list 만 | ❌ | ❌ |
| save-pronoun (줄별) | ✅ | ❌ | ❌ | ❌ |
| retrieve-expand / retrieve-filter | — | — | **✅ (핵심)** | — |
| 답 생성 (LLM 재조합·마크다운 포맷) | — | — | **✅** | — |
| 자연어 → 마크다운 변환 (핫키) | ❌ 비활성 | ✅ 에디터 in-place | — | — |
| 카테고리 분류 워커 (백그라운드) | ✅ | ✅ | ❌ | 옵션 |
| Wikidata 별칭 워커 (백그라운드) | ✅ | ✅ | ❌ | ✅ |

markdown 전체에서 save-pronoun 을 skip 하는 근거:
- 공문서·법령 원문에서 "그"·"이것"·"어제" 는 **문서 원문의 일부** 이며 치환되면 원문 훼손.
- key-value 는 구조화된 속성이라 지시어 존재 가능성 자체가 낮음.
- 자유 문장은 heading 경로가 이미 맥락을 주므로 지시어 모호성이 chat 보다 낮음.
- 호출량 절감 — 장문 markdown 게시물 저장 시 save-pronoun 줄별 호출이 2~4분 병목(세션노트 §2.3, 메모리 `project_save_pronoun_bottleneck`). markdown skip 으로 해소.

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

### 스키마 변경
```sql
-- posts 재생성 (SQLite 는 CHECK 제약·컬럼 리네임 ALTER 제한)
ALTER TABLE posts RENAME COLUMN input_mode TO kind;
ALTER TABLE posts RENAME COLUMN markdown TO source;
ALTER TABLE posts ADD COLUMN title TEXT;
-- CHECK 제약 확장: 'chat','markdown' → 'chat','markdown','synapse','insight'
-- (테이블 재생성 + 복사 패턴 필요. engine/db.py 에서 처리)

ALTER TABLE sentences ADD COLUMN origin TEXT;
-- sentences.post_id NOT NULL 강제:
-- 기존 post_id=NULL 인 assistant 응답은 마이그레이션 불가 — DB 리셋 권장.
```

### DB 리셋 권장
v22 는 app 재작성과 병행되므로, **기존 DB (`~/.synapse/synapse.db`) 는 리셋**하고 새 스키마로 시작하는 것이 안전. 엔진 `db.py` 가 스키마 없으면 자동 생성.

### 호출자 영향

| 호출부 | 변경 |
|---|---|
| `engine.cli` 대화형 | `kind='chat'` |
| `engine.cli --markdown-file` | `kind='markdown'` |
| `api/routes/graph.py` `/chat` | `kind='chat'` (현재 `/chat` 라우트는 채팅 축적 전용) |
| `api/routes/graph.py` `/ingest` 신설 | `kind='markdown'` (POST 본문에 마크다운 원본) |
| `api/routes/graph.py` `/synapse` 신설 | `kind='synapse'`. retrieve + answer + 세션 기록 전용 |
| `api/routes/graph.py` `/promote` 신설 | `kind='insight'` post 생성. source sentence_id + synapse post_id 받음 |
| 테스트 | 각 테스트 의도에 맞는 `kind` 명시 |

---

## 구현 경계 (PLAN-v22 범위)

**범위 내**
- `posts` 스키마 변경 (kind 리네임·값 확장·title·source 리네임)
- `sentences.post_id NOT NULL` 강제 + `origin` 신설
- `save(..., kind=...)` 시그니처 갱신
- `/chat`, `/compose`, `/synapse` 라우트 분리
- `/promote` API 및 `promote_to_insight()` 엔진 함수
- synapse retrieve 결과 노드 캐시 (승격 시 참조)
- 자연어→마크다운 변환 핫키 (`/compose` 에디터 전용)
- 모드 인식 UI (배지·전환 유도)

**범위 외 (후속 PLAN)**
- 하이퍼그래프 뷰 (`/hypergraph`) 재작성
- `/review` 통찰 삭제 승인 UI
- 온보딩 재작성
- 조직 모드 UI

---

## 참고

- 이 문서의 이전 기초: `PLAN-20260422-SYN-003-input-modes.md` (v19 — 2-모드 시작)
- v21 통합: `PLAN-20260423-SYN-007-hyperedge-unify.md` (node_mentions 리네임)
- 세션노트 `SESSION-NOTES-20260421-input-and-retrieval.md` §10·§11·§12
- `project_save_pronoun_bottleneck` 메모리

# Synapse 설계 — 입력 모드 & 인출 관계

**최종 업데이트**: 2026-04-23 (v19 예정 — PLAN-20260422-SYN-003 "마크다운 입력 체계 + 모드 분리". `posts.input_mode` 컬럼 신설 / `- key:: value` 파서 / save-pronoun 모드별 분기)

**관련 문서**: `DESIGN_PRINCIPLES.md` §1 원칙 9 · `DESIGN_PIPELINE.md` 저장 파이프라인 · `DESIGN_HYPERGRAPH.md` 스키마

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

## 모드 정의

| 모드 | UI 입력창 | API `mode` 값 | DB `posts.input_mode` | 주된 용도 |
|---|---|---|---|---|
| **chat** | 메신저 스타일 단일 줄 / 여러 줄 평문 | `'chat'` | `'chat'` | 즉흥 기록, 단편 생각, 일상 감상 |
| **markdown** | 전체 화면 에디터 + 저장 버튼 | `'markdown'` | `'markdown'` | 구조화된 기록, 공문서·법령 원문, 구조·키값이 포함된 글 |

**중간 전환 금지** — chat 입력창에서 `#` 을 쳐도 모드 전환되지 않는다. `#야근` 은 단순 텍스트. 모드는 **입력창 선택 단계에서 한 번** 결정하고, 저장 파이프라인은 그 결정을 따른다.

**API 계약** — `mode` 파라미터는 **기본값 없음**. 호출자가 반드시 `'chat'` 또는 `'markdown'` 으로 명시한다. (문자열 이외 값이면 입력 오류로 거부.)

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
  ↓ posts INSERT (input_mode='markdown', markdown=원문)
  ↓ parse_markdown — (category_path, kind, text) 튜플 스트림
                      kind ∈ {'heading', 'key_value', 'list', 'free'}
  ↓ [메타 필터] — 자유 문장·list 만 대상 (heading·key_value 제외)
  ↓ 요소별:
     [heading]
        — sentence INSERT 안 함
        — 카테고리 path 등록 (PLAN-004 categories 마스터 테이블)
     [key_value]
        ② ISO 날짜 정규화
        ③ unresolved 감지
        ④ sentence INSERT (text="key:: value", category_path 상속)
        ⑤ Kiwi 형태소 분석
        ⑥ 날짜 분할
        ⑦ 노드 upsert + mentions + sentence_categories
        — save-pronoun skip
     [list / free]
        ② ISO 날짜 정규화
        ③ unresolved 감지
        ④ sentence INSERT (category_path 상속)
        ⑤ Kiwi 형태소 분석
        ⑥ 날짜 분할
        ⑦ 노드 upsert + mentions + sentence_categories
        — save-pronoun skip
```

> note — `sentence_categories` 는 **PLAN-20260422-SYN-004(카테고리 재설계)** 에서 도입되는 테이블. PLAN-003 M2 구현 시점에는 아직 없으므로 heading 경로는 v18 `node_categories` 에 일단 기록됐다가 PLAN-004 M1 마이그레이션에서 재배선된다.

### 한 눈 비교표

| 요소 | chat | markdown heading | markdown key_value | markdown list/free |
|---|---|---|---|---|
| sentence INSERT | ✅ | ❌ | ✅ | ✅ |
| category_path | — | 등록 | 상속 | 상속 |
| 메타 필터 | ✅ | — | ❌ | ✅ |
| save-pronoun | ✅ | — | ❌ | ❌ |
| ISO 날짜 정규화 | ✅ | — | ✅ | ✅ |
| unresolved 감지 | ✅ | — | ✅ | ✅ |
| Kiwi 형태소 | ✅ | — | ✅ | ✅ |
| 날짜 분할 | ✅ | — | ✅ | ✅ |

### 공통 전처리

**어느 모드든 거치는 단계** — ISO 날짜 정규화·unresolved 감지·Kiwi 형태소·날짜 분할. 이는 모드와 무관한 **기계적·결정론적** 변환이라 origin 이 `system` 으로 남는다.

---

## 모드별 LLM 호출 요약

| LLM 태스크 | chat | markdown |
|---|---|---|
| 메타 필터 (게시물 단위 1회) | ✅ 전체 줄 | ✅ 자유 문장·list 만 |
| save-pronoun (줄별) | ✅ | ❌ |
| 카테고리 분류 워커 (백그라운드) | ✅ | ✅ |
| Wikidata 별칭 워커 (백그라운드) | ✅ | ✅ |

markdown 전체에서 save-pronoun 을 skip 하는 근거:
- 공문서·법령 원문에서 "그"·"이것"·"어제" 는 **문서 원문의 일부** 이며 치환되면 원문 훼손.
- key-value 는 구조화된 속성이라 지시어 존재 가능성 자체가 낮음.
- 자유 문장은 heading 경로가 이미 맥락을 주므로 지시어 모호성이 chat 보다 낮음.
- 호출량 절감 — 장문 markdown 게시물 저장 시 save-pronoun 줄별 호출이 2~4분 병목(세션노트 §2.3, 메모리 `project_save_pronoun_bottleneck`). markdown skip 으로 해소.

---

## 인출 모드와의 관계

**저장 모드(2)** 와 **인출 모드** 는 별개의 축이다. PLAN-003 은 저장 2-모드만 정립하며, 인출은 현재대로 `retrieve()` 단일 경로 — 질문은 chat 스타일이든 markdown 스타일이든 같은 BFS + retrieve-expand/filter 를 탄다.

### 왜 인출은 나누지 않나

- 인출은 `posts` 를 만들지 않음. 질문은 sentence 로 저장되지 않는다(role='assistant' 응답만 저장).
- 사용자 질문 형태(한 줄 "나 요즘 어때?" vs 구조화된 다중 조건)는 **프롬프트 레벨** 에서 retrieve-expand 가 흡수.
- 저장 mode 는 DB 에 영구 기록되지만, 인출 mode 는 세션 내 일회성 처리.

### 향후 확장 (범위 외)

3-모드 통합(`retrieve` / `chat_save` / `markdown_save`)의 형식적 모델 — 세 모드가 같은 `posts` 스키마 위에 얹히는 추상은 가능하지만 PLAN-003 범위 밖. 먼저 저장 2-모드를 운영하며 UX·데이터를 관찰한 뒤 재설계.

---

## 마이그레이션 (v18 → v19)

### 스키마 변경
```sql
ALTER TABLE posts ADD COLUMN input_mode TEXT NOT NULL DEFAULT 'chat'
  CHECK (input_mode IN ('chat', 'markdown'));
```

### Backfill
기존 v18 posts 행:
- `posts.markdown` 을 `has_heading()` 으로 판정
- heading 포함 → `input_mode='markdown'`
- 아니면 → `input_mode='chat'`

판정 로직은 v18 까지 자동 분기에 쓰던 `has_heading()` 과 동일. Backfill 은 M1 에서 1회 실행 후 로직 제거.

### 호출자 영향

| 호출부 | 변경 |
|---|---|
| `engine.cli` 대화형 | `mode='chat'` 고정 (단일 줄 입력) |
| `engine.cli --markdown-file` 추가 예정 | `mode='markdown'` |
| `api/routes/graph.py` `/ingest` | `mode` 쿼리·바디 파라미터 필수 |
| 테스트 (dogfood 등) | 각 테스트 의도에 맞는 `mode` 명시 |

---

## 구현 경계 (PLAN-003 범위)

**범위 내**
- `posts.input_mode` 컬럼 + CHECK 제약 + backfill
- `save(..., mode=...)` 시그니처
- `parse_markdown` 반환 형식 확장 (kind 추가)
- `- key:: value` 파서
- save-pronoun 모드별 분기
- 메타 필터 대상 범위 모드별 조정

**범위 외**
- UI 입력창 분리 (프론트 PLAN 별도)
- 인출 모드 분기
- `sentence_categories` 테이블 도입 (PLAN-004)
- 3-모드 통합 형식적 모델

---

## 참고

- PLAN-20260422-SYN-003-input-modes.md
- 세션노트 `SESSION-NOTES-20260421-input-and-retrieval.md` §10·§11·§12
- `project_save_pronoun_bottleneck` 메모리

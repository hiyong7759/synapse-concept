# Synapse 설계 — 저장/인출/대화 파이프라인

**최종 업데이트**: 2026-04-17 (v11 — 자동/수동 분리, 조사 엣지 폐기, node_mentions, unresolved_tokens)

## 근본 목표

> 자동 저장 범위는 "언급된 것"에 정확히 일치시키고, 의미 합성은 사용자 승인으로만 DB에 편입한다. 이 분리가 그래프의 신뢰성을 담보한다.

---

## DB 스키마 (v11 — 자동/수동 분리)

```sql
sentences:         id, text, role('user'|'assistant'), retention('memory'|'daily'), created_at
nodes:             id, name, status('active'|'inactive'), created_at, updated_at
node_mentions:     node_id, sentence_id, created_at                 — PK(node_id, sentence_id)
node_categories:   node_id, category, created_at                    — PK(node_id, category)
edges:             id, source_node_id, target_node_id, label(의미 관계), sentence_id, created_at, last_used
aliases:           alias TEXT PRIMARY KEY, node_id
unresolved_tokens: sentence_id, token, created_at                   — PK(sentence_id, token)
```

**핵심 원칙:** `edges` / `node_categories` / `aliases`는 **승인된 것만 존재**. 승인 전 제안은 저장하지 않고 `/review` 호출 시 런타임 도출. 유일한 예외는 `unresolved_tokens` — 저장 시점에만 감지되는 일회성 이벤트라 재생성 불가.

**node_mentions**: 모든 노드에 동일 적용되는 노드↔문장 역참조. 조사 엣지 폐기로 끊긴 경로를 대체. 시간·장소·부정 같은 특수 노드도 별도 취급 없이 여기만 참조한다.

**edges.label**: 의미 관계 종류 (`similar / cooccur / cause / contain / avoid / …`). 조사 저장 금지. 사후 생성 + 사용자 승인으로만 삽입.

**sentences.role**: `user`(그래프 추출 대상) / `assistant`(대화 기록).

**sentences.retention**: `memory`(잘 변하지 않는 사실·상태·이력) / `daily`(순간적 활동·감정·일상). LLM이 저장 시 판단.

---

## 자동 저장 파이프라인

모든 그래프 변경 중 **자동으로 일어나는 것은 원문·노드·역참조까지**. 나머지(카테고리·엣지·별칭·병합)는 `/review` 승인이 있어야 DB에 들어간다.

### 입력 모드

사용자 입력은 마크다운 파서(`engine/markdown.py`)를 먼저 거친다.

- **heading·list 구조가 있는 마크다운** → 마크다운 모드로 즉시 저장
- **heading·list 없는 평문** → `synapse/structure-suggest` 어댑터가 마크다운 초안을 제안. 사용자가 편집·확정 후 마크다운 모드로 재진입. 확정 전까지 저장되지 않음

### 마크다운 모드

```markdown
# 더나은
## 개발팀
- 팀장 박지수
- 프론트엔드 김민수
```

heading 경로(`더나은.개발팀`)가 사용자 명시 카테고리 경로가 된다.

### 파이프라인 흐름 (마크다운 모드)

```
사용자 입력(마크다운)
  ↓ parse_markdown(text)
  ↓
각 (heading 경로, 항목)마다:
  ↓
  [_preprocess — synapse/save-pronoun]  temperature=0
    지시어 치환 (지시대명사/시간부사/장소·사물·인물·부정부사)
    인칭대명사(나/내/저/제)는 치환하지 않음
    세션리스 — 직전 대화 context 주입 없음
    확정된 토큰 → tokens[{name, category?}] 목록
      category는 규칙 기반 분명한 것만 부여 (시간/장소/인물/사물/부정 등 모두 허용. 모호하면 생략)
    치환 실패 지시어 원형 → unresolved[] 목록 (예: "이거", "그때", "걔")
    저장 자체가 불가능한 완전 모호 케이스만 {"question": "..."} 반환 → 저장 중단
  ↓
  [규칙 — ISO 날짜 → 한국어 정규화]
    '2026-04-18' → '2026년 4월 18일', '2026-04' → '2026년 4월'
    한글 조사 뒤(예: '2026-04-18에')에서도 매칭되도록 negative lookbehind/lookahead 사용
    이 단계 이후 본문은 항상 한국어 표기 (사용자 언급 공간 = 한국어)
  ↓
  sentences INSERT (정규화된 effective_text, role='user', post_id, position)
  ↓
  [synapse/extract]  temperature=0, max_tokens=32768
    입력: 정규화된 텍스트 + "알려진 사실:" (인출 원본 문장들, 있을 때)
    출력: {nodes, retention, deactivate}
    edges·category 필드는 엔진에서 드롭 (프롬프트 필터 수준에서 무시. 재학습 전까지 유예)
    전처리: ()[] 공백 치환 (2B 모델 반복 루프 방지)
  ↓
  [규칙 — 부정부사 후처리]
    문장 내 '안'·'못'을 감지해 노드 추출 결과에 추가 (엣지 생성 없음)
  ↓
  [규칙 — 날짜 노드 분할]
    '2026년 4월 18일' → ['2026년', '4월', '18일'] 노드 후보 추가
    '2026년 4월' → ['2026년', '4월']
    '2026년' → ['2026년']
    '4월 18일' → ['4월', '18일']  (년 미상)
    한 sentence 안의 모든 단위(년·월·일)가 같은 sentence_id에 mention 연결됨
    → 시간 범위 쿼리 지원 ("4월에 뭐 있었지?", "2026년 기록", BFS 교집합으로 정밀 좁힘)
    식별 조건: 명시적 키워드('년/월/일') 또는 ISO 구분자('-')가 있을 때만.
    단독 4자리 숫자(2026)는 오탐 위험으로 제외.
  ↓
  DB 저장:
    nodes upsert (중복 이름은 기존 id 재사용 — '2026년'은 모든 게시물에서 같은 노드)
    node_mentions INSERT OR IGNORE (node_id, sentence_id)
    node_categories INSERT — heading 경로(사용자 명시) 또는 규칙 기반 분명 분류만
      LLM 추론 카테고리는 DB에 저장하지 않음
    sentences.retention UPDATE
    deactivate 필드 → _deactivate_by_sentence_ids (선택, 사용자가 취소한 과거 기록 표시)
  ↓
  unresolved_tokens INSERT (치환 실패 토큰)
```

### 날짜 처리 — 사용자 언급 공간 원칙

노드 = 사용자가 일상에서 말하는 단위. ISO(`2026-04-18`) 표기는 기계 친화적이지만 사용자는 `2026년 4월 18일`이라 말한다. 그래서:

| 입력 본문 | 정규화 후 sentence | 분할 노드 |
|----------|-------------------|----------|
| `2026-04-18에 진단` | `2026년 4월 18일에 진단` | `2026년`, `4월`, `18일`, `진단` |
| `2026년 4월 20일 운동` | (변동 없음) | `2026년`, `4월`, `20일`, `운동` |
| `2026-04 기록` | `2026년 4월 기록` | `2026년`, `4월`, `기록` |
| `4월에 시작` | (변동 없음) | `4월`, `시작` |
| `2026 매출` | (변동 없음) | `매출`만 (2026은 오탐 회피로 노드화 X) |

같은 `2026년` 노드는 게시물 횟수만큼 자동으로 mention이 누적. 사용자가 한 번도 카드 승인 안 해도 시간 단위로 BFS 가능.

### 파이프라인 흐름 (평문 모드)

```
사용자 입력(평문)
  ↓ parse_markdown — heading·list 없음 확인
  ↓
  [synapse/structure-suggest]  temperature=0, max_tokens=1024
    기존 사용자 카테고리 경로 목록을 컨텍스트로 받음
    출력: 마크다운 초안 (heading + list)
  ↓
  SaveResult.markdown_draft 반환 (DB 변경 없음)
  ↓
  프론트: 사용자가 초안 편집·확정
  ↓
  확정된 마크다운으로 save() 재호출 → 마크다운 모드 플로우
```

### 자동 저장 이후 제외된 것들

다음은 **자동 저장되지 않는다** — 사용자 승인 전까지 DB에 들어가지 않음:

- `edges` 삽입 (의미 관계는 사후 생성 + 승인)
- LLM 추론 카테고리 (사용자 명시·규칙 확정만 즉시 삽입)
- LLM 별칭 제안 (`/review`에서 사용자 요청 시에만 호출)
- 오타 교정에 의한 노드 이름 변경 (`_correct_typos` 폐기 — "언급된 것만 존재" 원칙)
- `_FIRST_PERSON_ALIASES`는 예외로 유지 (인칭대명사 11개 자동 시드)

---

## 인출 파이프라인

```
질문
  ↓ [synapse/retrieve-expand]  temperature=0, max_tokens=256
    질문 의도 해석 → 노드 후보 키워드
  ↓ [원문 토큰 병합]
    질문 원문 공백 분리 → keywords에 병합
  ↓ [DB 매칭]
    aliases 정확 매칭 우선 → name 정확 매칭 → name substring 매칭
  ↓ [BFS 루프]  max_layers=5
    현재 노드 집합마다 두 경로를 합쳐 다음 레이어 구성:
      ① node_mentions JOIN sentences → 같은 sentence에 함께 언급된 노드 (자동 저장 결과)
      ② edges JOIN                  → 사용자 승인된 의미 엣지의 인접 노드
                                       (label = similar/cause/contain/avoid/...)
    [synapse/retrieve-filter]  temperature=0, max_tokens=8
      ①은 sentence 단위로, ②는 근거 sentence가 있으면 그것으로,
      없으면 'src ─(label)→ tgt' 텍스트로 관련성 판단 (pass/reject). 불확실하면 pass
    통과한 항목의 새 노드 → 다음 레이어
    양쪽 모두 새 노드 없으면 종료
  ↓ [카테고리 보완] (선택)
    시작 노드의 카테고리 → 인접 카테고리의 미방문 노드 조회 → 재필터
  ↓ [last_used 배치 업데이트]
    BFS 동안 사용된 의미 엣지의 last_used 갱신 (콤팩팅·생존 카드 판단용)
  ↓ [synapse/chat]  temperature=0.3, max_tokens=4096
    인출 sentences + 사용자 승인 의미 엣지를 함께 컨텍스트로 자연어 답변
    답변 → sentences INSERT (role='assistant')
```

### 두 경로의 역할 구분

| 경로 | 데이터 출처 | 의미 |
|------|-------------|------|
| ① `node_mentions` | 자동 저장 (사용자가 같은 게시물·문장에 함께 언급) | "함께 등장한 사실" |
| ② `edges` | 사용자 승인된 검토 카드 | "확정된 의미 관계" |

①은 통계적·우연적 공출현, ②는 사용자가 명시적으로 인정한 관계. 둘 다 인출에 기여하되 답변 컨텍스트에서는 다르게 표시:
- ①은 sentence 원문 그대로 ("- 허리디스크 진단")
- ②는 근거 sentence가 있으면 그걸로, 없으면 관계 자체 ("- 허리디스크 ─(cause)→ 통증")

### 모든 노드는 같은 경로로 조회된다

날짜·시간부사·부정부사·장소 같은 토큰도 일반 명사 노드와 **같은 두 경로**를 거친다.

- "2026-04-17에 뭐 있었지?" → `2026-04-17` 노드 → `node_mentions` → sentences → 함께 언급된 노드
- "안 먹은 약" → `안` 노드 → mentions → sentence → 함께 언급된 약 노드
- "허리디스크의 원인" → `허리디스크` 노드 → 의미 엣지(`cause`)로 연결된 인접 노드

특수 카테고리(TIM/NEG 등)나 특수 경로 없음.

---

## /review — 검토 편입

자동 저장 외의 모든 그래프 변경은 `/review`를 통한다.

### 섹션별 런타임 도출 (저장 없음)

`engine/suggestions.py`가 페이지 호출 시점에 DB 쿼리 + 필요 시 LLM 호출로 제안 리스트를 반환한다. 도출기 함수는 결과를 DB에 쓰지 않는다.

| 섹션 | 데이터 소스 | LLM 호출 |
|------|-------------|----------|
| `unresolved` — 미해결 지시어 | `unresolved_tokens` 테이블 + 사용자 카테고리 노드 맥락 | 불요 |
| `uncategorized` — 미분류 노드 | `nodes LEFT JOIN node_categories WHERE category IS NULL` | 선택 (LLM 제안 옵션 추가 시) |
| `cooccur_pairs` — 공출현 쌍 | `node_mentions` self-JOIN, `edges`에 이미 있는 쌍 제외 | 선택 (관계 종류 옵션 제시 시) |
| `suspected_typos` — 오타 의심 | `find_suspected_typos` 런타임 jamo 계산 | 불요 |
| `alias_suggestions(node_id)` — 별칭 제안 | 사용자가 노드 상세에서 요청 시 | 필수 |
| `stale_nodes(days)` — 노드 생존 | `nodes.updated_at`, `edges.last_used` | 불요 |
| `daily(date)` — 일일 회고 | 해당 날짜 `sentences` | 불요 |
| `gaps()` — 기록 공백 | `sentences.created_at` 분석 | 불요 |

### 승인 처리 (POST /review/apply)

| type | params | 동작 |
|------|--------|------|
| `edge` | `{source_id, target_id, label}` | `edges` INSERT |
| `category` | `{node_id, category}` | `node_categories` INSERT |
| `alias` | `{node_id, alias}` | `aliases` INSERT |
| `merge` | `{keep_id, remove_id}` | `merge_nodes` 호출 |
| `archive` | `{node_id}` | `nodes.status='inactive'` |
| `token` | `{sentence_id, token, value}` | `nodes` upsert + `node_mentions` INSERT + `unresolved_tokens` DELETE |
| `token_dismiss` | `{sentence_id, token}` | `unresolved_tokens` DELETE (그래프 변경 없음) |

승인된 결과는 **즉시 최종 테이블에 반영**. 중간 상태(status·origin) 없음.

상세: `docs/DESIGN_REVIEW.md` 참고.

---

## 문장 관리

### 문장 수정 (`update_sentence`)

```
sentence_id + new_text
  → sentences.text UPDATE
  → 해당 sentence_id 연관 node_mentions DELETE → 고아 노드 보존
  → new_text 재분석 → 새 node_mentions INSERT (동일 sentence_id 재사용)
```

### 문장 삭제 (`delete_sentence`)

```
sentence_id
  → node_mentions CASCADE DELETE
  → edges.sentence_id 참조가 있으면 FK SET NULL (엣지 보존, 근거 문장만 끊김)
  → 고아 노드는 보존 (재연결 가능성)
  → sentences 삭제
```

### 콤팩팅

sentence 단위 정리. 고아 노드는 보존 (재연결 가능성).

**대상 조건** (세 조건 모두 충족):
- `retention='daily'`
- `edges.last_used IS NULL` + 해당 sentence 참조 노드의 mentions도 한 번도 인출 안 됨
- `created_at`이 N일 이상 경과

**사용자 설정:** 자동 정리 ON/OFF, 보관 기간, 정리 전 확인. 기본 OFF + 확인 ON.

구현: `compact()` 함수 — 앱 구현 시점에 `engine/db.py` 또는 `engine/save.py`에 추가. 현재 엔진에는 미구현.

---

## 직전 맥락 / 메타 대화

### 직전 맥락

**세션리스 아키텍처** — `_preprocess`에 직전 대화 context를 주입하지 않는다. 지시어 치환이 실패하면 `unresolved_tokens`에 기록하고 `/review`에서 사용자가 해소한다.

### 메타 대화 패턴

"계속해", "아까 말한 거" 등은 규칙 기반 감지로 시간·턴 범위 필터를 만들어 `sentences` + `node_mentions` 쿼리로 처리.

| 패턴 | 조회 범위 |
|------|-----------|
| "계속해", "자세하게", "다시 해줘" | 직전 1~2턴 |
| "아까 말한 거", "방금 그거" | 최근 수분~1시간 |
| "오전에 얘기한 거", "어제 그거" | 시간 범위 필터 |

### 과거 대화 검색

| 검색 방식 | 예시 |
|-----------|------|
| 키워드 (노드/별칭) | "허리 관련 대화" → 노드 → `node_mentions` → `sentences` |
| 시간 | "어제 대화" → `created_at` 필터 |
| 카테고리 | "건강 관련" → 해당 카테고리 노드 → mentions |
| 복합 | "지난달 병원 관련" → 시간 + 노드 교차 |

---

## 모델 & 서버

**서버**: MLX 서버 (localhost:8765, `api/mlx_server.py`) — OpenAI 호환 API

**베이스 모델**: `unsloth/gemma-4-E2B-it-UD-MLX-4bit`
- Google Gemma 4 2B (Early Access)
- MLX 4bit 양자화, 로컬 실행 (~3.6GB)
- 컨텍스트 윈도우: 양자화 32K / 원본 128K

```
앱 → HTTP → MLX 서버 (localhost:8765) → gemma4:e2b (태스크별 어댑터)
```

---

## 어댑터 구성

| 엔드포인트 (model) | 태스크 | 상태 |
|--------------------|--------|------|
| `synapse/retrieve-filter` | 인출 관련성 판단 (pass/reject). 입력 단위를 트리플 → sentence로 변경 | 재학습 예정 |
| `synapse/retrieve-expand` | 질문 → 노드 후보 키워드 확장 | 완료 |
| `synapse/save-pronoun` | 지시어·시간부사·부정부사 치환. `tokens` + `unresolved` 분리 반환 | 재학습 예정 |
| `synapse/extract` | nodes + retention + deactivate (edges·category 폐기) | **재학습 필요 — edges 제거** |
| `synapse/structure-suggest` **[신규]** | 평문 → 마크다운 구조화 초안 | 초기 base 모델 |
| `synapse/chat` | 응답 생성, `/review` LLM 섹션의 관계·카테고리·별칭 옵션 제시 | 베이스 모델 |

> 재학습은 별도 WI. 이 PLAN에서는 엔진 레벨 필터로 기존 어댑터의 edges·LLM category 출력을 무시.

---

## LLM 설정값

| 단계 | 어댑터 | temperature | max_tokens |
|------|--------|-------------|------------|
| 전처리 치환 | synapse/save-pronoun | 0 | 256 |
| 노드/retention/deactivate 추출 | synapse/extract | 0 | 32768 |
| 평문 → 마크다운 구조 제안 | synapse/structure-suggest | 0 | 1024 |
| 인출 확장 | synapse/retrieve-expand | 0 | 256 |
| 인출 필터 | synapse/retrieve-filter | 0 | 8 |
| /review LLM 섹션 (관계·카테고리·별칭 옵션) | synapse/chat (base) | 0 | 256 |
| 응답 생성 | synapse/chat (base) | 0.3 | 4096 |

---

## 독립 동작 (`--no-llm`)

시냅스는 LLM 없이도 기본 동작을 보장한다.

- 저장: `_preprocess` 규칙 기반 감지만 동작 (날짜 정규식, 부정부사 정규식). 지시어 치환이 불가하면 `unresolved_tokens`에 기록
- 인출: `retrieve-expand`·`retrieve-filter` 생략하고 키워드 정확 매칭 + BFS만
- `/review`: 규칙 기반 섹션(`unresolved`, `uncategorized`, `suspected_typos`, `cooccur_pairs`, `stale_nodes`, `daily`, `gaps`)만 반환. LLM 의존 섹션(`alias_suggestions`)은 빈 결과

---

## assistant 응답 그래프화 (미래)

현재: `role='assistant'` sentences에만 저장. 그래프 추출 안 함.
이유: 2B 로컬 모델 응답이 사용자 말 되풀이 수준. 그래프화 가치 < 부하 증가.

**재검토 조건:**
- 모델 품질 향상 (응답에 새로운 인사이트/분석 포함)
- 도구 확장으로 외부 데이터 수집 시

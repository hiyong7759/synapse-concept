# Synapse 설계 — 저장/인출/대화 파이프라인

## 근본 목표

> **저장은 자동, 출처는 기록한다.** 카테고리·별칭은 전부 자동 저장하되 `origin` 컬럼으로 `user` / `ai` / `system` / `external` 출처를 식별한다. 사용자는 `/review`에서 AI·시스템 생성물을 훑어보고 잘못된 것을 즉시 삭제할 수 있다. 노드 간 연결은 별도 엣지 테이블이 아니라 sentence·category·alias 세 종류의 **하이퍼엣지**(지식 바구니)로 표현된다.

---

## DB 스키마

```sql
posts:                  id, kind('note'|'synapse'|'insight'), title, source, created_at, updated_at
sentences:              id, post_id NOT NULL, position, text, role('user'|'assistant'), origin(NULL|'user'|'insight'), created_at, updated_at
nodes:                  id, name, created_at, updated_at
node_sentence_mentions: node_id, sentence_id, origin('user'|'ai'|'system'|'external'), created_at  — PK(node_id, sentence_id)
categories:             id, name, parent_id, created_at                                            — UNIQUE(parent_id, name), INDEX(parent_id)
sentence_categories:    sentence_id, category_id, origin('user'|'ai'|'system'|'external'), created_at  — PK(sentence_id, category_id)
node_category_mentions: node_id, category_id, origin('user'|'ai'|'system'|'external'), created_at      — PK(node_id, category_id)
aliases:                alias TEXT PRIMARY KEY, node_id, origin('user'|'ai'|'system'|'external'), created_at
unresolved_tokens:      sentence_id, token, created_at                                             — PK(sentence_id, token)
```

전체 정의·설계 결정은 `docs/DESIGN_HYPERGRAPH.md`.

**핵심 원칙:** `sentence_categories` / `node_category_mentions` / `aliases` 는 **자동 저장**되며 `origin` 컬럼으로 출처가 식별된다 (`categories` 마스터는 origin 없음 — 삭제 경로 부재). 유일한 승인 대기 예외는 `unresolved_tokens` — 저장 시점에만 감지되는 일회성 이벤트라 재생성 불가. **엣지 테이블 없음** — 노드 간 연결은 sentence 공출현·category 공유·alias 묶음이라는 세 종류의 하이퍼엣지로만 표현.

**origin 값:**
- `user` — 사용자 직접 입력 (마크다운 heading, 수동 등록)
- `ai` — LLM 추론 (카테고리 분류 워커. 베이스 모델 + 시스템 프롬프트)
- `system` — 결정론적 엔진 규칙 (Kiwi lemma 정규화, 날짜 분할, 부정부사 감지, doc_mode 계층 카테고리, 인칭대명사 별칭 시드)
- `external` — 외부 API (Wikidata altLabel로 가져온 별칭)
- `insight` — (`sentences.origin` 전용) 사용자 승격 통찰 본체. 본문 편집 불가

**node_sentence_mentions**: 문장 하이퍼엣지의 멤버십. 모든 노드에 동일 적용되는 노드↔문장 역참조. 시간·장소·부정 같은 특수 노드도 별도 취급 없이 여기만 참조한다.

**의미 관계(cause/avoid/similar 등)**: 별도 테이블로 저장하지 않는다. `sentences.text` 원문에 이미 담겨 있고, 해석은 외부 지능체(원칙 11) 몫.

**sentences.role**: `user`(하이퍼그래프 추출 대상) / `assistant`(대화 기록).

모든 sentence 는 동등하게 영구 보관한다. "무효화" 는 사용자가 `update_sentence` / `delete_sentence` 로 직접 처리. 시점 해석은 인출 LLM 이 `created_at` 순으로 읽고 최근 사실을 우선 반영.

---

## 자동 저장 파이프라인

모든 하이퍼그래프 변경은 **자동 저장**된다. `sentence_categories`(사용자 heading 계층 문장 매핑) · `node_category_mentions`(노드 ↔ 카테고리 단일 매핑) · `aliases` 모두 저장 시점에 `origin`을 부여받아 즉시 DB에 들어간다. 사용자는 `/review`의 AI·규칙 목록 뷰에서 잘못된 항목을 삭제할 수 있다. 유일한 예외는 `unresolved_tokens`(치환 실패 지시어) + 파괴적 작업(`merge_nodes`, 통찰 삭제)이다.

### 세션 그릇 (3 종)

**세션 그릇은 사용자 액션으로 결정**된다. 자동 판정 없음. `posts.kind` 에 그대로 저장.

| kind | 라우트 | 생성 시점 | save 파이프라인 (의미 처리) | 노드 편입 | 용도 |
|---|---|---|---|---|---|
| **note** | `/note` | 사용자가 `/note` 화면에서 입력 시 자동 생성 | save-pronoun ✓, 메타 필터 (자유문장·list 한정), `parse_markdown` heading 경로 상속, Kiwi 노드 추출 | ✓ | **모든 지식 축적** (한 줄 메모도 긴 마크다운도) |
| **synapse** | `/synapse` | 사용자가 `/synapse` 화면에서 질문 시 자동 생성 | retrieve 후 답 생성, 질문·답 sentence 로 기록 | **✗ (역사만)** | 인출·융합 세션 |
| **insight** | 승격 전용 | 시냅스 세션 메시지의 사용자 [⬆ 승격] 클릭 | 시냅스 세션의 retrieve 캐시 노드 전부와 `node_sentence_mentions` 일괄 INSERT | ✓ (허브) | 사용자 승격 통찰 1 본체 |

사용자는 입력 형식(평문 vs heading + list)을 인지·선택하지 않는다. 입력 형식 차이는 **LLM 의미 처리 단계가 흡수** — `parse_markdown` 이 heading 있으면 카테고리 등록, 없으면 free 처리. 사용자에겐 단일 입력 영역으로 보임. save-pronoun, 메타 필터, Kiwi 추출은 단일 경로로 일관 적용.

**`synapse`** — 저장이 아니라 **인출·조합** 이므로 파이프라인이 다르게 탄다. 질문·답은 `sentences` 에 `role='user'`/`'assistant'` 로 기록되지만 `node_sentence_mentions` 편입 없음 (원칙 15-1).

**`insight`** — 시냅스 세션 메시지의 사용자 승격으로만 생성. 본체 1 sentence, 시냅스 세션의 retrieve 캐시 노드 전부와 자동 허브 연결 (Hebbian — 원칙 15-2).

전체 명세는 **`docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md`**.

### 자동저장 vs 의미 처리 — 두 층 분리

`/note` 의 저장은 **두 층** 으로 갈라진다. 모바일 배터리·발열을 보호하면서 LLM 정정의 가치는 살리기 위함.

| 동작 | 트리거 | 갱신 대상 | LLM | 응답 시간 | 모바일 부담 |
|---|---|---|---|---|---|
| **자동저장** | 입력 1.5초 디바운스 + 페이지 이탈 (`pagehide`/`visibilitychange`) | `posts.source` 만 | ❌ | <50ms | 거의 없음 |
| **의미 처리** | 사용자 명시 트리거 (⌘S / "정리" 버튼 / 재진입 시 제안) | `sentences` 재계산 + Kiwi 노드 + `node_sentence_mentions` + LLM 정정 후보 | ✅ | 0.5~3초 (인프로세스 llamadart / Python frozen 의 MLX HTTP) | 사용자 자발적 호출만 |

**자동저장**은 "사용자가 친 원문 손실 방지" 단일 목적. SQL UPDATE 한 줄. 페이지 이탈 시 마지막 변경분 백업.

**의미 처리** 호출 흐름 (`POST /posts/{id}/process` 또는 `SynapseFlow.noteProcess`):
1. `posts.source` UPDATE (자동저장 미발화분 함께 flush)
2. 기존 `sentences` 모두 DELETE (post_id CASCADE)
3. `parse_markdown(source)` → heading / key_value / list / free 분기
4. 단일 경로 파이프라인 ① save-pronoun → ② ISO 날짜 정규화 → ③ unresolved 감지 → ④ sentence INSERT → ⑤ Kiwi 노드 추출 → ⑥ 날짜 분할 → ⑦ `node_sentence_mentions` + `sentence_categories`
5. **LLM 정정 후보 생성** — 본문 토큰 중 `aliases` 미등록 + 자모 거리 1~2 의심 쌍을 LLM 에 검증 요청 → 후보 목록 반환 (적용 안 함)
6. 응답에 `correction_candidates: [{from, to, confidence, reason}]` 포함

**LLM 정정 후보 정책**:
- **별칭 보호**: `aliases` 등록된 토큰(`스벅` 등) 은 후보에서 제외. 사용자 의도 정감 보존
- **자모 거리 사전 필터**: 클라이언트가 의심 쌍 1차 추림 → LLM 부담 감소
- **변경분만**: 직전 의미 처리 이후 새로 등장한 토큰만 검증
- **결과 캐싱**: `(토큰, 주변 5단어)` 키 — 같은 의심 쌍 재호출 안 함
- **자동 적용 금지**: 사용자가 카드의 [적용] 클릭 시에만 source/sentences 갱신 + alias 등록

저장 시점에 모델/규칙이 구조를 판정하지 않는다. 평문은 평문대로 저장하는 것이 원칙 4·원칙 9 와 일치.

### 마크다운 입력 예시

```markdown
# 더나은
## 개발팀
- 팀장:: 박지수
- 프론트엔드 김민수
오늘 회의가 세 개 연속이었다.
```

- heading 경로(`더나은.개발팀`) → `categories` 재귀 upsert + `sentence_categories`(heading 말단, origin='user')
- `- 팀장:: 박지수` → key_value 로 파싱, sentence 통째 저장(`text="팀장:: 박지수"`), save-pronoun skip
- `- 프론트엔드 김민수` → list, 일반 sentence
- 자유 문장 → free, 메타 필터 대상

### 의미 처리 파이프라인 (단일 경로 · Kiwi-first)

> 아래 흐름은 `/note` 의 **의미 처리** 트리거 시점 기준. 단일 경로 — `parse_markdown` 이 heading / key_value / list / free 를 자동 분기. heading 이 있으면 카테고리 경로 등록, 없으면 free 처리.

```
사용자 명시 트리거 (⌘S / "정리" 버튼)
  ↓ POST /posts/{id}/process { source: "<최신 source>" }
  ↓ posts.source UPDATE (자동저장 미발화분 함께 flush)
  ↓ 기존 sentences DELETE (post_id CASCADE 로 mentions·sentence_categories 동반)
  ↓ parse_markdown(source) — heading/list/key_value/free 분리
  ↓
  [메타 필터 — 게시물 단위 1회]
    자유 문장·list 만 대상 (heading·key_value 제외 — 메타 대화 가능성 없음)
    (b) 규칙 사전필터: Kiwi 명사 0개 + '?' 종결 → 즉시 메타 확정
    (a) 나머지 줄을 한 번에 LLM 배치 호출
        프롬프트: docs/META_FILTER_SYSTEMPROMPT.md
        temp=0, max_tokens=2048
        출력: {"meta": [idx, ...]}  — 저장 제외할 줄 idx
    로컬 LLM 사용 불가 시 → 필터 skip (모든 문장 저장 진행, 과포함은 UI 삭제로 해소)
  ↓
문장별로 (메타 idx 제외, kind 별 분기):
  ↓
  ① [save-pronoun — 베이스 모델]  temp=0, max_tokens=256     ← list/free 만 호출 (heading/key_value skip)
      프롬프트: docs/SAVE_PRONOUN_SYSTEMPROMPT.md
      세션리스 — 직전 대화 context 주입 없음
      모호 케이스(`{"question": "..."}` 반환) → 저장 중단
      실패·로컬 LLM 사용 불가 시 → 원문 그대로 진행 (skip)
  ↓
  ② [규칙 — ISO 날짜 → 한국어 정규화]
      '2026-04-18' → '2026년 4월 18일'
      이 단계 이후 본문은 항상 한국어 표기
  ↓
  ③ [규칙 — unresolved 감지]
      지시대명사/지시부사/시간 모호 부사/장소부사 정규식 스캔
      매칭된 토큰 → (sentence_id, token) 로 unresolved_tokens INSERT
  ↓
  ④ sentences INSERT (정규화된 text, role='user', post_id, position)
  ↓
  ⑤ [Kiwi 형태소 분석 — 저장 기본 경로]
      서버(조직): kiwipiepy (C++ 네이티브)
      모바일·데스크톱·웹(개인): kiwi-nlp (WASM)
      추출: NNG/NNP/NP 명사 + VV/VA lemma + MAG(안/못)
      원칙 2 적용:
        · 한국어 용언 → lemma 로 정규화 ("아파서/아프" → "아프")
        · 외래어·복합명사 → Kiwi 가 쪼갠 조각 그대로 수용
          ("React Native" → "React", "Native" 두 노드. 같은 sentence 공출현으로 연결 창발)
  ↓
  ⑥ [규칙 — 날짜 노드 분할]
      '2026년 4월 18일' → ['2026년', '4월', '18일'] 노드 후보 추가
      한 sentence 안의 모든 단위(년·월·일) 같은 sentence_id 에 mention 연결
      식별 조건: '년/월/일' 키워드 또는 ISO 구분자 '-' 있을 때만
      분할된 날짜 노드는 node_category_mentions 에 시드 카테고리 (TIM.year/TIM.month/TIM.day) id 로 origin='system' 자동 등록 (결정론적 예외)
  ⑦ DB 저장 (동기 — 즉시 반영):
      nodes upsert — 같은 이름은 기존 id 재사용
      node_sentence_mentions INSERT OR IGNORE (node_id, sentence_id)

      [사용자 heading 계층]
      categories upsert — heading path segments 재귀 upsert (parent_id 체인)
        예: ["더나은","개발팀"] → (더나은, NULL) · (개발팀, id_더나은)
      sentence_categories INSERT — 동기 origin 처리:
        · heading 말단 카테고리만 문장에 연결
        · 사용자 명시 heading → origin='user'
        · 규칙 분류(doc_mode 계층 등) → origin='system'
        · 문장 단위 매핑이므로 Kiwi 노드 전체에 경로 부여하던 과포함 문제 해소

      [노드 ↔ 카테고리 단일 매핑]
      node_category_mentions — 저장 시점 동기 처리:
        · Kiwi heading 토큰화 결과 자동 매핑 (heading 노드 id 기준, origin='system')
        · 결정론적 규칙(날짜 TIM.* 자동 태깅 등) origin='system' 동기 INSERT
        · 19 대분류 시드 카테고리 AI 추론은 백그라운드 CATEGORY 워커 (origin='ai')

      aliases INSERT — 동기 origin 처리:
        · 사용자 수동 등록 → origin='user'
        · 인칭대명사 시드 → origin='system'
        · Wikidata 추천은 여기서 생성하지 않음 → 백그라운드 워커로 이전
  ↓
  commit + 훅 발화 → 백그라운드 워커 체인 트리거 (아래 "백그라운드 워커" 섹션)
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

### 자동 저장되지 않는 것 (승인 유지)

다음은 저장 파이프라인에서 자동 처리하지 않는다 — `/review` 승인 흐름을 거침:

- **`unresolved_tokens` 해소** — 치환 실패 지시어. 사용자 옵션 선택 후 `nodes`/`node_sentence_mentions` 로 편입.
- **노드 병합 (`merge_nodes`)** — 되돌릴 수 없는 파괴적 작업. `suspected_typos` 도출기에서 후보 제시 → 사용자 승인.
- **노드 아카이브** — 사용자가 모르게 삭제되면 복구 불가이므로 `stale_nodes` 승인 유지. 물리 DELETE.
- **통찰 삭제** — `kind='insight'` post 삭제. 시냅스 세션에서 축적된 허브 연결 전체 CASCADE 사라지므로 파괴적, 승인 필수.
- **자동 오타 교정으로 노드 이름 변경 금지** — "언급된 것만 존재" 원칙 위배. 오타는 `suspected_typos`로 후보만 제시.

### 자동 시드 예외

- `_FIRST_PERSON_ALIASES` — 인칭대명사 11개는 origin='system'로 자동 시드 (모든 사용자 공통).

---

## 백그라운드 워커

저장 파이프라인은 노드·문장 저장까지만 동기로 수행한다. **카테고리 분류**와 **별칭 생성**은 별도 백그라운드 워커가 처리한다. 목적: UI 응답 속도 확보 + LLM/외부 API 비용을 저장 흐름에서 분리.

### 트리거

문장 저장이 완료되는 즉시(같은 트랜잭션 커밋 직후) **저장 완료 이벤트**를 발행한다. 워커는 이 이벤트를 큐에 쌓고 순차 처리.

```
[저장 파이프라인 끝]
  → POST 응답 즉시 반환 (UI는 "기록했어요" 표시)
  → 이벤트 큐잉: {sentence_id, new_node_ids: [...]}
        ↓
[카테고리 분류 워커]  new_node_ids 중 category 미보유 노드 대상
[Wikidata 별칭 워커]  new_node_ids 중 별칭 미보유 노드 대상
```

같은 노드가 여러 번 언급되면 이미 처리된 것은 스킵 (`node_category_mentions` / `aliases` 에 이미 있는지 확인).

### 실행 리소스 관리

리소스 여유 없으면 큐에 쌓아두고 유휴 시간에 처리:

- **동시 실행 제한**: 워커 최대 N개 병렬 (기본 2)
- **리소스 체크**: CPU/메모리/로컬 LLM 사용 여부 확인. 임계치 초과 시 지연
- **백오프**: 외부 API 실패 시 exponential backoff, 반복 실패는 해당 노드 skip 표시

### 워커 ①: 카테고리 분류 워커 (19 대분류 시드 매핑)

**어댑터 미사용** — 베이스 모델(gemma4:e2b)에 `docs/CATEGORY_SYSTEMPROMPT.md`를 시스템 프롬프트로 주입해서 19 대분류 코드로 분류.

```
입력: 노드명 + 이 노드가 언급된 최근 문장들 (상위 N건)
출력: {"categories": ["BOD.disease", ...]}  (빈 배열이면 분류 불가)
        ↓
각 코드를 categories 시드 루트의 id 로 역매핑:
  node_category_mentions INSERT (node_id, category_id, origin='ai')
        ↓
실패 / 빈 결과 → 아무것도 저장하지 않음 (나중에 재처리 대상으로 남음)
```

- 대상: `node_category_mentions` 의 시드 카테고리 매핑. heading 카테고리 매핑은 저장 파이프라인이 Kiwi 토큰화로 이미 채움 — 워커는 시드 카테고리만 보완.
- `sentence_categories` 는 저장 파이프라인이 heading path 로 채우며 워커는 건드리지 않음.
- 입력에 포함할 문장 선택: `node_sentence_mentions` JOIN `sentences` ORDER BY `created_at` DESC LIMIT N.
- 프롬프트 출력의 `"categories"` 필드값은 19 대분류 코드. 애플리케이션에서 `categories` 시드 루트 id 로 역매핑 후 저장.
- 이미 user/system origin 매핑이 있는 노드도 대상 (AI 분류는 보완적으로 함께 쌓임).

### 워커 ②: Wikidata 별칭 워커

**LLM 미사용** — 외부 지식베이스의 altLabel(다국어 별칭)을 그대로 가져옴.

```
입력: 노드명
        ↓
Wikidata API 호출:
  - search: ?action=wbsearchentities&search=<노드명>&language=ko
  - fetch:  ?action=wbgetentities&ids=<Q번호>&props=aliases&languages=ko|en
        ↓
altLabel 목록 (ko, en 언어)
        ↓
각 별칭마다:
  aliases INSERT OR IGNORE (alias, node_id, origin='external')
        ↓
실패 / 매칭 없음 → 스킵 (재시도 대상으로 큐에 남기거나 skip 플래그)
```

- 한국어 + 영어 altLabel만 사용 (다국어 확장은 추후).
- 같은 Wikidata 엔티티가 다른 노드 여러 개에 매핑될 수 있음 (동명이인 주의) → 사용자가 `/review`의 `external_generated` 뷰에서 잘못된 매핑 제거.
- rate limit: Wikidata 무료 API 표준 준수 + 로컬 캐시(동일 노드명은 중복 호출 안 함).

### 구현 방식 (실행 단위)

환경마다 비동기 실행 메커니즘이 다르지만 동작은 동일:

| 환경 | 메커니즘 | 동시 제한 |
|---|---|---|
| Python frozen (서버·dogfood) | `asyncio.create_task` + `asyncio.Semaphore` | 워커별 N=2 |
| Flutter 모바일·데스크톱 | Dart `Isolate` 또는 `compute()` + `Semaphore` 패키지 | 워커별 N=2 |

핵심은 "저장 트랜잭션 커밋 직후 이벤트 발행 → 큐잉 → 백그라운드에서 순차/병렬 처리" 의 패턴이며, 외부 큐 브로커는 불필요.

- 앱 재시작 시 미완료 작업은 다음 언급 때 자연 재시도 (`node_category_mentions`/`aliases` 테이블에 없으면 다시 대상).
- 수동 재실행 경로도 제공: `/review` 에서 "지금 다시 분류" 버튼 (선택적).

### `--no-llm` 모드 대응

- 카테고리 분류 워커: LLM 호출 불가 → 아예 실행 안 됨. `origin='system'`(Kiwi 자동 매핑·날짜 분할 등)·`'user'` 매핑만 DB 에 쌓임.
- Wikidata 별칭 워커: LLM과 무관하게 동작. 인터넷 없으면 스킵.
- 저장 파이프라인: 메타 필터 skip(모든 문장 저장 진행), save-pronoun skip(원문 그대로). Kiwi 경로는 LLM 과 무관하게 항상 동작.

---

## 인출 파이프라인

```
질문
  ↓ [synapse/retrieve-expand 어댑터]  temperature=0, max_tokens=256
    질문 의도 해석 → 노드 후보 키워드
  ↓ [Kiwi 명사·용언 추출]
    질문 → NNG/NNP/NP 명사 + VV/VA lemma 로 후보 보강
    "커피가 맛있었나?" → ['커피', '맛', '맛있'] 후보 추가
    → 조사·어미 붙은 표현도 매칭 가능, 어댑터 실패 시 폴백 역할
    keywords = retrieve-expand 결과 ∪ Kiwi 결과
  ↓ [DB 매칭]
    aliases 정확 매칭 우선 → name 정확 매칭 → name substring 매칭
  ↓ [BFS 루프]  max_layers=5
    현재 노드·카테고리 집합마다 세 경로를 합쳐 다음 레이어 구성:
      ① 문장 바구니 (node_sentence_mentions JOIN sentences) → 같은 sentence에 함께 언급된 노드
      ② 카테고리 공유 (node_category_mentions JOIN node_category_mentions) → 같은 시드 카테고리 + 인접 맵 한 홉
      ③ 사용자 heading 계층 (categories 재귀 CTE + sentence_categories)
         → 질의 키워드가 사용자 categories 와 매칭되면 서브트리 전체를 시드 sentence 로 수집
    [synapse/retrieve-filter]  temperature=0, max_tokens=8
      ①은 sentence 단위로, ②·③은 카테고리 경로 + 대표 sentence로
      관련성 판단 (pass/reject). 불확실하면 pass
    통과한 항목의 새 노드·카테고리 → 다음 레이어
    모든 경로에서 새 항목 없으면 종료
  ↓ [시간 순 정렬]
    통과한 sentence 들을 sentences.created_at 오름차순으로 정렬.
    각 줄 앞에 `[YYYY-MM-DD]` 날짜 힌트를 붙여 LLM 프롬프트 컨텍스트 구성.
  ↓ [synapse-answer]  temperature=0.3, max_tokens=4096
    인출 sentences를 컨텍스트로 자연어 답변.
    프롬프트 규칙: "충돌 시 최근 사실 우선", "'지금 어때?' 는 최신 기록 근거",
    "과거 사실도 유지 — 시점 구분해 설명".
    답변 → sentences INSERT (role='assistant')
```

### 세 경로의 역할 구분

| 경로 | 데이터 출처 | 의미 |
|------|-------------|------|
| ① 문장 바구니 (`node_sentence_mentions`) | 자동 저장 (사용자가 같은 게시물·문장에 함께 언급) | "함께 등장한 사실" |
| ② 카테고리 공유 (`node_category_mentions` + 인접 맵) | CATEGORY 워커 분류 + Kiwi heading 토큰화 + 규칙 시드 + 인접 맵 | "같은 주제군으로 묶인 개념" |
| ③ 사용자 heading 계층 (`categories` + `sentence_categories`) | 사용자 명시 heading path (adjacency list) | "사용자가 정한 계층 바구니" |

①은 공출현한 사실 덩어리, ②는 의미 기반 확장, ③은 사용자 계층 기반 확장(서브트리 스캔). 셋 모두 인출에 기여하며 답변 컨텍스트에서는 모두 sentence 원문으로 표시된다 ("- 허리디스크 진단"). 인과·유사·회피 같은 의미 해석은 외부 지능체가 sentence 원문을 읽고 수행한다 (원칙 11).

### 모든 노드는 같은 경로로 조회된다

날짜·시간부사·부정부사·장소 같은 토큰도 일반 명사 노드와 **같은 세 경로**(문장 바구니 + 카테고리 공유 + 사용자 heading)를 거친다.

- "2026-04-17에 뭐 있었지?" → `2026-04-17` 노드 → `node_sentence_mentions` → sentences → 함께 언급된 노드
- "안 먹은 약" → `안` 노드 → mentions → sentence → 함께 언급된 약 노드
- "허리디스크의 원인" → `허리디스크` 노드 → ① 문장 바구니 + ② `BOD.disease` 시드 카테고리 공유 → 외부 지능체가 원문에서 인과 해석
- "더나은 전체 보여줘" → `더나은` 이 `categories` 루트로 매칭 → 재귀 CTE 서브트리 수집 → `sentence_categories` JOIN 으로 문장 전체 조회 (③ 경로)

특수 카테고리(TIM/NEG 등)나 특수 경로 없음.

---

## /review — 검토 편입

자동 저장 체계에서 `/review`는 세 가지 역할만 담는다: (1) `unresolved_tokens` 해소, (2) AI·규칙 생성물 검수 뷰, (3) 파괴적 작업 승인.

상세(섹션별 도출기, API, 프론트 구조) → **`docs/DESIGN_REVIEW.md`**

### 요약

| 섹션 | 데이터 소스 | 역할 |
|------|-------------|------|
| `unresolved` | `unresolved_tokens` | 승인 대기 해소 |
| `ai_generated` | `node_category_mentions WHERE origin='ai'` · `sentence_categories WHERE origin='ai'` (있으면) | 검수 뷰 (유지/삭제) |
| `external_generated` | `aliases WHERE origin='external'` | Wikidata 별칭 검수 뷰 |
| `system_generated` | `node_category_mentions`·`sentence_categories`·`aliases` 중 `origin='system'` | 검수 뷰 (규칙 오류 추적) |
| `suspected_typos` | `find_suspected_typos` | 병합 승인 (파괴적) |
| `stale_nodes` | `nodes.updated_at` | 아카이브 승인 |
| `insight_delete` | `posts WHERE kind='insight'` | 통찰 삭제 승인 (파괴적) |
| `daily` / `gaps` | `sentences.created_at` | 정보 뷰 |

---

## 문장 관리

### 문장 수정 (`update_sentence`)

```
sentence_id + new_text
  → sentences.text UPDATE
  → 해당 sentence_id 연관 node_sentence_mentions DELETE → 고아 노드 보존
  → new_text 재분석 → 새 node_sentence_mentions INSERT (동일 sentence_id 재사용)
```

`origin='insight'` sentence 는 거부 (편집 불가).

### 문장 삭제 (`delete_sentence`)

```
sentence_id
  → node_sentence_mentions CASCADE DELETE
  → 고아 노드는 보존 (재연결 가능성)
  → sentences 삭제
```

---

## 직전 맥락 / 메타 대화

### 직전 맥락

**세션리스 아키텍처** — `_preprocess`에 직전 대화 context를 주입하지 않는다. 지시어 치환이 실패하면 `unresolved_tokens`에 기록하고 `/review`에서 사용자가 해소한다.

### 메타 대화 패턴

"계속해", "아까 말한 거" 등은 규칙 기반 감지로 시간·턴 범위 필터를 만들어 `sentences` + `node_sentence_mentions` 쿼리로 처리.

| 패턴 | 조회 범위 |
|------|-----------|
| "계속해", "자세하게", "다시 해줘" | 직전 1~2턴 |
| "아까 말한 거", "방금 그거" | 최근 수분~1시간 |
| "오전에 얘기한 거", "어제 그거" | 시간 범위 필터 |

### 과거 대화 검색

| 검색 방식 | 예시 |
|-----------|------|
| 키워드 (노드/별칭) | "허리 관련 대화" → 노드 → `node_sentence_mentions` → `sentences` |
| 시간 | "어제 대화" → `created_at` 필터 |
| 카테고리 공유 | "건강 관련" → `BOD.*` 시드 카테고리 노드 → `node_category_mentions` 역조회 → 노드 → mentions |
| 사용자 heading 계층 | "더나은 전체" → `categories` 재귀 CTE → `sentence_categories` → sentences |
| 복합 | "지난달 병원 관련" → 시간 + 노드 교차 |

---

## 모델 & 런타임 (환경별)

| 환경 | 런타임 | 베이스 모델 | 호출 방식 |
|---|---|---|---|
| **모바일·데스크톱** (프로덕션) | `llamadart` (llama.cpp 바인딩) — `synapse_engine` 패키지 내부 | Gemma 4 E2B-it Q4_K_M GGUF (~3.1GB, 앱 번들) | **인프로세스 직접 호출** (HTTP 없음, 레이턴시 0) |
| **Python frozen** (서버·dogfood·학습 검증) | MLX 서버 (`api/mlx_server.py`, OpenAI 호환) | `unsloth/gemma-4-E2B-it-UD-MLX-4bit` (~3.6GB) | HTTP `localhost:8765` |

베이스 모델은 동일한 Google Gemma 4 2B (Early Access). 양자화·런타임만 환경별로 갈라진다. 컨텍스트 윈도우: 양자화 32K / 원본 128K.

```
모바일·데스크톱: 앱 → llamadart (인프로세스) → gemma-4-E2B-it 4bit GGUF (± 태스크 어댑터)
Python frozen:   앱 → HTTP → MLX 서버 (localhost:8765) → gemma-4-E2B-it MLX 4bit (± 태스크 어댑터)
```

런타임이 갈라져도 **시스템 프롬프트·태스크 분담·output 포맷은 동일** — 같은 `docs/*_SYSTEMPROMPT.md` 가 양 환경 공통.

---

## Gemma 4 thinking 모드 OFF (전역 설정)

모든 LLM 호출은 `tokenizer.apply_chat_template(..., enable_thinking=False)` 로 thinking 블록을 차단한다.

- **이유**: 학습 데이터 system 메시지에 `<|think|>` 토큰이 없어 thinking 없이 학습됐고, ON 상태에서는 추론 시간이 약 10배 길어지며 한 단어 출력 태스크에서 오답률이 급증한다.
- **적용 위치**:
  - Python frozen: `api/mlx_server.py` 의 `apply_chat_template` 호출, `scripts/mlx/eval_*.py`
  - 모바일·데스크톱: `synapse_engine` 의 `LlamadartBackend.chat()` 내부 — 챗 템플릿 빌드 시 thinking 블록 차단 동등 구현
- **주의**: Gemma 4 4bit (E2B/E4B) 변종은 OFF 설정 시 빈 thought 블록도 출력하지 않음.

---

## 태스크 처리 방식

베이스 모델 + 시스템 프롬프트로 충분한 태스크는 어댑터 없이, 규칙 추출·패턴 매칭이 필수적인 태스크만 파인튜닝 어댑터로 운영.

| 태스크 | 처리 방식 | 프롬프트 파일 / 어댑터 경로 |
|--------|-----------|------|
| meta-filter | 베이스 모델 | `docs/META_FILTER_SYSTEMPROMPT.md` |
| save-pronoun | 베이스 모델 | `docs/SAVE_PRONOUN_SYSTEMPROMPT.md` |
| typo-normalize | 베이스 모델 | `docs/TYPO_NORMALIZE_SYSTEMPROMPT.md` — 별칭 보호 + 자모 거리 사전 필터 통과 토큰 검증 |
| retrieve-filter | 베이스 모델 | `docs/RETRIEVE_FILTER_SYSTEMPROMPT.md` |
| retrieve-expand | 어댑터 | `synapse/retrieve-expand` (모바일·데스크톱 번들 1 종) |
| category (백그라운드) | 베이스 모델 | `docs/CATEGORY_SYSTEMPROMPT.md` |
| synapse-answer | 베이스 모델 | `docs/SYNAPSE_ANSWER_SYSTEMPROMPT.md` |

시스템 프롬프트 파일 로더는 환경별로 갈라진다 — Python frozen: `engine/prompts.py` / Flutter: `synapse_engine` 의 `lib/src/llm/prompts/` assets 로더. 권한 판단(security-access 등)은 결정론적 백엔드 로직 소관이라 LLM 태스크에서 제외.

---

## LLM 설정값

| 단계 | 처리 방식 | temperature | max_tokens |
|------|-----------|-------------|------------|
| 메타 필터 (저장 진입부) | 베이스 + META_FILTER_SYSTEMPROMPT.md | 0 | 2048 |
| 전처리 치환 (save-pronoun) | 베이스 + SAVE_PRONOUN_SYSTEMPROMPT.md | 0 | 256 |
| 정정 후보 (typo-normalize) | 베이스 + TYPO_NORMALIZE_SYSTEMPROMPT.md | 0 | 256 |
| 카테고리 분류 (백그라운드) | 베이스 + CATEGORY_SYSTEMPROMPT.md | 0 | 512 |
| 인출 확장 (retrieve-expand) | synapse/retrieve-expand 어댑터 | 0 | 256 |
| 인출 필터 (retrieve-filter) | 베이스 + RETRIEVE_FILTER_SYSTEMPROMPT.md | 0 | 8 |
| 시냅스 답변 (synapse-answer) | 베이스 + SYNAPSE_ANSWER_SYSTEMPROMPT.md | 0.3 | 4096 |

---

## 독립 동작 (`--no-llm`)

시냅스는 LLM 없이도 기본 동작을 보장한다 (원칙 11).

- 자동저장: 항상 동작 (sqflite UPDATE 한 줄, LLM 호출 없음)
- 의미 처리: Kiwi 형태소 분석으로 노드 추출 + 규칙 기반 날짜 분할·unresolved 감지. 메타 필터·save-pronoun·typo-normalize 는 skip. 평문 저장 자체는 완결됨 (정정 카드만 생성 안 됨)
- 백그라운드 워커: 카테고리 분류 워커는 LLM 호출 불가로 비활성 (`origin='ai'` 카테고리 발생 안 함). Wikidata 별칭 워커는 **인터넷만 있으면 동작** (LLM과 무관)
- 인출: `retrieve-expand`·`retrieve-filter` 생략하고 Kiwi 키워드 매칭 + BFS만
- `/review`: `unresolved`, `ai_generated`(빈 결과), `external_generated`, `system_generated`, `suspected_typos`, `stale_nodes`, `insight_delete`, `daily`, `gaps` 모두 쿼리만으로 동작

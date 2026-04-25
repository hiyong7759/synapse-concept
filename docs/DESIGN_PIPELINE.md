# Synapse 설계 — 저장/인출/대화 파이프라인

**최종 업데이트**: 2026-04-25 (v22 반영 — M3 에서 스키마 실 구현 완료. post 가 "세션 그릇" 으로 일반화. `kind ∈ {chat, markdown, synapse, insight}` 4 모드. `synapse` 인출·융합 모드는 질문·답을 역사로만 기록(노드 편입 안 함). `insight` 는 사용자 명시 승격 → 시냅스 세션 retrieve 캐시 노드 전부와 허브 연결. 선행 v21: PLAN-007 `node_mentions` → `node_sentence_mentions`, `node_categories` → `node_category_mentions` 통합. v20: PLAN-004 카테고리 재설계. v19: `posts.input_mode` 신설. v18: 상태 레이어 제거. v17: Kiwi-first + origin `rule→system`)

## 근본 목표

> **저장은 자동, 출처는 기록한다.** 카테고리·별칭은 전부 자동 저장하되 `origin` 컬럼으로 `user` / `ai` / `system` / `external` 출처를 식별한다. 사용자는 `/review`에서 AI·시스템 생성물을 훑어보고 잘못된 것을 즉시 삭제할 수 있다. 노드 간 연결은 별도 엣지 테이블이 아니라 sentence·category·alias 세 종류의 **하이퍼엣지**(지식 바구니)로 표현된다.

---

## DB 스키마 (v22)

```sql
posts:                  id, kind('chat'|'markdown'|'synapse'|'insight'), title, source, created_at, updated_at
sentences:              id, post_id NOT NULL, position, text, role('user'|'assistant'), origin(NULL|'user'|'insight'), created_at, updated_at
nodes:                  id, name, created_at, updated_at
node_sentence_mentions: node_id, sentence_id, origin('user'|'ai'|'system'|'external'), created_at  — PK(node_id, sentence_id)
categories:             id, name, parent_id, created_at                                            — UNIQUE(parent_id, name), INDEX(parent_id)
sentence_categories:    sentence_id, category_id, origin('user'|'ai'|'system'|'external'), created_at  — PK(sentence_id, category_id)
node_category_mentions: node_id, category_id, origin('user'|'ai'|'system'|'external'), created_at     — v21 통합, PK(node_id, category_id)
aliases:                alias TEXT PRIMARY KEY, node_id, origin('user'|'ai'|'system'|'external'), created_at
unresolved_tokens:      sentence_id, token, created_at                                             — PK(sentence_id, token)
```

**v22 변경점** (M3 에서 `engine/db.py` 실 구현 완료): post 를 "세션 그릇" 으로 일반화.
- **`posts.kind`** — `input_mode` 리네임 + 값 확장. 4 모드 (`chat`/`markdown`/`synapse`/`insight`).
- **`posts.title`** — 목록 표시용. 첫 행 자동, 사용자 편집 가능. NULL 허용.
- **`posts.source`** — `markdown` 리네임. 세션 전체 원본 누적 저장 (모드별 포맷 다름). NULL 허용.
- **`sentences.post_id NOT NULL`** — "미아 sentence 없음". assistant 응답도 그 대화 post 에 귀속.
- **`sentences.origin`** — 통찰 식별용. `NULL`/`'user'`/`'insight'`. `'insight'` 는 편집 불가 + retrieve 가중치 +.

**v21 변경점**: `node_mentions` → `node_sentence_mentions` 리네임, `node_categories` → `node_category_mentions` 통합 (축 A·B 흡수). `nodes.status` 폐기 (merge_nodes 물리 DELETE).

**v20 변경점**: 카테고리 재설계 — `categories` · `sentence_categories` 신설로 heading 계층 분리.

**v19 변경점(PLAN-003 M1)**: `posts.input_mode` 컬럼 신설. 저장 모드를 사용자 명시(UI 입력창 선택)로 기록 — `'chat'` / `'markdown'` 양자택일. 저장 파이프라인은 이 값을 보고 parse·save-pronoun·메타 필터 분기를 결정한다. 상세는 `docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md`.

**v18 변경점**: `sentences.status` 컬럼 제거. 모든 sentence 는 영구 기록이며, "이건 이제 아님" 은 원문 `update_sentence` / `delete_sentence` 로 처리한다. `extract-state` LLM 판정 단계 자체를 폐기해 저장 시점 해석을 없앴다 (원칙 7·8·10·11 정합). 시점 해석은 인출 LLM 의 `created_at` 기반 최근성 판단이 담당.

**핵심 원칙:** `sentence_categories` / `node_categories` / `aliases`는 **자동 저장**되며 `origin` 컬럼으로 출처가 식별된다(`categories` 마스터는 origin 없음 — 삭제 경로 부재). 유일한 승인 대기 예외는 `unresolved_tokens` — 저장 시점에만 감지되는 일회성 이벤트라 재생성 불가. **엣지 테이블(`edges`) 폐기(v15)** — 노드 간 연결은 sentence 공출현·category 공유·alias 묶음이라는 세 종류의 하이퍼엣지로만 표현.

**origin 값** (v17 에서 `rule` → `system` 으로 리네이밍):
- `user` — 사용자 직접 입력 (마크다운 heading, 수동 등록)
- `ai` — LLM 추론 (카테고리 분류 워커. 베이스 모델 + 시스템 프롬프트)
- `system` — 결정론적 엔진 규칙 (Kiwi lemma 정규화, 날짜 분할, 부정부사 감지, doc_mode 계층 카테고리, 인칭대명사 별칭 시드)
- `external` — 외부 API (Wikidata altLabel로 가져온 별칭)

**node_mentions**: 문장 하이퍼엣지의 멤버십. 모든 노드에 동일 적용되는 노드↔문장 역참조. 시간·장소·부정 같은 특수 노드도 별도 취급 없이 여기만 참조한다.

**의미 관계(cause/avoid/similar 등)**: 별도 테이블로 저장하지 않는다. `sentences.text` 원문에 이미 담겨 있고, 해석은 외부 지능체(원칙 11) 몫.

**sentences.role**: `user`(하이퍼그래프 추출 대상) / `assistant`(대화 기록).

**sentences.retention 폐기 (v13~)**: 모든 sentence는 동등하게 영구 보관한다. 과거 memory/daily 분류는 (1) 2B 어댑터의 "daily → 빈 nodes" 과적합 원인, (2) 오분류 시 중요 기억 소실 위험, (3) 실제 인출·검색에서 쓰이지 않음 — 세 가지 이유로 제거.

**sentences.status 폐기 (v18)**: 과거 v17 까지는 `extract-state` LLM 판정으로 `inactive` / `pending` 상태를 자동 부여했으나, 2026-04-21~23 실측(114쌍 골든셋)에서 3분류 F1=0.46, 이진 V1 F1=0.81 수준으로 **모델·사람 둘 다 헷갈리는 본질적 애매함** 확인 (과거 사건 25건 중 13건 오판, pending 남발 시 재현율 0.33). 구조 자체가 원칙 7·8·10·11 과 어긋나 전면 제거. 모든 sentence 는 항상 조회 대상이며, "무효화" 는 `update_sentence` / `delete_sentence` 로, 시점 해석은 인출 LLM 이 `created_at` 순으로 읽고 판단한다.

---

## 자동 저장 파이프라인

모든 하이퍼그래프 변경은 **자동 저장**된다. `sentence_categories`(사용자 heading 축) · `node_categories`(19 대분류 축) · `aliases` 모두 저장 시점에 `origin`을 부여받아 즉시 DB에 들어간다. 사용자는 `/review`의 AI·규칙 목록 뷰에서 잘못된 항목을 삭제할 수 있다. 유일한 예외는 `unresolved_tokens`(치환 실패 지시어) + 파괴적 작업(`merge_nodes`, 아카이브)이다.

### 입력 모드 (v22 — 4 모드)

**모드는 UI 라우트 선택으로 결정**한다. `save()` · `retrieve()` 호출자는 `kind` 를 **필수** 지정. 자동 판정 없음. 결정된 모드는 `posts.kind` 에 그대로 저장된다.

| 모드 | 라우트 | save 파이프라인 | 노드 편입 | 용도 |
|---|---|---|---|---|
| **chat** | `/chat` | save-pronoun ✓, 메타 필터 전체, Kiwi 노드 추출 | ✓ | 메신저 스타일 평문 축적 |
| **markdown** | `/compose` | save-pronoun ✗ (공문서 원형 보존), 메타 필터 자유문장·list, parse_markdown heading 경로 상속 | ✓ | 구조화된 글 축적 |
| **synapse** | `/synapse` | save-pronoun ✗, 메타 필터 ✗, retrieve 후 답 생성, 질문·답 sentence 로 기록 | **✗ (역사만)** | 인출·융합 세션 |
| **insight** | 승격 전용 | 시냅스 세션의 retrieve 노드 전부와 `node_sentence_mentions` 일괄 INSERT | ✓ (허브) | 사용자 승격 통찰 1 본체 |

**모드 차이의 근거** (원칙 13 참조):
- `chat` vs `markdown` — save-pronoun 차이는 **문서 성격** (일상 대화 vs 공식 문서). heading 경로 차이는 **입력 문법의 유무**. Kiwi 노드 추출 + 19 대분류 태깅은 두 모드 동일.
- `synapse` — 저장이 아니라 **인출·조합** 이므로 파이프라인이 다르게 탄다. 질문·답은 `sentences` 에 `role='user'`/`'assistant'` 로 기록되지만 `node_sentence_mentions` 편입 없음 (원칙 15-1).
- `insight` — 시냅스 세션 메시지의 사용자 승격으로만 생성. 본체 1 sentence, 시냅스 세션의 retrieve 캐시 노드 전부와 자동 허브 연결 (Hebbian — 원칙 15-2).

전체 명세는 **`docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md`**.

**`structure-suggest` 폐기 (v17)** — 기존 v16 까지는 평문 입력 시 LLM 이 heading 초안을 강제로 달아 마크다운 모드로 재진입시켰으나, 2026-04-21 dogfood 에서 14건 중 6건이 같은 날짜 heading 으로 뭉쳐 "카테고리 공유 = 연결" 원칙을 무력화. 평문은 평문인 채로 저장하는 것이 원칙 4·원칙 9 와 일치. v19 의 사용자 명시 모드 분리, v22 의 4 모드 확장은 이 방향의 연장 — 저장 시점에 모델/규칙이 구조를 판정하지 않는다.

**자연어 → 마크다운 핫키 (v22)** — `markdown` 모드 에디터 전용. 사용자가 STT 로 자연어 입력 → 핫키(`⌘⇧M` 등) → LLM 이 현재 에디터 내용을 마크다운 문법으로 정제 → in-place 치환 → 사용자 추가 편집 후 저장. 채팅 모드엔 제공하지 않는다 (모드 경계 흐리지 않기 — 원칙 14 참조).

### 마크다운 모드 예시

```markdown
# 더나은
## 개발팀
- 팀장:: 박지수
- 프론트엔드 김민수
오늘 회의가 세 개 연속이었다.
```

- heading 경로(`더나은.개발팀`) → `categories` 재귀 upsert + `sentence_categories`(heading 말단, origin='user') (v20)
- `- 팀장:: 박지수` → key_value 로 파싱, sentence 통째 저장(`text="팀장:: 박지수"`), save-pronoun skip
- `- 프론트엔드 김민수` → list, 일반 sentence
- 자유 문장 → free, 메타 필터 대상

### 파이프라인 흐름 (v19 계획 · v17~18 현재 · Kiwi-first)

> 아래 흐름은 **chat 모드** 기준. markdown 모드는 ① save-pronoun 전체 skip 이고 메타 필터가 자유 문장·list 한정이며, `parse_markdown` 이 kind(heading/key_value/list/free) 별로 분기한다. 모드별 전체 비교는 `docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md` "저장 파이프라인 — 모드별 비교" 표.

```
사용자 입력 (mode='chat' or 'markdown')
  ↓ posts INSERT (kind=mode, source=원문, title=첫 행 자동)
  ↓ parse_markdown(text) — heading/list/평문 분리 (markdown), 전부 (None,'free',text) (chat)
  ↓
  [메타 필터 — 게시물 단위 1회]                                     ← NEW (v17)
    chat: 모든 줄 대상 / markdown: 자유 문장·list 만 대상 (heading·key_value 제외)
    (b) 규칙 사전필터: Kiwi 명사 0개 + '?' 종결 → 즉시 메타 확정
    (a) 나머지 줄을 한 번에 LLM 배치 호출
        프롬프트: docs/META_FILTER_SYSTEMPROMPT.md
        temp=0, max_tokens=2048
        출력: {"meta": [idx, ...]}  — 저장 제외할 줄 idx
    MLX 서버 다운 시 → 필터 skip (모든 문장 저장 진행, 과포함은 UI 삭제로 해소)
  ↓
문장별로 (메타 idx 제외):
  ↓
  ① [save-pronoun — 베이스 모델]  temp=0, max_tokens=256     ← chat 모드 전용 (markdown 전체 skip)
      프롬프트: docs/SAVE_PRONOUN_SYSTEMPROMPT.md
      세션리스 — 직전 대화 context 주입 없음
      모호 케이스(`{"question": "..."}` 반환) → 저장 중단
      실패·MLX 다운 시 → 원문 그대로 진행 (skip)
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
      모바일·웹(개인): kiwi-nlp (WASM)
      추출: NNG/NNP/NP 명사 + VV/VA lemma + MAG(안/못)
      원칙 2 적용:
        · 한국어 용언 → lemma 로 정규화 ("아파서/아프" → "아프")
        · 외래어·복합명사 → Kiwi 가 쪼갠 조각 그대로 수용
          ("React Native" → "React", "Native" 두 노드. 같은 sentence 공출현으로 연결 창발)
      LLM extract / extract-merge 없음 (v17 폐기)
  ↓
  ⑥ [규칙 — 날짜 노드 분할]
      '2026년 4월 18일' → ['2026년', '4월', '18일'] 노드 후보 추가
      한 sentence 안의 모든 단위(년·월·일) 같은 sentence_id 에 mention 연결
      식별 조건: '년/월/일' 키워드 또는 ISO 구분자 '-' 있을 때만
      분할된 날짜 노드는 node_categories.major_category='TIM.*' 에 origin='system' 으로 자동 등록 (축 B 결정론적 예외)
  ⑦ DB 저장 (동기 — 즉시 반영):
      nodes upsert — 같은 이름은 기존 id 재사용
      node_mentions INSERT OR IGNORE (node_id, sentence_id)

      [축 A — 사용자 heading 계층] (v20 PLAN-004)
      categories upsert — heading path segments 재귀 upsert (parent_id 체인)
        예: ["더나은","개발팀"] → (더나은, NULL) · (개발팀, id_더나은)
      sentence_categories INSERT — 동기 origin 처리:
        · heading 말단 카테고리만 문장에 연결
        · 사용자 명시 heading → origin='user'
        · 규칙 분류(doc_mode 계층 등) → origin='system'
        · 문장 단위 매핑이므로 Kiwi 노드 전체에 경로 부여하던 과포함 문제 해소

      [축 B — 19 대분류 태깅] (v20 PLAN-004)
      node_categories — 저장 시점에는 건드리지 않음.
        · 결정론적 규칙(날짜 TIM.* 자동 태깅 등)만 예외적으로 origin='system' 으로 동기 INSERT
        · AI 추론은 전량 백그라운드 CATEGORY 워커로 이전 (origin='ai')

      aliases INSERT — 동기 origin 처리:
        · 사용자 수동 등록 → origin='user'
        · 인칭대명사 시드 → origin='system'
        · Wikidata·LLM 추천은 여기서 생성하지 않음 → 백그라운드 워커로 이전
  ↓
  commit + 훅 발화 → 백그라운드 워커 체인 트리거 (아래 "백그라운드 워커" 섹션)
```

v18: ⑧ extract-state 단계 폐기. 저장은 순수 기록으로, 시점 해석은 인출 LLM 담당.

### v17~v18 폐기 단계 — 왜 뺐나

| 폐기된 단계 | 이유 |
|---|---|
| `llm_extract` (v17) | Kiwi 단독으로 노드 추출 커버. LLM 호출 줄당 1회 절감 |
| `llm_extract_merge` (v17) | dogfood 수량·단위 누락(`1주`·`12시간`·`150%`·`15일`·`80퍼센트`) 의 **범인**. base 모델 프롬프트 튜닝으로 해결 불가 |
| `structure-suggest` (v17) | 평문 14건 중 6건을 같은 날짜 heading 으로 뭉쳐 저장해 카테고리 공유 원칙 무력화. 평문은 평문대로 저장이 원칙 4·9 와 일치 |
| 외래어 원형 복원 LLM (v17) | Kiwi 쪼갠 채 저장이 원칙 2·4 에 부합 |
| `extract-state` + `sentences.status` (v18) | 2026-04-21~23 실측(114쌍 골든셋) 결과 3분류 F1=0.46 / 이진 V1 F1=0.81 — 모델·사람 둘 다 애매. 저장 시점 판정이 원칙 7·8·10·11 과 어긋남. 시점 해석은 인출 LLM 의 `created_at` 최근성 판단으로 이관 |

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

- **`unresolved_tokens` 해소** — 치환 실패 지시어. 사용자 옵션 선택 후 `nodes`/`node_mentions`로 편입.
- **노드 병합 (`merge_nodes`)** — 되돌릴 수 없는 파괴적 작업. `suspected_typos` 도출기에서 후보 제시 → 사용자 승인.
- **노드 아카이브 (`status='inactive'`)** — 사용자가 모르게 비활성화되면 당황할 수 있어 `stale_nodes` 승인 유지.
- **자동 오타 교정으로 노드 이름 변경** — `_correct_typos` 폐기. "언급된 것만 존재" 원칙 위배. 오타는 `suspected_typos`로 후보만 제시.

### 자동 시드 예외

- `_FIRST_PERSON_ALIASES` — 인칭대명사 11개는 origin='system'로 자동 시드 (모든 사용자 공통).

---

## 백그라운드 워커 (v15 신규)

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

같은 노드가 여러 번 언급되면 이미 처리된 것은 스킵 (`node_categories` / `aliases`에 이미 있는지 확인).

### 실행 리소스 관리

리소스 여유 없으면 큐에 쌓아두고 유휴 시간에 처리:

- **동시 실행 제한**: asyncio 세마포어로 각 워커 최대 N개 병렬 (기본 2)
- **리소스 체크**: CPU/메모리/MLX 서버 사용 여부 확인. 임계치 초과 시 지연
- **백오프**: 외부 API 실패 시 exponential backoff, 반복 실패는 해당 노드 skip 표시

### 워커 ①: 카테고리 분류 워커 (축 B 전용 — v20)

**어댑터 미사용** — 베이스 모델(gemma4:e2b)에 `docs/CATEGORY_SYSTEMPROMPT.md`를 시스템 프롬프트로 주입해서 19 대분류 코드로 분류.

```
입력: 노드명 + 이 노드가 언급된 최근 문장들 (상위 N건)
출력: {"categories": ["BOD.disease", ...]}  (빈 배열이면 분류 불가)
        ↓
각 카테고리마다:
  node_categories INSERT (node_id, major_category, origin='ai')
        ↓
실패 / 빈 결과 → 아무것도 저장하지 않음 (나중에 재처리 대상으로 남음)
```

- 대상: 축 B(`node_categories`) 만. 축 A(`sentence_categories`) 는 저장 파이프라인이 heading path 로 이미 채움 — 워커는 건드리지 않는다.
- 입력에 포함할 문장 선택: `node_mentions` JOIN `sentences` ORDER BY `created_at` DESC LIMIT N.
- 프롬프트 출력의 `"categories"` 필드값은 19 대분류 코드(`major_category`). 공간 효율상 TEXT 로 저장하며, 값 validation 은 `CATEGORY_SYSTEMPROMPT.md` 상수로 애플리케이션에서 수행.
- 이미 user/system origin `major_category` 가 있는 노드도 대상 (AI 분류는 보완적으로 함께 쌓임).

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

**FastAPI BackgroundTasks + asyncio 세마포어** 조합 (복잡한 외부 큐 브로커 불필요):

```python
# /ingest 저장 엔드포인트 끝부분
background_tasks.add_task(category_worker, sentence_id, new_node_ids)
background_tasks.add_task(alias_worker, new_node_ids)

# 워커는 내부에 asyncio.Semaphore로 동시 제한 + 리소스 체크
```

- 앱 재시작 시 미완료 작업은 다음 언급 때 자연 재시도 (`node_categories`/`aliases` 테이블에 없으면 다시 대상).
- 수동 재실행 경로도 제공: `/review`에서 "지금 다시 분류" 버튼 (선택적).

### `--no-llm` 모드 대응

- 카테고리 분류 워커: LLM 호출 불가 → 아예 실행 안 됨. `origin='system'`·`'user'` 카테고리만 DB에 쌓임.
- Wikidata 별칭 워커: LLM과 무관하게 동작. 인터넷 없으면 스킵.
- 저장 파이프라인: 메타 필터 skip(모든 문장 저장 진행), save-pronoun skip(원문 그대로). Kiwi 경로는 LLM 과 무관하게 항상 동작. (v18: extract-state 폐기로 애초에 호출 없음)

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
    현재 노드·카테고리 집합마다 세 경로를 합쳐 다음 레이어 구성 (v20 PLAN-004):
      ① 문장 바구니 (node_mentions JOIN sentences) → 같은 sentence에 함께 언급된 노드
      ② 의미 태깅 축 (node_categories.major_category) → 같은 19 대분류 + 카테고리 인접 맵 한 홉
      ③ 사용자 heading 축 (categories 재귀 CTE + sentence_categories)
         → 질의 키워드가 사용자 categories 와 매칭되면 서브트리 전체를 시드 sentence 로 수집
    [synapse/retrieve-filter]  temperature=0, max_tokens=8
      ①은 sentence 단위로, ②·③은 카테고리 경로 + 대표 sentence로
      관련성 판단 (pass/reject). 불확실하면 pass
    통과한 항목의 새 노드·카테고리 → 다음 레이어
    모든 경로에서 새 항목 없으면 종료
  ↓ [시간 순 정렬 (v18)]
    통과한 sentence 들을 sentences.created_at 오름차순으로 정렬.
    각 줄 앞에 `[YYYY-MM-DD]` 날짜 힌트를 붙여 LLM 프롬프트 컨텍스트 구성.
  ↓ [synapse/chat]  temperature=0.3, max_tokens=4096
    인출 sentences를 컨텍스트로 자연어 답변.
    프롬프트 규칙: "충돌 시 최근 사실 우선", "'지금 어때?' 는 최신 기록 근거",
    "과거 사실도 유지 — 시점 구분해 설명".
    상태 레이어(v17 이하) 대신 시점 해석을 여기서 수행 (v18 설계 결정).
    답변 → sentences INSERT (role='assistant')
```

### 세 경로의 역할 구분 (v20)

| 경로 | 데이터 출처 | 의미 |
|------|-------------|------|
| ① 문장 바구니 (`node_mentions`) | 자동 저장 (사용자가 같은 게시물·문장에 함께 언급) | "함께 등장한 사실" |
| ② 의미 태깅 축 (`node_categories.major_category`) | CATEGORY 워커 분류 + 규칙 시드 + 인접 맵 | "같은 주제군으로 묶인 개념" |
| ③ 사용자 heading 축 (`categories` + `sentence_categories`) | 사용자 명시 heading path (adjacency list) | "사용자가 정한 계층 바구니" |

①은 공출현한 사실 덩어리, ②는 의미 기반 확장, ③은 사용자 계층 기반 확장(서브트리 스캔). 셋 모두 인출에 기여하며 답변 컨텍스트에서는 모두 sentence 원문으로 표시된다 ("- 허리디스크 진단"). 인과·유사·회피 같은 의미 해석은 외부 지능체가 sentence 원문을 읽고 수행한다 (원칙 11).

### 모든 노드는 같은 경로로 조회된다

날짜·시간부사·부정부사·장소 같은 토큰도 일반 명사 노드와 **같은 세 경로**(문장 바구니 + 의미 태깅 + 사용자 heading)를 거친다 (v20).

- "2026-04-17에 뭐 있었지?" → `2026-04-17` 노드 → `node_mentions` → sentences → 함께 언급된 노드
- "안 먹은 약" → `안` 노드 → mentions → sentence → 함께 언급된 약 노드
- "허리디스크의 원인" → `허리디스크` 노드 → ① 문장 바구니 + ② `BOD.disease` 의미 태깅 바구니 → 외부 지능체가 원문에서 인과 해석
- "더나은 전체 보여줘" → `더나은` 이 `categories` 루트로 매칭 → 재귀 CTE 서브트리 수집 → `sentence_categories` JOIN 으로 문장 전체 조회 (③ 경로)

특수 카테고리(TIM/NEG 등)나 특수 경로 없음.

---

## /review — 검토 편입

자동 저장 체계에서 `/review`는 세 가지 역할만 담는다: (1) `unresolved_tokens` 해소, (2) AI·규칙 생성물 검수 뷰, (3) 파괴적 작업 승인.

상세(섹션별 도출기, API, 프론트 구조) → **`docs/DESIGN_REVIEW.md` 참고.**

### 요약

| 섹션 | 데이터 소스 | 역할 |
|------|-------------|------|
| `unresolved` | `unresolved_tokens` | 승인 대기 해소 |
| `ai_generated` | `node_categories WHERE origin='ai'` (축 B) · `sentence_categories WHERE origin='ai'` (축 A, 있으면) | 검수 뷰 (유지/삭제) |
| `external_generated` | `aliases WHERE origin='external'` | Wikidata 별칭 검수 뷰 |
| `system_generated` | `node_categories`·`sentence_categories`·`aliases` 중 `origin='system'` | 검수 뷰 (규칙 오류 추적) |
| `suspected_typos` | `find_suspected_typos` | 병합 승인 (파괴적) |
| `stale_nodes` | `nodes.updated_at` | 아카이브 승인 |
| `daily` / `gaps` | `sentences.created_at` | 정보 뷰 |

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
  → 고아 노드는 보존 (재연결 가능성)
  → sentences 삭제
```

### 콤팩팅 (v13에서 재설계 예정)

v12 이전 설계는 `retention='daily'` 기반으로 자동 정리했으나, retention 폐기에 따라 해당 로직도 제거. 현재는 모든 sentence가 영구 보관된다.

DB 경량화가 필요한 시점에 별도 정책 재설계 예정. 후보: `last_used IS NULL` + N일 경과 + 참조 노드 없음 + 사용자 수동 확인.

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
| 의미 태깅 (축 B) | "건강 관련" → `node_categories.major_category='BOD.*'` 노드 → mentions |
| 사용자 heading (축 A) | "더나은 전체" → `categories` 재귀 CTE → `sentence_categories` → sentences |
| 복합 | "지난달 병원 관련" → 시간 + 노드 교차 |

---

## 모델 & 서버

**서버**: MLX 서버 (localhost:8765, `api/mlx_server.py`) — OpenAI 호환 API

**베이스 모델**: `unsloth/gemma-4-E2B-it-UD-MLX-4bit`
- Google Gemma 4 2B (Early Access)
- MLX 4bit 양자화, 로컬 실행 (~3.6GB)
- 컨텍스트 윈도우: 양자화 32K / 원본 128K

```
앱 → HTTP → MLX 서버 (localhost:8765) → gemma-4-E2B-it (베이스 모델 ± 태스크 어댑터)
```

---

## Gemma 4 thinking 모드 OFF (전역 설정)

모든 LLM 호출은 `tokenizer.apply_chat_template(..., enable_thinking=False)` 로 thinking 블록을 차단한다.

- **이유**: 학습 데이터 system 메시지에 `<|think|>` 토큰이 없어 thinking 없이 학습됐고, ON 상태에서는 추론 시간이 약 10배 길어지며 한 단어 출력 태스크에서 오답률이 급증한다.
- **적용 위치**: `api/mlx_server.py` 의 `apply_chat_template` 호출, `scripts/mlx/eval_*.py`.
- **주의**: Gemma 4 4bit (E2B/E4B) 변종은 OFF 설정 시 빈 thought 블록도 출력하지 않음 (공식 문서 확인).

---

## 태스크 처리 방식

베이스 모델 + 시스템 프롬프트로 충분한 태스크는 어댑터 없이, 규칙 추출·패턴 매칭이 필수적인 태스크만 파인튜닝 어댑터로 운영.

| 태스크 | 처리 방식 | 프롬프트 파일 / 어댑터 경로 |
|--------|-----------|------|
| meta-filter | 베이스 모델 | `docs/META_FILTER_SYSTEMPROMPT.md` |
| save-pronoun | 베이스 모델 | `docs/SAVE_PRONOUN_SYSTEMPROMPT.md` |
| retrieve-filter | 베이스 모델 | `docs/RETRIEVE_FILTER_SYSTEMPROMPT.md` |
| retrieve-expand | 어댑터 | `synapse/retrieve-expand` |
| retrieve-expand-org | 어댑터 | `synapse/retrieve-expand-org` |
| security-context | 베이스 모델 | (개인 민감정보 노출 여부 판단) |
| category (백그라운드) | 베이스 모델 | `docs/CATEGORY_SYSTEMPROMPT.md` |
| chat (응답 생성) | 베이스 모델 | — |

v17 폐기: `extract`, `extract-merge`, `structure-suggest` — `llm_extract()`·`llm_extract_merge()`·`structure_suggest()` 함수와 프롬프트 파일(`EXTRACT_SYSTEMPROMPT.md`·`EXTRACT_MERGE_SYSTEMPROMPT.md`) 모두 제거. Kiwi 단독이 저장 기본 경로.

v18 폐기: `extract-state` — `llm_extract_state()` 함수와 프롬프트 파일(`EXTRACT_STATE_SYSTEMPROMPT.md`) 제거. `sentences.status` 컬럼 폐기. 시점 해석은 인출 LLM 이 `created_at` 기반 최근성 판단으로 처리.

시스템 프롬프트 파일 로더는 `engine/prompts.py`. 권한 판단(security-access 등)은 결정론적 백엔드 로직 소관이라 LLM 태스크에서 제외.

---

## LLM 설정값

| 단계 | 처리 방식 | temperature | max_tokens |
|------|-----------|-------------|------------|
| 라우팅 | 베이스 + ROUTING_SYSTEMPROMPT.md | 0 | 32 |
| 메타 필터 (저장 진입부) | 베이스 + META_FILTER_SYSTEMPROMPT.md | 0 | 2048 |
| 전처리 치환 | 베이스 + SAVE_PRONOUN_SYSTEMPROMPT.md | 0 | 256 |
| 카테고리 분류 (백그라운드) | 베이스 + CATEGORY_SYSTEMPROMPT.md | 0 | 512 |
| 인출 확장 | synapse/retrieve-expand | 0 | 256 |
| 인출 필터 | 베이스 + RETRIEVE_FILTER_SYSTEMPROMPT.md | 0 | 8 |
| 민감정보 확인 | 베이스 모델 | 0 | 512 |
| 응답 생성 | 베이스 모델 (chat) | 0.3 | 4096 |

---

## 독립 동작 (`--no-llm`)

시냅스는 LLM 없이도 기본 동작을 보장한다 (원칙 11).

- 저장: Kiwi 형태소 분석으로 노드 추출 + 규칙 기반 날짜 분할·unresolved 감지. 메타 필터·save-pronoun·extract-state 는 skip. 평문 저장 자체는 완결됨
- 백그라운드 워커: 카테고리 분류 워커는 LLM 호출 불가로 비활성 (`origin='ai'` 카테고리 발생 안 함). Wikidata 별칭 워커는 **인터넷만 있으면 동작** (LLM과 무관)
- 인출: `retrieve-expand`·`retrieve-filter` 생략하고 Kiwi 키워드 매칭 + BFS만
- `/review`: `unresolved`, `ai_generated`(빈 결과), `external_generated`, `system_generated`, `suspected_typos`, `stale_nodes`, `daily`, `gaps` 모두 쿼리만으로 동작

---

## assistant 응답 하이퍼그래프 편입 (미래)

현재: `role='assistant'` sentences에만 저장. 하이퍼그래프 추출 안 함.
이유: 2B 로컬 모델 응답이 사용자 말 되풀이 수준. 하이퍼엣지 편입 가치 < 부하 증가.

**재검토 조건:**
- 모델 품질 향상 (응답에 새로운 인사이트/분석 포함)
- 도구 확장으로 외부 데이터 수집 시

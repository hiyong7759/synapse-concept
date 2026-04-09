# Synapse 설계 — 그래프 모델

**최종 업데이트**: 2026-04-09 (v8 스키마, 통합 파이프라인, 부사 치환 규칙)

## 핵심 설계 원칙

1. **노드는 개념이다.** 인물, 장소, 수치, 상태, 행위 전부 노드. 품사 무관. 하나의 개념 = 하나의 노드. 중복 생성 금지.
2. **엣지는 조사다.** 원문의 조사를 그대로 label로 사용. 의미 해석 금지. 조사 없으면 NULL.
3. **개인 모드: "나" 노드 없다.** 1인칭 표현("나는", "내가", "내", "저", "제")은 노드로 추출하지 않는다. "나"를 노드로 저장하면 모든 사실이 "나"를 통해 연결되어 BFS가 전체 그래프로 폭발한다. 사용자 이름이 anchor 노드.
   **조직 모드: 주어 항상 명시.** 조직 그래프에서는 누가 말했는지가 핵심. 1인칭은 사용자 이름으로 치환. 주어가 불명확하면 LLM이 질문.
4. **부정부사는 노드다.** "안", "못"은 독립 노드로 저장. `스타벅스 → 안 → 좋아` 구조. 긍정/부정 구분 없이 검색 유연성 확보.
5. **엣지는 유방향이다.** `source_node_id → target_node_id` 구조. 조사가 앞 명사에 붙으므로 source가 고정됨. BFS 탐색은 양방향으로 조회하되 저장은 방향 있음.
6. **문장 단위로 묶인다.** `edges.sentence_id`로 같은 문장에서 생성된 엣지를 그룹핑. rollback과 인출 필터링의 기본 단위. 여러 문장은 하나의 session으로 묶인다.
7. **도메인은 관찰하는 것이다.** 연결이 많아진 노드가 허브가 되고, 허브가 도메인으로 기능한다. 사전 정의하지 않는다.

---

## 스키마 (v8 — 현재)

```sql
sessions:
  id         INTEGER PRIMARY KEY
  type       TEXT DEFAULT 'conversation'  -- conversation | archive
  created_at TEXT DEFAULT (datetime('now'))

sentences:
  id              INTEGER PRIMARY KEY
  session_id      INTEGER REFERENCES sessions(id) ON DELETE CASCADE
  paragraph_index INTEGER DEFAULT 0       -- 같은 session 내 문단 순서
  text            TEXT NOT NULL           -- 원본 문장 (사용자) 또는 응답 텍스트 (모델)
  role            TEXT DEFAULT 'user'     -- user | assistant
  retention       TEXT DEFAULT 'memory'   -- memory | daily (role='user'만 적용)
  created_at      TEXT DEFAULT (datetime('now'))

nodes:
  id         INTEGER PRIMARY KEY
  name       TEXT NOT NULL UNIQUE
  category   TEXT    -- 대분류.소분류 형식 (예: BOD.disease). NULL 허용.
  status     TEXT DEFAULT 'active'  -- active | inactive
  created_at TEXT DEFAULT (datetime('now'))
  updated_at TEXT DEFAULT (datetime('now'))

edges:
  id             INTEGER PRIMARY KEY
  source_node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  target_node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE
  label          TEXT    -- 원문 조사 1개. 없으면 NULL
  sentence_id    INTEGER REFERENCES sentences(id) ON DELETE SET NULL
  created_at     TEXT DEFAULT (datetime('now'))
  last_used      TEXT

aliases:
  alias   TEXT PRIMARY KEY
  node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE
```

**설계 결정:**
- `sessions`: 대화 세션 단위. `conversation`(일반 대화) / `archive`(월별 장기 보관함) 두 종류.
- `sentences`: 사용자 입력(`role='user'`)과 모델 응답(`role='assistant'`) 모두 저장. 대화 히스토리 표시용.
- `sentences.role`: `user` — 그래프 추출 대상. `assistant` — 대화 히스토리 표시용만. 그래프 추출 제외.
- `sentences.retention`: `memory`(잘 변하지 않는 사실) / `daily`(일상·순간). `role='user'`에만 적용. LLM 저장 시 자동 분류. 콤팩팅 기본 선택 기준.
- `edges.sentence_id`: 어느 문장에서 생성된 엣지인지 추적. 수정/삭제 시 같은 sentence_id 엣지 전체 rollback.
- `edges.source_node_id` / `target_node_id`: 방향성 있음.
- `nodes.category`: `대분류.소분류` 형식. 저장 시 LLM이 자동 부여. 인출 시 동일 대분류 노드 추가 조회로 BFS 보완.
- `status`: active | inactive. deleted 없음. 비활성화해도 엣지 보존.
- `domain`, `source`, `weight`, `safety`, `edges.type` 없음.

---

## 노드 카테고리

`nodes.category`: `대분류.소분류` 형식 (예: `BOD.disease`, `MON.spending`). NULL 허용.

**분류체계 전체 및 카테고리 인접 맵 → `docs/DESIGN_CATEGORY.md` 참고**

카테고리 부여 목적: 파편화된 입력(병원명·질병명이 별도 문장으로 저장) 간 BFS 연결 부재 보완.
`"허리 아파"` 질문 → 같은 BOD 카테고리 노드 집합 추가 조회 → 강남세브란스 도달 가능.

파인튜닝 데이터: `archive/finetune/data/task6_*.jsonl` — 1,677건 (카테고리별 40~236건, 17개 대분류 전체 커버).

---

## 노드

LLM(파인튜닝 모델)이 문장에서 개념 단위로 직접 추출. 형태소 분석기 없음.

| 노드 종류 | 예시 | 비고 |
|-----------|------|------|
| 인물·조직 | 조용희, 강남세브란스, 삼성 | 개인: "나" 노드 없음, 이름이 anchor. 조직: 주어 명시. |
| 개념·사물 | 허리디스크, 식기세척기, ChatGPT | |
| 장소 | 진천, 강남역, L4-L5 | |
| 수치·날짜 | 50살, 2026-04-09, 30만원 | |
| 상태·행위 | 번아웃, 퇴사, 다녀왔 | 동사/형용사도 개념이면 노드 |
| 부정부사 | 안, 못 | 독립 노드. 뒤 어절과 분리 저장 |

---

## 엣지

| 구성요소 | 설명 |
|----------|------|
| source_node_id | 출발 노드 |
| target_node_id | 도착 노드 |
| label | 원문 조사 그대로 (에서, 으로, 의, 고, 는 등). 없으면 NULL |
| sentence_id | 이 엣지가 생성된 원본 문장 ID (sentences.id FK) |

**예시:**
```
"조용희고 50살 웹기획자야"
→ 조용희 —(고)→ 50살
→ 50살 — 웹기획자

"스타벅스 안 좋아"
→ 스타벅스 — 안
→ 안 — 좋아

"진천으로 이사했어"
→ 진천 —(으로)— 이사
```

---

## 통합 파이프라인

모든 대화 입력에 대해 **인출 → 저장 → 응답** 3단계가 항상 실행된다. 의도(저장/인출/일반대화)에 따른 분기 없음. 모든 응답이 개인 맥락을 반영한다.

```
사용자 입력 (role='user' — sentences에 저장)
  ↓
[1단계: 인출] — 항상 실행
  [LLM] 키워드 추출 → DB 매칭 (aliases 우선 → name → substring)
  → BFS 루프 (양방향, max_layers=5, visited 수렴)
  → 개인 맥락 수집 (= 상태변경 감지용 기존 문장 조회 겸용)
  ↓
[2단계: 저장] — 항상 실행
  [전처리 — 규칙 기반] 시간 부사 → session 날짜 기반 자동 치환
  [전처리 — LLM 기반]  대명사·장소 지시어 → 구체값 치환 or 모호성 질문 반환
  [LLM 추출] 노드 + 엣지 + 카테고리 + 비활성화 대상 → JSON
  DB 저장 (nodes, edges, sentence_id 포함)
  별칭 추가 (기본 실행 — 새 노드 시 aliases 자동 등록)
  ↓
[3단계: 응답] — 항상 실행
  인출 맥락 + 저장 결과 종합 → LLM 개인화 답변
  답변 → sentences 저장 (role='assistant')
```

LLM에 **원본 문장**을 컨텍스트로 전달:
```
알려진 사실:
- 조용희고 50살 웹기획자야
- 진천으로 이사했어
- 병원 다녀왔어
```

응답 시간이 길 수 있다. 정확성 우선으로 대기 허용. 사용자에게 "탐색 중" 상태 안내 필요.

취소/수정:
```
sentence_id 기준으로 해당 edges 전체 삭제
→ 고아 노드(연결 없는 노드) 삭제
→ sentence 텍스트 교체 후 재추출 (수정 시)
→ session 단위 삭제 가능 (콤팩팅으로 memory 항목 보관함 이동 후 삭제)
```

---

## 저장 전처리 — 치환 규칙

두 단계로 처리한다. 1단계는 LLM 없이 자동, 2단계는 LLM이 맥락 파악.

### 1단계: 규칙 기반 (자동 계산)

| 대상 | 처리 | 예시 |
|------|------|------|
| 시간 부사 — 일 | session 날짜 기준 계산 | 오늘→2026-04-09, 어제→2026-04-08, 그제→2026-04-07 |
| 시간 부사 — 일 | session 날짜 기준 계산 | 내일→2026-04-10, 모레→2026-04-11 |
| 시간 부사 — 주 | session 기준 주 | 이번 주→2026-W15, 지난주→2026-W14, 다음 주→2026-W16 |
| 시간 부사 — 연 | session 연도 기준 | 올해→2026, 작년→2025, 내년→2027 |
| 1인칭 (개인 모드) | 제거 (노드 미생성) | "나는 48살이야" → "48살" |
| 1인칭 (조직 모드) | 사용자 이름으로 치환 | "내가 승인했어" → "조용희가 승인했어" |

### 2단계: LLM 기반 (맥락 파악 필요)

| 대상 | 처리 | 예시 |
|------|------|------|
| 장소 지시어 | 직전 언급 장소 노드로 치환 | 거기서/거기에/그곳에서 → 구체 장소명 |
| 인물 지시어 | 직전 언급 인물 노드로 치환 | 그분/그사람/걔/쟤 → 구체 인물명 |
| 모호성 | 특정 불가 시 사용자에게 되물음 | "거기 그만뒀어" + 후보 복수 → "어디를 그만두신 건가요?" |

**규칙:**
- 나이·숫자·금액은 절대 치환하지 않음
- 개인 모드: 1인칭 제거 후 나머지만 추출
- 조직 모드: 1인칭은 사용자 이름으로 치환, 주어 항상 명시
- 모호성 질문 발생 시 저장 중단, 사용자 응답 대기

---

## Aliases

노드의 다른 이름/변형. 인출 정확도의 핵심.

| 방식 | 시점 | 설명 |
|------|------|------|
| LLM 자동 제안 | 새 노드 생성 직후 | 줄임말·외래어·다국어 표기 |
| 사용자 수동 등록 | 언제든 | "스벅은 스타벅스야" |
| missing 기반 | 인출 실패 시 | 매칭 실패 키워드 연결 제안 |

인출 매칭 우선순위:
```
1. aliases 정확 매칭
2. 노드명 직접 매칭
3. 노드명 substring 매칭
```

---

## 개인 / 조직 모드

| | 개인 모드 | 조직 모드 |
|---|---|---|
| 1인칭 처리 | 제거 (노드 미생성) | 사용자 이름으로 치환 (주어 명시) |
| 주어 생략 | 그대로 저장 | LLM이 사용자에게 질문 |
| doc_mode | 거의 사용 안 함 | 주 사용 (취업규칙, 법령 등) |
| 목적 | 개인 지식 그래프 | 조직 날리지 관리 |

### doc_mode (조직 모드 특화)

정규식으로 자동 감지:
```python
DOC_PATTERN = re.compile(
    r'제\s*\d+\s*조'        # 제N조
    r'|[①②③④⑤⑥⑦⑧⑨⑩]'   # 원문자 항
    r'|\d+\s*호\b'          # N호
    r'|제\s*\d+\s*항'       # 제N항
)
```

doc_mode=True이면 앵커 노드 + 계층 엣지 + seq 카운터 생성.

---

## LLM 설정값

| 단계 | 어댑터 | temperature | max_tokens |
|------|--------|-------------|------------|
| 전처리 치환 | synapse/save-pronoun | 0 | 256 |
| 노드/엣지/카테고리/상태변경 추출 | synapse/extract | 0 | 512 |
| 인출 확장 | synapse/retrieve-expand | 0 | 256 |
| 인출 필터 | synapse/retrieve-filter | 0 | 8 |
| 별칭 제안 | synapse/chat (base) | 0 | 64 |
| 응답 생성 | synapse/chat (base) | 0.3 | 4096 |

**모델:** `unsloth/gemma-4-E2B-it-UD-MLX-4bit` (Google Gemma 4 2B, MLX 4bit 양자화, ~3.6GB)
**서버:** MLX 서버 (localhost:8765, `api/mlx_server.py`) — OpenAI 호환 API

---

## 허브 → 도메인 부상

도메인은 사전에 정의하지 않는다. 관찰하는 것이다.

```
초기: 허리, 감기, 두통, 병원, 약 노드가 각각 존재
      ↓ 연결 축적
허브 감지: 특정 노드의 degree가 임계값 초과
      ↓
도메인 부상: 해당 노드가 클러스터의 대표 허브로 기능
```

- 허브 노드는 UI 그래프 뷰에서 시각적으로 강조
- 도메인 부상은 노드/엣지 구조를 바꾸지 않음

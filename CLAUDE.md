# Synapse — 개인 지식 그래프

## 핵심 원칙 (이것부터 읽어라)

> **원칙 전체 목록은 `docs/DESIGN_PRINCIPLES.md` — 모든 설계 문서의 원칙이 통합된 단일 출처.**

프로젝트 전체를 관통하는 13개 원칙 요약 (상세는 `DESIGN_PRINCIPLES.md §1` 참고):

**존재론**
1. 언급된 것만 존재한다.
2. 노드는 원자다 (품사 무관, 하나의 개념 = 하나의 노드).
3. 외부 참조는 저장하지 않는다.

**구조**
4. 엣지는 문장을 뛰어넘는 의미 관계다 (조사 엣지 폐기, `/review` 승인 필요).
5. 엣지는 유방향이다.
6. 동의어/다국어는 aliases.
7. meta 컬럼·JSON 필드를 노드에 추가 금지 (예외: `node_categories`).

**저장과 승인**
8. 저장과 합성의 분리 (자동 저장은 sentence + 노드 + `node_mentions` + `unresolved_tokens`까지).
9. DB에 있는 것은 전부 승인된 것.
10. 입력 단위 = 마크다운 구조화된 게시물.

**동작**
11. 도메인은 관찰하는 것이다.
12. 지능체는 분리되어 있다 (시냅스는 LLM 없이도 동작).
13. 모든 질문은 개인 맥락이 있으면 더 나은 답을 만든다.

개인/조직 모드, /review 검토, 카테고리, UI, 데이터 정책 원칙 → `docs/DESIGN_PRINCIPLES.md §2~§6` 참고.

## 구조

```
노드      = 개념 (React Native, 허리디스크, 맥미니, 조용희, 2026-04-17)
mentions  = 노드가 어느 문장에 언급되었는지 (모든 노드에 공통 적용)
엣지      = 문장을 뛰어넘는 의미 관계 (similar/cooccur/cause/contain…), 사용자 승인으로만 생성
별칭      = 키워드 매칭 강화 (aliases 테이블)
```

노드에 `description`, `meta`, `detail`, `domain`, `weight`, `safety` 같은 필드를 추가하면 이 설계를 위반한다.
단, `category`는 예외 — BFS 검색 범위 필터·표시용으로 허용. `node_categories` 테이블로 다대다 관리(노드당 복수 카테고리 가능). 두 종류: 사용자 지정 경로(마크다운 heading, 예: `더나은.개발팀`) 또는 규칙 기반 분명 분류(예: 날짜 패턴 → 시간). LLM이 추론만 하고 사용자가 승인하지 않은 카테고리는 DB에 저장하지 않는다.

## DB 스키마 (v13 — retention 폐기 + node_mentions)

```sql
sentences:        id, text, role(user|assistant), created_at
nodes:            id, name(UNIQUE 아님), status(active|inactive), created_at, updated_at
node_mentions:    node_id, sentence_id, created_at  — PK(node_id, sentence_id)
node_categories:  node_id, category, created_at     — PK(node_id, category)
edges:            id, source_node_id, target_node_id, label(의미 관계), sentence_id, created_at, last_used
aliases:          alias TEXT PRIMARY KEY, node_id
unresolved_tokens: sentence_id, token, created_at   — PK(sentence_id, token)
```

- `node_mentions`: 모든 노드에 동일 적용되는 노드↔문장 역참조. 조사 엣지 폐기로 끊긴 경로를 대체. 시간·장소·부정 같은 특수 노드도 구분 없이 여기만 참조.
- `edges.label`: 의미 관계 종류 (`similar / cooccur / cause / contain / …`). 조사 저장 금지. `status`·`origin` 컬럼 없음 — 삽입된 것은 곧 승인된 것.
- `node_categories`: 사용자 승인된 카테고리만 존재. 승인 전 LLM 제안은 저장하지 않음.
- `unresolved_tokens`: 치환 실패한 지시어 기록. 저장 시점에만 감지되는 일회성 이벤트이므로 런타임 재생성 불가 → 유일한 "승인 대기" 저장 예외.
- `sentences.role`: `user`(그래프 추출 대상) / `assistant`(대화 기록).
- sessions 테이블 없음 (세션리스 아키텍처).
- `domain`, `source`, `weight`, `safety`, `edges.type`, `filters`, `filter_rules`, `nodes.category`, `status/origin` 컬럼 없음.

## CLI

```bash
python3 -m engine.cli           # 대화형 (MLX 서버 필요: python api/mlx_server.py)
python3 -m engine.cli --no-llm  # LLM 없이 BFS 구조만 (독립 동작 보장)
python3 -m engine.cli --stats   # DB 통계
python3 -m engine.cli --reset   # DB 초기화
python3 -m engine.cli --typos   # 오타 의심 노드 쌍 스캔
```

DB 위치: `~/.synapse/synapse.db` (SYNAPSE_DATA_DIR 환경변수로 변경 가능)

## 아키텍처

```
engine/          ← Python 패키지. 그래프 저장/인출 파이프라인.
  db.py          ← v11 스키마 + 마이그레이션 + 연결 관리
  llm.py         ← MLX 서버 클라이언트 + 파이프라인 함수
  markdown.py    ← 마크다운 파서 (heading 경로 + 항목 분리)
  save.py        ← 자동 저장 파이프라인 (sentence + node + node_mentions + unresolved_tokens)
  retrieve.py    ← BFS 인출 파이프라인 (node_mentions JOIN 기반)
  suggestions.py ← /review 런타임 제안 도출기 (쿼리 + LLM 호출, 저장 없음)
  jamo.py        ← 한글 자모 분해 + Levenshtein 거리 (오타 의심 쌍 판정)
  cli.py         ← CLI 인터페이스

api/
  mlx_server.py  ← MLX 태스크 라우터 (OpenAI 호환, 어댑터 스왑)
  routes/
    graph.py     ← FastAPI 라우터 (/chat, /review, /review/apply, …)

app/             ← React 웹앱 (Vite + TypeScript)
  src/
    pages/       ← ExplorerPage, ChatPage, OnboardingPage, GraphPage, ReviewPage
    components/
    styles/tokens.css
```

## 저장 파이프라인 (자동 저장만)

```
사용자 입력 → parse_markdown(text)

[마크다운 모드] heading(#) 있음:
  각 (경로, 항목)마다:
    → [_preprocess] 지시어·시간부사 치환 (LLM save-pronoun)
    → [규칙] ISO 날짜 → 한국어 정규화 ('2026-04-18' → '2026년 4월 18일')
    → sentence 저장 (정규화된 본문)
    → [synapse/extract] 노드 추출 (edges·category 필드 무시)
    → [규칙] 부정부사·날짜 토큰 추출
        - 부정부사: '안', '못'
        - 날짜 분할: '2026년 4월 18일' → ['2026년', '4월', '18일']
          한 sentence 안에 모든 단위(년·월·일)가 함께 mention → 시간 범위 쿼리 지원
    → nodes upsert + node_mentions 기록 (모든 노드 ↔ 같은 sentence)
    → heading 경로를 node_categories에 삽입 (사용자 명시 → 즉시 승인)
    → 치환 실패 토큰은 unresolved_tokens에 기록
    → (끝. 엣지·자동 별칭·LLM 카테고리 없음)

[평문 모드] heading 없음:
  → [synapse/structure-suggest] 마크다운 구조화 초안 제안 → 사용자 확인 후 저장 플로우 재진입
  (구조 없이 저장 안 함)
```

### 날짜 노드 — 사용자 언급 공간 = 한국어

날짜는 ISO(`2026-04-18`)로 들어와도 본문 sentence와 노드 모두 **한국어 표기**(`2026년`, `4월`, `18일`)로 통일. 노드 = 사용자가 일상에서 말하는 단위와 일치해야 한다는 원칙.

식별 규칙: 명시적 키워드(`년/월/일`) 또는 ISO 구분자(`-`)가 있을 때만 날짜로 판단. 단독 4자리 숫자(`2026`)는 오탐 위험으로 노드화하지 않음.

쿼리 예:
- "4월에 뭐 있었지?" → `4월` 노드 → mentions → 4월의 모든 sentence
- "2026-04-18 기록" → `2026년 4월 18일` 노드 → 그 날 sentence + `2026년` ∩ `4월` ∩ `18일` 교집합으로 정확히 좁힘 가능

## 인출 파이프라인

```
질문
  → [synapse/retrieve-expand] 노드 후보 키워드 목록
  → DB 매칭: aliases 우선 → name 직접 → substring
  → BFS 루프 (현재 노드 집합마다 두 경로 합치기):
      • node_mentions JOIN → 같은 sentence 함께 언급된 노드
      • edges JOIN        → 사용자 승인된 의미 엣지의 인접 노드 (label = similar/cause/contain/...)
  → 카테고리 보완 (선택): node_categories 기반 인접 소분류 노드 추가 조회
  → [synapse/chat] 인출 sentences + 의미 엣지를 컨텍스트로 자연어 답변
```

## 검토 편입 (/review)

자동 저장 이외의 모든 그래프 변경은 `/review`를 통한다. 승인 대기 테이블은 `unresolved_tokens` 하나뿐이고, 나머지 제안은 요청 시점에 런타임으로 도출한다.

- **미분류 노드** → `node_categories` LEFT JOIN으로 도출 → 사용자가 카테고리 선택 → `node_categories` INSERT
- **공출현 노드 쌍** → `node_mentions` self-JOIN으로 도출 → LLM이 의미 관계 옵션 제시 → 사용자 선택 → `edges` INSERT
- **오타 의심 쌍** → `find_suspected_typos` 런타임 → 사용자 승인 → `merge_nodes` 실행
- **별칭 제안** → 사용자가 노드 상세에서 "별칭 추천" 요청 시에만 LLM 호출 → 승인 시 `aliases` INSERT
- **지시어 해소** → `unresolved_tokens` 읽고 옵션 제시 → 사용자 선택 → `nodes` upsert + `node_mentions` INSERT + `unresolved_tokens` DELETE
- **노드 생존 / 일일 회고 / 공백 채우기** → sentences·nodes 쿼리로 런타임 뷰 생성

## LLM 설정

| 단계 | 어댑터 | temperature | max_tokens |
|------|--------|-------------|------------|
| 전처리 치환 | synapse/save-pronoun | 0 | 256 |
| 노드/deactivate 추출 | synapse/extract | 0 | 32768 |
| 평문 → 마크다운 구조 제안 | synapse/structure-suggest | 0 | 1024 |
| 인출 확장 | synapse/retrieve-expand | 0 | 256 |
| 인출 필터 | synapse/retrieve-filter | 0 | 8 |
| /review LLM 섹션(관계·카테고리·별칭) | synapse/chat (base) | 0 | 256 |
| 응답 생성 | synapse/chat (base) | 0.3 | 4096 |

모델: gemma4:e2b (MLX, localhost:8765)

## 파인튜닝/학습 작업 규칙

**추측하지 마라. 검색해라. 실행 전에 검증해라.**

학습/파인튜닝 관련 작업 시 일반적인 ML 지식으로 추측하여 진행하지 말 것.
이 프로젝트에는 확정된 설계·하이퍼파라미터·실패 기록·성공 패턴이 이미 문서화되어 있다.

### Phase 0: 설계 파악 (반드시 읽기)

- `docs/DESIGN_FINETUNE.md` — 태스크 구조, 하이퍼파라미터, 데이터 현황, 실패 기록
- `scripts/runpod/train_all.py` — 확정된 학습 설정 (TaskConfig 클래스)
- `scripts/runpod/README.md` — RunPod 사용법, 태스크 목록

### Phase 1: 환경 검증 루틴 (실행 전 필수)

문서의 설정이 현재 환경에서 유효한지 **매번** 확인. 하루만 지나도 바뀔 수 있다.

```
[ ] 라이브러리 버전 확인
    - pip show unsloth peft transformers trl → 버전이 문서/스크립트 작성 시점과 다르면 변경사항 검색
    - 특히 unsloth, trl은 API가 자주 바뀜 (deprecated 파라미터, 클래스 이동 등)
[ ] 모델/토크나이저 확인
    - 베이스 모델 접근 가능한지 (HF 캐시 또는 다운로드)
    - chat_template이 변경되지 않았는지
[ ] 데이터 파일 존재 + 건수 확인
    - wc -l data/finetune/tasks/*/train.jsonl
    - 빈 파일, 0건 데이터 체크
[ ] GPU/VRAM 확인
    - nvidia-smi (RunPod이면 할당된 GPU 종류와 VRAM)
    - 이전 프로세스 잔류 VRAM 점유 여부
[ ] 디스크 여유 확인
    - df -h /workspace (RunPod 볼륨 용량)
[ ] 기존 어댑터 백업
    - 재학습 시 기존 결과 덮어쓰기 전 _backup 또는 타임스탬프 보존
```

### Phase 2: 소규모 검증 (첫 실행 필수)

새 환경, 새 라이브러리 버전, 새 데이터에서는 반드시 **1개 태스크 100 iters**로 먼저 돌린다.

```
[ ] 100 iters 테스트 실행 (가장 작은 태스크)
[ ] train_loss 정상 감소 확인
[ ] eval_loss 트렌드 확인 (↓이면 정상, →이면 과적합 조짐)
[ ] 출력 포맷 확인 (GGUF 변환 후 실제 프롬프트로 추론 1건)
[ ] 문제 있으면 → 전체 학습 진행하지 말고 원인 분석
```

### 금지 사항

- 하이퍼파라미터(lr, layers, alpha, batch 등)를 임의로 정하지 말 것 — 이미 확정된 값이 있음
- 이전에 실패한 접근(전체 레이어 LoRA, alpha=160 등)을 반복하지 말 것
- 환경을 가정하지 말 것 — RTX3080 없음, RunPod 사용, MLX는 로컬 테스트용
- "설정 완료"를 동작 확인 전에 말하지 말 것 — 실제 1회 실행으로 검증 후 보고
- 에러 발생 시 로그 일부만 보고 판단하지 말 것 — 성공/실패 케이스 비교 후 판단

## 환경

- **학습**: RunPod (FP16, google/gemma-4-E2B-it)
- **로컬 추론**: Mac M4 + MLX 4bit (api/mlx_server.py)
- **학습 데이터**: `data/finetune/`
- **학습 모델 (로컬)**: `data/finetune/models/`
- **RunPod 산출물**: `runpod_output/adapters/`

## 상세 설계

`docs/DESIGN_*.md` 참고:
- `DESIGN_OVERVIEW.md` — 제품 비전·데이터 정책
- `DESIGN_PIPELINE.md` — 저장/인출/응답 파이프라인 세부
- `DESIGN_ENGINE.md` — 엔진 패키지 구조 (모바일 포팅 포함)
- `DESIGN_REVIEW.md` — `/review` 섹션별 런타임 제안 도출 및 승인 흐름
- `DESIGN_CATEGORY.md` — 카테고리 분류체계
- `DESIGN_GRAPH.md` — 그래프 뷰 UX

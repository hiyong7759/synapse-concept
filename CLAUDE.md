# Synapse — 개인 지식 그래프

## 핵심 원칙 (이것부터 읽어라)

1. **노드는 원자다.** 하나의 개념 = 하나의 노드. 중복 생성 금지. 대소문자, 언어 불문 같은 개념이면 같은 노드.
2. **엣지는 선택자다.** 모든 관계, 속성, 상세 정보는 엣지로 표현한다. 노드에 데이터를 넣지 않는다.
3. **meta 컬럼, JSON 필드 같은 것을 노드에 추가하지 마라.** "기간", "전공", "담당업무" 같은 상세 정보도 전부 엣지다.
4. **동의어/다국어는 aliases 테이블.** React Native ──(same)── 리액트 네이티브 → aliases에 등록.
5. **BFS 전체 탐색 → LLM이 필터링.** 탐색 결과가 넓어도 잘라내지 마라. 사용자가 쌓은 맥락이다.
6. **모든 질문은 개인 맥락이 있으면 더 나은 답을 만든다.**

## 구조

```
노드 = 개념 (React Native, 허리디스크, 맥미니, 조용희)
엣지 = 원문의 조사 (에서, 으로, 의, 에, 를 등. 없으면 NULL)
별칭 = 키워드 매칭 강화 (aliases 테이블)
```

조사 라벨 예시:
```
나 ──(에서)── 더나은         → "나는 더나은에서 [일한다]"
박지수 ──(으로)── 개발팀장   → "박지수가 개발팀장으로 [됐다]"
허리디스크 ── L4-L5          → 조사 없는 명사 나열 (NULL)
나 ──(에)── 2018.02          → "나는 2018.02에 [입사했다]"
```

노드에 description, meta, detail, domain, weight, safety 같은 필드를 추가하는 것은 이 설계를 위반한다.
단, `category`는 예외 — BFS 검색 범위 필터링을 위해 허용. 두 종류: 사용자 지정 경로(마크다운 heading, 예: `더나은.개발팀`) 또는 LLM 기본 분류(`대분류.소분류`, 예: `BOD.disease`). 마크다운 입력 시 heading 경로가 우선, 평문은 DB 매칭 후 LLM 폴백.

## DB 스키마 (v9 — 세션리스)

```sql
nodes:     id, name(UNIQUE 아님), category, status(active|inactive), created_at, updated_at
edges:     id, source_node_id, target_node_id, label, sentence_id, created_at, last_used
aliases:   alias TEXT PRIMARY KEY, node_id INTEGER
sentences: id, text, role(user|assistant), retention(memory|daily), created_at
```

- status: active | inactive 2종. deleted 없음. 비활성화하면 엣지 보존됨.
- category: 사용자 지정 경로 (예: `더나은.개발팀`) 또는 LLM 기본 분류 (`대분류.소분류`, 예: `BOD.disease`). NULL 허용.
- edges.label: 원문의 조사 (에서, 으로, 의, 에, 를/을, 와/과 등). 조사 없으면 NULL.
- edges.last_used: 불용 엣지 판단용.
- edges: 동일 구조 엣지 중복 허용 (의도된 설계). 출처문장(sentence_id)이 다르면 별개 엣지.
- sentences.role: `user`(그래프 추출 대상) / `assistant`(대화 기록 + 메타 대화 참조용).
- sessions 테이블 없음 (세션리스 아키텍처). 그래프가 영속 메모리, sentences가 대화 기록.
- domain, source, weight, safety, edges.type, filters, filter_rules 없음 (v6에서 제거).

## CLI

```bash
python3 -m engine.cli           # 대화형 (MLX 서버 필요: python api/mlx_server.py)
python3 -m engine.cli --no-llm # LLM 없이 BFS 구조만
python3 -m engine.cli --stats  # DB 통계
python3 -m engine.cli --reset  # DB 초기화
python3 -m engine.cli --typos # 오타 의심 노드 쌍 스캔
```

DB 위치: `~/.synapse/synapse.db` (SYNAPSE_DATA_DIR 환경변수로 변경 가능)

## 아키텍처

```
engine/          ← Python 패키지. 그래프 저장/인출 파이프라인.
  db.py          ← v9 세션리스 스키마 + 연결 관리
  llm.py         ← MLX 서버 클라이언트 (localhost:8765) + 파이프라인 함수
  markdown.py    ← 마크다운 파서 (heading 경로 + 항목 분리)
  save.py        ← 저장 파이프라인 + rollback() + merge_nodes() + find_suspected_typos()
  retrieve.py    ← BFS 인출 파이프라인 + 카테고리 보완
  jamo.py        ← 한글 자모 분해 + Levenshtein 거리 (오타 교정용)
  cli.py         ← CLI 인터페이스

api/
  mlx_server.py  ← MLX 태스크 라우터 (OpenAI 호환, 어댑터 스왑)

app/             ← React 웹앱 (Vite + TypeScript) — 미구현
  src/
    components/
    pages/
    styles/tokens.css
```

## 저장 파이프라인

```
사용자 입력 → parse_markdown(text)

[마크다운 모드] heading(#) 있음:
  각 (경로, 항목)마다:
    → 항목을 sentence로 저장
    → [synapse/extract] 노드+엣지 추출 (()[] 공백 치환 전처리)
    → category를 heading 경로로 설정 (LLM 분류 무시)
    → [규칙 기반] 부정부사 후처리, 오타 교정
    → DB 저장 + 별칭 제안

[평문 모드] heading 없음:
  [1단계: 인출] synapse/retrieve-expand → BFS → 개인 맥락 수집
  [2단계: 저장]
    → [synapse/save-pronoun] 항상 호출 (직전 대화 2건을 context로 전달)
      지시대명사 치환 + 시간부사 치환 + 생략 복원 (주어/목적어/장소) + 모호성 → 질문 반환
      인칭대명사(나/내/저/제)는 치환하지 않음
    → [synapse/extract] 노드+엣지+카테고리+deactivate(sentence_id 배열) → JSON (()[] 공백 치환 전처리)
    → [규칙 기반] category DB 매칭 (사용자 지정 경로 우선, 없으면 LLM 폴백)
    → [규칙 기반] 부정부사 후처리, 오타 교정
    → DB 저장 + 별칭 제안
  [3단계: 응답] 인출 맥락 + 저장 결과 → [synapse/chat] 개인화 답변
                → sentences 저장 (role='assistant')
```

## 인출 파이프라인

```
질문
  → [synapse/retrieve-expand] 노드 후보 키워드 목록
  → DB 매칭: aliases 우선 → name 직접 → substring
  → BFS 루프: get_triples → [synapse/retrieve-filter] → 새 노드 → 반복
  → 카테고리 보완: 동대분류 미방문 노드 추가 조회 → 재필터
  → [synapse/chat] 자연어 답변
```

## LLM 설정

| 단계 | 어댑터 | temperature | max_tokens |
|------|--------|-------------|------------|
| 전처리 치환 | synapse/save-pronoun | 0 | 256 |
| 노드/엣지/카테고리/상태변경/보관유형 추출 | synapse/extract | 0 | 32768 |
| 인출 확장 | synapse/retrieve-expand | 0 | 256 |
| 인출 필터 | synapse/retrieve-filter | 0 | 8 |
| 별칭 제안 | synapse/chat (base) | 0 | 64 |
| 응답 생성 | synapse/chat (base) | 0.3 | 4096 |

모델: gemma4:e2b (MLX, localhost:8765)

## 상세 설계

`docs/DESIGN_*.md` 참고.

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
단, `category`는 예외 — BFS 검색 범위 필터링을 위해 허용 (형식: `대분류.소분류`, 예: `BOD.disease`, `MON.spending`).

## DB 스키마 (v8 — 현재)

```sql
nodes:     id, name, category, status(active|inactive), created_at, updated_at
edges:     id, source_node_id, target_node_id, label, sentence_id, created_at, last_used
aliases:   alias TEXT PRIMARY KEY, node_id INTEGER
sentences: id, session_id, paragraph_index, text, role(user|assistant), retention(memory|daily), created_at
sessions:  id, type(conversation|archive), created_at
```

- status: active | inactive 2종. deleted 없음. 비활성화하면 엣지 보존됨.
- category: `대분류.소분류` 형식 (예: `BOD.disease`, `MON.spending`). NULL 허용.
- edges.label: 원문의 조사 (에서, 으로, 의, 에, 를/을, 와/과 등). 조사 없으면 NULL.
- edges.last_used: 불용 엣지 판단용.
- sentences.role: `user`(그래프 추출 대상) / `assistant`(대화 히스토리 표시용만).
- domain, source, weight, safety, edges.type, filters, filter_rules 없음 (v6에서 제거).

## CLI

```bash
python3 -m engine.cli           # 대화형 (MLX 서버 필요: python api/mlx_server.py)
python3 -m engine.cli --no-llm # LLM 없이 BFS 구조만
python3 -m engine.cli --stats  # DB 통계
python3 -m engine.cli --reset  # DB 초기화
```

DB 위치: `~/.synapse/synapse.db` (SYNAPSE_DATA_DIR 환경변수로 변경 가능)

## 아키텍처

```
engine/          ← Python 패키지. 그래프 저장/인출 파이프라인.
  db.py          ← v8 스키마 + 연결 관리
  llm.py         ← MLX 서버 클라이언트 (localhost:8765) + 파이프라인 함수
  save.py        ← 저장 파이프라인 + rollback()
  retrieve.py    ← BFS 인출 파이프라인 + 카테고리 보완
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
사용자 입력 → sentences 저장 (role='user')
  [1단계: 인출] synapse/retrieve-expand → BFS → 개인 맥락 수집
  [2단계: 저장]
    → [규칙 기반] 시간 부사 자동 치환
    → [synapse/save-pronoun] 대명사/장소 지시어 치환, 모호성 → 질문 반환
    → [synapse/extract] retention + 노드 + 엣지 + 카테고리 + deactivate → JSON (한 번에)
    → DB 저장 (nodes, edges, sentence_id 포함, deactivate 엣지 비활성화)
    → [synapse/chat] 별칭 제안 (새 노드 시에만)
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
| 노드/엣지/카테고리/상태변경/보관유형 추출 | synapse/extract | 0 | 512 |
| 인출 확장 | synapse/retrieve-expand | 0 | 256 |
| 인출 필터 | synapse/retrieve-filter | 0 | 8 |
| 별칭 제안 | synapse/chat (base) | 0 | 64 |
| 응답 생성 | synapse/chat (base) | 0.3 | 4096 |

모델: gemma4:e2b (MLX, localhost:8765)

## 상세 설계

`docs/DESIGN_*.md` 참고.

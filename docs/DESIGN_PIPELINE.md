# Synapse 설계 — 저장/인출/대화 파이프라인

**최종 업데이트**: 2026-04-09 (통합 파이프라인, v8 스키마, 어댑터 목록 정리)

## 근본 목표

> 저장, 인출, 대화 전체에서 실제로 가치 있게 동작하되, 최소한의 리소스로.

---

## DB 스키마 (현재)

```sql
sessions:  id, type('conversation'|'archive'), created_at
sentences: id, session_id, paragraph_index, text, role('user'|'assistant'), retention('memory'|'daily'), created_at
nodes:     id, name, category, status('active'|'inactive'), created_at, updated_at
edges:     id, source_node_id, target_node_id, label, sentence_id, created_at, last_used
aliases:   alias TEXT PRIMARY KEY, node_id
```

**sentences.role**
- `user`: 사용자 입력. 그래프 추출 대상.
- `assistant`: 모델 응답. 대화 히스토리 표시용만. 그래프 추출 제외.

**nodes.category**: `대분류.소분류` 형식 (예: `BOD.disease`, `MON.spending`). NULL 허용.
저장 시 LLM이 자동 부여. 분류체계 상세 → `docs/DESIGN_CATEGORY.md`.

**sessions.type**
- `conversation`: 일반 대화 세션
- `archive`: 월별 장기 보관함 (콤팩팅으로만 유입). `strftime('%Y-%m', created_at)`으로 월 식별.

**sentences.retention**
- `memory`: 잘 변하지 않는 사실·상태·이력. LLM이 저장 시 판단.
- `daily`: 순간적 활동·감정·일상. 콤팩팅 시 기본 제외 대상.

---

## 통합 파이프라인

모든 대화 입력에 대해 **인출 → 저장 → 응답** 3단계가 항상 실행된다.
의도(저장/인출/일반대화) 분기 없음. 모든 응답이 개인 맥락을 반영한다.

### LLM 추출 출력 형식 (synapse/extract)

LLM이 형태소 분석 없이 노드·엣지·카테고리·상태변경을 한 번에 추출한다.

```json
{
  "retention": "memory|daily",
  "nodes": [{"name": "노드명", "category": "대분류.소분류"}],
  "edges": [{"source": "노드명", "label": "조사", "target": "노드명"}],
  "deactivate": [{"source": "노드명", "target": "노드명"}]
}
```

추출 규칙:
- 노드는 원자 (하나의 개념 = 하나의 노드)
- 개인 모드: 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드 추출. 없으면 미생성 + 엣지에도 미사용.
- 조직 모드: 1인칭 → 사용자 이름으로 치환, 주어 항상 명시
- 3인칭 주어는 원문 그대로 노드 추출
- 엣지 label = 원문의 조사 그대로. 조사 없으면 null.
- `deactivate`: 상태변경으로 비활성화할 기존 엣지 목록 (1단계 인출 결과 참조)

### 파이프라인 흐름

```
사용자 입력
  ↓ sentences 저장 (role='user')
[1단계: 인출]  temperature=0
  [LLM — synapse/retrieve-expand] 키워드 추출
  → DB 매칭 (aliases 우선 → name → substring)
  → BFS 루프 (양방향, max_layers=5, visited 수렴)
  → 개인 맥락 수집 + 상태변경 감지용 기존 문장 조회
  ↓
[2단계: 저장]
  [전처리 — 규칙 기반] 시간 부사 → session 날짜 자동 치환
  [전처리 — LLM synapse/save-pronoun]  temperature=0, max_tokens=256
    대명사·장소 지시어 → 구체값 치환
    모호하면 {"question": ...} 반환 → 저장 중단
  [LLM — synapse/extract]  temperature=0, max_tokens=512
    노드 + 엣지 + 카테고리 + deactivate → JSON
  DB 저장:
    nodes upsert (name + category)
    edges insert (sentence_id 포함)
    deactivate 엣지 → status='inactive'
  [별칭 추가 — 기본]
    새 노드 → aliases 자동 등록 (줄임말·외래어·다국어)
    [LLM — synapse/chat] 동의어 제안 (새 노드 시에만)
  ↓
[3단계: 응답]  temperature=0.3, max_tokens=1024
  인출 맥락 + 저장 결과 종합 → [LLM — synapse/chat] 개인화 답변
  답변 → sentences 저장 (role='assistant')
```

> **응답 max_tokens=4096** (~3,000자 한국어 기준). 이력서·요약·계획서 등 긴 결과물 태스크 대응 + 2B 모델 런어웨이 상한 보장.

---

## 세션 관리

### 문장 수정 (`update_sentence`)

```
sentence_id + new_text
  → sentences.text UPDATE
  → 해당 sentence_id edges DELETE + 고아 노드 정리
  → new_text 재분석 → 새 edges INSERT (동일 sentence_id 재사용)
```

### 세션 삭제 (`rollback_session`)

`edges.sentence_id`는 `ON DELETE SET NULL`이므로 순서 중요:

```
1. 해당 session의 sentences 조회
2. sentence_id로 연결된 edges 삭제
3. 고아 노드 (다른 edges 없는 노드) 삭제
4. session DELETE → sentences CASCADE 삭제
```

`preview_session_delete(session_id)` → 제거될 edges + 고아 노드 미리보기 반환.

### 콤팩팅 (`compact_session`)

```
session_id + selected_sentence_ids
  → get_or_create_archive_session('YYYY-MM')  ← strftime('%Y-%m', created_at) 기준
  → 선택 sentences.session_id → archive session으로 이동
  → 비선택 sentences → edges 삭제 + 고아 노드 정리 + sentences 삭제
  → 원본 session 삭제
```

---

## 인출 (1단계 상세)

통합 파이프라인의 1단계. 모든 대화에서 항상 먼저 실행된다.

```
[LLM — synapse/retrieve-expand]  temperature=0, max_tokens=256
  질문 의도 해석 → 관련 노드 후보 키워드 추출
  ↓
[원문 토큰 병합]
  질문 원문을 공백 분리 → keywords에 병합
  ↓
[DB 매칭]
  1. aliases 정확 매칭 우선
  2. name 정확 매칭
  3. name substring 매칭
  ↓
[BFS 루프]  max_layers=5
  현재 노드 집합 → 연결 엣지 + 원본 문장 조회 (sentences LEFT JOIN)
  → [LLM — synapse/retrieve-filter] 관련성 판단 (관련/무관)
  → 관련 문장의 새 노드 → 다음 레이어
  새 노드 없으면 종료
  ↓
[카테고리 보완]
  시작 노드 소분류 → ADJACENT_SUBCATEGORIES 1-hop → 해당 소분류 노드 조회
  → synapse/retrieve-filter로 재필터
  ↓
[last_used 배치 업데이트]  BFS 완료 후 1회
```

### 종료 보장

```python
visited = set()
while True:
    new_nodes = 이번 레이어 통과 노드 - visited
    if not new_nodes:
        break
    visited.update(new_nodes)
```

### 카테고리 보완 목적

파편화된 입력으로 BFS 미연결 시 보완. 소형 모델의 탐색 범위 한계도 보완.
상세 설계(분류체계, 인접 맵, 독립 소분류) → `docs/DESIGN_CATEGORY.md`

---

## 노드 카테고리

`nodes.category`: `대분류.소분류` 형식. NULL 허용.
- 저장 시 synapse/extract LLM이 카테고리 부여 (노드/엣지와 함께 단일 호출)
- 인출 시 소분류 인접 맵(1-hop)으로 보완 조회 → `engine/retrieve.py`의 `ADJACENT_SUBCATEGORIES`

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

## 어댑터 구성 (현재)

| 엔드포인트 (model) | 태스크 | 학습 iters | val_loss | 상태 |
|--------------------|--------|-----------|---------|------|
| `synapse/retrieve-filter` | 인출 관련성 판단 (관련/무관) | 670 | 0.311 | 완료 |
| `synapse/retrieve-expand` | 질문 → 노드 후보 키워드 확장 | 740 | 0.412 | 완료 |
| `synapse/retrieve-expand-org` | 질문 → 조직 노드 후보 키워드 확장 | 540 | 0.131 | 완료 |
| `synapse/routing` | 개인/조직 모드 라우팅 판단 | 400 | 0.174 | 완료 |
| `synapse/save-pronoun` | 대명사/날짜/장소 지시어 치환 | 550 | 0.338 | 완료 |
| `synapse/save-state-org` | 조직 그래프 상태변경 감지 | 400 | 0.253 | 완료 |
| `synapse/save-subject-org` | 조직 모드 주체 파악 | 680 | 0.262 | 완료 |
| `synapse/security-access` | 접근 권한 판단 | 660 | 0.335 | 완료 |
| `synapse/security-context` | 보안 컨텍스트 분류 | 550 | 0.278 | 완료 |
| `synapse/security-org` | 조직 보안 정책 적용 | 540 | 0.120 | 완료 |
| `synapse/security-personal` | 개인 보안 정책 적용 | 1900 | 0.280 | 완료 |
| `synapse/extract` | 노드/엣지/카테고리/상태변경 추출 | 600 | 0.286 | **재학습 필요** |
| `synapse/chat` | 대화, 별칭 제안 | — | — | 베이스 모델 (어댑터 없음) |

> `synapse/save-state-personal` 제거 — synapse/extract의 `deactivate` 필드로 통합됨.

**task6 데이터**: `archive/finetune/data/task6_*.jsonl` — 1,677건 (카테고리별 40~236건, 17개 대분류 전체 커버)
→ `deactivate` 필드 추가로 재학습 필요.

---

## LLM 설정값

| 단계 | 어댑터 | temperature | max_tokens |
|------|--------|-------------|------------|
| 인출 확장 | synapse/retrieve-expand | 0 | 256 |
| 인출 필터 | synapse/retrieve-filter | 0 | 8 |
| 전처리 치환 | synapse/save-pronoun | 0 | 256 |
| 노드/엣지/카테고리/상태변경 추출 | synapse/extract | 0 | 512 |
| 별칭 제안 | synapse/chat (base) | 0 | 64 |
| 응답 생성 | synapse/chat (base) | 0.3 | 4096 |

---

## LLM 역할 요약

| 단계 | 어댑터 | 역할 |
|------|--------|------|
| 1단계 인출 — 확장 | retrieve-expand | 질문 의도 → 노드 후보 키워드 |
| 1단계 인출 — 필터 | retrieve-filter | 관련성 판단 (관련/무관) |
| 2단계 저장 — 전처리 | save-pronoun | 대명사/날짜/장소 지시어 치환, 모호성 질문 반환 |
| 2단계 저장 — 추출 | extract | 노드+엣지+카테고리+deactivate 한 번에 추출 |
| 2단계 저장 — 별칭 | chat (base) | 동의어 자동 제안 (새 노드 시에만) |
| 3단계 응답 | chat (base) | 인출 맥락 + 저장 결과 종합 → 개인화 답변 |

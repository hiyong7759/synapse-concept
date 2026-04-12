# Synapse 설계 — 저장/인출/대화 파이프라인

**최종 업데이트**: 2026-04-11 (v9 세션리스 스키마, 메타 대화/직전 맥락 추가)

## 근본 목표

> 저장, 인출, 대화 전체에서 실제로 가치 있게 동작하되, 최소한의 리소스로.

---

## DB 스키마 (v9 — 세션리스)

```sql
sentences: id, text, role('user'|'assistant'), retention('memory'|'daily'), created_at
nodes:     id, name, category, status('active'|'inactive'), created_at, updated_at
edges:     id, source_node_id, target_node_id, label, sentence_id, created_at, last_used
aliases:   alias TEXT PRIMARY KEY, node_id
```

**sentences.role**
- `user`: 사용자 입력. 그래프 추출 대상.
- `assistant`: 모델 응답. 대화 기록 + 메타 대화 참조용. 그래프 추출 제외.

**nodes.category**: 두 종류.
- 사용자 지정 경로: 마크다운 heading에서 생성 (예: `더나은.개발팀`, `취업규칙.근로시간`). 깊이 제한 없음.
- LLM 기본 분류: `대분류.소분류` 형식 17개 (예: `BOD.disease`, `MON.spending`). 마크다운 heading 없는 평문에서 폴백.
NULL 허용. 분류체계 상세 → `docs/DESIGN_CATEGORY.md`.

**sentences.retention**
- `memory`: 잘 변하지 않는 사실·상태·이력. LLM이 저장 시 판단.
- `daily`: 순간적 활동·감정·일상.

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
  "deactivate": [sentence_id, ...]
}
```

deactivate는 sentence_id 배열. 알려진 사실에 `[번호]`가 붙어서 제공되며, 현재 입력과 상충되는 문장의 번호를 반환. 해당 sentence_id에 연결된 엣지가 전부 비활성화됨.

추출 규칙:
- 노드는 원자 (하나의 개념 = 하나의 노드)
- 개인 모드: 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드 추출. 없으면 미생성 + 엣지에도 미사용.
- 조직 모드: 1인칭 → 사용자 이름으로 치환, 주어 항상 명시
- 3인칭 주어는 원문 그대로 노드 추출
- 엣지 label = 원문의 조사 그대로. 조사 없으면 null.
- `deactivate`: 상태변경으로 비활성화할 기존 엣지 목록 (1단계 인출 결과의 원본 문장들을 "알려진 사실:" 형태로 참조)

### 입력 모드

사용자 입력은 마크다운 파서(`engine/markdown.py`)를 먼저 거친다.
heading(`#`)이 하나라도 있으면 **마크다운 모드**, 없으면 **평문 모드**.

#### 마크다운 모드 — 문서 입력

```markdown
# 더나은
## 개발팀
- 팀장 박지수
- 프론트엔드 김민수
```

→ heading 경로(`더나은.개발팀`) + 각 항목을 개별 extract.
→ 추출된 노드의 category를 heading 경로로 설정 (LLM 분류 무시).
→ 각 항목이 개별 sentence로 저장.

계층 입력 두 방식 (동일 결과):
- `# 더나은.개발부.개발팀` (점 구분 한 줄)
- `# 더나은` → `## 개발부` → `### 개발팀` (heading 중첩)

#### 평문 모드 — 대화 입력

기존 파이프라인 + category DB 매칭 추가.
추출된 노드 이름으로 DB의 사용자 지정 category를 검색하여 매칭.
매칭 안 되면 LLM 17개 기본 분류 폴백.

### 파이프라인 흐름

```
사용자 입력
  ↓ parse_markdown(text)
  ↓
[마크다운 모드] heading 있음
  각 (경로, 항목)마다:
    → 항목을 sentence로 저장
    → [LLM — synapse/extract] 노드+엣지 추출
    → category를 heading 경로로 설정
    → [후처리] 부정부사, 오타 교정
    → DB 저장 (nodes, edges, aliases)
  ↓
[평문 모드] heading 없음
  ↓ sentences 저장 (role='user')
  [1단계: 인출]  temperature=0
    [LLM — synapse/retrieve-expand] 키워드 추출
    → DB 매칭 (aliases 우선 → name → substring)
    → BFS 루프 (양방향, max_layers=5, visited 수렴)
    → 개인 맥락 수집 + 상태변경 감지용 기존 문장 조회
    ↓
  [2단계: 저장]
    [전처리 — LLM synapse/save-pronoun]  temperature=0
      항상 호출 (조건 체크 없음). 직전 대화 2건을 DB에서 조회하여 context로 전달.
      지시대명사(이거/거기 등) → 구체값 치환
      생략된 주어/목적어/장소 → 직전 대화에서 복원 (예: "엑셀 못해" + 직전 "김부장 짜증나" → "김부장이 엑셀 못해")
      인칭대명사(나/내/저/제)는 치환하��� 않음
      시간부사(어제/오늘 등) → 날짜 치환
      복원/치환 불가하면 {"question": ...} 반환 → 저장 중단
    [LLM — synapse/extract]  temperature=0, max_tokens=32768
      입력: 사용자 텍스트 + "알려진 사실:" (인출 원본 문장들)
      출력: 노드 + 엣지 + 카테고리 + deactivate → JSON
      전처리: ()[] 공백 치환 (2B 모델 반복 루프 방지)
    [후처리 — category DB 매칭]
      추출된 노드 이름으로 DB category 검색 → 사용자 지정 경로 매칭
      매칭 안 되면 LLM 기본 분류 유지
    [후처리 — 부정부사(안/못)]
      1차: extract가 label에 "안"/"못"을 넣은 경우 → 노드+엣지로 변환
      2차: 문장에 안/못이 있는데 1차에서 미감지 → LLM 2-pass로 대상 특정
    [후처리 — 오타 교정]
      추출된 노드 이름을 기존 노드+별칭과 자모 분해 Levenshtein 거리 비교
      distance == 1 && 자모 길이 >= 6 → 기존 노드 이름으로 치환
      치환된 오타는 별칭으로 자동 등록 (재발 방지)
      LLM 호출 없음, 규칙 기반
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

## 문장 관리

### 문장 수정 (`update_sentence`)

```
sentence_id + new_text
  → sentences.text UPDATE
  → 해당 sentence_id edges DELETE + 고아 노드 정리
  → new_text 재분석 → 새 edges INSERT (동일 sentence_id 재사용)
```

### 문장 삭제 (`rollback_sentences`)

```
sentence_id 목록
  → 해당 sentence_id로 연결된 edges 삭제
  → 고아 노드는 보존 (재연결 가능성)
  → sentences 삭제
```

### 콤팩팅

sentence 단위 정리. 고아 노드는 보존 (재연결 가능성).

**대상 조건** (세 조건 모두 충족):
- `retention='daily'`
- `edges.last_used IS NULL` (한 번도 인출 안 됨)
- `created_at`이 N일 이상 경과

**트리거**: 앱 시작 시 조건 체크. 대상 있으면 실행 (사용자 설정에 따라).

**사용자 설정**:
- 자동 정리: ON/OFF (기본 OFF)
- 보관 기간: N일 (기본 30일)
- 정리 전 확인: ON/OFF (기본 ON)

```
앱 시작
  → 자동 정리 OFF → 패스
  → 자동 정리 ON → 대상 수집
    → 0건 → 패스
    → 정리 전 확인 ON → "N건 정리할까요?" 알림
    → 정리 전 확인 OFF → 자동 삭제
```

구현: `compact()` 함수 — 앱 구현 시점에 `engine/db.py` 또는 `engine/save.py`에 추가. 현재 엔진에는 미구현.

---

## 직전 맥락 / 메타 대화

### 직전 맥락

매 메시지 처리 시, sentences 테이블에서 **최근 3턴(user+assistant 3쌍)**을 자동 포함.
save-pronoun에 context로 전달하여 대명사/지시어 해소에 사용.

### 메타 대화 패턴 감지

"계속해", "자세하게", "아까 말한 거" 등 대상이 생략된 발화는 규칙 기반으로 감지하여
시간/턴 기반으로 sentences를 조회한 뒤 처리.

| 패턴 | 조회 범위 |
|------|-----------|
| "계속해", "자세하게", "다시 해줘" | 직전 1~2턴 |
| "아까 말한 거", "방금 그거" | 최근 수분~1시간 |
| "오전에 얘기한 거", "어제 그거" | 시간 범위 필터 |

### 과거 대화 검색

사용자 요청 시 sentences + 그래프 기반 검색. LLM 전달 문장 수 제한 없음 (실사용 품질 기반 조정).

| 검색 방식 | 예시 |
|-----------|------|
| 키워드 (노드/별칭) | "허리 관련 대화" → 노드 → edges → sentence_id → sentences |
| 시간 | "어제 대화" → created_at 필터 |
| 카테고리 | "건강 관련" → BOD 카테고리 노드 → 연결 sentences |
| 복합 | "지난달 병원 관련" → 시간 + 노드 교차 |

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
  → [LLM — synapse/retrieve-filter] 엣지의 sentence_text(원본 문장)로 관련성 판단 (관련/무관)
    같은 sentence_id는 재판단 없이 스킵 (visited_sentence_ids 추적)
  → 통과 문장의 새 노드 → 다음 레이어
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
| 1단계 인출 — 필터 | retrieve-filter | 엣지의 원본 문장(sentence_text)으로 관련성 판단 |
| 2단계 저장 — 전처리 | save-pronoun | 대명사/날짜/장소 지시어 치환, 모호성 질문 반환 |
| 2단계 저장 — 추출 | extract | 노드+엣지+카테고리+deactivate 한 번에 추출 |
| 2단계 저장 — 별칭 | chat (base) | 동의어 자동 제안 (새 노드 시에만) |
| 3단계 응답 | chat (base) | 인출 원본 문장들("알려진 사실:") + 저장 결과 → 개인화 답변 |

---

## assistant 응답 그래프화 (미래)

현재: `role='assistant'` sentences에만 저장. 그래프 추출 안 함.
이유: 2B 로컬 모델 응답이 사용자 말 되풀이 수준. 그래프화 가치 < 부하 증가.

**재검토 조건:**
- 모델 품질 향상 (응답에 새로운 인사이트/분석 포함)
- 도구 확장으로 외부 데이터 수집 시

---

## 도구 라우팅 (미래)

앱 레이어에서 규칙 기반으로 도구 호출 판단 (LLM 판단 아님, 2B 모델로는 신뢰성 부족).

**저장 기준:** 원본이 사라지면 다시 얻을 수 없는 결과만 그래프에 저장. 다시 조회/계산 가능한 결과는 저장하지 않음.

| 도구 | save | 이유 |
|------|:---:|------|
| 날씨 API | false | 다시 조회 가능 |
| 웹 검색 | false | 다시 검색 가능 |
| 뉴스 조회 | false | 다시 검색 가능 |
| 번역 | false | 다시 번역 가능 |
| 계산기 | false | 다시 계산 가능 |
| 단위/환율 변환 | false | 다시 변환 가능 |
| 지도/경로 검색 | false | 다시 검색 가능 |
| 캘린더 조회 | false | 앱 내 히스토리 있음 |
| 연락처 조회 | false | 디바이스에 있음 |
| 알림/리마인더 | false | OS에서 관리 |
| OCR (명함/처방전) | **true** | 원본 삭제 시 재추출 불가 |
| 문서 파싱 (PDF) | **true** | 파일 삭제 시 재추출 불가 |
| 음성 메모 (STT) | **true** | 원본 삭제 시 재변환 불가 |
| 개인 데이터 종합/분석 | **true** | 시점 기반 그래프 도출 결과 |

각 도구에 `save` 속성을 등록 시점에 설정. 런타임 판단 불필요.

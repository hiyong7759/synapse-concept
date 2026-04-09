# Synapse 분류 정확도 개선 — 설계서

## 핵심 원칙

### 1. 도메인은 노드다
```
기존: Docker [domain=기술]  ← 메타데이터 라벨
이후: Docker --(종류)--> 기술  ← 그래프 관계
```
- domain 컬럼 삭제
- 도메인은 선언하는 게 아니라 많은 관계를 가진 노드가 자연히 도메인이 됨
- 사람마다 다른 허브가 생김 — 개발자에겐 "기술"이 허브, 다른 사람에겐 그냥 노드일 수 있음

### 2. 복합명사는 그래프가 해결한다
```
기존 생각: "허리디스크" → 하나의 노드로 인식 → Stanza 필요
실제:      허리 --(관련)--> 디스크  (분리 노드 + 엣지)
           맥미니 --(모델)--> M4 --(라인업)--> 프로
```
- "맥미니" 검색 → BFS → M4, M5 모두 도달
- 복합명사 경계 탐지 불필요 → Stanza 역할 재정의

### 3. 공통사전이 저장 품질을 결정한다
```
저장 시: 형태소 → 공통사전 참조(메모리) → 있으면 그 노드명 사용, 없으면 새 노드 생성
인출 시: 형태소 → 사용자 그래프만 검색 → 없으면 진짜 없는 것
```
- 저장이 품질 게이트 — 저장이 맞으면 인출은 단순해짐
- 공통사전: 메모리 상주, DB write 없음
- 사용자 노드와 연결되는 순간 해당 노드명으로 저장

### 4. 조사가 엣지 방향을 결정한다
```
조사 → 방향
이/가, 은/는  → source
을/를        → target
에           → target (장소/도착)
에서         → source (출발/출처)
으로/로      → target (수단/방향)
의           → source → target (소유)
에게/한테/께 → target (수신)
와/과        → 방향 없음 (협력/공동)
보다/처럼    → 방향 없음 (비교)
이라고/라고  → target (별칭)
```
- BFS가 양방향이라 방향이 틀려도 노드는 찾음 — 저장 방향 오류가 miss로 이어지지 않음
- 조사 정보는 라벨로 표현됨 (수신, 협력, 비교, 별칭 등)

### 5. Kiwi + Stanza 역할 분담

LLM 최소화 목표 — 로컬 처리 우선.

| 도구 | 역할 |
|------|------|
| **Kiwi** | 조사 분리 → 방향 결정, 명사/외국어 추출, 사용자 사전(기존 노드 등록), NP 감지 |
| **Stanza** | 단일 입력 내 대명사 해소 (로컬, no LLM) |

대명사 처리:

| 케이스 | 처리 |
|--------|------|
| 단일 입력 내 ("A 만났다. 그가...") | Stanza 로컬 해소 |
| "나", "저" | identity 노드 고정 매핑 |
| 교차 호출 지시대명사 | **저장 경로에서만** 되물음 → 치환 후 재처리 |
| 인출 경로의 미해소 대명사 | 무시, 나머지 키워드로만 BFS |

```python
CROSS_TURN_PRONOUNS = {"그", "그가", "그는", "그를", "그것", "거기", "그곳", "이것", "저것"}

# 저장 경로에서만
if token in CROSS_TURN_PRONOUNS and not stanza_resolved:
    ask_user(f"'{token}'이 누구/무엇을 가리키나요?")
    # 응답 받으면 치환 후 파이프라인 재진입
```

---

## 공통사전 소스 (메모리 상주)

**행정안전부 공공데이터 공통표준용어**
- 13,176개 표준용어 — 공공 DB 컬럼명이자 개인 프로필 어휘 (연간급여액, 재직여부, 주민등록번호 등)
- 한글명 + 영문약어 + 동의어 → 메모리 dict에 적재
- 라이선스: 이용허락범위 제한 없음 (상업 이용 가능)
- 파일: `docs/행정안전부_공공데이터 공통표준용어_20251101.csv`
- 컬럼: `공통표준용어명`, `공통표준용어영문약어명`, `공통표준도메인명`, `용어 이음동의어 목록`

**보완 소스:**
- 법령 복합용어: `seeds/legal.txt` — `통상임금`, `연차유급휴가`, `육아휴직`, `귀책사유` 등 100~200개
- 의학 용어: `seeds/medical.csv` — 일상 질환 50~100개 수동 등록 후 KCD 확장

### seed_loader.py 메모리 로드 전략

```python
# seed_loader.py — DB write 없음, 메모리 전용
SEED_DICT: dict[str, str] = {}           # canonical_name → canonical_name
SEED_ALIASES: dict[str, str] = {}        # alias/약어/동의어 → canonical_name
SEED_COMPONENTS: dict[str, list[str]] = {}  # 형태소 → [복합어들] (역방향 인덱스)

def load_seed(csv_paths: list[str]):
    for csv_path in csv_paths:
        for row in read_csv(csv_path):
            name = row['공통표준용어명']
            abbr = row['공통표준용어영문약어명']
            synonyms = row['용어 이음동의어 목록']
            domain_type = extract_type_prefix(row['공통표준도메인명'])

            # 1. 용어 → SEED_DICT
            SEED_DICT[name] = name

            # 2. 영문약어 → SEED_ALIASES
            if abbr:
                SEED_ALIASES[abbr] = name

            # 3. 이음동의어 → SEED_ALIASES
            for syn in synonyms.split(';'):
                if syn.strip():
                    SEED_ALIASES[syn.strip()] = name

            # 4. Kiwi 형태소 분해 → SEED_COMPONENTS (역방향)
            morphs = kiwi_split(name)  # ["주민", "등록", "번호"]
            for morph in morphs:
                SEED_COMPONENTS.setdefault(morph, []).append(name)

def match_seed(token: str) -> str | None:
    """형태소/약어 → canonical_name. 없으면 None."""
    return SEED_ALIASES.get(token) or SEED_DICT.get(token)

def expand_seed(morph: str) -> list[str]:
    """형태소 → 해당 형태소를 포함하는 복합어 목록."""
    return SEED_COMPONENTS.get(morph, [])
```

**예시:**
```
CSV 행: 연간급여액 | ANNU_SALRY_AMT | 금액N1000 | 연봉액;급여총액

→ SEED_DICT["연간급여액"] = "연간급여액"
→ SEED_ALIASES["ANNU_SALRY_AMT"] = "연간급여액"
→ SEED_ALIASES["연봉액"] = "연간급여액"
→ SEED_ALIASES["급여총액"] = "연간급여액"
→ SEED_COMPONENTS["연간"].append("연간급여액")
→ SEED_COMPONENTS["급여"].append("연간급여액")
→ SEED_COMPONENTS["액"].append("연간급여액")
```

**Kiwi 사용자 사전 등록:**
```python
# seed 로드 후 Kiwi 사용자 사전에 등록 → 복합어 분리 방지
for name in SEED_DICT:
    kiwi.add_user_word(name, 'NNG')  # 분리 없이 통째로 인식
```

---

## DB 스키마 변경

```sql
-- nodes: domain 컬럼 제거, source는 user/ai만 (seed 없음)
nodes: id, name, status, source, weight, safety, safety_rule, created_at, updated_at
-- source: 'user' | 'ai'
-- status: 'active' | 'inactive'

-- edges: seq 컬럼 추가 (문서 구조 순서 보존)
edges: id, source_node_id, target_node_id, type, label, seq, created_at, last_used
-- seq: INTEGER NULL — 문서 구조 엣지(항/호)에만 부여, 일반 관계 엣지는 NULL

-- filter_rules: domain 문자열 → hub_node_id 참조로 변경
filter_rules: id, filter_id, hub_node_id, node_id, action(exclude)
-- hub_node_id: 해당 허브 노드와 연결된 모든 노드를 제외
-- node_id: 특정 노드 단독 제외 (기존 유지)
```

---

## BFS 탐색 전략 (Option C)

양방향 1-hop + 정방향 2-hop 이상

```python
def calc_hub_threshold(conn) -> int:
    """그래프 중앙값의 3배. 최소 10."""
    degrees = conn.execute("SELECT COUNT(*) c FROM edges GROUP BY source_node_id").fetchall()
    if not degrees:
        return 10
    median = sorted(d['c'] for d in degrees)[len(degrees) // 2]
    return max(10, median * 3)

def bfs(start_nodes, conn, max_depth=3):
    hub_threshold = calc_hub_threshold(conn)
    visited = set(start_nodes)

    # depth 1: 양방향 (역방향 포함 — 앵커 탐색, 공문서 역추적)
    layer = get_neighbors_bidirectional(start_nodes, conn)
    visited.update(layer)

    # depth 2~: 정방향만 + 허브 경유 차단
    queue = layer
    for depth in range(2, max_depth + 1):
        next_layer = set()
        for node_id in queue:
            if get_degree(node_id, conn) >= hub_threshold:
                continue
            neighbors = get_neighbors_forward(node_id, conn)
            next_layer.update(n for n in neighbors if n not in visited)
        visited.update(next_layer)
        queue = next_layer
    return visited
```

### seq 기반 선순위 탐색

```python
def get_prior_siblings(node_id, conn):
    """같은 parent의 선순위 항들을 seq 기준으로 반환. 조 경계 넘지 않음."""
    parent_edge = conn.execute(
        "SELECT source_node_id, seq FROM edges WHERE target_node_id = ? AND seq IS NOT NULL",
        (node_id,)
    ).fetchone()
    if not parent_edge or parent_edge['seq'] <= 1:
        return []
    siblings = conn.execute(
        """SELECT target_node_id FROM edges
           WHERE source_node_id = ? AND seq < ? AND seq IS NOT NULL ORDER BY seq""",
        (parent_edge['source_node_id'], parent_edge['seq'])
    ).fetchall()
    return [s['target_node_id'] for s in siblings]
```

---

## 엣지 라벨 정규화

559개 자유형 라벨 → **45개 정규 라벨**

```python
CANONICAL_LABELS = {
    # 조직
    "소속", "담당", "역할", "직급", "근무",
    # 교육
    "전공", "졸업", "입학",
    # 기술
    "프레임워크", "언어", "도구", "설치", "빌드",
    # 장비/스펙
    "모델", "라인업", "스펙", "OS", "RAM",
    # 위치
    "거주", "근무지", "위치",
    # 시간
    "기간", "입사", "퇴사", "취득",
    # 건강
    "부위", "원인", "제약", "증상",
    # 관계
    "종류", "관련", "소유", "사용", "포함",
    # 프로젝트
    "발주", "고객사", "플랫폼",
    # 조사 대응
    "수신", "협력", "비교", "별칭", "이동", "수단",
    # 문서 구조
    "구성", "참조", "타입", "조건",
}
```

559→45 매핑: `label_mapping.json` — 상위 20개 라벨(전체 50%)부터 먼저, 나머지는 가장 가까운 정규 라벨로.

---

## 문서 구조 앵커

```
취업규칙 --(포함)--> 35조
35조     --(제목)--> 연차유급휴가
35조     --(항, seq=1)--> 35조1항
35조1항  --(조건)--> 80퍼센트이상출근
35조1항  --(부여)--> 15일
```

앵커 패턴:

```python
ANCHOR_PATTERNS = [
    (r'제\s*(\d+)\s*장', lambda m: f'{m.group(1)}장'),
    (r'제?\s*(\d+)\s*조(?!\s*(?:원|달러|엔|위안|억|만|천))', lambda m: f'{m.group(1)}조'),
    (r'[①-⑳]', lambda m: m.group(0)),
    (r'제?\s*(\d+)\s*항', lambda m: f'{m.group(1)}항'),
    (r'^(\d+)\s*\.', lambda m: f'{m.group(1)}호'),
    (r'제?\s*(\d+)\s*호', lambda m: f'{m.group(1)}호'),
]
```

---

## 파이프라인

```
입력 텍스트
  ↓
[Stage 0] Kiwi 형태소 분석
  - 명사/외국어 → 노드 후보
  - 조사 태그 → 엣지 방향 + 라벨 힌트
  - NP 감지 → Stanza에 위임
  ↓
[Stage 0'] Stanza 대명사 해소 (NP 있을 때만)
  ↓
  ├── 저장 경로                         인출 경로
  │                                       │
  [Stage 1] 공통사전 참조(메모리)       [Stage 1'] 사용자 그래프 검색
  SEED_DICT/ALIASES/COMPONENTS           형태소 → 정확 매칭
  히트 → 기존 노드명 사용               없으면 "없음" 반환
  미스 → 새 노드 후보                     │
  │                                     [Stage 2'] BFS Option C
  [Stage 2] LLM 구조화                   양방향 1-hop + 정방향 2-hop
  조사 힌트 포함 프롬프트                 동적 threshold 적용
  45개 정규 라벨 사용                    seq 선순위 탐색
  │                                       │
  [Stage 3] 후처리 검증                 [Stage 3'] 프롬프트 조립
  스키마, 라벨 정규화                    seq 기반 순서 정렬
  │
  저장
```

---

## 숫자 처리 규칙

| 케이스 | 처리 | 예시 |
|--------|------|------|
| 단독 수량 숫자 | 버림 | `1`, `80`, `3` |
| 숫자 + 단위 | 합쳐서 노드 | `15일`, `2006년`, `80퍼센트` |
| 영문 + 숫자 | 합쳐서 노드 | `M4`, `v3`, `iPhone15` |
| 조항 번호 | 앵커 노드 보존 | `35조`, `74조` |
| 항/호 번호 | 앵커 노드 보존 | `①②`, `1호`, `2호` |

---

## 구현 순서

| Phase | 작업 | 파일 | 우선순위 |
|-------|------|------|----------|
| **1** | `morpho.py` — Kiwi 단독, 조사→방향+라벨 | 신규 | 높음 |
| **1** | `seed_loader.py` — CSV 메모리 로드 (DICT+ALIASES+COMPONENTS), Kiwi 사전 등록 | 신규 | 높음 |
| **1** | `prematch.py` — seed 참조 + 사용자 그래프 노드 매칭 | 신규 | 높음 |
| **1** | `label_mapping.json` — 559→45 매핑 테이블 | 신규 | 높음 |
| **2** | `migrate_domain_to_nodes.py` — domain→종류 엣지 + filter_rules + rollback | 신규 | 높음 |
| **2** | `init_db.py` — domain 제거, source는 user/ai만, edges.seq 추가 | 수정 | 높음 |
| **2** | `get_context.py` — BFS Option C, 동적 threshold, 상향 탐색 종료, seq 선순위 | 수정 | 높음 |
| **2** | `system_prompt.py` — 45 라벨, 조사 힌트 | 수정 | 중간 |
| **3** | `postprocess.py` — 스키마 검증, 라벨 정규화 | 신규 | 중간 |
| **3** | `add_nodes.py` — 파이프라인 통합, Stanza, 되물음, doc_mode, seq 카운터 | 수정 | 중간 |
| **4** | `graph-search.ts` — domain 필터 제거, BFS Option C (Poomacy) | 수정 | 낮음 |

---

## 검증

1. BFS Option C — 양방향 1-hop 앵커 역추적 정상 동작
2. 동적 threshold — 그래프 성장에 따라 허브 차단 조정
3. 상향 탐색 종료 — "제목" 엣지 도달 시 탐색 멈춤
4. seq 선순위 탐색 — 조 경계 넘지 않음
5. 공통사전 히트율 — 저장 시 seed 매칭 비율
6. SEED_COMPONENTS 정확도 — 단형 형태소 → 복합어 유도 오탐 없음
7. 라벨 정규화 eval — `eval_model.py` Edge F1 비교
8. doc_mode 격리 — 일반 대화 앵커 오탐 없음
9. 대명사 되물음 — 교차 호출 감지 → 되물음 → 치환 흐름 확인

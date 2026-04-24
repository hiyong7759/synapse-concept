# PLAN-20260424-SYN-007 — 하이퍼그래프 매핑 단일화 + 표준 마크다운 heading 복귀

**상태**: ✅ **완료** (2026-04-24, M0~M4 전부)
**대체**: PLAN-20260423-SYN-006 (폐기 — 방향 변경)
**의존**: PLAN-005 M0 (완료), PLAN-005 M1 규칙 3 **폐기**
**스키마 변경**: 신설 1·리네임 1·폐기 2·컬럼 폐기 1 (구조 대규모 재편)
**최종 브랜치**: `feature/hypergraph-mapping-unify` — 머지 대기

### 완료 마일스톤

- ✅ **M0** (커밋 `b94ec5b`): 재현 고정 + PLAN-006 폐기 처리
- ✅ **M1** (커밋 `e3372b9`): `normalize_hash_syntax` 규칙 3 폐기 → 표준 마크다운 heading
- ✅ **M2** (커밋 `adbb5ed`): 스키마 v21 (`node_sentence_mentions`·`node_category_mentions` 신설, `nodes.status` 폐기) + Kiwi 토큰화 매핑
- ✅ **M3** (커밋 `1e2e85d`): 인출 경로 교체 + `node_categories` 폐기 + 축 A·B 단일화
- ✅ **M4**: DESIGN_HYPERGRAPH v21 반영 + dogfood 재실행 리포트

### 실측 달성 (M4 dogfood)

| 질문 | 이전 (v20) | 이후 (v21) |
|---|---|---|
| 연차 휴가 며칠이야 | `[]` | ✅ 2 건 |
| 징계 사유 뭐 있어 | `[]` | ✅ 2 건 |
| 수습기간 얼마야 | `[]` | ✅ 2 건 |
| 임산부 보호 | `[]` | ✅ 2 건 |
| 회사·야근·피곤 | `[]` | `[]` (데이터 한계 — heading 에 해당 단어 부재 또는 Kiwi 사전 밖) |

**4/7 매칭** — PLAN §성공 기준 "최소 4 건" 달성. 상세는 `DOGFOOD-REPORT-PLAN-007.md`.

### 마이그레이션 정책 (M4 확정)

- **v20 → v21 자동 전환**: `engine/db.py:init_db` 의 `_is_current_schema(conn)` 판정이 v21 기준으로 갱신됨. 구 스키마 감지 → 자동 백업 (`synapse.db.backup-YYYYMMDD-HHMMSS`) + v21 재생성.
- **무손실 마이그레이션 함수는 구현하지 않음** — 이유:
  1. 사용자 실제 로컬 DB 는 빈 상태 (2026-04-24 본 PLAN 착수 시점 확인)
  2. `node_mentions` 리네임 + origin 추가 + `node_categories` TEXT → categories FK 역매핑 + `nodes.status` DROP 이 동시에 필요해 구현 복잡도 ↑
  3. 백업은 남기므로 필요 시 수동 복구 경로 존재
- **영향 평가**: 프로덕션 데이터 없음. 빈 DB 상태라 재생성 비용 0.

---

## 배경 — 세 가지 발견을 한 PLAN 에 묶음

### 발견 1. PLAN-006 의 LIKE 방향은 추상 수준 부적절
PLAN-006 은 `_match_start_categories` 의 exact match 를 LIKE 로 바꾸려 했음. 재현·실험 중:
- 현재 `normalize_hash_syntax` 가 "첫 공백 = 개행" 으로 긴 heading 을 번호 조각(`제6장`·`제55조`)만 남김 → LIKE 로도 매칭 불가
- **Kiwi 가 `휴가및휴일`·`연차휴가의사용및특별한지정` 같은 붙여쓰기·조사 붙은 heading 을 완벽히 의미 토큰으로 분리** (검증 완료)

올바른 layer 는 "heading 을 문장처럼 Kiwi 토큰화 → 기존 노드 인프라(aliases·형태소·다국어) 경유". LIKE 는 폐기.

### 발견 2. `normalize_hash_syntax` 규칙 3 폐기 가능
이 규칙은 chat 한 줄 입력 편의 (`#건강 허리 아픔` → 분류·본문 분리) 위해 도입됐고, markdown heading 공백 금지 제약을 강요함. 사용자 실측: **Gemma-4-E2B-it 의 자연어 → 마크다운 변환 품질이 충분** → chat 편의는 LLM 변환 핫키로 대체. 규칙 3 제거해 표준 마크다운 복귀.

### 발견 3. 하이퍼엣지 매핑·상태 레이어 정리 여지
PLAN-006 조사 중 드러난 구조 냄새:
- `node_categories(node_id, major_category TEXT)` — 19 대분류 태깅 전용. TEXT 문자열이라 `categories.id` FK 와 분리된 이중 시스템
- `node_mentions` — 노드↔문장 전용인데 이름은 모호 ("뭐에 언급?")
- `nodes.status` — `merge_nodes` 에서 soft-delete 마커로만 사용. 원칙 10 "도메인은 관찰" 위배 (v18 에서 `sentences.status` 는 폐기, `nodes.status` 만 legacy 잔존)

세 발견을 한 번에 정리해야 스키마가 정합.

---

## 목표

1. **표준 마크다운 heading 복귀** — heading 줄 전체가 분류. 공백·괄호·특수문자 허용
2. **하이퍼엣지 매핑 테이블 단일 대칭 구조**:
   - `node_sentence_mentions` (기존 `node_mentions` 리네임)
   - `node_category_mentions` (신설)
   - `sentence_categories` (기존 유지)
3. **`node_categories` 폐기** — 19 대분류도 `categories` 트리 내부 노드이므로 `node_category_mentions` 로 흡수
4. **`nodes.status` 폐기** — `merge_nodes` 를 물리 DELETE 로 전환
5. **인출 경로 교체** — `_match_start_categories` 를 `node_category_mentions` JOIN 으로. 축 B 인접 맵도 같은 테이블 역조회로 통합
6. **기존 DB 마이그레이션 + archive 파일 롤백**

---

## 스키마 변경

### 신규·리네임

```sql
-- 기존 node_mentions 리네임 (이름이 모호했음)
CREATE TABLE node_sentence_mentions (
    node_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    origin      TEXT    NOT NULL DEFAULT 'rule' CHECK(origin IN ('user','ai','rule','external')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, sentence_id)
);
CREATE INDEX idx_nsm_sentence ON node_sentence_mentions(sentence_id);

-- 신설: 노드 ↔ 카테고리 멤버십
CREATE TABLE node_category_mentions (
    node_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    origin      TEXT    NOT NULL DEFAULT 'rule' CHECK(origin IN ('user','ai','rule','external')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, category_id)
);
CREATE INDEX idx_ncm_category ON node_category_mentions(category_id);
```

### 폐기

- `node_categories` 테이블 DROP — 데이터는 마이그레이션으로 `node_category_mentions` 로 이관 (19 대분류 TEXT → `categories.id` 역매핑)
- `nodes.status` 컬럼 DROP + `idx_nodes_status` 제거

### 하이퍼엣지 매핑 최종 구조

| 테이블 | 관계 | origin 컬럼 |
|---|---|---|
| `node_sentence_mentions` | 노드 ↔ 문장 | ✅ |
| `node_category_mentions` | 노드 ↔ 카테고리 | ✅ |
| `sentence_categories` | 문장 ↔ 카테고리 | ✅ (기존 유지) |
| `aliases` | 노드 ↔ 텍스트 별칭 | ✅ (기존 유지) |

대칭 완성. `node_categories` / `nodes.status` / 별도 인덱스 제거로 스키마 약 2 개 단순화.

---

## 파이프라인 변경

### 1. `engine/markdown.py:normalize_hash_syntax` — 규칙 3 삭제
"분류명 뒤 첫 공백 → 개행" 규칙 제거. 규칙 1·2·4·5 는 유지.

영향:
- `## 제6장 휴일 및 휴가` 한 줄 전체가 heading (공백 보존)
- `#건강 허리 아픔` 도 한 줄 전체가 heading 으로 잡힘. chat 한 줄 입력은 LLM 변환 핫키 전제 (본 PLAN 범위 밖)

### 2. `engine/save.py:_upsert_category_path` — Kiwi 토큰화 + node 매핑

각 path 세그먼트마다 추가 로직:
```python
kiwi_nouns = kiwi_extract_for_save(segment)["nouns"]
for noun in kiwi_nouns:
    node_id = _match_or_create_node(conn, noun)  # 기존 로직 재활용
    conn.execute(
        "INSERT OR IGNORE INTO node_category_mentions (category_id, node_id, origin) VALUES (?,?,?)",
        (category_id, node_id, "rule"),
    )
```

원칙 준수: 원칙 1 "언급된 것만 존재" — heading 은 사용자 명시 언급.

### 3. `engine/save.py:merge_nodes` — 물리 DELETE 전환

```python
# 기존: UPDATE nodes SET status='inactive' WHERE id=remove_id
# 신규: 하이퍼엣지 전부 이관 후
DELETE FROM nodes WHERE id=remove_id
```

모든 하이퍼엣지(`node_sentence_mentions`·`node_category_mentions`·`aliases`) 가 `keep_id` 로 이관된 뒤라 무결성 영향 없음.

### 4. `engine/retrieve.py:_match_start_categories` — 노드 경유로 교체

```python
def _match_start_categories(conn, start_node_ids: set[int]) -> dict[int, set[int]]:
    """start_nodes 의 node_id 들을 node_category_mentions 로 매핑 →
    재귀 CTE 로 서브트리 확장. 반환: {root_category_id: {id, ...}}"""
    if not start_node_ids:
        return {}
    ph = ",".join("?" * len(start_node_ids))
    rows = conn.execute(f"""
        WITH RECURSIVE sub(id) AS (
            SELECT DISTINCT category_id FROM node_category_mentions WHERE node_id IN ({ph})
            UNION ALL
            SELECT c.id FROM categories c JOIN sub ON c.parent_id = sub.id
        )
        SELECT DISTINCT id FROM sub
    """, list(start_node_ids)).fetchall()
    # ... root → subtree 매핑 구성
```

인터페이스 변경: `keywords: list[str]` → `start_node_ids: set[int]`. 호출부 (`retrieve.py:558`) 도 같이 수정. 결과 `RetrieveResult.start_categories` 는 categories.name 역조회로 기존 반환 형식 유지.

### 5. `engine/retrieve.py` 축 B 인접 맵 통합

현재 `node_categories.major_category` 경유 인접 노드 20 개 추가 로직(line 367-391) 을 **`node_category_mentions` 역조회** 로 교체:
```sql
-- start_nodes 가 속한 카테고리들의 다른 구성원 노드 조회
SELECT DISTINCT ncm2.node_id
FROM node_category_mentions ncm1
JOIN node_category_mentions ncm2 ON ncm1.category_id = ncm2.category_id
WHERE ncm1.node_id IN (...) AND ncm2.node_id NOT IN (...)
LIMIT 20
```

축 A·축 B 구분 폐기 — 하나의 `node_category_mentions` 로 통합.

### 6. `status='active'` 필터 전수 제거

영향 파일:
- `engine/retrieve.py` (8 곳)
- `engine/suggestions.py` (5 곳)
- `engine/save.py` (1 곳 — `_match_or_create_node`)
- `engine/db.py:get_stats` (1 곳 — `nodes_active` 통계)

모두 간단 제거. `inactive` 노드 자체가 없어지므로 필터 불필요.

---

## 마이그레이션

### 스키마 업그레이드 (engine/db.py)

v20 → v21 버전 bump. 감지·자동 업그레이드 로직:

1. `node_mentions` → `node_sentence_mentions` 리네임 + origin 컬럼 추가 (`INSERT ... SELECT` 재작성)
2. `node_category_mentions` 신설
3. 기존 `node_categories(node_id, major_category TEXT, origin)` 데이터를 **`categories` 트리에서 major_category 문자열로 역매핑** 후 `node_category_mentions` 에 insert
   - 19 대분류 시드는 이미 `categories` 트리 id 1-133 에 존재
   - `"BOD.medical"` 같은 점 path 는 재귀 조회로 말단 `category_id` 찾기
4. `node_categories` DROP
5. `nodes.status` 컬럼 DROP + 인덱스 제거

### 기존 DB 호환 백필

기존 저장된 categories 는 heading 이름만 있고 `node_category_mentions` 매핑 없음. 백필:
```python
for cat_row in conn.execute("SELECT id, name FROM categories"):
    for noun in kiwi_extract_for_save(cat_row["name"])["nouns"]:
        node_id = _match_or_create_node(conn, noun)
        INSERT OR IGNORE INTO node_category_mentions ...
```

시동 시 자동 or CLI 서브커맨드로 1 회 실행.

### archive/docs 롤백

이 세션에서 덮어쓴 `archive/docs/(주)더나은_취업규칙_개정(안)_20250430.md` 를 `git checkout main -- ...` 로 공백 포맷 복원. 표준 마크다운 복귀 방침에 맞춤.

---

## 마일스톤

### M0 — 재현 고정 + PLAN-006 폐기 처리
- PLAN-006 문서 상태를 "폐기 — PLAN-007 로 대체" 표시
- `feature/retrieve-category-seed-fix` 브랜치 폐기 (미 push)
- 새 브랜치 `feature/hypergraph-mapping-unify` 생성
- archive 파일 **롤백** (공백 포맷 복원)
- `tests/regression_category_seed.py` 를 본 PLAN 기준으로 조정
  - 입력: 공백 포맷 원본 heading
  - 기대: 현재 main 에서 7 질문 전부 `start_categories=[]` lock-in (재현)

### M1 — `normalize_hash_syntax` 규칙 3 삭제
- `engine/markdown.py` 규칙 3 제거
- 기존 회귀 테스트(`tests/regression_v19_m2_markdown_detail.py` 등) 영향 조정
- chat 모드 한 줄 입력 케이스는 "LLM 변환 핫키 전제" 주석 명시
- 영향 최소 · 빠른 마일스톤

### M2 — 스키마 대수술 + 저장 파이프라인
- `engine/db.py`:
  - `node_mentions` → `node_sentence_mentions` 리네임 + origin 컬럼
  - `node_category_mentions` 신설
  - `node_categories` 마이그레이션 후 DROP
  - `nodes.status` 컬럼 DROP
  - v21 스키마 감지·업그레이드 함수
- `engine/save.py`:
  - `_upsert_category_path` 에 Kiwi 토큰화 + `node_category_mentions` insert
  - `merge_nodes` 물리 DELETE 로 전환
  - 참조하던 테이블명·컬럼명 전수 교체
- 저장 회귀 테스트 — 취업규칙 저장 후 `node_category_mentions` 에 의미 토큰 매핑 존재 검증

### M3 — 인출 경로 교체 + status 필터 제거
- `engine/retrieve.py`:
  - `_match_start_categories` 를 node_id 입력·`node_category_mentions` JOIN 으로 교체
  - 축 B 인접 맵을 같은 테이블 역조회로 통합
  - `status='active'` 필터 전수 제거
- `engine/suggestions.py`, `engine/save.py`, `engine/db.py:get_stats` — `status='active'` 필터 제거
- M0 regression 테스트 통과: 7 질문 중 최소 5 건 `start_categories` 비지 않음
- 노드 매칭 회귀 없음

### M4 — 마이그레이션 + dogfood
- 기존 DB 백필 경로 (시동 자동 감지 or CLI 서브커맨드)
- DESIGN_HYPERGRAPH.md 스키마 섹션 v21 반영
- PLAN-003 M3 dogfood 재실행 → `start_categories` 품질 체감 보고

---

## 성공 기준

- dogfood 7 질문 중 **최소 5 건** 이상 `start_categories` 가 의미 있는 서브트리 반환
- 기존 노드 매칭(`start_nodes`) 회귀 없음
- 공백 heading (`## 제6장 휴일 및 휴가`) 도 정상 작동 — Kiwi 가 `휴일`·`휴가` 분리
- 붙여쓴 heading (`## 제6장.휴일및휴가`) 도 동일 품질
- 매핑 테이블 3 개(`node_sentence_mentions`·`node_category_mentions`·`sentence_categories`) 로 대칭 — `node_categories` / `nodes.status` 흔적 없음

---

## 범위 외

- **chat → markdown LLM 변환 핫키** — 별도 UI/UX 작업
- **카테고리 alias** — Kiwi 토큰화로 대부분 해소. 필요 시 후속
- **retrieve-expand 프롬프트 재학습** — 노드 경유로 exact 매칭 해소되면 불필요

---

## 리스크 · 완화

| 리스크 | 완화 |
|---|---|
| PLAN-005 M1 의 일부 규칙을 되돌림 | 규칙 3 만 삭제. 규칙 1·2·4·5 유지 |
| `node_mentions` 리네임으로 쿼리 전수 수정 | M2 한 커밋에 일괄. grep 으로 누락 방지 |
| `status='active'` 필터 제거로 의도치 않은 노드 노출 | `merge_nodes` 가 물리 DELETE 로 전환되어 inactive 노드 자체가 존재 안 함 |
| 마이그레이션 실패로 기존 DB 데이터 손상 | 백업 경로 가이드 제공 (`cp ~/.synapse/synapse.db ~/.synapse/synapse.db.bak`). M4 시작 전 명시 |
| M2 가 무거움 (스키마 4 개 변경) | 정합성상 분할 어려움. 단위 테스트로 각 단계 독립 검증 |

---

## 구현 세션 시작 가이드

1. 본 PLAN + `engine/db.py`(스키마) + `engine/markdown.py:normalize_hash_syntax` + `engine/save.py:_upsert_category_path, merge_nodes` + `engine/retrieve.py:_match_start_categories, _get_adjacent_by_major_category` 읽기
2. **M0 먼저** — PLAN-006 폐기 표시 + archive 롤백 + 새 브랜치 + 재현 테스트 (수정 전 실패 고정)
3. **M1 → M2 → M3 → M4 순차**. 각 마일스톤 커밋·보고·승인 대기
4. M2 가 제일 큼 — 스키마·저장 동시 변경. 마이그레이션 로직 단위 테스트 필수

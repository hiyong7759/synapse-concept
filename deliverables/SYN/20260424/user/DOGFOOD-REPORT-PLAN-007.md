# PLAN-20260424-SYN-007 M4 — Dogfood 재실행 리포트

**실행 일시**: 2026-04-24
**브랜치**: `feature/hypergraph-mapping-unify` (커밋 1e2e85d 기준)
**LLM**: 비활성화 (`use_llm=False`) — MLX 서버 독립 재현

---

## 배경

PLAN-003 M3 dogfood (2026-04-23) 에서 7 질문 전부 `retrieve().start_categories = []` 로 카테고리 경로 시드가 무력화된 상태를 확인. PLAN-007 (M0~M3) 에서 하이퍼엣지 매핑 단일화 + Kiwi 기반 카테고리 매핑으로 해결한 뒤 같은 7 질문을 재실행.

## 저장 파이프라인 통계

입력: `archive/docs/(주)더나은_취업규칙_개정(안)_20250430.md` (공백 포맷, 27,359 chars, heading 121 개)

| 테이블 | 행 수 | 비고 |
|---|---:|---|
| `posts` | 1 | 게시물 1건 |
| `sentences` | 393 | heading 제외 본문 문장 |
| `nodes` | 1,020 | 본문·heading 통합 노드 원자 |
| `categories` | 254 | 시드 133 + 사용자 heading 121 |
| `node_sentence_mentions` | 4,776 | 노드 ↔ 문장 멤버십 |
| `node_category_mentions` | **448** | v21 신설, Kiwi 토큰화 자동 매핑 |
| `sentence_categories` | 393 | 문장 ↔ heading 말단 |

**확인 포인트**: `node_category_mentions` 448 건이 이번 PLAN 의 핵심 기반. `_upsert_category_path` 가 heading 세그먼트마다 Kiwi 돌려 의미 토큰을 매핑한 결과.

## 7 질문 인출 결과

| 질문 | `start_nodes` | `start_categories` |
|---|---|---|
| 연차 휴가 며칠이야 | `연차#177`, `휴가#179` | ✅ 2 건 |
| 징계 사유 뭐 있어 | `징계#323`, `사유#272`, `있#104` | ✅ 2 건 |
| 수습기간 얼마야 | `수습#199`, `기간#66` | ✅ 2 건 |
| 임산부 보호 | `임산부#610`, `보호#682` | ✅ 2 건 |
| 회사 이름 뭐야 | `회사#3` | ❌ 0 건 |
| 야근 어땠지 | (없음) | ❌ 0 건 |
| 피곤 | (없음) | ❌ 0 건 |

**요약**: 4/7 질문에서 `start_categories` 가 의미 있는 서브트리 반환. PLAN-007 §성공 기준 "최소 4 건" 달성.

## 미매칭 3 건의 원인

| 질문 | 원인 | 대응 |
|---|---|---|
| 회사 이름 뭐야 | 취업규칙 heading 에 "회사" 라는 단어 없음 (모든 heading 이 `제N장 …`·`제N조 …` 체계). `회사` 노드는 본문에서만 뽑힘 → `node_category_mentions` 매핑 없음 | 데이터 한계. 회사명을 heading 에 포함하면 즉시 매칭됨 (예: `# 취업규칙 > 주식회사 더나은 > …`) |
| 야근 어땠지 | "야근" 이 Kiwi 명사 사전에 없어 본문에서도 노드로 추출되지 않음 | 사용자 alias 등록(`야근 → 야간근로`) 또는 Kiwi 사용자 사전 확장 |
| 피곤 | 본문에 "피곤" 직접 등장 없음 (취업규칙은 규정 문서라 감정 표현 부재) | 데이터 성격상 원천 부재 — 질문이 도메인 밖 |

세 경우 모두 **인출 로직 결함이 아닌 데이터 한계**. PLAN-007 의 개선 범위 밖.

## 인출 경로 — v20 vs v21 비교

**v20 이전** (`_match_start_categories` exact name match):
- 질문 키워드 `연차` → `WHERE categories.name = '연차'` → 0 건 (긴 heading 명과 매칭 불가)
- 7 질문 전부 `start_categories=[]`

**v21 (PLAN-007 M3)** (`node_category_mentions` JOIN):
- 질문 키워드 `연차` → `_match_start_nodes` → `연차#177` 노드 매칭
- 노드 `연차` → `node_category_mentions` → `제35조 (연차유급휴가)`, `제36조 (연차휴가의 사용)`, `제37조 (연차유급휴가의 대체)` 카테고리
- 재귀 CTE 로 서브트리 확장 → `sentence_categories` JOIN → 해당 조항 문장 시드

Kiwi 가 저장 시 heading 의 의미 토큰을 자동 추출하므로, 사용자가 별도 별칭·태깅 없이도 도메인 단어가 바로 인출에 쓰임.

## 축 B 인접 맵 — 데이터 주도 확장

**v20 이전**: `_ADJACENT_PAIRS` 72 쌍 수동 정의 (예: `BOD.medical ↔ MON.insurance`). 19 대분류 제한.

**v21 (PLAN-007 M3)**: `node_category_mentions` 역조회:
```sql
SELECT DISTINCT ncm2.node_id
FROM node_category_mentions ncm1
JOIN node_category_mentions ncm2 ON ncm1.category_id = ncm2.category_id
WHERE ncm1.node_id IN (:start_nodes)
  AND ncm2.node_id NOT IN (:start_nodes)
LIMIT 50
```

**예**: `징계` 노드 시작 → 카테고리 `제61조 (징계)`, `제62조 (징계의 종류)` 등 → 같은 카테고리의 다른 노드 (`종류`·`절차`·`처분`…) 를 인접 시드로 편입. 사용자 heading 구조가 도메인 인접성을 표현하므로 **수동 매핑 정의 불필요**.

## 결론

- PLAN-007 §성공 기준 **4/7 매칭 달성** ✓
- 노드 매칭 경로 회귀 없음 (5/7 — 이전과 동일) ✓
- 스키마 정합성 — 매핑 테이블 3 개 대칭 (`node_sentence_mentions` / `node_category_mentions` / `sentence_categories`) ✓
- `node_categories` · `nodes.status` 폐기 — 원칙 10 "도메인은 관찰" 일관성 복원 ✓

## 후속 제안 (범위 외)

1. **`회사` 계열 노드의 카테고리 매핑 보완** — 취업규칙 저장 시 `#` 이 아닌 메타데이터(`posts` 수준) 에 문서 소유자·기관명을 걸 수 있으면 "회사 이름" 같은 자연어 인출에도 대응 가능
2. **Kiwi 사용자 사전 확장** — 야근·법령 전문 용어 등 도메인 고유어를 명사 사전에 등록하면 노드 추출 커버리지 개선
3. **LLM on 재측정** — 본 리포트는 `use_llm=False`. retrieve-expand(LLM) 가 키워드 확장 시 추가 매칭 생길 가능성 (예: "야근" → "야간근로·연장근로") 검증 필요

# DOGFOOD-REPORT-PLAN-004 — 실행 보고서

**실행 시각**: 2026-04-23T11:27:17Z
**실행자**: Claude Code (Opus 4.7, 에이전트)
**브랜치**: feature/category-redesign @ ac8c39b6ed875987db1e34d84b3e124a095dd006
**MLX 서버**: off (use_llm=False 기준)

## 자동 검증 결과

| 시나리오 | PASS/FAIL | 비고 |
|---|---|---|
| 0. 환경 준비 | ✅ PASS | HEAD=ac8c39b, 카테고리 마스터 133 (시드 19+계층) 확인 |
| 1. 다층 heading + 동일 루트 | ✅ PASS | deonaeun_roots=1, 하위 `개발팀·휴가` 2개, linked 개발팀4·휴가2, node_cats=0, warnings 전부 `[]` |
| 2. 시드 루트 충돌 경고 | ✅ PASS | BOD·TIM 각 1건, "19 대분류 시드 이름과 동일" 문구 포함 |
| 3. 사용자 루트 검수 뷰 | ✅ PASS | `더나은`만 노출, BOD·TIM 미노출, user_category_roots=1 |
| 4. TIM 자동 태깅 | ✅ PASS | 4건 (2026년/4월/18일/20일) 전부 origin=system, TIM.year/month/day |
| 5. 축 A 서브트리 인출 | ⚠️ PARTIAL | Q1·Q3 PASS, Q2 FAIL — 휴가 검색에 개발팀 하위 문장 [1] 누수 |
| 6. LIKE fallback | ⚠️ PARTIAL | 런북 테스트 데이터 정확히 20건(임계치 `>20` 경계) → 미발동. +1건 추가 시 정상 발동 확인 (pre=21→post=2) |
| 7. 최종 상태 점검 | ✅ PASS | user_roots=4(≥3), sc_total=32(≥10), nc_total=4(≥4) |

**최종 판정 요약**: 코어 기능 모두 정상 동작. 시나리오 5 Q2 의 휴가→개발팀 누수는 **회귀 의심**이며 M5 또는 PLAN-005 에서 원인 조사 필요. 시나리오 6은 런북 테스트 데이터 이슈(코드는 정상).

---

## 실제 STDOUT

### 시나리오 0 — 환경 준비

```
$ git rev-parse HEAD
ac8c39b6ed875987db1e34d84b3e124a095dd006

$ yes y | python3 -m engine.cli --reset
DB를 초기화합니다 (/Users/hiyong/.synapse/synapse.db). 계속? (y/N) [reset] /Users/hiyong/.synapse/synapse.db 삭제됨
[reset] 빈 DB 생성 완료

$ python3 -m engine.cli --stats
DB: /Users/hiyong/.synapse/synapse.db
  문장 0 (user=0, assistant=0)
  노드 0/0 (활성/전체)
  언급 0 (문장 바구니 멤버십)
  카테고리 마스터 133 (categories 트리 — 시드 19 대분류 + 사용자 heading)
  축 A 문장-카테고리 0 (sentence_categories, 사용자 heading 주 매핑)
  축 B 노드-대분류 0 (node_categories.major_category, 19 대분류 태깅)
  별칭 0
  미해결 토큰 0
```

### 시나리오 1 — 다층 heading + 동일 루트 재사용

```
[save 1] post=1 sentences=[1, 2, 3] warnings=[]
[save 2] post=2 sentences=[4] warnings=[]
[save 3] post=3 sentences=[5, 6] warnings=[]
```

검증 쿼리:

```
deonaeun_roots
--------------
1

name  parent
----  ------
개발팀   더나은
휴가    더나은

cat  linked
---  ------
개발팀  4
휴가   2

node_cats
---------
0
```

### 시나리오 2 — 시드 루트 충돌 경고

```
[BOD] warnings=["heading 루트 'BOD' 이 19 대분류 시드 이름과 동일 — 시드 트리에 병합됨. /review 에서 분리 여부 확인 필요."]
[TIM] warnings=["heading 루트 'TIM' 이 19 대분류 시드 이름과 동일 — 시드 트리에 병합됨. /review 에서 분리 여부 확인 필요."]
```

### 시나리오 3 — 사용자 루트 검수 뷰

```
=== recent_user_categories ===
  더나은 desc=2 linked=6

=== counts ===
{
  "total": 0,
  "unresolved": 0,
  "ai_generated": {
    "category": 0
  },
  "external_generated": {
    "alias": 0
  },
  "suspected_typos": 0,
  "missing_basic_info": 0,
  "node_categories_by_origin": {
    "user": 0,
    "ai": 0,
    "system": 0,
    "external": 0
  },
  "user_category_roots": 1
}
```

### 시나리오 4 — TIM 자동 태깅

```
18일|TIM.day|system
20일|TIM.day|system
4월|TIM.month|system
2026년|TIM.year|system
```

### 시나리오 5 — 축 A 서브트리 인출

```
질문: '더나은 개발팀 휴가'
  start_nodes=['팀장#11']
  start_categories=['더나은', '개발팀', '휴가']
  sentences (6):
    [1] 민지가 이번 주 프로젝트 맡음
    [2] 영희는 신입 온보딩 담당
    [3] 팀장은 박지수
    [4] 오늘 스탠드업에서 릴리즈 일정 논의
    [5] 다음 주 금요일 연차 쓸 예정
    [6] 민수 화요일 반차

질문: '휴가 연차'
  start_nodes=['연차#20']
  start_categories=['휴가']
  sentences (3):
    [5] 다음 주 금요일 연차 쓸 예정
    [6] 민수 화요일 반차
    [1] 민지가 이번 주 프로젝트 맡음   ← 기대에 없는 누수

질문: '건강'
  start_nodes=[]
  start_categories=['건강']
  sentences (2):
    [10] 2026년 4월 18일 강남세브란스 다녀옴
    [11] 2026년 4월 20일 약 처방 받음
```

### 시나리오 6 — LIKE fallback

**1차 실행 (런북 스펙 그대로, 문장 20개):**

```
pre_narrow_count  = 20
post_narrow_count = 20
like_narrowed     = False
like_tokens_used  = []
context_sentences: (20건 — React Native·React·Native·잡담 혼재, narrowing 미발동)
```

원인: `engine/retrieve.py:648` 의 조건이 `if len(context_sentences) > like_fallback_threshold` (strict `>`), 기본 임계치 20. 정확히 20건이면 경계에서 미발동.

**재검증 (+1건 추가 = 21건):**

```
pre_narrow_count  = 21
post_narrow_count = 2
like_narrowed     = True
like_tokens_used  = ['React', 'Native']
context_sentences:
  [12] React Native 설정 완료
  [13] React Native 빌드 에러 났음
```

→ 임계치 초과 조건에서는 정상 동작. 모든 결과 문장 "React" AND "Native" 포함.

### 시나리오 7 — 최종 상태 점검

```
DB: /Users/hiyong/.synapse/synapse.db
  문장 32 (user=32, assistant=0)           ← 시나리오 6 재검증 +1 포함
  노드 61/61 (활성/전체)
  언급 113 (문장 바구니 멤버십)
  카테고리 마스터 142
  축 A 문장-카테고리 32
  축 B 노드-대분류 4
  별칭 11
  미해결 토큰 0

posts|sentences|nodes|all_roots|user_roots|sc_total|nc_total
23|32|61|23|4|32|4
```

user_roots=4: `더나은 / 건강 / 개발 / 잡담` (이외 시드 19 제외).

---

## UX 관찰 사항

- **저장 속도 (markdown 여러 항목 게시물)**: 한 게시물당 체감 < 1초, use_llm=False 기준 지연 없음. 시나리오 6 의 잡담 15건 배치도 수초 내 완료. (단 MLX 모델 로드 워닝 `Quantization is not supported for ArchType::neon` 가 호출마다 stderr 로 찍힘 — 기능엔 영향 없지만 로그 소음.)
- **축 A 인출 정확도 (서브트리 범위 맞게 좁혀지는지)**: Q1 "더나은 개발팀 휴가" (6건 정확히 잡힘, 건강 제외 확인) 와 Q3 "건강" (서브트리만 2건) 은 원하는 동작. **Q2 "휴가 연차" 에서 개발팀 하위 [1] 문장이 역침투** — 시나리오 2의 `휴가 하위 2 문장만` 기대를 위반. 추정 원인: `연차` 가 start_node 로 잡히면서 연차 노드의 공출현 경로로 [1]이 재진입하거나, `이번 주/다음 주` 같은 주 관련 표현 공출현이 의심됨. 카테고리 축 A 로는 개발팀 하위가 명시적으로 잡히지 않으므로 BFS 공출현 확장 쪽 이슈로 보임.
- **LIKE fallback 오버슈팅 (임계치 20 적절한지)**: 임계치 자체는 합리적이나 런북의 테스트 데이터 수(정확히 20)가 경계에 걸려 1차 실행에서 미발동. 실사용에서는 20건 근처 결과가 자주 나오면 불안정 체감 가능 — 기본값 상향(예: 25~30) 또는 경고 힌트 제공 검토 여지.
- **시드 루트 충돌 경고 가시성 (사용자가 알아차릴만한가)**: 경고 메시지가 명확하고 `/review 에서 분리 여부 확인 필요` 로 다음 행동 지시까지 포함 — 가독성 OK. 다만 `category_warnings` 가 save 반환값으로만 노출되며, UI/CLI 저장 후 요약 화면에 별도 배지·하이라이트가 있는지는 본 런에서 미확인.
- **TIM 자동 태깅 오작동 (연도 아닌 숫자가 TIM 로 잘못 찍히지 않는지)**: 시나리오 4에서 `2026년/4월/18일/20일` 만 태깅됨. 문장 안의 다른 한글 토큰 (`강남세브란스`, `약`, `처방` 등) 은 TIM 으로 찍히지 않음 — 오인식 없음. 단 본 런에는 "3시/15분" 같은 시각 표현이나 "2일" 같은 모호 표현 샘플이 부족 → 별도 케이스 검증 필요.
- **사용자 루트 난립 가능성 (오타로 `더나은`/`더 나은` 분리되는지)**: 본 런에서 의도적 오타 저장은 수행하지 않음. 현재 구현은 heading 루트 이름 정규화(공백·대소문자 축약)가 없어 보이므로, 사용자가 `# 더 나은` 과 `# 더나은` 을 섞어 쓰면 별도 루트로 분리될 가능성 높음. `recent_user_categories` 뷰에서 유사 루트 감지·병합 제안이 필요할 것.

---

## 재현 가능한 이슈

### ISSUE-1: 휴가 카테고리 검색에 개발팀 하위 문장 누수 (시나리오 5 Q2)

- **재현 스텝**:
  1. `python3 -m engine.cli --reset`
  2. 런북 시나리오 1 세 저장 실행 (`# 더나은` → `## 개발팀` 2건, `# 더나은` → `## 휴가` 1건; 한 줄 표기로는 `더나은.개발팀` / `더나은.휴가`)
  3. `retrieve("휴가 연차", use_llm=False)` 실행
- **기대**: `context_sentences` 에 휴가 하위 2건 ([5], [6]) 만
- **실제**: 3건 반환, 개발팀 하위 [1] "민지가 이번 주 프로젝트 맡음" 이 함께 나옴
- **심각도**: 중 — 축 A 카테고리 바구니 격리가 약한 신호. 사용자가 휴가 질문을 할 때 무관한 개발팀 컨텍스트 오염 가능. use_llm=True 시 LLM 이 걸러줄 수 있으나, `--no-llm` 독립 동작 원칙에서 정확도 저하.
- **조사 방향 후보 (초안)**: `start_nodes=['연차#20']` 공출현 확장 경로 추적 → `_get_co_mentioned_node_ids` / BFS visited 경계 확인. ← 후속 분석에서 부정확으로 판명, 아래 재추적 참고.

**원인 재추적 (후속 분석)**:

DB 쿼리로 `node_mentions` 확인 결과, 실제 원인은 BFS visited 경계가 아니라 **저장 시 Kiwi 형태소 분석의 1음절 허브 노드 생성**.

```
[1] "민지가 이번 주 프로젝트 맡음"  → nodes: 민지, 이번, 주, 프로젝트, 맡
[5] "다음 주 금요일 연차 쓸 예정"   → nodes: 다음, 주, 금요일, 연차, 예정, 쓰
[6] "민수 화요일 반차"               → nodes: 민수, 화요일, 반
```

공유 노드 `주`(NNB 의존명사) 가 [1] 과 [5] 를 관통. BFS 1홉에서 카테고리 `휴가` 시드 → [5],[6] 수집 → 공출현 노드 `주` → `주` 의 다른 mention 인 [1] 흡수.

**근본 계층 (DESIGN_INPUT_MODES_AND_RETRIEVAL.md 대조)**:

설계상 chat 모드는 save-pronoun 으로 "다음 주" → 절대 날짜 치환, markdown 모드는 원문 보존 (save-pronoun skip). 치환되면 허브 자체가 생성되지 않음. 그러나 현재 `_save_one_item` ([engine/save.py:449](engine/save.py#L449)) 이 `mode` 파라미터를 받지 않아 모드별 분기가 미구현 상태 (PLAN-003 M2 범위). 가드는 `if use_llm:` 하나뿐 ([save.py:470](engine/save.py#L470)).

M2 가 구현되면:
- **chat 입력**: MLX on 시 save-pronoun 자동 치환으로 "다음 주" → 절대 날짜 → 허브 소멸
- **markdown 입력**: 공문서 특성상 상대 시간 부사가 거의 없음 → 허브 자체 드묾

**단 ISSUE 자체는 유지**:

1. M2 구현 전까지 현재 시스템에서 동일 조건 재현 가능 (실운영 상태 결함)
2. M2 후에도 공문서에 예외적 상대 표현이 섞이거나, Kiwi 의 다른 1음절 분해(`일`·`것`·`중`·`편` 등) 로 유사 허브 발생 가능성 남음
3. "축 A 격리 강화" 제안은 M2 와 독립적으로 방어 레이어 가치 있음

### ISSUE-2: LIKE fallback 임계치가 경계(20) 에서 미발동 — 런북 테스트 데이터 이슈

- **재현 스텝**: 시나리오 6 런북 스니펫 그대로 실행 → 총 20건 결과
- **기대**: `pre_narrow_count > 20`, `like_narrowed=True`
- **실제**: `pre_narrow_count = 20`, `like_narrowed=False` (조건 strict `>` 이므로 정상 동작)
- **심각도**: 하 — 코드 결함 아님. 런북의 테스트 데이터를 `for i in range(16)` 으로 바꾸거나 임계치 기본값을 경계 예시와 명시적으로 맞추면 해결.

### ISSUE-3: stderr 로그 소음 (`Quantization is not supported for ArchType::neon`)

- **재현 스텝**: `use_llm=False` 에서도 save/retrieve 호출마다 노출
- **심각도**: 하 — 기능 정상. 로그 가독성만 영향. Kiwi/MLX 측 워닝으로 추정되며, stderr 를 WARNING 레벨 이상 필터링하거나 1회만 찍도록 가드 가능.

---

## 제안 (PLAN-004 M5 또는 PLAN-005 후보)

1. **축 A 격리 강화 (ISSUE-1)**: `retrieve` 에서 `start_categories` 가 있을 때 공출현 확장 결과를 해당 카테고리 서브트리 문장으로 교집합 필터링. `use_llm=False` 경로에서 카테고리 기반 격리가 가장 큰 UX 가치.
2. **LIKE fallback 임계치 튜닝 (ISSUE-2 연관)**: 기본값 25 또는 데이터셋 크기 비례 동적 산정. 런북의 검증 데이터 수도 한 단계 넉넉히(예: 22건) 조정.
3. **heading 루트 정규화 가이드**: `# 더나은` / `# 더 나은` 같은 공백 편차에 대해 저장 시점에 suggestions 경고 또는 alias 연결 제안. `recent_user_categories` 에 유사 루트 클러스터 뷰 추가.
4. **TIM 경계 케이스 테스트 시나리오 추가**: "오후 3시", "2일" 등 시각·짧은 숫자 표현 샘플을 dogfood 런북에 포함.
5. **`category_warnings` UI 노출**: save 반환의 경고를 CLI/채팅 UI에서 사용자에게 즉시 표시하고 `/review` 진입 링크 제공.
6. **로그 정리 (ISSUE-3)**: Kiwi 워닝을 import 시 1회만 출력하거나 `logging.WARNING` 이상 필터.

---

**최종 판정**: **보강 필요** — 코어 M0~M4 기능은 정상 통합. 단 ISSUE-1 (축 A 격리 누수) 은 use_llm=False 독립 동작 원칙의 신뢰도와 직결되므로 main 머지 전 M5 로 해결 권장. ISSUE-2, 3 은 머지와 무관하게 별도 PR 로 처리 가능.

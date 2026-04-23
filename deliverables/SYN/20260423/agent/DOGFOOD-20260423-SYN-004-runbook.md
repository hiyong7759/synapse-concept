# DOGFOOD-20260423-SYN-004 — PLAN-004 카테고리 재설계 dogfood 런북

## 목적

PLAN-004 (카테고리 재설계 v20) M0~M4 전체를 실데이터 시나리오로 검증하고, 기능 정상·성능·UX 관점의 이상 여부를 보고한다.

**브랜치**: `feature/category-redesign` (이미 체크아웃 상태여야 함)
**선행 커밋**: `ac8c39b` (M4 완료 지점)
**대상 DB**: `~/.synapse/synapse.db` (dogfood 전용으로 wipe 허용)

---

## 에이전트 작업 원칙

1. **단계 건너뛰지 말 것**. 각 시나리오는 앞 단계가 남긴 데이터를 전제로 한다.
2. **출력은 그대로 옮겨 담기**. 해석·요약 말고 실제 STDOUT·쿼리 결과를 보고서에 원문 인용.
3. **PASS/FAIL 자동 체크 + 수동 관찰** 모두 수행. 자동 검증이 통과해도 "UX 관찰" 필드 채울 것.
4. **DB 상태 건드리지 말 것**. 시나리오에 명시된 reset/save 외의 DDL·DML 금지.
5. **MLX 서버는 선택**. 기본은 `use_llm=False` 로 진행. MLX 서버 돌아가면 병행 확인 가능.
6. **문제 발견 시 중단 말고 계속**. 후속 시나리오가 선행 실패에 의존하지 않는 한 끝까지 실행.
7. **보고서는 반드시 아래 §보고 템플릿 형식으로 작성** 후 `deliverables/SYN/20260423/user/DOGFOOD-REPORT-PLAN-004.md` 에 저장.

---

## 0. 환경 준비

```bash
cd /Volumes/macex/workspace/claude-agentic-subagent-team/projects/synapse
git rev-parse HEAD                    # ac8c39b 이어야 정상
python3 -m engine.cli --reset         # DB 초기화
python3 -m engine.cli --stats         # v20 시드 133 출력되는지 확인
```

**기대**: `카테고리 마스터 133 (categories 트리 — 시드 19 대분류 + 사용자 heading)` 라인 출력.

---

## 1. 다층 heading + 동일 루트 재사용 (M1 축 A 기본)

### 실행

```python
python3 << 'EOF'
from engine.save import save
r1 = save("# 더나은\n## 개발팀\n- 민지가 이번 주 프로젝트 맡음\n- 영희는 신입 온보딩 담당\n- 팀장은 박지수", mode="markdown", use_llm=False)
r2 = save("# 더나은\n## 개발팀\n- 오늘 스탠드업에서 릴리즈 일정 논의", mode="markdown", use_llm=False)
r3 = save("# 더나은\n## 휴가\n- 다음 주 금요일 연차 쓸 예정\n- 민수 화요일 반차", mode="markdown", use_llm=False)
for i, r in enumerate([r1, r2, r3], 1):
    print(f"[save {i}] post={r.post_id} sentences={r.sentence_ids} warnings={r.category_warnings}")
EOF
```

### 자동 검증

```bash
sqlite3 ~/.synapse/synapse.db <<SQL
.headers on
.mode column
-- A. 더나은 루트가 유일한지
SELECT COUNT(*) AS deonaeun_roots FROM categories WHERE name='더나은' AND parent_id IS NULL;
-- B. 개발팀·휴가가 더나은 하위에만 달렸는지
SELECT c.name, p.name AS parent
FROM categories c JOIN categories p ON p.id = c.parent_id
WHERE p.name='더나은' ORDER BY c.name;
-- C. sentence_categories 에 heading 말단(개발팀·휴가) 만 연결되는지
SELECT c.name AS cat, COUNT(*) AS linked
FROM sentence_categories sc JOIN categories c ON c.id = sc.category_id
GROUP BY c.name ORDER BY linked DESC;
-- D. node_categories 는 비어 있어야 (heading 경로가 안 들어가야)
SELECT COUNT(*) AS node_cats FROM node_categories;
SQL
```

### 기대

| 항목 | 기대값 |
|---|---|
| A. `deonaeun_roots` | `1` |
| B. 하위 | `개발팀 \| 더나은`, `휴가 \| 더나은` |
| C. `linked` | `개발팀: 4`, `휴가: 2` |
| D. `node_cats` | `0` |
| warnings 출력 | 전부 `[]` |

**자동 PASS 조건**: A=1 AND D=0 AND 하위 2개(개발팀·휴가) AND warnings 전부 빈 배열.

---

## 2. 시드 루트 충돌 경고 (M3)

### 실행

```python
python3 << 'EOF'
from engine.save import save
rB = save("# BOD\n## 허리\n- 오늘 허리 많이 아팠어\n- 데스크 오래 앉아있어서 그런듯", mode="markdown", use_llm=False)
rT = save("# TIM\n## 2026-04-23\n- 오후 3시 미팅", mode="markdown", use_llm=False)
print(f"[BOD] warnings={rB.category_warnings}")
print(f"[TIM] warnings={rT.category_warnings}")
EOF
```

### 기대

- `BOD` 저장: `category_warnings` 에 `BOD` 관련 경고 1 건 (문장 2 개여도 dedup)
- `TIM` 저장: 마찬가지로 경고 1 건
- 메시지에 "19 대분류 시드 이름과 동일" 문구 포함

**자동 PASS 조건**: 두 warnings 리스트 모두 len=1, 각각 "BOD"/"TIM" 문자열 포함.

---

## 3. 사용자 루트 검수 뷰 (M3)

### 실행

```python
python3 << 'EOF'
from engine.suggestions import recent_user_categories, counts
import json
print("=== recent_user_categories ===")
for c in recent_user_categories():
    print(f"  {c['name']} desc={c['descendants']} linked={c['linked_sentences']}")
print("\n=== counts ===")
print(json.dumps(counts(), ensure_ascii=False, indent=2))
EOF
```

### 기대

- `recent_user_categories` 에 **`더나은` 만** 나와야 함 (`BOD`·`TIM` 은 시드 배제 조건으로 제외)
- `counts.node_categories_by_origin` 전부 0 (아직 TIM.* 트리거될 sentence text 없음)
- `counts.user_category_roots` = 1

**자동 PASS 조건**: `recent_user_categories` 에 `더나은` 있고 `BOD`/`TIM` 없음, `user_category_roots == 1`.

---

## 4. 축 B TIM 자동 태깅 (M1)

### 실행

```python
python3 << 'EOF'
from engine.save import save
save("# 건강\n- 2026-04-18 강남세브란스 다녀옴\n- 2026-04-20 약 처방 받음", mode="markdown", use_llm=False)
EOF
sqlite3 ~/.synapse/synapse.db "
  SELECT n.name, nc.major_category, nc.origin
  FROM node_categories nc JOIN nodes n ON n.id = nc.node_id
  ORDER BY nc.major_category;
"
```

### 기대

| name | major_category | origin |
|---|---|---|
| 2026년 | TIM.year | system |
| 4월 | TIM.month | system |
| 18일 | TIM.day | system |
| 20일 | TIM.day | system |

**자동 PASS 조건**: 4 개 이상 row, 전부 `origin='system'`, major_category 가 `TIM.year/month/day` 조합.

---

## 5. 축 A 서브트리 인출 (M2 성공 기준)

### 실행

```python
python3 << 'EOF'
from engine.retrieve import retrieve
for q in ["더나은 개발팀 휴가", "휴가 연차", "건강"]:
    r = retrieve(q, use_llm=False)
    print(f"\n질문: {q!r}")
    print(f"  start_nodes={r.start_nodes}")
    print(f"  start_categories={r.start_categories}")
    print(f"  sentences ({len(r.context_sentences)}):")
    for sid, t in r.context_sentences:
        print(f"    [{sid}] {t}")
EOF
```

### 기대

- `"더나은 개발팀 휴가"` → `start_categories` 에 `더나은`·`개발팀`·`휴가` 중 최소 2개, 개발팀·휴가 하위 문장 6 건 (4+2) 포함. 건강 하위는 제외.
- `"휴가 연차"` → 휴가 하위 2 문장만 잡힘.
- `"건강"` → 건강 루트 서브트리 (2 문장) 잡힘.

**자동 PASS 조건**:
- Q1: `더나은` ∈ start_categories, context_sentences 개수 >= 6, 건강 관련 문장 미포함
- Q2: 휴가 하위 2 문장 포함, 개발팀 하위 미포함
- Q3: 건강 하위 2 문장 포함

---

## 6. LIKE fallback — Kiwi 쪼갠 외래어 복원 (M4)

### 실행

```python
python3 << 'EOF'
from engine.save import save
from engine.retrieve import retrieve

# 외래어 관련 문장 + noise 15건 → 임계치 20 넘기기
save("""# 개발
- React Native 설정 완료
- React Native 빌드 에러 났음
- React 컴포넌트 구조 개선
- React hook 리팩터
- Native API 호출 샘플""", mode="markdown", use_llm=False)

for i in range(15):
    save(f"# 잡담\n- React 관련 잡담 {i}", mode="markdown", use_llm=False)

r = retrieve("React Native", use_llm=False)
print(f"pre_narrow_count  = {r.pre_narrow_count}")
print(f"post_narrow_count = {r.post_narrow_count}")
print(f"like_narrowed     = {r.like_narrowed}")
print(f"like_tokens_used  = {r.like_tokens_used}")
print("context_sentences:")
for sid, t in r.context_sentences:
    print(f"  [{sid}] {t}")
EOF
```

### 기대

- `pre_narrow_count > 20`
- `post_narrow_count` 은 `React Native` 원문 구절이 포함된 문장 2 건 근방
- `like_narrowed == True`, `like_tokens_used == ['React', 'Native']`
- 최종 context 에 `React hook 리팩터` 같은 Native 없는 문장은 **제외** 돼야 함 (AND 매칭)

**자동 PASS 조건**: `like_narrowed=True`, `post<pre`, context 문장 모두 "React" AND "Native" 둘 다 포함.

---

## 7. 최종 상태 점검

### 실행

```bash
python3 -m engine.cli --stats
sqlite3 ~/.synapse/synapse.db "
  SELECT
    (SELECT COUNT(*) FROM posts) AS posts,
    (SELECT COUNT(*) FROM sentences) AS sentences,
    (SELECT COUNT(*) FROM nodes) AS nodes,
    (SELECT COUNT(*) FROM categories WHERE parent_id IS NULL) AS all_roots,
    (SELECT COUNT(*) FROM categories WHERE parent_id IS NULL AND name NOT IN ('PER','BOD','MND','FOD','LIV','MON','WRK','TEC','EDU','LAW','TRV','NAT','CUL','HOB','SOC','REL','REG','TIM','ACT')) AS user_roots,
    (SELECT COUNT(*) FROM sentence_categories) AS sc_total,
    (SELECT COUNT(*) FROM node_categories) AS nc_total;
"
```

### 기대 (대략)

- `user_roots` ≥ 3 (`더나은`·`건강`·`개발`·`잡담` 중 일부)
- `sc_total` ≥ 10 (시나리오 1·2·4·6 누적)
- `nc_total` ≥ 4 (시나리오 4 의 TIM.* 자동 태깅)

---

## 보고 템플릿

**반드시 아래 형식으로** `deliverables/SYN/20260423/user/DOGFOOD-REPORT-PLAN-004.md` 에 작성:

```markdown
# DOGFOOD-REPORT-PLAN-004 — 실행 보고서

**실행 시각**: (ISO 타임스탬프)
**실행자**: (에이전트명 또는 사람)
**브랜치**: feature/category-redesign @ (HEAD SHA)
**MLX 서버**: on | off

## 자동 검증 결과

| 시나리오 | PASS/FAIL | 비고 |
|---|---|---|
| 0. 환경 준비 | ☐ | |
| 1. 다층 heading + 동일 루트 | ☐ | |
| 2. 시드 루트 충돌 경고 | ☐ | |
| 3. 사용자 루트 검수 뷰 | ☐ | |
| 4. TIM 자동 태깅 | ☐ | |
| 5. 축 A 서브트리 인출 | ☐ | |
| 6. LIKE fallback | ☐ | |
| 7. 최종 상태 점검 | ☐ | |

## 실제 STDOUT (요약)

### 시나리오 1
(실제 출력 붙여넣기)

### 시나리오 2
...

## UX 관찰 사항

아래 각 항목에 대해 "이상 없음" 또는 구체적 관찰 기록:

- 저장 속도 (markdown 여러 항목 게시물):
- 축 A 인출 정확도 (서브트리 범위 맞게 좁혀지는지):
- LIKE fallback 오버슈팅 (임계치 20 적절한지):
- 시드 루트 충돌 경고 가시성 (사용자가 알아차릴만한가):
- TIM 자동 태깅 오작동 (연도 아닌 숫자가 TIM 로 잘못 찍히지 않는지):
- 사용자 루트 난립 가능성 (오타로 `더나은`/`더 나은` 분리되는지):

## 재현 가능한 이슈

(PASS 여도 관찰된 이슈가 있으면 재현 스텝·기대·실제·심각도 기록)

## 제안

(PLAN-004 M5 또는 PLAN-005 로 이어질 개선 후보)
```

---

## 완료 조건

- [ ] 시나리오 0~7 전부 실행했고 STDOUT 확보
- [ ] 자동 PASS/FAIL 매트릭스 채움
- [ ] UX 관찰 6 항목 모두 코멘트
- [ ] 보고서 파일이 `deliverables/SYN/20260423/user/DOGFOOD-REPORT-PLAN-004.md` 에 존재
- [ ] 최종 판정 (머지 가능 / 보강 필요) 보고서 마지막에 한 줄 명시

끝.

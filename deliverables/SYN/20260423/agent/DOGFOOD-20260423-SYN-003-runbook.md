# DOGFOOD-20260423-SYN-003 — PLAN-003 M2·M3 마크다운 모드 확장 dogfood 런북

## 목적

PLAN-003 M2 (markdown kind 분기 + `- key:: value` 파서 + save-pronoun 전체 skip) 를
실데이터 시나리오로 검증. M3 범위는 "두 모드 통합 검증" — chat/markdown 혼합 저장,
save-pronoun 호출 계수, 세션노트 §4.1 오동작 재현 시도, 백필 정합.

**브랜치**: `feature/markdown-mode-detail` (체크아웃 상태)
**선행 커밋**: `634348a` (M2 완료 지점)
**대상 DB**: `~/.synapse/synapse.db` (dogfood 전용, reset 허용 — 사용자 승인 완료)

---

## 에이전트 작업 원칙

1. **단계 건너뛰지 말 것**. 각 시나리오는 앞 단계 데이터를 전제로 한다.
2. **출력은 그대로 옮겨 담기**. STDOUT·쿼리 결과 원문 인용.
3. **PASS/FAIL 자동 체크 + 수동 관찰** 모두 수행.
4. **DB 상태 건드리지 말 것**. 시나리오 외의 DDL·DML 금지.
5. **LLM 병행 확인 선택**. 기본은 `use_llm=False`. MLX 서버 기동 시 `use_llm=True` 로
   시나리오 4 만 재실행 (save-pronoun 호출 계수 실측).
6. **문제 발견 시 중단 말고 계속**.
7. **보고서는 반드시 아래 §보고 템플릿** → `deliverables/SYN/20260423/user/DOGFOOD-REPORT-PLAN-003.md`.

---

## 0. 환경 준비

```bash
cd /Volumes/macex/workspace/claude-agentic-subagent-team/projects/synapse
git rev-parse HEAD                    # 634348a 이어야 정상
python3 -m engine.cli --reset         # DB 초기화
python3 -m engine.cli --stats         # v20 시드 133 출력되는지 확인
```

**기대**: `카테고리 마스터 133 (…)` 라인 + posts/sentences/nodes 모두 0.

---

## 1. chat 모드 기본 — `#` 해시태그 보존, 메타 필터 대상 전체

### 실행

```python
python3 << 'EOF'
from engine.save import save
r1 = save("# 야근\n오늘 회의 길었어", mode="chat", use_llm=False)
r2 = save("나 요즘 피곤해", mode="chat", use_llm=False)
r3 = save("허리 또 아픔\n병원 다시 가야할듯", mode="chat", use_llm=False)
for i, r in enumerate([r1, r2, r3], 1):
    print(f"[save {i}] post={r.post_id} sentences={r.sentence_ids}")
EOF
```

### 자동 검증

```bash
sqlite3 ~/.synapse/synapse.db <<'SQL'
.headers on
.mode column
-- A. posts 모두 input_mode='chat'
SELECT id, input_mode FROM posts ORDER BY id;
-- B. `# 야근` 원문이 sentence 로 보존
SELECT text FROM sentences WHERE text LIKE '%야근%' ORDER BY id;
-- C. '야근' 이 카테고리로 등록되지 않음 (해시태그 감각 보존)
SELECT COUNT(*) AS yageun_cat FROM categories WHERE name='야근';
-- D. sentence_categories 에 chat 게시물 sentence 가 등록되지 않음
SELECT COUNT(*) AS chat_sc FROM sentence_categories sc
  JOIN sentences s ON s.id=sc.sentence_id
  JOIN posts p ON p.id=s.post_id WHERE p.input_mode='chat';
SQL
```

### 기대

| 항목 | 기대값 |
|---|---|
| A. input_mode | 3 건 모두 `chat` |
| B. text | `# 야근` 원문 한 줄 포함 |
| C. yageun_cat | `0` |
| D. chat_sc | `0` |

**자동 PASS 조건**: A 3건·B 포함·C=0·D=0 전부 충족.

---

## 2. markdown 모드 — heading + list 기본 (kind 분기 검증)

### 실행

```python
python3 << 'EOF'
from engine.save import save
text = (
    "# 건강\n"
    "## 허리\n"
    "- 오늘 허리 많이 아팠어\n"
    "- 데스크 오래 앉아 있어서 그런듯\n"
    "어제부터 계속 찌릿함"
)
r = save(text, mode="markdown", use_llm=False)
print(f"post={r.post_id} sentences={r.sentence_ids}")
print(f"nodes_added={r.nodes_added}")
print(f"warnings={r.category_warnings}")
EOF
```

### 자동 검증

```bash
sqlite3 ~/.synapse/synapse.db <<'SQL'
.headers on
.mode column
-- A. posts 에 input_mode='markdown' 추가
SELECT COUNT(*) AS markdown_posts FROM posts WHERE input_mode='markdown';
-- B. sentence 3건만 저장 (heading 2 건 제외)
SELECT COUNT(*) AS md_sentences FROM sentences s
  JOIN posts p ON p.id=s.post_id WHERE p.input_mode='markdown';
-- C. 카테고리 '건강.허리' 계층 생성
SELECT c.name, p.name AS parent FROM categories c
  LEFT JOIN categories p ON p.id=c.parent_id
  WHERE c.name IN ('건강','허리');
-- D. sentence_categories 연결 3건 (허리 말단)
SELECT c.name, COUNT(*) AS linked FROM sentence_categories sc
  JOIN categories c ON c.id=sc.category_id
  WHERE c.name='허리' GROUP BY c.name;
SQL
```

### 기대

| 항목 | 기대값 |
|---|---|
| A. markdown_posts | `1` |
| B. md_sentences | `3` (heading `건강`·`허리` 제외) |
| C. 계층 | `건강` (parent NULL), `허리` (parent 건강) |
| D. linked | `허리: 3` |

---

## 3. markdown 모드 — `- key:: value` 파서

### 실행

```python
python3 << 'EOF'
from engine.save import save
text = (
    "# 직장.더나은.개발팀\n"
    "- 팀장:: 박지수\n"
    "- 프론트엔드:: 김민수\n"
    "- 모델:: Gemma 4 E2B\n"
    "- 팀원 총 5명"
)
r = save(text, mode="markdown", use_llm=False)
print(f"post={r.post_id} sentences={r.sentence_ids}")
print(f"nodes_added={r.nodes_added}")
EOF
```

### 자동 검증

```bash
sqlite3 ~/.synapse/synapse.db <<'SQL'
.headers on
.mode column
-- A. key_value sentence 원문 "key:: value" 보존
SELECT text FROM sentences WHERE text LIKE '%::%' ORDER BY id;
-- B. Kiwi 가 '박지수'·'김민수'·'팀장' 노드를 뽑았는지
SELECT name FROM nodes WHERE name IN ('박지수','김민수','팀장','팀원','모델') ORDER BY name;
-- C. 일반 list '팀원 총 5명' 도 sentence 로 저장
SELECT text FROM sentences WHERE text LIKE '%팀원%';
-- D. 개발팀 말단 sentence_categories 에 4건 연결
SELECT c.name, COUNT(*) AS linked FROM sentence_categories sc
  JOIN categories c ON c.id=sc.category_id
  WHERE c.name='개발팀' GROUP BY c.name;
SQL
```

### 기대

| 항목 | 기대값 |
|---|---|
| A. text | `팀장:: 박지수`, `프론트엔드:: 김민수`, `모델:: Gemma 4 E2B` 3건 |
| B. nodes | `박지수`, `김민수`, `팀장` 최소 3건 (Kiwi 결과에 따라 추가 가능) |
| C. text | `팀원 총 5명` |
| D. linked | `개발팀: 4` (key_value 3 + list 1) |

---

## 4. markdown 모드 save-pronoun 전체 skip 실측 (병목 해소 검증)

### 실행

```python
python3 << 'EOF'
import time
import engine.save as save_mod

call_log = {"pronoun": 0, "meta": 0, "meta_input": 0}
orig_pronoun = save_mod.save_pronoun
orig_meta = save_mod.llm_meta_filter

def count_pronoun(text, context="", today=""):
    call_log["pronoun"] += 1
    return {"text": text, "unresolved": []}

def count_meta(items):
    call_log["meta"] += 1
    call_log["meta_input"] += len(items)
    return set()

save_mod.save_pronoun = count_pronoun
save_mod.llm_meta_filter = count_meta

long_md = "# 장문.시험\n" + "\n".join(
    f"- 항목 {i}: 세부 내용 {i} 번째 문장입니다." for i in range(20)
) + "\n## 메모\n" + "\n".join(
    f"이것은 자유 문장 {i} 입니다." for i in range(10)
) + "\n- 팀장:: 박지수\n- 모델:: Gemma 4 E2B"

long_chat = "\n".join(f"chat 줄 {i}" for i in range(30))

t0 = time.perf_counter()
rm = save_mod.save(long_md, mode="markdown", use_llm=True)
t_md = time.perf_counter() - t0

t0 = time.perf_counter()
rc = save_mod.save(long_chat, mode="chat", use_llm=True)
t_chat = time.perf_counter() - t0

print(f"[markdown] post={rm.post_id} sentences={len(rm.sentence_ids)} elapsed={t_md:.3f}s")
print(f"[chat]     post={rc.post_id} sentences={len(rc.sentence_ids)} elapsed={t_chat:.3f}s")
print(f"calls: {call_log}")

save_mod.save_pronoun = orig_pronoun
save_mod.llm_meta_filter = orig_meta
EOF
```

### 기대

| 항목 | 기대값 |
|---|---|
| `call_log['pronoun']` | `30` (chat 30줄만 호출, markdown 기여 0) |
| `call_log['meta']` | `2` (게시물당 1회 — markdown·chat 각 1) |
| `call_log['meta_input']` | markdown (list·free 만 = 32) + chat (30) = `62` |
| 시간 | `markdown < chat` 예상. chat 은 save-pronoun stub 30회 포함 |

**자동 PASS 조건**: `call_log['pronoun']==30` AND `call_log['meta']==2` AND `call_log['meta_input']==62`.

---

## 5. 세션노트 §4.1 오동작 재현 시도 (회귀 없어야 함)

### 실행

```python
python3 << 'EOF'
from engine.save import save
# §4.1 case A: `#` 해시태그를 markdown heading 으로 오인 → 야근 카테고리 강제 분류
r1 = save("# 야근\n오늘 회의 길었어", mode="chat", use_llm=False)
# §4.1 case B: markdown 쓰다 heading 누락 → chat 으로 떨어짐
r2 = save("오늘 회의에서 릴리즈 일정 논의", mode="chat", use_llm=False)
# §4.1 case C: 동일 텍스트 재호출 → 매번 재계산
r3a = save("허리 또 아픔", mode="chat", use_llm=False)
r3b = save("허리 또 아픔", mode="chat", use_llm=False)
print(f"[case A] post={r1.post_id} sentences={r1.sentence_ids}")
print(f"[case B] post={r2.post_id} sentences={r2.sentence_ids}")
print(f"[case C] post a={r3a.post_id} b={r3b.post_id}")
EOF
```

### 자동 검증

```bash
sqlite3 ~/.synapse/synapse.db <<'SQL'
.headers on
-- A. '야근' 이 카테고리에 없어야 (§4.1-A 회귀 없음)
SELECT COUNT(*) AS yageun_cat FROM categories WHERE name='야근';
-- B. input_mode='chat' post 가 sentence_categories 등록 없음 (§4.1-B 증상 없음)
SELECT COUNT(*) AS chat_sc FROM sentence_categories sc
  JOIN sentences s ON s.id=sc.sentence_id
  JOIN posts p ON p.id=s.post_id WHERE p.input_mode='chat';
-- C. 동일 텍스트가 독립 posts 로 저장 (세션리스 원칙, 재계산 자체가 이상 아님)
SELECT COUNT(*) AS dup_posts FROM posts WHERE markdown='허리 또 아픔';
SQL
```

### 기대

| 항목 | 기대값 |
|---|---|
| A. yageun_cat | `0` |
| B. chat_sc | `0` |
| C. dup_posts | `2` (세션리스 원칙 — 이상 아님) |

---

## 6. 입력 3종 혼합 — 전체 통합 상태 확인

### 자동 검증

```bash
sqlite3 ~/.synapse/synapse.db <<'SQL'
.headers on
.mode column
-- A. posts 분포
SELECT input_mode, COUNT(*) FROM posts GROUP BY input_mode;
-- B. sentence 수
SELECT p.input_mode, COUNT(*) AS sent
  FROM sentences s JOIN posts p ON p.id=s.post_id
  GROUP BY p.input_mode;
-- C. key_value sentence (LIKE '%::%') 만 필터
SELECT COUNT(*) AS kv_sent FROM sentences WHERE text LIKE '%::%';
-- D. 사용자 heading 루트 목록
SELECT name FROM categories WHERE parent_id IS NULL AND id > 133 ORDER BY name;
SQL
```

### 기대 (시나리오 1·2·3·5 누적 기준)

| 항목 | 기대값 |
|---|---|
| A. input_mode | `chat: 5` (시나리오 1: 3 + 시나리오 5: 2 독립 posts + `오늘 회의…` 1 = 6. 실측 확인) · `markdown: 2` |
| C. kv_sent | `3` (시나리오 3) |
| D. 사용자 루트 | `건강`, `직장` |

> note — 정확한 건수는 실행 시 확정. 방향성(chat 다수 · markdown 2 · key_value 3) 이 맞으면 PASS.

---

## 7. (옵션) 백필 마이그레이션 확인

**범위 외 — regression_v19_chat_mode.py Case 5 는 M1 이전부터 실패 상태, PLAN-003 M3 에선 재현만 확인하고 원인 수정은 PLAN-005 또는 bugfix.**

```bash
python3 -m tests.regression_v19_chat_mode 2>&1 | tail -20
```

### 기대

Case 1~4 통과 (4/5). Case 5 실패는 M1 이전부터 존재 (사실 보고만).

---

## 보고 템플릿

`deliverables/SYN/20260423/user/DOGFOOD-REPORT-PLAN-003.md` 에 아래 형식으로 저장.

```markdown
# DOGFOOD-REPORT-PLAN-003 — 실행 결과

**실행 일시**: YYYY-MM-DD HH:MM
**실행 환경**: Mac M4 / DB=~/.synapse/synapse.db / use_llm=False (기본)
**HEAD**: <git rev-parse HEAD>

## 요약

- 시나리오 N 중 M PASS / K PARTIAL / L FAIL
- 주목할 이슈: (있으면 기술 · 없으면 "없음")
- 최종 판정: 머지 가능 / 수정 후 재검증

## 시나리오별 결과

### 0. 환경 준비
- HEAD: ...
- stats 출력: ...
- 상태: PASS / FAIL

### 1. chat 모드 기본
- 실행 출력: (원문 인용)
- 자동 검증 쿼리 결과: (원문 인용)
- UX 관찰: (해시태그 보존·분류 누락 감각 등)
- 판정: PASS / FAIL

(…2~6 시나리오 동일 포맷…)

## 발견 사항

- (이슈 있으면 원인 추정 + 후속 PLAN 제안)

## 최종 판정

머지 판단 + 근거
```

---

## 완료 체크리스트

- [ ] 환경 준비 완료 (HEAD·stats 확인)
- [ ] 시나리오 1~6 실행 + 자동 검증
- [ ] save-pronoun 호출 계수 실측 (시나리오 4)
- [ ] §4.1 회귀 재현 시도 — 재발 없음 (시나리오 5)
- [ ] 보고서 저장 + 최종 판정 기록

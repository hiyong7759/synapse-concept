# SESSION-CONTINUE-001 — v12 전환 완료 + Phase 5 보강 + 다음 세션 인계

**작업 기간**: 2026-04-17 ~ 2026-04-18
**대상**: 시냅스 v12 전환 (조사 엣지 폐기 → node_mentions + /review 검토 시스템)
**원안**: [PLAN-20260417-SYN-001.md](../../20260417/user/PLAN-20260417-SYN-001.md)

---

## 1. 완료된 것

### Phase 0 — 설계 문서화
- [CLAUDE.md](../../../../projects/synapse/CLAUDE.md) v12 원칙 11개 + 저장 파이프라인 + 인출 파이프라인 + 검토 편입 명문화
- [docs/DESIGN_OVERVIEW.md](../../../../projects/synapse/docs/DESIGN_OVERVIEW.md) — 외부 참조 정책 + 지능체 분리 추가
- [docs/DESIGN_PIPELINE.md](../../../../projects/synapse/docs/DESIGN_PIPELINE.md) — 전면 재작성, 양 경로 BFS, 날짜 정규화 단계 포함
- [docs/DESIGN_ENGINE.md](../../../../projects/synapse/docs/DESIGN_ENGINE.md) — Flutter 포팅 v11 스키마 매핑 갱신
- [docs/DESIGN_REVIEW.md](../../../../projects/synapse/docs/DESIGN_REVIEW.md) (신규) — `/review` 섹션별 도출·승인 흐름

### Phase 1 — 엣지 폐기 + node_mentions
- `engine/db.py` v12 스키마 (`posts`, `node_mentions`, `unresolved_tokens`)
- `engine/llm.py` `llm_extract` edges·category 필드 드롭
- `engine/save.py` `_insert_edge` 호출 전부 제거, `_postprocess_negation` 재설계, `_correct_typos` 자동 교정 폐기, 노드 upsert 직후 `node_mentions` 기록
- `api/routes/graph.py` `SaveResponseModel.mentions_added` 추가
- `app/src/components/Chat/ChangeNotice.tsx` v12 응답 구조 반영

### Phase 2 — 마크다운 게시물 단위
- `engine/db.py` `posts` 테이블 + `sentences.post_id, position` 추가
- `engine/markdown.py` 개행 단위 분리 + `has_heading()` 보조
- `engine/llm.py` `synapse/structure-suggest` 함수 (base 모델 + 프롬프트)
- `engine/save.py` 매 `save()` = `posts` 1건 INSERT, heading 없으면 `markdown_draft` 반환 게이트
- `app/src/components/Chat/MarkdownDraftCard.tsx` (신규) — 초안 편집 UI
- `app/src/pages/ChatPage.tsx` `markdown_draft` 응답 처리

### Phase 3 — 치환 토큰 + 노드 mentions BFS
- `engine/llm.py` `save_pronoun` 반환에 `unresolved` 배열
- `engine/save.py` `_add_unresolved` 헬퍼, 치환 실패 토큰 기록
- `engine/retrieve.py` 전면 재작성 — `node_mentions` JOIN BFS + 의미 엣지 보조 경로

### Phase 4 — 카테고리 편집 API/UI
- `api/routes/graph.py` `GET/POST/DELETE/PUT /nodes/{id}/categories`, `GET /categories`
- `app/src/components/Graph/NodeCategoryEditor.{tsx,module.css}` (신규) — 칩 편집·datalist 자동완성
- `app/src/pages/GraphPage.tsx` 노드 상세 패널 통합

### Phase 5 — `/review` 런타임 제안 + UI
- `engine/suggestions.py` (신규) — 8개 도출기 + `counts`
- `api/routes/graph.py` `/review`, `/review/count`, `/review/apply`, `/review/alias-suggestions/{id}`
- `app/src/pages/ReviewPage.{tsx,module.css}` (신규) — 섹션별 카드 리스트
- `app/src/components/ReviewBadge.tsx` (신규) — 30초 polling 배지
- `app/src/categories.ts` (신규) — 17개 대분류 + ~80개 소분류 + 의미 관계 5종 한글·의미 매핑

### Phase 6 — 온보딩 인출 시뮬레이션
- `engine/suggestions.py` `missing_basic_info` 도출기 (직업·지역·관심사 키워드)
- `app/src/pages/OnboardingPage.tsx` 4단계 (welcome → chat → simulation → done) + v12 판정 적응

### 추가 보강 (Phase 5 후속)
- `engine/llm.py` `mlx_chat` 어댑터 404 fallback → `synapse/chat` (base 모델)
- `engine/save.py` ISO 날짜 → 한국어 정규화(`_normalize_dates_to_korean`) + 한글 단위 분할(`_expand_date_tokens`)
  - `2026-04-18` → 본문 `2026년 4월 18일` + 노드 `2026년`/`4월`/`18일` 모두 같은 sentence에 mention
- `api/routes/graph.py` `markdown_draft` 응답에도 `retrieve` + `answer` 함께 반환 (검색 의도 평문 호환)
- `engine/suggestions.py` `cooccur_pairs` 임계값 `min_cooccur=2`, `limit=10` (1회 우연 거름)
- `engine/suggestions.py` `unresolved`에 게시물 정보 (post_id, post_markdown, post_created_at)
- `app/src/pages/ReviewPage.tsx` 카테고리 한글 라벨 + 코드 병기, 미해결 카드 게시물 헤더 + 원본 토글

### 검증
- 백엔드 정적: 13개 라우트 200 OK (TestClient)
- 프론트 정적: `pnpm exec tsc -b` + `pnpm build` 통과
- 헤드리스 브라우저 (gstack): 5개 페이지 200 OK + 콘솔 에러 0
- E2E uvicorn + curl: PLAN E2E 4~7 시나리오 모두 통과
- 실제 LLM (base fallback) 통합:
  - 마크다운 입력 → 노드 5건 추출 + mentions ✓
  - 인출 "허리디스크" → mentions BFS + 자연어 답변 ✓
  - 평문 → `markdown_draft` 게이트 ✓
  - 날짜 분할 → "4월에 뭐 있었지?" → 두 게시물 sentence 발견 ✓

### Deliverable
- [PLAN-20260417-SYN-001.md](../../20260417/user/PLAN-20260417-SYN-001.md) — v12 전환 원안

---

## 2. 알려진 한계 (별도 WI)

### LLM 어댑터 미학습
- `data/finetune/models/tasks/` 디렉토리 비어있음 — 파인튜닝 어댑터 없음
- 현재는 `engine/llm.py` `mlx_chat` 폴백으로 base 모델(`synapse/chat`)이 어댑터 system prompt를 받아 동작
- 정확도는 어댑터에 비해 떨어지고 비결정적 (같은 입력에도 다른 응답 가능)
- **별도 WI**: 학습 데이터(`data/finetune/tasks/*/train.jsonl`)로 LoRA 학습 + RunPod FP16 파이프라인. v12 변경 반영하여 extract 어댑터는 edges·category 필드 빼고 학습 데이터 재생성 필요

### 외부 참조 / 외부 LLM 브릿지
- `engine/external.py`, `engine/bridge.py` 미구현. PLAN에서 별도 WI로 분리됨

### `_FIRST_PERSON_ALIASES` 자동 시드
- "나" 노드 생성 시 인칭대명사 11개 자동 별칭 등록 — 사용자 결정으로 유지

---

## 3. 다음 세션에 할 일 (이 문서 작성 시점에 미해결)

사용자 피드백 (2026-04-18 저녁):

> "지금 리뷰 ui에 입력하고나서 저장버튼이 없더라고 엔터로 저장되긴하는거 같은데 저장이 잘된건지 토스트 같은것도 안나오고 좀더 개선해야겠고
> 지금 전체 패턴이 잘 검증된건가? 데이터 더 넣어서
> 리뷰할거가 더 나오게 해주고 이거 약간 게임같이 해달라했는데 전혀 게임같지 가 않네"

### A. 저장 피드백 (즉시 시급)
- `/review` 카드 옵션 클릭 → **토스트** ("✓ 카테고리 추가됨", "✓ 의미 엣지 생성됨" 등)
- 카드 자체가 **체크마크와 함께 fade-out** 애니메이션 (현재는 무반응 후 reload)
- 자유 입력 textbox 옆에 **저장 버튼** 명시 (현재는 Enter만 지원)

### B. 데이터 다양화로 패턴 검증
의도적으로 다양한 카드 발생시켜 전체 패턴 확인:
- 같은 노드 쌍 2회 이상 등장 → `cooccur_pairs` 발생 (현재 데이터로는 전부 1회라 임계값 미달)
- 비슷한 이름 노드 → `suspected_typos`
- "나" 노드만 있고 직업·지역 키워드 없음 → `missing_basic_info`
- 오래 미참조 노드 → `stale_nodes`
- 며칠 공백 → `gaps`

각 카드 종류별로 실제 흐름 검증 + 옵션 클릭 → 그래프 반영 확인.

### C. 게임화 (PLAN 핵심인데 아직 누락)
**현재**: 그냥 카드 세로 리스트 — "검토 작업"으로 느껴짐.
**목표**: PLAN의 "게임화된 편입 시스템" — 짝짓기/묶기/체인/생존/일일/공백 6종류 게임 + 보상 (그래프 시각적 성장).

단계별:
- **A (즉시)**: 한 장씩 풀스크린 모드, "다음/건너뛰기" 버튼, 진행률 바 (`5 / 23`)
- **B (다음)**: 점수·콤보, 카드별 시각 차별화 (짝짓기는 두 노드 카드, 묶기는 그룹, 체인은 화살표)
- **C (나중)**: 카드 완료 직후 그래프 페이지에서 새 엣지·노드 하이라이트 애니메이션 (보상)

---

## 4. 환경 정보

### 포트
- API: `8000` (`USE_LLM=true python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level warning`)
- vite dev: `5173` (`pnpm dev --port 5173 --strictPort`)
- MLX: `8765` (`python3 api/mlx_server.py`)

### Python
- 시스템 Python `/opt/homebrew/bin/python3` (3.14)
- `mlx_lm` 설치됨 (PEP 668 우회 `--break-system-packages`)

### 브라우저 (gstack)
- Playwright Chromium 1217 다운로드됨
- gstack browse가 1208 찾으니 심볼릭 링크 만들어둠 (`~/Library/Caches/ms-playwright/chromium-1208 -> chromium-1217`)
- 헤드리스: `~/.claude/skills/gstack/browse/dist/browse`
- headed: `$B connect` → 실제 macOS Chromium 윈도우. `$B focus` 로 앞으로

### DB
- 위치: `~/.synapse/synapse.db`
- 스키마 변경 시 자동 drop·재생성 (CLAUDE.md "DB는 날려도 된다" 원칙)

### Worktree
- 경로: `/Volumes/macex/workspace/claude-agentic-subagent-team/projects/synapse/.claude/worktrees/amazing-raman-06521c`
- 브랜치: `claude/amazing-raman-06521c`
- main: `main`

---

## 5. 다음 세션 시작 프롬프트 (자기완결적 — 그대로 복사해서 입력)

```
시냅스 v12 전환 후속 작업. 이전 세션 마지막 결과는
deliverables/SYN/20260418/user/SESSION-CONTINUE-001.md 에 정리되어 있다.
그 문서의 "3. 다음 세션에 할 일" 섹션 (A 저장 피드백, B 데이터 다양화, C 게임화)
을 순서대로 진행한다.

원칙:
- 더미 데이터로 검증 금지 — 항상 실제 사용자 입력 흐름으로 검증
- LLM 어댑터 미학습 환경이므로 base 모델 fallback에 의존
  (engine/llm.py mlx_chat 의 404 fallback)
- 한국어 사전 보고 후 진행 (큰 작업은 단계별로)
- 검증은 백엔드 단위 테스트 + 헤드리스 브라우저 (gstack)

먼저 SESSION-CONTINUE-001 의 "1. 완료된 것" + "2. 알려진 한계" 를 읽고
현재 상태 파악. A 작업부터 단계별로 시작.
```

---

## 6. 미커밋 파일 (이 문서 작성 시점 git status)

전체 변경 파일은 git status로 확인. 이 세션 말미에 단일 커밋으로 묶을 예정.
다음 세션은 그 커밋 위에서 시작.

# F-bundle 인수인계 — 다음 세션 진입 프롬프트

> 새 세션 시작 시 이 문서를 읽고 들어간다. F8'-2 ~ F-bundle 5 까지 완료, F-bundle 6 (사용자 macOS 검증) 도중 사이드바 비어있는 이슈로 중단됨.

---

## 1. 현재 git 상태

**브랜치**: `feature/v22-rewrite`
**최근 커밋 (HEAD)**:
```
9212fee F-bundle step 5 — backfill = ⌘S 1 회 + 진행 로그
3aa49d3 F-bundle step 4 — noteProcess 가 새 노드 categorize → addCategoryMention
359260c F-bundle step 3 — LlmTasks.categorize 추가
90084d5 F-bundle step 2 — engineProvider 가 LlamadartInferenceBackend 활성화
691816e F-bundle PLAN — 모델 번들 마일스톤 신설
7fc59aa F8'-2-fix5 — 페어 엣지 폐기 + bipartite + sentence 색 분리
ef0ae46 F8'-2-fix2 — macOS network entitlement + 투명 배경 제거
9e39fc6 F8'-2-fix — webview_flutter → flutter_inappwebview (macOS 지원)
417a5c5 F8'-2 — /hypergraph 라우트 + WebView + vis-network 첫 렌더
```

### 미커밋 변경 (다음 세션이 결정)

```
M app/assets/graph/index.html  ← 카테고리 19 색 정의 완료 (CSS + CAT_COLOR map)
M docs/DESIGN_UI.md            ← 토큰 표 19 색 갱신, line 501 의 "7 체크박스 + [기타 12]" 표현 미정정 (19 그룹별로 갱신 필요)
```

작업 중단 직전이라 일관성 검토 안 됨. 다음 세션에서:
1. DESIGN_UI line 501 (필터 사양) 의 "7 체크박스" → "19 그룹별" 정정
2. `flutter test` 회귀 확인
3. WIP 커밋 또는 별도 마일스톤 단위로 분리

---

## 2. F-bundle 6 — 사이드바 비어있는 이슈 (정확한 진단)

**증상**: 사용자가 macOS 에서 `flutter run -d macos` 띄웠을 때 `/note` 라우트의 좌측 post 사이드바가 빈 채로 보임.

**원인**: F8'-2-fix2 에서 macOS App Sandbox 의 `com.apple.security.network.client` 추가 + F-bundle step 2 에서 `app-sandbox` Debug **OFF** 한 영향. `getApplicationDocumentsDirectory()` 의 path 가 sandbox 상태에 따라 달라진다:

| sandbox | path | 상태 |
|---|---|---|
| ON (이전) | `~/Library/Containers/dev.synapse.synapseApp/Data/Documents/synapse.db` | **사용자 데이터 그대로 (937 노드, 393 sentence, 4566 mention) — 647KB, Apr 27 수정** |
| OFF (현재 Debug) | `~/Documents/synapse.db` | **새 빈 DB — 102KB, post 0** |

확인 명령:
```bash
ls -la ~/Documents/synapse.db
ls -la ~/Library/Containers/dev.synapse.synapseApp/Data/Documents/synapse.db
sqlite3 ~/Documents/synapse.db 'SELECT COUNT(*) FROM posts'   # → 0
sqlite3 ~/Library/Containers/dev.synapse.synapseApp/Data/Documents/synapse.db \
  'SELECT COUNT(*) FROM nodes'   # → 938 (그대로)
```

**해결 옵션 (미결정 — 사용자 결정 필요)**:

| 옵션 | 설명 |
|---|---|
| **A. sandbox=true 로 되돌리기 + 외장 모델 read entitlement 추가** | 데이터 보존, 모델 read 가능. `com.apple.security.temporary-exception.files.absolute-path.read-only` 같은 entitlement 추가 필요 (deprecated 경향, 동작 검증 필요) |
| **B. sandbox=false 유지 + 데이터 마이그레이션** | `~/Library/Containers/.../synapse.db` → `~/Documents/synapse.db` 복사. 한 번만 |
| **C. sandbox=true + 외장 모델을 sandbox 내부로 심볼릭 링크** | `ln -s /Volumes/macex/models/gemma-4-...gguf ~/Library/Containers/dev.synapse.synapseApp/Data/Documents/`. `_resolveModelPath` 가 documents 폴더 내 모델도 찾도록 변경. macOS sandbox 가 심볼릭 링크 따라가는지 검증 필요 |
| **D. sandbox=false 유지 + 새 빈 DB 로 시작** | 데이터 포기. dogfood 처음부터 새로. 가장 단순 |

각 옵션의 영향 (데이터 / 모델 / 사용자 액션) 다음 세션에서 비교·결정.

---

## 3. F-bundle 까지 완료된 것 (HEAD 기준)

| 단계 | 내용 | 상태 |
|---|---|---|
| F-bundle 1 | PLAN 갱신 (F-bundle row 신설) | ✓ commit `691816e` |
| F-bundle 2 | engineProvider 가 `EngineConfig.modelPath` 채움 + LlamadartInferenceBackend 활성. `/Volumes/macex/models/gemma-4-E2B-it-Q4_K_M.gguf`. macOS Debug `app-sandbox=false` (Release 는 그대로 true) | ✓ commit `90084d5`. 부팅 시 `[engine] LLM ON` 출력 확인됨 |
| F-bundle 3 | `LlmTasks.categorize(nodeName, contextSentences) → List<String>` 추가. `assets/prompts/CATEGORY_SYSTEMPROMPT.md` 는 기존부터 있었음. 5 단위 테스트 | ✓ commit `359260c` |
| F-bundle 4 | `note_pipeline.dart` 에 `_categorizePostNodes(postId)` + `_resolveSubCategoryId(code)`. ⌘S 끝에 호출 → `addCategoryMention(origin='ai')`. `BOD.disease` → root `BOD` + leaf `disease` lookup. 3 단위 테스트 | ✓ commit `3aa49d3` |
| F-bundle 5 | 별도 backfill 코드 안 만듦. **⌘S 1 회 = 그 post 의 모든 미분류 노드 일괄 처리**. 진행 로그 (`[categorize] post=N nodes pending` / `[categorize] done/total`) | ✓ commit `9212fee` |
| F-bundle 6 | 사용자 macOS 직접 검증 (취업규칙 ⌘S → /hypergraph 색 분포) | ✗ **사이드바 비어있는 이슈로 중단** |

**테스트 상태** (HEAD):
- engine 단위: 143 통과 / 6 skip / 0 fail
- app 단위: 16 통과 / 0 fail

---

## 4. 미커밋 변경 정리 — 19 색 그룹화 (C 옵션)

사용자가 "왜 7 색이지?" 물음에 C 결정 — 시드 19 모두 색 정의 (8 그룹별 색조). 작업 중단 직전이라 일부 갱신 미완.

### 완료된 부분

`app/assets/graph/index.html` — CSS 변수 19 + `CAT_COLOR` map 19 항목

### 색 매핑 (8 그룹)

| 그룹 | 코드 | 색 |
|---|---|---|
| 사람·관계·사회 (빨강) | PER / REL / SOC | `#C85D5D` / `#D87878` / `#B85D5D` |
| 신체·심리 (보라) | BOD / MND | `#B68AC8` / `#9870B0` |
| 음식·생활 (주황·노랑) | FOD / LIV | `#D9A55D` / `#D9C58D` |
| 일·돈·법 (파랑) | WRK / MON / LAW | `#6E9DC8` / `#5D7DB0` / `#4E68A8` |
| 기술·학습 (청자·녹) | TEC / EDU | `#6E8DA8` / `#5DAB8A` |
| 자연·이동·여행 (청록) | NAT / TRV | `#8AC8B6` / `#7AB89A` |
| 문화·취미 (자홍) | CUL / HOB | `#C88AB8` / `#C870A0` |
| 종교·시간·행동 (보·회) | REG / TIM / ACT | `#8B7DA8` / `#7A7B82` / `#5D5E62` |

### 미완 부분

`docs/DESIGN_UI.md`:
- §디자인 토큰 카테고리 19 색 표 ✓ (line ~117 부근, 여러 행 추가됨)
- 시각화 가치 D ✓ (line ~408)
- 동작 사양 §노드 색상 ✓ (line ~490)
- **§필터 (line ~501)** — 아직 "7 체크박스 + [기타 12] 토글" 표현 — **19 그룹별 체크박스로 정정 필요**

---

## 5. 누적 결정 사항 (이 세션 + 이전)

### 시각 정책 (옵션 ε)
- **node-centric** — 노드가 시각의 주인공, 바구니 (sentence/category) 는 클릭 시 detail panel 텍스트로
- **bipartite (β)** — sentence 자체를 작은 다이아 점, mentions 1:1 엣지. 페어 엣지 (v15 잔재) 폐기
- **클러스터링 폐기** — post 단위 ≈ 게시물 그 자체. 사용자 "왜 안 보이지" 지적 후 폐기
- **엣지는 노드 ↔ sentence (멤버십)** 만, 노드 ↔ 노드 직접 선 X

### 가치 4 (왜 보는가)
- A. 허브 부상 (mention degree → 노드 크기)
- B. 통찰 중력 (`origin='insight'` → 앰버 + 외곽 링)
- C. 고립 발견 (degree 1 = 작은 점)
- D. 도메인 분포 (`primaryCategoryCode` → 19 색)

### 모델 정책
- 외장 `/Volumes/macex/models/gemma-4-E2B-it-Q4_K_M.gguf` (3.1GB)
- 환경변수 `SYNAPSE_MODEL_PATH` 우선, 없으면 외장 기본 경로
- iOS / Android 는 별도 마일스톤 (F-late)

### 라이브러리
- `flutter_inappwebview` 6.1.5 (webview_flutter 4.x macOS 미지원이라 갈음)
- vis-network 9.x CDN (google_fonts 와 동일 정책 — 데이터-bearing 자산만 온디바이스)

### 카테고리 정책
- LLM categorize 가 sub code 반환 (`BOD.disease`)
- root code 만 시각 색상 결정 (`primaryCategoryCode`)
- LLM 이 빈 list 반환하면 다음 ⌘S 때 다시 시도 (사용자 A 결정)
- 별도 backfill 기능 없음 — ⌘S 1 회로 채움 (`origin='ai'` 매핑 없는 노드 SELECT)

---

## 6. 다음 단계

### 우선 처리

1. **사이드바 이슈 해결** (위 §2) — 옵션 A/B/C/D 결정 후 진행
2. **DESIGN_UI line 501 필터 사양 정정** (위 §4 미완)
3. WIP 커밋 또는 정합 후 단일 커밋

### F-bundle 6 (검증)
- 취업규칙 post 에서 ⌘S → 콘솔 진행 로그 확인 (`[categorize] post=2 — 937 nodes pending` ... `[categorize] 50/937` ... )
- ~15~30 분 LLM 호출 대기
- `/hypergraph` 진입 → 노드 19 색 분포 보임
- `node_category_mentions` 0 → ≥ 100 건 검증

### F8'-3 / F8'-4 / F8'-5 (F-bundle 후)
- F8'-3: 노드 클릭 시 우측 detail panel (바구니 원문 + 카테고리 + 별칭)
- F8'-4: 좌측 필터 — 검색 / 칩 (전체/허브/✦통찰/고립) / 19 카테고리 그룹별 체크박스 / BFS 깊이 슬라이더
- F8'-5: ⊟ 접기 + 모바일 토글 + F7d/F9 wrapper 인터페이스

### F7d / F9 (F8 끝난 후)
- F7d: `/note` 그래프 패널 — `GraphView` 코어를 `postId` 필터로 wrap
- F9: `/synapse` 그래프 패널 — `nodeIds` (retrieve 캐시) 필터로 wrap

---

## 7. 환경

- macOS Debug 빌드: sandbox=false (외장 모델 read 위해)
- macOS Release 빌드: sandbox=true (production 그대로)
- 모델: 외장 (`/Volumes/macex`) — 사용자 컴퓨터 환경
- DB 위치는 sandbox 상태에 따라 갈림 (위 §2 참고)

---

## 8. 진행 룰 (전역 CLAUDE.md)

- 사전 보고 형식: 전체 목표·각 범위 목적·추천 + 회귀 리스크 + 검증
- 한국어 사전 보고 → 사용자 ㄱ → 진행
- 마일스톤 단위 한국어 커밋
- macOS 점검은 사용자 직접 (자동 빌드 verify 안 함). UI 변경 시 직접 띄워 캡처 검증
- 새 패키지 제안 시 pub.dev 플랫폼 지원 표 첨부 (이번 세션 webview_flutter 사고 — 두 번 안 일어나도록)

---

## 9. 이번 세션 사고·시정 사항 (다음 세션 참고)

| 사고 | 시정 |
|---|---|
| webview_flutter 4.x macOS 미지원 사전 검증 누락 | flutter_inappwebview 로 갈음. 다음부터 pub.dev 플랫폼 표 사전 확인 |
| 페어 엣지 자동 변환 (v15 잔재 코드화) | bipartite β 로 갈음 |
| post 단위 클러스터링 = 게시물 그 자체, 시각 가치 0 | 클러스터링 폐기 |
| 7 색만 정의로 12 도메인 회색 묻힘 | 19 색 그룹화 (C, 미완) |
| sandbox off 했을 때 DB 위치 변경으로 데이터 사라진 듯 보임 | 본 인수인계서로 명시 |
| UI 변경 시 직접 띄워 검증 안 하고 사용자에게 미룬 적 있음 | 직접 macOS 띄워 캡처 검증 도입 (이번 세션 후반) |

# /hypergraph perf + 후속 갈래 인수인계 — 2026-04-29

> 새 세션 시작 시 이 문서부터 읽어. 8-perf-A ~ C-fix 까지 마침. 8-perf-D
> (위치 DB 캐시 — 진짜 근본 해결) 미진행. F8'-4 필터 / 호버·디밍 /
> analyze info 5 도 후속.

---

## 1. git

**브랜치**: `feature/synapse-route` (이전 `feature/v22-rewrite` 에서 갈라져 옴 — 다른 세션에서 /synapse 작업과 합류)
**HEAD**: `ffa5294 resizable_split — clamp(min, max) 에서 max<min 가능성 fix`
**미커밋**: 없음

최근 흐름 (이번 세션 작업):
```
ffa5294 resizable_split — clamp(min, max) 에서 max<min 가능성 fix
08ba394 8-perf-C-fix — physics backstop timer (멈춤 의심 보호)
8bdf457 8-perf-C — 첫 stabilize 1500 → 300 iter
eb13d88 8-perf-A-fix — shape 변경 감지 시 강제 재생성
73d8245 8-perf-A — ring hybrid (N<=1 native dot, N>=2 ctxRenderer) + CSS 캐시
0431abb 8-3-ring — 다중 카테고리 노드 segment border ring
0efb6a8 8-3b-2 — categorize 진척 자동 반영 (debounced + max-wait)
3dc2654 8-3b-1 — vis-network DataSet incremental update
d5bcf1d 8-3c — ⌘S 후 hypergraphGraphProvider invalidate
e5c4dbe / 80c4579 8-3-A(-fix) — sentence 다이아 invisible
582d6b9 8-3a — ShellRoute + GraphProvider 캐시
3707cca F8'-3 — 노드 클릭 → detail panel
```

(참고) 다른 세션 commit 도 같은 브랜치에 있음:
- `969c243 AB — /synapse Q/A 스레드 + synapseTurn 실호출 + 동적 추천 칩`
- `258613b PLAN — /synapse 라우트 1차 구현 (synapse-route)`

---

## 2. 진행 중 갈래

| 갈래 | 상태 | 다음 |
|---|---|---|
| **8-perf-A** ring hybrid + CSS 캐시 | 완료. shape flip 감지 (8-perf-A-fix) 도 완료 | 사용자 macOS 검증 (perf 효과 확인) |
| **8-perf-C** stabilize 1500→300 + backstop | 완료 | 사용자 R 누르고 멈춤 사라졌는지 확인 |
| **8-perf-D** 노드 위치 DB 캐시 | 미진행. 5천+ 노드 임계 도달 전 진짜 근본 해결 | 사전 보고 + 진행 |
| **F8'-4** 필터 UI (좌측 placeholder) | 미진행. 좌측 220px 자리에 검색·칩·19 카테고리 체크박스·BFS 깊이 |  |
| **호버·디밍 polish** | 미진행. Obsidian 패턴 (비이웃 opacity 0.25) | F8'-3 의 후속 |
| **analyze info 5** | 미진행. `(_, __)` → `(_, _)` 스타일 1 분 | 사소함 |

---

## 3. 이번 세션 누적 결정

### 시각 정책
- **다중 카테고리 노드**: fill = primary 색, **border = N 색 균등 segment ring** (사용자 명시 결정)
- **insight sentence**: 앰버 다이아 + 글로우 (가치 B 통찰 중력)
- **일반 sentence**: invisible (size 0.1, 색 투명) — anchor 만, force-layout 효과 유지
- **mentions 엣지**: insight 의 엣지만 옅은 앰버, 일반은 투명 (force 만 작용)

### 데이터 흐름
- **categorize 큐 진척**: ValueNotifier → trailing 500ms + max-wait 5s debounce → `ref.invalidateSelf` → 8-3b-1 의 vis DataSet incremental
- **⌘S 후 invalidate**: postListProvider + hypergraphGraphProvider 둘 다 (note_process.run 끝)
- **부팅 backfill**: engineProvider 가 `engine.startBackgroundBackfill()` fire-and-forget
- **ShellRoute IndexedStack**: /note · /synapse · /hypergraph 영구 mount

### Perf 정책
- **첫 stabilize**: 1500 → 300 iter (5x 빠름)
- **shape hybrid**: ring N<=1 또는 insight = native dot fastpath. ring N>=2 만 ctxRenderer
- **CSS 변수 캐시**: render 시작 시 TEXT/TEXT2 한 번 → getComputedStyle 호출 2k 회 → 2 회
- **physics backstop**: 2s timer 가 안전망 (event 안 fire 시)
- **다음 단계 (D)**: 노드 좌표를 nodes 테이블에 저장 + 다음 진입 시 stabilize 자체 안 함

---

## 4. 사용자 환경 (macOS)

- `flutter run -d macos` 떠있음 (PID 33605)
- DB: `~/Documents/synapse.db` (마이그레이션됨)
- 모델: `/Volumes/macex/models/gemma-4-E2B-it-Q4_K_M.gguf` (외장)
- mentions = **1393** / distinct nodes **914 / 938 (97%)** — 사용자 데이터 거의 다 분류 완료

---

## 5. Hot reload 룰 (사용자 + 내가 모두 잊지 말 것)

| 명령 | 적용 |
|---|---|
| `r` (소문자) | dart 파일만 반영 |
| **`R` (대문자, hot restart)** | dart + assets 둘 다 (index.html 변경은 반드시 R) |
| 앱 종료 + flutter run | 전부 새로 |

→ index.html 만 수정한 commit 후엔 사용자에게 `R` 명시.

---

## 6. 이번 세션 사고·시정 (다음 세션 같은 사고 안 만들기)

| 사고 | 시정 |
|---|---|
| Hot reload 의 r 와 R 차이 모르고 사용자에게 r 만 부탁 → assets 변경 반영 안 됨 → "왜 안 나오냐" | R (대문자) 항상 명시 |
| 내가 직접 검증 가능한 것 (analyze, build, 캡처) 미루고 사용자에게 강요 | screencapture 직접 / flutter analyze / flutter test 미리 돌리고 결과만 보고 |
| 8-3-ring 도입 시 ctxRenderer 의 perf cost 미고려 → 사용자 "느림" | 모든 큰 시각 변경 전 perf 영향 추정 후 보고 |
| Shape flip (custom ↔ dot) 시 vis-network DataSet update 가 internal 재인스턴스화 안 함 → 빈 캔버스 | 8-perf-A-fix 의 shapeFlipped 감지 + destroy + 재생성 |
| `clamp(min, max)` 에서 max<min 케이스 미가드 → ArgumentError | math.max/min 으로 lowerBound 강제 (resizable_split.dart) |
| stabilizationIterationsDone 이벤트 fire 안 하는 edge case → physics 무한 frame loop | 8-perf-C-fix 의 2s backstop timer |
| 주석에 task ID (`8-3c`, `F-bundle 7`) 박음 | simplify pass 가 잡음. WHY 본문은 유지하되 task ID 제거 |
| simplify hook 강제 — 매 commit 전 /simplify 실행 필요 | 자동 가드. 무시하지 말 것 |

---

## 7. 다음 진입점 (우선순위)

### 즉시
1. **사용자 R 누른 후 화면 정상 / 멈춤 사라짐 확인** — 캡처 직접
2. 정상이면: F8'-4 (필터 UI) 또는 8-perf-D 중 사용자 결정
3. 비정상이면: 8-perf-D 우선 (위치 캐시로 stabilize 자체 회피)

### 8-perf-D 사전 보고 (다음 세션이 작성 후 ㄱ 받음)
- engine 측: nodes 테이블에 `x`, `y`, `pinned` 컬럼 추가 (DB migration). first stabilize 끝 시 좌표 저장 (`network.getPositions()` → DB UPDATE)
- app 측: 페이로드에 x/y 추가 → vis options 의 `nodes[id] = { x, y, fixed: false }` 로 시작 → physics 자동 stabilize 안 함 (또는 짧게 새 노드만)
- 효과: 두 번째 진입부터 stabilize 0 회. 새 노드만 추가 layout. 5천+ 노드 임계 견딤

### F8'-4 (필터 UI)
- DESIGN_UI line 501: 카테고리 19 체크박스 (8 그룹 헤더), 칩 (전체/허브/✦/고립), BFS 깊이 슬라이더
- 좌측 220px ResizableSplit 의 start 자리. 현재 `_FilterPanelPlaceholder` 텍스트 placeholder

---

## 8. 핵심 파일 위치

| 갈래 | 파일 |
|---|---|
| 그래프 시각 | `app/assets/graph/index.html` |
| 그래프 페이로드 | `app/lib/src/widgets/graph_view.dart` |
| /hypergraph 페이지 | `app/lib/src/pages/hypergraph_page.dart` |
| 그래프 state | `app/lib/src/state/hypergraph_state.dart` |
| categorize 큐 | `synapse_engine/lib/src/flow/categorize_queue.dart` |
| getGraph 로직 | `synapse_engine/lib/src/flow/synapse_flow.dart` (§586~ primaryByNode walk) |
| 디자인 토큰 (19 색) | `app/lib/src/theme/tokens.dart` (`categoryColors19`) |
| 라우트 (ShellRoute) | `app/lib/main.dart` |
| 분할 위젯 (clamp 사고 fix) | `app/lib/src/widgets/resizable_split.dart` |
| PLAN | `deliverables/SYN/20260425/user/PLAN-20260425-SYN-flutter-rewrite.md` |

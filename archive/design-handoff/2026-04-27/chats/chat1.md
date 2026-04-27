# 앱서비스 디자인시스템

_Started 2026-04-26 07:23 UTC_

---

## User

위 문서들 보고 실제 앱서비스에 적용할 디자인 시스템을 만들어줘

## Assistant

사용자의 Synapse 프로젝트 문서를 잘 읽었습니다. 이는 사용자 본인의 오리지널 제품이므로 (synapse 프로젝트), 디자인 시스템을 처음부터 만들어드리겠습니다.

먼저 첨부된 napkin 스케치를 확인하고, 관련 자료를 둘러보겠습니다.

_[tool: list_files]_

_[tool: list_files]_

_[tool: view_image]_

좋습니다. napkin 스케치에 이미 브랜드 방향성이 잡혀 있군요 — Playfair Display + Noto Sans KR + JetBrains Mono, 딥 네이비블랙 + 앰버골드 액센트, 시냅스 점화 메타포. 이걸 실제 앱 UI 에 적용 가능한 living design system 으로 발전시키겠습니다.

전체 시스템을 한 페이지 design canvas 에 넣어서, 토큰 → 컴포넌트 → 실제 화면 적용까지 보여드리는 방식으로 가겠습니다.

_[tool: set_project_title]_

_[tool: copy_starter_component]_

I'll plan out the design system structure now.

_[tool: update_todos]_

_[tool: write_file]_

_[tool: snip]_

Now let me build the components and screen applications.

_[tool: write_file]_

Now the foundation cards (color, type, brand) and the screen application cards.

_[tool: write_file]_

_[tool: snip]_

_[tool: write_file]_

_[tool: snip]_

_[tool: write_file]_

_[tool: done]_

_[tool: snip]_

_[tool: fork_verifier_agent]_

Synapse 설계 문서를 기반으로 디자인 시스템을 만들었습니다. 다섯 섹션의 design canvas로 구성:

**01 / Brand** — 커버, 로고 스위트 (시냅스 두 노드 + 발화 아크), 스케일 ladder
**02 / Foundations** — 컬러 팔레트 (surface/foreground/semantic 토큰), Playfair × Noto Sans KR × JetBrains Mono 타입 시스템
**03 / Components** — 버튼·뱃지·인풋·노드 글리프·정정 카드 등 베이스
**04 / Screens (Desktop)** — `/note` (3-pane: 사이드바 + 에디터 + 그래프 패널), `/synapse` (Q/A + retrieve 캐시 시각화), `/hypergraph` (필터 + 누적 그래프)
**05 / Mobile + Modal** — 모바일 적응 + 통찰 승격 모달

핵심 디자인 결정:
- **앰버 글로우는 발화·점화 순간에만** — 정적 강조 금지
- **하이퍼엣지 시각화**: 점선 타원 (바구니) + 옅은 라인 (멤버 연결). 통찰 노드는 큰 원 + 링 + 강한 글로우
- **자동저장 ≠ 의미 처리**: 상단바에서 시각적으로 분리 (success badge + primary 버튼)
- **`✦` 통찰 post**는 사이드바에서 앰버 보더로 별도 그룹

다음 단계로 추가하면 좋을 것: BFS 탐색 중 `[이 방향 제외하기]` 인터랙션, 호버 디밍 상태, /review 라우트, 빈 상태(첫 노트 작성).

## User

위 내용보고 와이어프래임에 해당하는 하이퍼그래프뷰 화면 수정해줘

## Assistant

_[tool: snip]_

_[tool: read_file]_

_[tool: snip]_

Now I'll rewrite the hypergraph view with the option ε approach: node-centric, mention-degree sizing, category color coding, co-occurrence weighted edges, isolated nodes at periphery, and a hover side panel.

_[tool: str_replace_edit]_

_[tool: snip]_

I also need to remove the now-unused `FullHypergraph` function and update the artboard size to fit the wider 3-pane layout.

_[tool: grep]_

_[tool: snip]_

_[tool: read_file]_

_[tool: str_replace_edit]_

_[tool: snip]_

_[tool: str_replace_edit]_

_[tool: snip]_

_[tool: done]_

_[tool: snip]_

_[tool: fork_verifier_agent]_

/hypergraph 화면을 옵션 ε (노드 중심) 방식으로 다시 그렸습니다:

**좌측 — 필터 사이드바**
- 19 시드 카테고리에 색상 칩 (BOD 빨강, WRK 파랑, FOD 주황, REL 보라, MED 초록, PLC 청록, TIM 회색)
- "고립만" 필터 추가
- 고립 노드 12개 경고 표시

**중앙 — 노드 중심 캔버스**
- 노드 크기 = mention degree (sqrt 스케일, 4~16px)
- 노드 색상 = 시드 카테고리
- 엣지 두께 = 공출현 가중치 (0.5~3.5px), 굵을수록 자주 함께 등장
- 허리━━물리치료 (공출현 6회) 같은 굵은 라인이 또렷
- ✦ 통찰 노드는 가장 크고 (16px) 앰버 글로우 + 외곽 링 → 무게중심처럼 떠오름
- 외곽 12시·6시·9시·3시 방향에 고립 노드를 작은 점(2.5px)으로 산재
- 노드 hover 시 그 노드 + 이웃만 또렷, 나머지는 opacity 0.25로 디밍 (Obsidian 스타일)

**우측 — Hover Detail 패널**
- 카테고리 색상 도트 + 노드명
- degree, category, user heading
- 문장 바구니 멤버 (s#3, s#28, s#106…) 텍스트로 풍부하게
- 별칭 목록
- "이 노드가 들어있는 노트로 →" 액션

**Legend** 좌상단에 추가 — 크기/두께/통찰의 의미를 코드 없이 한눈에.

바구니의 본질(멤버십·원문)은 시각 잼 없이 텍스트 패널로 빠지고, 시각의 주인공은 노드가 됐습니다. 가치 A·B·C·D 모두 살아있는 표현입니다.


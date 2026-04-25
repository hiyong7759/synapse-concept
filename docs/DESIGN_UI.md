# Synapse 설계 — UI/UX

UI 동작 원칙은 **`docs/DESIGN_PRINCIPLES.md §5`** 참고.

신규 와이어프레임은 [`PLAN-20260425-SYN-flutter-rewrite.md`](../deliverables/SYN/20260425/user/PLAN-20260425-SYN-flutter-rewrite.md) F7 (`/note`) · F8 (`/synapse`) 마일스톤에서 작성.

---

## 핵심 동작 사양

### 라우트 (모바일 우선·데스크톱 통합)

- `/note` — 지식 축적 (자동저장 + 의미 처리)
- `/synapse` — 인출·융합 세션 (통찰 승격)

`/hypergraph` (조회 전용), `/review` (검수 전용) 는 후속 PLAN.

같은 Flutter 위젯이 모바일·데스크톱에서 자연 확장. post 사이드바는 모바일에선 슬라이드 패널, 데스크톱에선 고정 패널로 노출.

### `/note` — 모든 입력의 단일 그릇

- 입력 형식 인지·선택 없음. 한 줄 메모도 긴 마크다운도 평문도 같은 입력 영역.
- **자동저장 상태 상시 표시**: `변경됨 / 저장 중… / ✓ 저장됨 (방금)` (1.5초 디바운스 + 페이지 이탈, LLM 미사용)
- **의미 처리 트리거**: ⌘S 또는 "정리" 버튼 → `⚙ 정리 중… → ✦ 정리됨` (사용자 명시, LLM 호출)
- **LLM 정정 카드 인라인**: 의미 처리 직후 / 재진입 시 노출. `[적용]` / `[무시]` 클릭 강제 (자동 적용 금지). 별칭 등록 토큰은 카드에 안 뜸 (사용자 정감 보존).
- **post 사이드바**: 번호·제목·수정시간 + ✦ insight 표시.
- **post 삭제**: 사이드바 호버 액션. sentences·mentions CASCADE.
- **재진입·이어쓰기**: post 사이드바에서 클릭 시 source 그대로 로드.

### `/synapse` — 인출·융합 세션

- 질문 입력 → `retrieve-expand` + Kiwi 보강 → BFS 인출 → `retrieve-filter` → `synapse-answer` 합성
- 답변 카드 표시 + 메시지 hover 시 `[⬆ 통찰로 승격]`
- **탐색 중 BFS 상태 시각화**: 진행 중인 노드 탐색을 가볍게 노출 (사용자 방향 개입 가능)
- **승격 시**: 새 `kind='insight'` post 생성 + 시냅스 세션 retrieve 캐시 노드 전부와 `node_sentence_mentions` 일괄 INSERT (Hebbian)

### 통찰 시각화

- `origin='insight'` sentence: 앰버 보더 + ✦ 아이콘
- `/note` 사이드바에서 통찰 post 는 ✦ 아이콘
- `/hypergraph` 뷰에서 허브 크기 강조 (후속 PLAN)

### 조직 연결 인디케이터

상단 바에 조직 연결 여부 항상 노출 (후속 PLAN).

---

## 디자인 토큰

| 항목 | 값 |
|------|----|
| Background | `#0A0B0E` (딥 네이비블랙) |
| Surface | `#141519` (다크 카드) |
| Border | `#252730` |
| Text Primary | `#E8E4D9` (웜 크림) |
| Text Secondary | `#7A7B82` |
| Accent | `#C8A96E` (앰버골드 — 하이퍼그래프 노드, 핵심 액션) |
| Success | `#5DAB8A` |
| Danger | `#C85D5D` |
| Hyperedge Line | `#3A3D4A` (하이퍼엣지 시각화 선) |

### 타이포그래피

| 역할 | 폰트 | 용도 |
|------|------|------|
| Display | Playfair Display | 로고, 온보딩 헤드라인 |
| Body KR | Noto Sans KR | 대화, 본문 전반 |
| Mono | JetBrains Mono | 하이퍼그래프 노드 이름, 카테고리 코드 표시 |

### 컨셉

"나만 아는 비서." 외부에 데이터가 없다는 사실이 디자인에서도 느껴져야 한다. 따뜻하고 정밀하며, 기계적이지 않은 인터페이스.

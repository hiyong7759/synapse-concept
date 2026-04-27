# Synapse 디자인 시스템

> **이 문서는 가이드다.** 토큰 값·컴포넌트 시그니처의 단일 출처는 코드 자체.
> 변경하려면 코드를 고치고 이 문서는 따라 업데이트한다 — 반대 방향 금지.

## 단일 출처 매트릭스

| 자산 | 단일 출처 | 비고 |
|---|---|---|
| 색·폰트·spacing·radius·glow·motion 토큰 | [`app/lib/src/theme/tokens.dart`](../app/lib/src/theme/tokens.dart) | 인라인 hex/px 금지 |
| 베이스 컴포넌트 | [`app/lib/src/widgets/components/`](../app/lib/src/widgets/components/) | 5종 — `SButton` `SBadge` `STextInput` `SNodeGlyph` `SBrandMark`/`SBrandLockup` |
| 와이어 (HTML/JSX 원본) | [`archive/design-handoff/2026-04-27/`](../archive/design-handoff/2026-04-27/) | claude.ai/design 에서 export 한 스냅샷. 변경 안 됨 — 새 핸드오프는 새 날짜 디렉토리 |
| 라우트·서비스 흐름·인터랙션 명세 | [`docs/DESIGN_UI.md`](DESIGN_UI.md) | "어떻게 동작하나" |
| 디자인 원칙 (12개) | [`docs/DESIGN_PRINCIPLES.md`](DESIGN_PRINCIPLES.md) §5 | 시각 동작의 의미론 |

## 토큰 빠른 참조

코드에서는 항상 `SynapseTokens.X`. 옛 alias (`background`, `caption`, `spaceL`) 는 M3 에서 다 제거됨 — 다시 추가 금지.

### Surface (8단계)
`bg` `bg2` `surface` `surface2` `surface3` `border` `border2` `borderStrong`

### Foreground (4단계)
`text` `text2` `text3` `text4` — 본문 → 비활성

### Brand
`accent` `accent2` `accentSoft` `accentLine`

### Semantic
`success` `danger` `warning` `info`

### Hypergraph
`node` `nodeHub` `nodeInsight` `hyperedge` `hyperedgeSoft`

### Spacing — `s1` `s2` `s3` `s4` `s5` `s6` `s8` `s10` `s12` (4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 px)
### Radius — `rSm` `rMd` `rLg` `rXl` (4 / 6 / 10 / 14 px)
### Type scale — `tXs` `tSm` `tBase` `tMd` `tLg` `tXl` `t2xl` `t3xl` `tDisplay`
### Type families — `displayStyle()` `bodyStyle()` `monoStyle()` (Playfair / Noto Sans KR / JetBrains Mono)
### Shadow / Glow — `shadow1` `shadow2` `shadow3` `glowAmber` `glowAmberSm`
### Motion — `durFast` `durBase` `durSlow` `ease`

> **앰버 글로우는 발화·점화 순간에만.** 정적 강조에 `glowAmber` 쓰지 않는다.

## 베이스 컴포넌트 사용법

```dart
import '../widgets/components.dart';   // barrel — 한 줄로 5종 다 들어옴
```

### `SButton`
- variant: `primary` (브랜드 액션·앰버 fill·hover 글로우) / `secondary` / `ghost` / `outline` (앰버 보더만 — 통찰 승격 등 중요·되돌릴 수 있는 액션) / `danger`
- size: `sm` / `md` (default) / `lg`
- icon: `Widget?` — 14px 권장. 색은 자동
- kbd: `String?` — `'⌘S'` 같은 단축키 힌트

### `SBadge`
- tone: `neutral` / `insight` (앰버 soft) / `success` / `danger` / `mono` (JetBrains Mono + uppercase + 트래킹 — 카테고리 코드 BOD/WRK/...)

### `STextInput`
- focus 시 보더가 `border2 → accentLine`
- `mono: true` — 노드명 검색 등

### `SNodeGlyph`
- 인라인/칩 버전. 본체 그래프 (F8) 는 CustomPaint 직접
- 상태: `hub` (액센트 fill + 작은 글로우) / `insight` (큰 글로우 + 외곽 링) / `dim` (opacity 0.35)

### `SBrandMark` / `SBrandLockup`
- `SBrandMark(size, glow)` — 두 뉴런 + 발화 아크 (CustomPaint)
- `SBrandLockup(size, glow)` — 마크 + Playfair "Synapse" 워드마크. TopBar 표준

## /hypergraph 작업 시 절차 (F8)

1. **와이어 참조** — [`archive/design-handoff/2026-04-27/project/screens.jsx`](../archive/design-handoff/2026-04-27/project/screens.jsx) 의 `HypergraphScreen`, `HypergraphFilters`, `NodeCentricGraph`, `GraphLegend`, `NodeDetailPanel` 4 함수
2. **레이아웃** — `ResizableSplit(start: HypergraphFilters, center: NodeCentricGraph, end: NodeDetailPanel)`. TopBar 의 `/hypergraph` 탭은 현재 disabled — `top_bar.dart` 에서 `onTap` 활성화
3. **카테고리 색** — 와이어의 `CAT_COLORS` (BOD/WRK/FOD/REL/MED/PLC/TIM 7개) 는 19시드 전체로 확장 필요. `tokens.dart` 의 Hypergraph 섹션에 `Map<String, Color> categoryColors` 또는 별도 enum
4. **본체 그래프** — `CustomPaint`. 노드 반지름 = `min(14, 3 + sqrt(degree) * 2.2)`, 통찰은 16. 엣지 굵기 = `min(3.5, 0.5 + weight * 0.4)`. 호버 시 비이웃 opacity 0.25 (Obsidian 디밍)
5. **재사용** — `STextInput` (검색), `SBadge` (전체/허브/✦통찰/고립만 필터), `SButton.ghost` (`+`/`fit`/`−` 줌)
6. **인라인 hex 금지** — 새 색이 필요하면 먼저 `tokens.dart` 에 등록

## 새 토큰 추가 절차

1. `tokens.dart` 에 추가 — 의미 있는 이름, 비슷한 토큰 옆 그룹화
2. `tokens.css` 와 동기 유지 (있다면)
3. 이 문서의 빠른 참조 표에 한 줄 추가
4. 호출처는 PR 단위로 — 한 컴포넌트가 한 토큰 쓰면 `git grep` 으로 확인

## 새 베이스 컴포넌트 추가 기준

- 와이어에서 **3곳 이상** 반복되는 시각 패턴이어야 함
- 도메인 로직 (riverpod 등) 의존 금지 — 토큰만으로 그릴 수 있어야 함
- `widgets/components/` 에 `s_*.dart` 로 추가하고 `widgets/components.dart` barrel 에 export

도메인 위젯 (post_sidebar, note_editor 등) 은 `widgets/` 직속에 두고 베이스 컴포넌트를 *조립* 한다.

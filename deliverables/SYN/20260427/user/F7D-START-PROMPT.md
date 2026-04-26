# F7d 진입 프롬프트 — 노트 그래프 패널

> 새 세션 시작 시 이 프롬프트를 그대로 입력.

---

PLAN-20260425-SYN-flutter-rewrite 의 F7d 마일스톤 진입한다 (F7 분할의 그래프 시각화 절반).

## 현재 상태

- 브랜치: `feature/v22-rewrite`
- 작업 디렉토리: `/Volumes/macex/workspace/claude-agentic-subagent-team/projects/synapse`
- 최근 commit: `428d66a` (F7c-fix — Kiwi 실 백엔드 + 라벨 일관성 + post 갈음 시 process clear)
- F1·F2·F3·F4·F5a·F5b·F6·F7a·F7b·F7c 완료
- 단위 테스트: synapse_engine 129 통과 / app 14 통과 / 통합 6 스킵 (LLM 4 + Kiwi 2)
- macOS 검증 통과: ⌘S 의미 처리 → nodes 938 / sentences 395 / mentions 4566 / categories 254 (취업규칙 본문 1 회 ⌘S 결과)
- iOS·Android·Windows 점검은 후속 (사용자 환경 준비 시)

## F7d 명세 (PLAN §3 F7 row 의 그래프 패널 절반)

| 항목 | 내용 |
|---|---|
| 산출물 | 해당 post 의 노드/sentence/카테고리 시각화 패널 (DESIGN_UI line 122-152). 데스크톱 3-pane 의 우측 컬럼, 모바일 📊 토글. 노드 hover 시 같은 sentence 멤버 highlight |
| 검증 | 사용자 macOS 점검 — 본문 입력 + ⌘S 후 그래프 패널에 노드 등장. 노트 갈음 시 그래프도 갈음 |

## 단일 출처 문서

- `docs/DESIGN_UI.md` line 122-152 (데스크톱 3-pane 와이어프레임), line 154-178 (모바일 토글)
- `docs/DESIGN_HYPERGRAPH.md` (노드·sentence·category 스키마)

## 누적 결정 사항 (이 세션 + 이전 세션 합의)

### F7 분할 (사용자 결정)
- F7a: 골격 (사이드바·에디터·그래프 패널 자리)
- F7b: 자동저장 + 재진입 + 제목 편집 + 삭제 (b1~b14 까지 polish 포함)
- F7c: ⌘S 의미 처리 + 정정 카드
- **F7d (이번 마일스톤)**: 그래프 패널

### 라이브러리·렌더링 (검토 대상)
- 시각화 — 외부 라이브러리 (`flutter_force_directed_graph` 등) vs 직접 구현 (CustomPainter + 단순 force-layout)
- 추천: **직접 구현 (~150줄)** — 한 post 의 노드는 보통 10~50 개라 외부 라이브러리 무거움
- 사용자 결정 받기

### 시각 정책
- 노드: dot + name 라벨
- edge: 같은 sentence 안 노드 페어 (공출현)
- 카테고리: 하단에 노드 묶음 라벨
- hover: 같은 sentence 의 다른 노드 highlight
- DESIGN_UI 의 와이어프레임 line 130-145 그대로 매핑

### 데이터 흐름
- `selectedPostIdProvider` → `postGraphProvider (FutureProvider.autoDispose)` 가 해당 post 의 nodes·sentences·mentions·categories fetch
- post 갈음 시 자동 invalidate
- ⌘S 직후에도 invalidate 필요 (noteProcess 가 nodes 새로 추가)

### 시각 가중치 (이전 피드백 반영)
- 아이콘 일관성 — 한쪽만 ⚙ ✦ 같은 이모지 X. 텍스트 또는 아이콘 통일
- 시각 흔들림 X (위치 이동·크기 변화 최소화)

### F7c-fix 완료
- `engineProvider` 가 `FlutterKiwiBackend.load()` 사용 (실 형태소 분석)
- LLM 은 모델 번들 미도입이라 비활성 — typoNormalize stub, metaFilter null 통과
- 노드 추출은 Kiwi 단독으로 충분히 동작 검증

### 다음 후속 (F7d 다음)
- F8: `/hypergraph` 별도 라우트 — 전체 누적 그래프 + 허브 노드 강조 + 검색·필터·BFS 깊이 슬라이더
- F9: `/synapse` 페이지 (Q/A 스레드, 통찰 승격 모달)
- F10: 3 플랫폼 통합 검증
- 별도: 모델 번들 + LLM 활성화 (F-late 영역, ~3.1GB Gemma)

## 진행 룰 (전역 CLAUDE.md)

1. 사전 조사 → 결과 보고 → 결정 받기 → 본 작업 사전 고지 → 사용자 승인 → 작업 → 마일스톤 커밋 → 진행 보고 → "ㄱ"/"진행"/"계속" 대기
2. 본 작업 사전 고지 형식 (필수): 전체 목표·각 범위 목적·추천 + 회귀 리스크 + 검증 (간결 명료, 단순 파일 나열 X)
3. 한국어 사전 보고 — 작업 직전 한국어로 뭘 할지 고지 후 승인
4. 마일스톤 단위 커밋 메시지 한국어
5. macOS 점검은 사용자 직접 (자동 빌드 verify 안 함)

## 보고 형식

```
✅ 완료: ...
📁 변경 파일: ...
➡️ 다음 단계: ...
🔍 검토 체크리스트:
  - 완결성
  - 회귀 리스크
  - 원칙 준수
  - 롤백 가능성
```

## 작업 시작

먼저 F7d 사전 조사:
1. DESIGN_UI line 122-152 의 와이어프레임 — 노드 dot 배치·edge 모양·카테고리 묶음·hover 동작
2. 그래프 데이터 fetch 패턴 — 한 post 에서 노드·sentence·mentions·categories 한 번에 가져오는 SQL
3. 외부 라이브러리 vs 직접 구현 — 노드 50 개 이내 force-directed layout 직접 구현 가능성
4. 모바일 토글 — `_showGraph` 가 이미 있어서 GraphPanelPlaceholder 자리에 NoteGraphPanel 갈음만

조사 후 사용자 결정 받고 본 작업 사전 고지 → 승인 → 들어간다.

# Poomacy NLI Chat — 구현 계획 (2026-03-29 승인)

**Synapse 현황은 `synapse/docs/SYNAPSE_STATUS.md` 참고.**

## Poomacy v2 기술 스택

```
프레임워크: React 19 + Vite 7 + TypeScript
스타일:    Tailwind CSS 4 + Shadcn/ui
라우터:    React Router DOM 7
테스트:    Vitest + Playwright
HTTP:     Axios (토큰 자동 갱신)
프로젝트:  /projects/poomacy-v2/
```

## 기존 NLI 시스템 (src/nli/)

```
L1 (패턴): 9개 도메인, 500+ regex, <1ms, 무료
  hrPatterns, messagePatterns, boardPatterns, noticePatterns,
  queryPatterns, reservationPatterns, expensePatterns, documentPatterns, welfarePatterns

L2 (로컬 LLM): Groq llama-3.3-70b, 카테고리별 최소 프롬프트
  7 카테고리: VACATION, ATTENDANCE, QUERY, MESSAGE, NOTICE, RESERVATION, UNKNOWN

L3 (클라우드 LLM): 미구현 (disabled)

라우팅: L1 confidence ≥ 0.9 → 바로 실행, 아니면 L2 호출
```

### 기존 NLI 입력바
- 위치: `src/components/layout/NLIInputBar.tsx` (730줄)
- 퀵 프레이즈: 내일 휴가, 다음주 월요일 연차, 오늘 야근 공지 등
- 응답 카드: VacationRequestCard, NoticeTemplateCard, LunchRouletteCard 등

### 기존 dchat (메신저)
- 위치: `src/pages/dchat/`
- 사람 간 P2P 메신저 (WebSocket). AI Chat과 별도.
- 컴포넌트 재사용 안 함 (구조가 다름).

## @synapse/core 설치

```bash
npm install ../synapse/core
```

로컬 패키지 (npm 미배포). 빌드 완료 (`dist/` 존재).
core 코드 변경 시 `cd ../synapse/core && npm run build` 후 재설치.

## Claude API 호출 — 프록시 + 스트리밍 구조

### 전체 흐름

```
브라우저
    │
    ├─ [1] 사용자가 질문 입력
    │
    ├─ [2] 브라우저 안에서 Synapse 동작 (sql.js)
    │      graph.db 탐색 → 맥락 프롬프트 조립
    │      맥락 + 질문을 합침
    │
    ├─ [3] 합쳐진 프롬프트를 서버로 전송
    │      POST /api/llm/stream
    │
    ▼
프록시 서버 (:3001)
    │
    │  프록시는 맥락이 뭔지 모름. 받은 프롬프트를 그냥 전달.
    │
    ├─ claude --print --output-format stream-json --verbose "{프롬프트}"
    │
    ├─ 토큰 단위로 SSE 스트리밍 → 브라우저에 실시간 표시
    │
    ▼
브라우저
    │
    ├─ [4] Claude 응답을 실시간으로 렌더링 (마크다운, 코드 블록)
    │
    └─ [5] 대화 로그를 브라우저 로컬 sessions.db에 저장
```

서버는 프롬프트를 Claude에 전달하고 응답을 스트리밍하는 역할만.
그래프 탐색, 맥락 조립, 대화 로그 저장은 전부 브라우저에서.

### Claude CLI 스트리밍

```bash
# 스트리밍 모드
claude --print --model sonnet --output-format stream-json --verbose "질문"

# 응답이 토큰 단위로 실시간 전송:
{"type":"assistant","content":"패"}
{"type":"assistant","content":"키지"}
{"type":"assistant","content":" 분리"}
...
{"type":"result","content":"전체 응답..."}

# SSE로 브라우저에 실시간 표시 → ChatGPT처럼 타이핑 효과
```

### 모델 선택

```bash
claude --print --model opus "질문"     # 복잡한 작업, 구조화
claude --print --model sonnet "질문"   # 일반 대화
claude --print --model haiku "질문"    # 간단한 질문, FAQ
```

### 세션 유지 (--resume)

```bash
# 첫 호출 → session_id 반환
claude --print "질문" --output-format json
# → { "session_id": "abc123", ... }

# 이어서 대화
claude --print --resume abc123 "아까 뭐라고 했지?"
```

### 대화 이력 관리: 두 모드

```
세션 유지 (--resume):
  첫 질문 → 맥락 + 질문 → session_id 반환
  이후 → --resume {session_id} → 맥락 재주입 불필요
  적합: 긴 대화, 이어지는 작업

독립 호출:
  매 질문 → 맥락 + 질문 → 매번 새로
  맥락 일관성은 Synapse가 보장
  적합: 단발 질문, FAQ
```

### 기존 NLI LLM과의 관계

```
NLI 패턴 매칭 (L1): 프록시 불필요, 브라우저에서 직접 처리
NLI LLM (L2):       Groq 제거 → Claude CLI haiku로 대체
AI Chat (Claude):    /api/llm/stream (새 프록시 엔드포인트) → Claude CLI
```

### 컨셉

하나의 입력에서 NLI 업무 명령과 AI 대화를 자동 구분하는 통합 채팅 페이지.
Claude.ai 스타일 UI + Synapse 맥락 주입 + 기존 NLI 패턴 시스템 통합.

### 입력 라우팅

```
사용자 입력
  ├─ "/" 로 시작 → NLI 스킬 목록 표시
  ├─ L1 패턴 매칭 (confidence ≥ 0.9) → NLI 카드 응답
  └─ 나머지 → Synapse 맥락 + Claude API 호출 → AI 대화
```

### 승인된 와이어프레임

#### 데스크톱 — 새 채팅 (빈 상태)

```
┌──────────────────────┬──────────────────────────────────────────────────┐
│  SIDEBAR (260px)     │                                                  │
│                      │                                                  │
│  NLI                 │                                                  │
│                      │         ✳️ 저녁 인사드려요, 용희님                │
│  + 새 채팅            │                                                  │
│  🔍 검색              │  ┌──────────────────────────────────────────┐   │
│                      │  │ 스킬을 보려면 /를 입력하세요              │   │
│  최근 항목            │  │                                          │   │
│  ┌────────────────┐  │  │ +                    Sonnet ∨       ⎍⎍⎍  │   │
│  │ 시냅스 모델설계  │  │  └──────────────────────────────────────────┘   │
│  │ 아보카도 무게    │  │                                                  │
│  │ ...            │  │  [🏖 내일 휴가] [📅 다음주 월요일 연차]           │
│  └────────────────┘  │  [🌙 오늘 야근 공지] [🍺 이번주 금요일 회식]      │
│                      │                                                  │
│                      │  [💬 코드 리뷰]  [💬 이력서 작성]                 │
│                      │  [💬 개발환경 추천]  [💬 상태관리 비교]            │
│                      │                                                  │
│  👤 용희              │                                                  │
└──────────────────────┴──────────────────────────────────────────────────┘
```

#### 데스크톱 — 대화 중 (NLI + AI Chat 혼합)

```
┌──────────────────────┬──────────────────────────────────────────────────┐
│  SIDEBAR             │  오늘의 업무                              ∨     │
│                      │                                                  │
│  NLI                 │     ┌────────────────────────────┐              │
│                      │     │ 출근합니다                  │ (You)        │
│  + 새 채팅            │     └────────────────────────────┘              │
│  🔍 검색              │                                                  │
│                      │  ┌──────────────────────────────────────┐       │
│  최근 항목            │  │ ✅ 출근 처리 완료 (09:02)             │ NLI  │
│  ┌────────────────┐  │  └──────────────────────────────────────┘       │
│  │ ● 오늘의 업무   │  │                                                  │
│  │ 시냅스 모델설계  │  │     ┌────────────────────────────┐              │
│  │ 아보카도 무게    │  │     │ 오늘 할 일 정리해줘        │ (You)        │
│  └────────────────┘  │     └────────────────────────────┘              │
│                      │                                                  │
│                      │  🧠 Synapse                                     │
│                      │  ┌──────────────────────────────────────┐       │
│                      │  │ 고용정보망통합유지관리 (프로젝트)       │       │
│                      │  │ BA (역할)                             │       │
│                      │  └──────────────────────────────────────┘       │
│                      │                                                  │
│                      │  Claude                                         │
│                      │  ┌──────────────────────────────────────┐       │
│                      │  │ 현재 프로젝트 기준으로 정리하면:       │       │
│                      │  │                                      │       │
│                      │  │ 1. 고용정보망 통합 유지관리            │       │
│                      │  │    - BA 역할 수행 중                 │       │
│                      │  │    - 이번 주 산출물: ...              │       │
│                      │  │                                      │       │
│                      │  │ ```typescript                        │       │
│                      │  │ // 코드 블록                          │       │
│                      │  │ ```           [📋 복사] [⬇ 다운로드]  │       │
│                      │  │                                      │       │
│                      │  │ ┌────────────────────────────────┐   │       │
│                      │  │ │ 📄 주간보고_0329.md             │   │       │
│                      │  │ │ 문서 · MD            [다운로드]  │   │       │
│                      │  │ └────────────────────────────────┘   │       │
│                      │  │                                      │       │
│                      │  │              [📋 복사] [📌 저장]      │       │
│                      │  └──────────────────────────────────────┘       │
│                      │                                                  │
│                      │  📌 맥락: 고용정보망, BA                         │
│                      │                                                  │
│                      │     ┌────────────────────────────┐              │
│                      │     │ 내일 오전반차 신청해줘      │ (You)        │
│                      │     └────────────────────────────┘              │
│                      │                                                  │
│                      │  ┌──────────────────────────────────────┐       │
│                      │  │ 📋 휴가 신청                          │ NLI  │
│                      │  │ ┌────────────────────────────────┐   │       │
│                      │  │ │ 유형: 오전반차                  │   │       │
│                      │  │ │ 날짜: 2026-03-30              │   │       │
│                      │  │ │      [수정 ✏️]    [신청]       │   │       │
│                      │  │ └────────────────────────────────┘   │       │
│                      │  └──────────────────────────────────────┘       │
│                      │                                                  │
│  👤 용희              ├──────────────────────────────────────────────────┤
│                      │  [🏖 내일 휴가] [🌙 야근 공지] [❓ 휴가 남은거]   │
│                      │  스킬을 보려면 /를 입력하세요                     │
│                      │  +                         Sonnet ∨       ⎍⎍⎍  │
└──────────────────────┴──────────────────────────────────────────────────┘
```

#### 모바일

```
┌──────────────────────┐
│ ☰  오늘의 업무    [+] │
├──────────────────────┤
│                      │
│   ┌────────────────┐ │
│   │ 출근합니다      │ │
│   └────────────────┘ │
│                      │
│ ✅ 출근 처리 (09:02)  │
│                      │
│   ┌────────────────┐ │
│   │오늘 할 일 정리  │ │
│   └────────────────┘ │
│                      │
│ 🧠 고용정보망, BA     │
│                      │
│ Claude               │
│ 현재 프로젝트 기준... │
│                      │
│ 📄 주간보고.md        │
│            [다운로드]  │
│                      │
│ [📋 복사] [📌 저장]   │
│ 📌 맥락: 고용정보망   │
│                      │
│   ┌────────────────┐ │
│   │내일 오전반차    │ │
│   └────────────────┘ │
│                      │
│ 📋 휴가 신청          │
│ 오전반차 / 2026-03-30│
│ [수정 ✏️]    [신청]  │
├──────────────────────┤
│ [🏖 휴가] [🌙 야근]   │
│ 스킬: /를 입력       │
│ +       Sonnet ∨  ⎍  │
└──────────────────────┘
```

#### 📌 저장 클릭 시 모달

```
┌──────────────────────────────────┐
│ 📝 다음을 시냅스에 저장할까요?    │
│                                  │
│ 노드:                            │
│   ☑ Zustand (기술)               │
│   ☑ create() (기술)              │
│                                  │
│ 관계:                            │
│   ☑ Zustand --(API)--> create()  │
│                                  │
│ [취소]              [저장]       │
└──────────────────────────────────┘
```

#### 상태 변화

- **빈 상태:** 인사말 + 입력바 + 퀵 프레이즈 (NLI + AI 혼합)
- **로딩:** Claude 응답 대기 시 ● ● ● typing indicator
- **에러:** "⚠️ 응답을 받지 못했습니다. [다시 시도]"
- **NLI 처리 중:** L1 "패턴 분석중..." / L2 "LLM 생각중..."

### Synapse 맥락 → Claude 프롬프트 합성 예시

```
사용자 입력: "상태관리 뭐 쓸까?"

1. search.getContext("상태관리 뭐 쓸까?") 호출
2. 반환된 prompt:

   "[사용자 맥락 정보]
    - Zustand (기술)
    - Redux (기술)
    관계:
      Zustand --(프레임워크)--> Poomacy"

3. Claude에 보내는 최종 프롬프트:

   "[사용자 맥락 정보]
    - Zustand (기술)
    - Redux (기술)
    관계:
      Zustand --(프레임워크)--> Poomacy

    ---

    사용자 질문: 상태관리 뭐 쓸까?"
```

### sessions.db 스키마 (브라우저 로컬, sql.js)

```sql
CREATE TABLE sessions (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    claude_session_id TEXT,     -- Claude CLI --resume용
    model      TEXT NOT NULL DEFAULT 'sonnet',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,    -- user | assistant | nli | synapse
    content    TEXT NOT NULL,
    metadata   TEXT,             -- JSON: NLI 카드 데이터, 맥락 노드 등
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

- role: user(사용자), assistant(Claude), nli(NLI 카드 응답), synapse(맥락 카드)
- metadata: NLI 카드는 `{type: "vacation", data: {...}}`, 맥락은 `{nodes_used: [...]}`

### 프록시 서버

Claude CLI를 호출하는 새 프록시 엔드포인트를 별도로 만든다.
Spring 백엔드와 별개. dchat 프록시 사용하지 않음. Groq 사용하지 않음.

```
새 프록시:
  POST /api/llm/stream → Claude CLI spawn → SSE 스트리밍
  Body: { prompt, model, session_id? }
  Response: SSE stream

Vite 프록시 (vite.config.ts):
  /api/llm/* → 새 프록시 서버
```

NLI L1 패턴 매칭은 브라우저에서 직접 처리 (프록시 불필요).
NLI L2는 같은 프록시를 통해 Claude CLI haiku로 대체.

### 필요한 컴포넌트 (위치는 프로젝트 구조에 맞게 결정)

```
페이지:
  NLIChatPage              — 메인 페이지 (사이드바 + 채팅 영역)

컴포넌트:
  ChatSidebar              — 사이드바 (새 채팅, 검색, 히스토리)
  ChatArea                 — 채팅 영역 (메시지 목록 + 입력바)
  MessageList              — 메시지 목록 렌더링
  MessageBubble            — 개별 메시지 (user/assistant/nli/synapse 분기)
  NLICard                  — NLI 응답 카드 (휴가, 출근 등) + [수정] 버튼
  SynapseContextCard       — 🧠 맥락 카드 (접기/펼치기)
  AIChatInput              — 입력바 (퀵 프레이즈 + 텍스트 + 모델 선택)
  CodeBlock                — 코드 블록 (복사 + 다운로드)
  ArtifactCard             — 파일 아티팩트 카드 (다운로드)
  SaveToSynapseModal       — 📌 저장 확인 모달

훅:
  useAIChat                — AI Chat 상태 관리 (메시지, 세션, 스트리밍)
  useSynapse               — Synapse 초기화 + 맥락 조회

서비스:
  claudeService            — Claude API 호출 (SSE 스트리밍)
  sessionService           — sessions.db CRUD (sql.js)
```

### 구현 순서

```
1단계: 기본 틀
  NLIChatPage + ChatSidebar + ChatArea + AIChatInput
  라우터 추가 (/nli-chat)

2단계: AI Chat
  claudeService (SSE 스트리밍)
  useAIChat (메시지 상태)
  MessageBubble (마크다운 렌더링)
  CodeBlock + ArtifactCard

3단계: NLI 통합
  입력 라우팅 ("/" → 스킬, L1 패턴 → NLI 카드, 나머지 → Claude)
  NLICard ([수정] → 페이지 이동, [신청] → 실행)

4단계: Synapse 통합
  useSynapse (SqlJsAdapter 초기화, IndexedDB 영속화)
  SynapseContextCard (맥락 표시)
  SaveToSynapseModal (📌 저장)

5단계: 세션 관리
  sessionService (sessions.db)
  ChatSidebar 히스토리
  Claude --resume 세션 유지
```

### 기존 Poomacy 재사용 가능 컴포넌트
- Shadcn/ui (Button, Input, Card, Skeleton 등)
- Tailwind CSS 스타일링
- NLI 패턴 시스템 (src/nli/) — L1 매칭 로직 그대로
- NLI 카드 컴포넌트 (NoticeTemplateCard, LunchRouletteCard 등)
- apiClient (Axios + 토큰 관리)
- useAuth 훅

### 기존 dchat과의 관계
- dchat = 사람 간 P2P 메신저 (WebSocket). 별도 유지.
- NLI Chat = AI 대화 + 업무 명령. 새 페이지.
- 컴포넌트 재사용하지 않음 (구조가 다름).

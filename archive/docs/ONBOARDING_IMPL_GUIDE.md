# Poomacy 시냅스 온보딩 — 구현 가이드

## 문제

현재 "시냅스 온보딩" 버튼을 눌러도 LLM이 뭘 해야 하는지 모른다.
시스템 프롬프트가 `"당신은 푸마시 그룹웨어의 AI 어시스턴트입니다"` 뿐이라
모델이 휴가 신청 가이드 같은 걸 지어낸다.

## 해결 구조

온보딩은 **일반 AI 대화가 아니다.** 단계별 가이드 대화 → 응답 파싱 → 노드 저장 플로우.

```
[시냅스 온보딩] 클릭
    ↓
온보딩 전용 시스템 프롬프트 주입
    ↓
LLM이 단계별 질문 (기술 → 장비 → 프로젝트 → 건강 → ...)
    ↓
사용자 응답마다 → 노드/엣지 JSON 추출 → SaveToSynapseModal
    ↓
check_onboarding 기준 충족 시 완료
```

---

## 1. 온보딩 모드 상태

`useAIChat.ts`에 온보딩 모드 플래그 추가.

```typescript
// 상태
const [onboardingMode, setOnboardingMode] = useState(false);
const [onboardingStep, setOnboardingStep] = useState(0);
```

"시냅스 온보딩" 버튼 클릭 시:
```typescript
setOnboardingMode(true);
setOnboardingStep(0);
// 첫 메시지를 자동 전송 (사용자 입력 없이 LLM 호출)
```

---

## 2. 온보딩 전용 시스템 프롬프트

일반 대화 프롬프트 대신 이걸 주입한다.

```typescript
const ONBOARDING_SYSTEM_PROMPT = `당신은 시냅스(Synapse) 개인 지식 그래프의 온보딩 도우미입니다.

## 목표
사용자의 정보를 자연스러운 대화로 수집하여 개인 지식 그래프를 초기 구축합니다.

## 규칙
1. 한 번에 하나의 주제만 질문한다. 질문은 짧고 구체적으로.
2. 사용자 응답에서 개념(노드)과 관계(엣지)를 추출한다.
3. 추출 결과를 반드시 아래 JSON 블록으로 응답 끝에 포함한다.
4. 부정형("안 써", "모름")은 노드를 만들지 않는다.
5. 일상 인사에는 빈 결과를 반환한다.

## 추출 JSON 형식
응답 텍스트 뒤에 반드시 이 블록을 붙인다:

\`\`\`synapse-extract
{
  "nodes": [{"name": "이름", "domain": "도메인"}],
  "edges": [{"source": "A", "target": "B", "type": "link", "label": "관계"}]
}
\`\`\`

- domain: 기술, 프로젝트, 장비, 회사, 학력, 역할, 위치, 용도, 프로필, 건강, 고객사, 직급, 업무, 조직, 자격, 병역, 음식, 경력, 스펙 중 하나
- type: link / same / similar 중 하나. link이면 label 필수.
- safety가 필요한 노드(알레르기, 건강): {"name": "...", "domain": "건강", "safety": true, "safety_rule": "설명"}

## 온보딩 단계
현재 단계: {step}

### step 0: 인사 + 첫 질문
"안녕하세요! 시냅스에 오신 걸 환영합니다 🧠
먼저, 주로 사용하시는 기술 스택이 뭔가요? (언어, 프레임워크, 도구 등)"

### step 1: 장비/환경
"어떤 장비로 개발하세요? (노트북, 데스크탑, 모니터 등)"

### step 2: 현재 프로젝트/회사
"지금 어떤 프로젝트나 업무를 하고 계세요?"

### step 3: 건강/주의사항
"혹시 건강이나 식이 관련해서 기억해두면 좋을 게 있나요? (없으면 '없음')"

### step 4: 자유 추가
"그 외에 기억해두면 좋을 것들이 있으면 자유롭게 알려주세요. 없으면 '끝'이라고 해주세요."

### step 5+: 완료 판단
현재 그래프 상태를 확인하고:
- 4개 이상 도메인, 15개 이상 노드, 3개 도메인에 각 2개+ 노드 → 완료
- 미달 → 부족한 도메인 안내 후 추가 질문

## 중요
- 추출 블록 없이 응답하지 마라. 추출할 게 없으면 빈 배열.
- 사용자가 "끝", "됐어", "그만" 하면 즉시 마무리.
- 각 응답은 간결하게. 장황한 설명 금지.`;
```

---

## 3. 시스템 프롬프트 분기

`useAIChat.ts`의 `sendMessage`에서:

```typescript
// 기존
const systemPrompt = synapseContext ? `...${synapseContext.prompt}` : '...';

// 변경
const systemPrompt = onboardingMode
  ? ONBOARDING_SYSTEM_PROMPT.replace('{step}', String(onboardingStep))
  : synapseContext?.prompt?.trim()
    ? `당신은 푸마시 그룹웨어의 AI 어시스턴트입니다. 아래 컨텍스트를 참고하여 답변하세요.\n\n${synapseContext.prompt}`
    : '당신은 푸마시 그룹웨어의 AI 어시스턴트입니다. 친절하고 정확하게 답변하세요.';
```

---

## 4. 응답 파싱 — synapse-extract 블록 추출

`MessageBubble.tsx`의 기존 추출 로직(백틱/볼드 파싱)은 정확도가 낮다.
온보딩 모드에서는 LLM이 구조화된 JSON을 직접 출력하므로 이걸 파싱한다.

```typescript
function extractSynapseBlock(content: string): BatchInput | null {
  const match = content.match(/```synapse-extract\s*\n([\s\S]*?)\n```/);
  if (!match) return null;
  try {
    const data = JSON.parse(match[1]);
    // 기본 검증
    if (!data.nodes && !data.edges) return null;
    return {
      nodes: data.nodes ?? [],
      edges: data.edges ?? [],
    };
  } catch {
    return null;
  }
}
```

**표시 처리:** `synapse-extract` 블록은 사용자에게 렌더링하지 않는다. 마크다운 렌더링 전에 제거.

```typescript
const displayContent = content.replace(/```synapse-extract[\s\S]*?```/, '').trim();
```

---

## 5. 자동 저장 플로우

온보딩 모드에서 LLM 응답이 도착할 때마다:

```typescript
// useAIChat.ts — 스트리밍 완료 후
if (onboardingMode) {
  const batch = extractSynapseBlock(assistantMessage);
  if (batch && (batch.nodes.length > 0 || batch.edges.length > 0)) {
    // SaveToSynapseModal을 자동으로 열어서 확인받기
    setPendingBatch(batch);
    setShowSaveModal(true);
  }
  setOnboardingStep(prev => prev + 1);
}
```

사용자가 모달에서 확인하면 `synapse.addBatch()` 호출 — 기존 로직 그대로.

---

## 6. 온보딩 완료 판정

`check_onboarding.py`의 기준을 TypeScript로 옮긴다:

```typescript
function checkOnboardingStatus(synapse: SynapseHook): {
  complete: boolean;
  totalNodes: number;
  domainCount: number;
  suggestions: string[];
} {
  // GraphStore에서 통계 조회
  const nodes = synapse.listNodes({ status: 'active' });
  const domainMap = new Map<string, number>();
  for (const n of nodes) {
    domainMap.set(n.domain, (domainMap.get(n.domain) ?? 0) + 1);
  }

  const domainCount = domainMap.size;
  const coveredDomains = [...domainMap.values()].filter(c => c >= 2).length;
  const totalNodes = nodes.length;

  const complete = domainCount >= 4 && totalNodes >= 15 && coveredDomains >= 3;

  const suggestions: string[] = [];
  if (totalNodes < 15) suggestions.push(`노드 ${15 - totalNodes}개 더 필요`);
  if (domainCount < 4) suggestions.push(`도메인 ${4 - domainCount}개 더 필요`);

  const common = ['기술', '장비', '건강', '프로젝트', '위치', '용도'];
  const missing = common.filter(d => !domainMap.has(d));
  if (missing.length && !complete) suggestions.push(`아직 없는 분야: ${missing.join(', ')}`);

  return { complete, totalNodes, domainCount, suggestions };
}
```

step 5 이후 매 응답마다 확인 → 완료 시 축하 메시지 + 온보딩 모드 해제.

---

## 7. 온보딩 트리거 (버튼)

`ChatArea.tsx`의 빈 상태에 버튼 추가:

```tsx
// 기존 퀵 프레이즈 위 또는 별도 영역
<button
  onClick={() => onStartOnboarding()}
  className="px-4 py-2 bg-purple-600 text-white rounded-lg"
>
  🧠 시냅스 온보딩
</button>
```

클릭 시:
1. `setOnboardingMode(true)`
2. step 0 시스템 프롬프트로 LLM 호출 (사용자 입력 = "시냅스 온보딩 시작")
3. LLM이 인사 + 첫 질문 출력

---

## 8. 온보딩 종료 조건

| 조건 | 동작 |
|------|------|
| 사용자가 "끝", "됐어", "그만" | 현재 상태 요약 → 모드 해제 |
| 완료 기준 달성 (15노드/4도메인) | 축하 메시지 → 모드 해제 |
| 세션 전환 (새 채팅, 다른 세션) | 모드 해제 |

---

## 9. 변경 파일 요약

| 파일 | 변경 |
|------|------|
| `useAIChat.ts` | onboardingMode 상태, 시스템 프롬프트 분기, 스트리밍 완료 후 추출 |
| `ChatArea.tsx` | 온보딩 버튼 추가 |
| `MessageBubble.tsx` | synapse-extract 블록 파싱 + 렌더링 제거 |
| 신규: `onboardingPrompt.ts` | ONBOARDING_SYSTEM_PROMPT 상수 |
| 신규: `checkOnboarding.ts` | 완료 판정 함수 (선택 — useSynapse에 포함 가능) |

기존 `SaveToSynapseModal`, `useSynapse`, `groqService`는 변경 없음.

---

## 10. 핵심 포인트

1. **시스템 프롬프트가 전부다.** LLM이 뭘 해야 하는지 시스템 프롬프트에 명확히 써야 한다.
2. **구조화된 출력 (`synapse-extract`).** 볼드/백틱 추출은 불안정하다. LLM에게 JSON 블록을 강제한다.
3. **단계 관리는 프롬프트에서.** step 번호만 넘기면 LLM이 알아서 다음 질문을 한다. 복잡한 상태 머신 불필요.
4. **기존 저장 플로우 재사용.** SaveToSynapseModal + synapse.addBatch()는 이미 있다.

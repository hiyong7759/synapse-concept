"""Generate fine-tuning datasets for Synapse 6 tasks using Claude CLI.

Tasks:
  1  상태 변경 감지       — 500건
  2  대명사/부사 구체화   — 500건
  3  인출 필터            — 800건
  4  인출 확장            — 400건
  5a 트리플 민감도 마킹  — 500건
  5b 컨텍스트 민감도 판단 — 400건

Usage:
    python3 generate_task_data.py [--task 1|2|3|4|5a|5b|all] [--dry-run] [--batch-size 25]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CLAUDE_CMD = "claude"
CLAUDE_MODEL = "opus"

# Fixed system prompts (used verbatim in training data)
SYSTEM_PROMPTS = {
    1: '당신은 지식 그래프 관리 엔진입니다. 사용자 입력과 기존 트리플을 보고, 상태가 변경된 엣지를 찾아 JSON으로 반환하세요. 변경이 없으면 빈 배열을 반환하세요. 출력 형식: {"inactive": [{"source": "...", "target": "..."}]}',
    2: '당신은 지식 그래프 저장 엔진입니다. 텍스트에서 대명사와 부사를 구체적인 값으로 치환하세요. 대화 맥락이 제공되면 활용하세요. 치환 불가능하면 {"question": "질문 내용"}을 반환하세요. 출력 형식: {"text": "치환된 텍스트"} 또는 {"question": "..."}',
    3: '당신은 지식 그래프 인출 필터입니다. 질문과 트리플을 보고, 이 트리플이 질문과 관련 있는지 판단하세요. 불확실하면 pass로 판단하세요 (제외보다 포함이 안전). 출력: pass 또는 reject (한 단어만)',
    4: '당신은 지식 그래프 검색 엔진입니다. 질문을 보고 그래프에서 검색해야 할 관련 노드 후보를 생성하세요. 형태소 단위로 쪼개진 노드 이름으로 나열하세요. 출력 형식: ["노드1", "노드2", ...]',
    "5a": '당신은 지식 그래프 보안 엔진입니다. 트리플 하나를 보고 민감정보 여부를 판단하세요. 출력 형식: safe 또는 sensitive:<카테고리> (카테고리: health_detail | financial | location_precise | relationship_private | schedule_combined)',
    "5b": '당신은 지식 그래프 보안 엔진입니다. 질문과 인출된 전체 트리플 컨텍스트(각 트리플의 5A 마킹 포함)를 보고, 답변에 민감정보가 포함되는지 종합 판단하세요. 출력 형식: {"result": "safe"} 또는 {"result": "confirm", "message": "사용자에게 보여줄 확인 메시지"}',
}

TARGET_COUNTS = {1: 500, 2: 500, 3: 800, 4: 400, "5a": 500, "5b": 400}
OUTPUT_FILES = {
    1: "task1_state_change.jsonl",
    2: "task2_pronoun_adverb.jsonl",
    3: "task3_retrieval_filter.jsonl",
    4: "task4_retrieval_expand.jsonl",
    "5a": "task5a_sensitivity_triple.jsonl",
    "5b": "task5b_sensitivity_context.jsonl",
}

# --- Generation prompts ---

TASK1_PROMPT = """\
Synapse 지식 그래프의 "상태 변경 감지" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
Synapse는 한국어 형태소 단위로 그래프를 구성합니다.
- 노드: 형태소 단위 개념 (허리, 아프, 낫, 삼성, 재직, 이사, 하, 었, 커피, 끊, 헬스)
- 트리플: source → target (엣지 라벨 있을 수도 없을 수도)
- 상태 변경: 사용자가 "허리 나았어"라고 하면 기존 트리플 "허리 → 아프"를 inactive 처리

## 출력 형식 (JSON 배열, 다른 텍스트 없이)
[
  {{"user": "입력: <문장>\\n기존 트리플:\\n- <노드A> → <노드B>\\n- <노드C> → <노드D>", "assistant": "{{\\"inactive\\": [{{\\"source\\": \\"노드A\\", \\"target\\": \\"노드B\\"}}]}}"}},
  ...
]

## 생성 규칙

### 상태 변경 케이스 (70%): inactive 배열에 항목 있음
도메인과 표현을 최대한 다양하게:
- 건강 회복: "허리 이제 안 아파", "감기 다 나았어", "다이어트 성공해서 목표 달성했어", "물리치료 끝났어", "약 다 먹었어"
- 건강 악화/재발: "허리 또 아프기 시작했어", "감기 다시 걸렸어"
- 직장 변화: "회사 그만뒀어", "이직했어", "팀 바꿨어", "프리랜서 됐어", "창업했어", "휴직 들어갔어"
- 이사/거주지: "진천으로 이사 완료", "서울 왔어", "고향 내려갔어"
- 관계 변화: "걔랑 연락 끊었어", "그 친구랑 화해했어", "헤어졌어", "결혼했어"
- 취향/습관 변화: "커피 끊었어", "헬스 그만뒀어", "담배 끊었어", "채식 시작했어", "술 끊었어"
- 학습/프로젝트: "그 프로젝트 끝났어", "자격증 땄어", "학원 그만뒀어"
- 기기/도구: "맥미니 팔았어", "모니터 바꿨어"

### 변경 없는 케이스 (30%): inactive 배열 비어있음
- 새 정보 추가 (기존 상태 건드리지 않음): "스타벅스 요즘 또 자주 가" + 기존 트리플에 스타벅스 관련 있어도 변경 없음
- 상태 변경 표현 없는 단순 사실: "오늘 병원 예약했어", "내일 회의 있어"
- 감정/의견 표현: "요즘 힘들어", "그거 별로더라"
- 미래 계획: "이사 알아보고 있어", "이직 생각 중이야"

### 트리플 품질
- 2~4개 트리플. 노드는 실제 형태소 단위 (조사/종결어미 제외)
- 다양한 도메인 혼합 (건강 + 직장 + 취향 섞이는 경우도)
- inactive 엣지: 1~2개만. 변경된 것만 정확히 지정.
- 라벨 있는 트리플도 포함: "진천 —[으로]→ 이사", "삼성 —[에서]→ 재직"
  → 라벨 있는 트리플은 user에 "- <노드A> —[<라벨>]→ <노드B>" 형식

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK2_PROMPT = """\
Synapse 지식 그래프의 "대명사/부사 구체화" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
저장 파이프라인에서 모델이 대명사와 부사를 구체값으로 치환합니다.
- 대명사: 지시대명사("이거", "그거", "저분"), 인칭대명사("걔", "그쪽", "그분")
- 부사: 시간("오늘", "내일", "어제", "요즘", "최근에"), 장소("여기", "거기", "저기")
- "나/저"는 노드 생성 안 함 → 치환 대상 아님, text에 그대로 포함
- 맥락 있으면 추론, 없으면 사용자에게 질문 반환

## 출력 형식 (JSON 배열, 다른 텍스트 없이)
[
  {{"user": "입력: <텍스트>\\n<맥락 줄>", "assistant": "{{\\"text\\": \\"치환된 텍스트\\"}}"}},
  {{"user": "입력: <텍스트>\\n<맥락 줄>", "assistant": "{{\\"question\\": \\"질문\\\"}}"}},
  ...
]

## 생성 규칙

### 치환 성공 (70%): {{"text": "..."}} 반환
다양한 치환 유형:
- 날짜 부사 (맥락: "날짜: 2026-04-04"):
  * "오늘" → "2026-04-04", "어제" → "2026-04-03", "내일" → "2026-04-05"
  * "그저께" → "2026-04-02", "모레" → "2026-04-06"
  * "이번 주 월요일" → "2026-03-30", "지난주 금요일" → "2026-03-27"
- 지시대명사 (맥락: "직전 대화 - 사용자: <이전 발화>"):
  * "이거" → 직전 발화의 대상
  * "그거", "저거", "그것", "이것"
- 인칭대명사:
  * "걔" → 이름/관계로 치환 ("김민수", "팀장님", "동생")
  * "그분", "그쪽", "저분", "그 사람"
- 장소 대명사:
  * "여기서" / "거기서" → 맥락에서 특정 가능한 경우
- 복합: "오늘 거기서 그분 만났어" → 모두 한번에 치환

치환된 text는 자연스러운 한국어 문장이어야 함.

### 치환 불가 (30%): {{"question": "..."}} 반환
- 맥락 없이 "거기서", "저기서", "그때", "저분", "그분" 등
- 맥락 있어도 특정 불가한 경우: "그게 뭐야?" (직전 발화에 여러 대상)
- 질문은 자연스럽고 간결한 한국어: "어디서 드셨나요?", "누구를 말씀하시는 건가요?", "어떤 것이요?"

### 맥락 줄 형식
- "날짜: 2026-04-04"
- "직전 대화 - 사용자: <이전 발화>"
- "맥락: 이전 발화 없음"
- "직전 대화 - 사용자: <A>. 사용자: <B>" (여러 발화 있을 때)

### 주제 다양성
병원, 카페, 회사, 회의, 쇼핑, 음식, 약속, 운동, 여행, 취미, 가족, 친구

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK3_PROMPT = """\
Synapse 지식 그래프의 "인출 필터" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
BFS 탐색 중 각 트리플이 원래 질문과 관련 있는지 판단합니다.
- 판단 원칙: 불확실하면 반드시 pass (제외보다 포함이 안전)
- 시제 어미(었/겠/더)는 시간축 허브 → 시간/과거 관련 질문이면 항상 pass
- 트리플: 형태소 단위 노드 쌍 (허리, 아프, 낫, 었, 이사, 하, 먹, 좋, 안, 삼성, 재직)

## 출력 형식 (JSON 배열, 다른 텍스트 없이)
[
  {{"user": "질문: <질문>\\n트리플: <노드A> → <노드B>", "assistant": "pass"}},
  {{"user": "질문: <질문>\\n트리플: <노드A> —[<라벨>]→ <노드B>", "assistant": "reject"}},
  ...
]

## 생성 규칙

### 비율: pass {pass_count}개 / reject {reject_count}개 (정확히 맞춰주세요)

### pass 케이스 (다양한 유형):
1. 직접 관련: 질문과 트리플 노드가 같은 도메인
   - "허리 언제 아팠어?" + "허리 → 아프" → pass
   - "좋아하는 음식 뭐야?" + "치킨 → 좋" → pass
2. 시제 어미 허브: 시간/과거 질문 + 시제 어미 트리플
   - "최근에 뭐 했어?" + "낫 → 었" → pass
   - "언제 이사했어?" + "이사 —[하]→ 었" → pass
   - "작년에 어디 다녔어?" + "다니 → 었" → pass
3. 간접 관련: 연관 개념 (건강 질문 + 병원/약/치료 트리플)
   - "요즘 몸 어때?" + "병원 → 다니" → pass
4. 불확실 경계: 애매하게 관련될 수 있으면 pass
   - "먹는 거 좋아해?" + "먹 → 었" → pass

### reject 케이스 (다양한 유형):
1. 완전 다른 도메인:
   - 건강 질문 + 직장 트리플: "허리 괜찮아?" + "삼성 → 재직" → reject
   - 음식 질문 + 장비 트리플: "뭐 먹어?" + "맥미니 → 개발" → reject
2. 완전 무관:
   - "어디 살아?" + "Python —[로]→ 개발" → reject
   - "좋아하는 음악 뭐야?" + "연봉 → 높" → reject
3. 특정 주제 + 전혀 다른 주제 트리플

### 트리플 형식 다양성
- 라벨 없음 (70%): "노드A → 노드B"
- 라벨 있음 (30%): "노드A —[으로]→ 노드B", "노드A —[에서]→ 노드B", "노드A —[하]→ 노드B"

### 질문 유형 (골고루 분산)
건강 상태, 좋아하는 것/취향, 직장/커리어, 거주지/이사, 과거 사건/시간, 사람/관계, 학습/기술, 장비/도구

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK4_PROMPT = """\
Synapse 지식 그래프의 "인출 확장" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
사용자 질문을 받아 그래프에서 검색할 노드 후보를 생성합니다.
- 노드는 한국어 형태소 단위: 허리, 아프, 낫, 병원, 이사, 살, 먹, 좋, 삼성, 개발, 했, 었
- 동의어·관련어·연상어 포함 (허리 아팠을 때 → 디스크, 척추, 물리치료, 진통제도 포함)
- 후보 4~8개 (적절한 깊이)

## 출력 형식 (JSON 배열, 다른 텍스트 없이)
[
  {{"user": "질문: <한국어 질문>", "assistant": "[\\"노드1\\", \\"노드2\\", \\"노드3\\", ...]"}},
  ...
]

## 생성 규칙

### 질문 유형 (각 유형 비슷한 비율로):
1. 건강/신체: "언제 아팠지?", "허리 언제 나았어?", "병원 어디 다녔어?", "약 뭐 먹었지?", "어디 다쳤어?"
2. 직장/커리어: "지금 어디 다녀?", "전 직장 어디였어?", "직급이 뭐야?", "연봉 얼마야?", "팀이 어디야?"
3. 거주지/이동: "지금 어디 살아?", "이사 언제 했어?", "어디로 이사 갔어?", "고향이 어디야?"
4. 음식/취향: "좋아하는 음식 뭐야?", "자주 가는 카페 어디야?", "안 먹는 거 있어?", "요즘 즐기는 거 뭐야?"
5. 시간/과거: "최근에 뭐 했어?", "작년에 뭐 했지?", "언제 그랬어?", "얼마나 됐어?"
6. 기기/도구: "어떤 컴퓨터 써?", "개발 환경이 어때?", "뭐로 작업해?"
7. 학습/기술: "뭐 배우고 있어?", "어떤 언어 써?", "자격증 있어?", "전공이 뭐야?"
8. 복합/모호: "요즘 어때?", "뭐가 힘들어?", "근황이 뭐야?", "어떻게 지내?"

### 노드 후보 품질
- 형태소 단위: 조사(을/를/이/가), 종결어미(요/어/아) 제외
- 동의어/변형 포함: "아프" → ["아프", "통증", "낫", "회복", "병원", "약", "치료"]
- 관련 허브 포함: 시간 관련 질문이면 반드시 시제 어미("었", "겠") 포함
- 너무 일반적인 노드 피하기: "하", "되", "있" 단독으로 쓰지 않기 (다른 노드와 체인으로만 의미 있음)

### 다양성
- 같은 도메인 질문도 표현 다양하게 (구어체/문어체/반말/존댓말 혼합)
- 노드 후보도 매 예시마다 다르게

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK5A_PROMPT = """\
Synapse 지식 그래프의 "트리플 단위 민감도 마킹" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
BFS 인출 후 각 트리플에 민감정보 여부를 태깅합니다. 트리플 하나만 보고 판단합니다.
노드는 형태소 단위: 허리, L4-L5, 세레콕시브, 삼성, 재직, 연봉, 주소, 진천, 수술, 처방

## 민감도 카테고리
- safe              — 개인정보 아님 (일반 건강 언급, 회사명, 기술명, 음식 취향 등)
- sensitive:health_detail    — 구체적 병명/처방약/진단/수술 내역
- sensitive:financial        — 연봉/계좌/자산/대출 등 재정 정보
- sensitive:location_precise — 구체적 주소/집 위치 (시/구 이하 세부 주소)
- sensitive:relationship_private — 연애/이혼/사망/가족 사생활 관련
- sensitive:schedule_combined    — 특정 날짜+장소+행동 조합 (일정 노출)

## 경계 판단 기준
- `허리 → 아프` → safe (일반 증상)
- `허리 → L4-L5` → sensitive:health_detail (구체 진단명)
- `약 → 세레콕시브` → sensitive:health_detail (처방약명)
- `삼성 → 재직` → safe (직장 일반)
- `연봉 → 8000` → sensitive:financial
- `주소 → 진천시 XX동` → sensitive:location_precise
- `엄마 → 입원` → sensitive:relationship_private
- `2026-04-04 → 병원` → safe 단독으로는 (날짜+병원만으로는 조합 필요)
- `수술 → 예정` + `날짜 → 2026-04-10` 두 트리플이 있으면 각각 별개로 판단

## 출력 형식 (JSON 배열, 다른 텍스트 없이)
[
  {{"user": "트리플: <노드A> → <노드B>", "assistant": "safe"}},
  {{"user": "트리플: <노드A> —[<라벨>]→ <노드B>", "assistant": "sensitive:health_detail"}},
  ...
]

## 생성 규칙
- safe 60% / sensitive 40% (카테고리 골고루)
- 트리플은 형태소 단위. 라벨 있는 것 30% (—[으로]→, —[에서]→, —[하]→ 등)
- 경계 케이스 풍부하게: 언뜻 보면 sensitive 같지만 safe인 것, 반대 경우
- 도메인: 건강, 직장, 거주지, 재정, 관계, 일정, 기술, 취향 골고루
- 각 카테고리 최소 10% 이상 포함

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK5B_PROMPT = """\
Synapse 지식 그래프의 "컨텍스트 전체 민감도 판단" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
BFS 인출 후 전체 트리플 컨텍스트를 보고 답변에 민감정보 포함 여부를 종합 판단합니다.
각 트리플에는 5A 마킹 결과가 이미 붙어있습니다.
단일 트리플이 safe여도 조합하면 sensitive가 될 수 있습니다.

## 종합 판단 원칙
- 5A에서 하나라도 sensitive → 거의 항상 confirm
- 5A 전부 safe여도 조합 효과로 confirm 가능:
  * 날짜 + 장소 + 행동 조합 → 특정 일정 노출
  * 이름추정 가능 정보 + 민감 행동 조합
  * 건강 safe 여러 개 → 특정 질환 패턴 추론 가능
- 5A 전부 safe이고 조합 효과 없으면 → safe

## confirm 메시지 가이드
- 구체적이고 친절하게: 어떤 정보가 왜 민감한지 명시
- 예: "처방약(세레콕시브)과 진단(L4-L5 디스크) 정보가 포함됩니다. 답변에 포함할까요?"
- 예: "2026-04-04 병원 방문 일정이 노출될 수 있습니다. 계속할까요?"

## 출력 형식 (JSON 배열, 다른 텍스트 없이)
[
  {{
    "user": "질문: <질문>\\n컨텍스트:\\n- [safe] <노드A> → <노드B>\\n- [sensitive:health_detail] <노드C> → <노드D>\\n...",
    "assistant": "{{\\"result\\": \\"confirm\\", \\"message\\": \\"...\\"}}"}},
  {{
    "user": "질문: <질문>\\n컨텍스트:\\n- [safe] <노드A> → <노드B>\\n- [safe] <노드C> → <노드D>\\n...",
    "assistant": "{{\\"result\\": \\"safe\\"}}"}},
  ...
]

## 생성 규칙
- safe:confirm 비율 50:50
- 컨텍스트 트리플: 3~6개. 실제 BFS 결과처럼 다양한 도메인 섞임
- confirm 케이스 유형:
  * 5A에 sensitive 있는 케이스 (가장 많음)
  * 5A 전부 safe이지만 조합 → confirm (약 20% 정도)
- safe 케이스 유형:
  * 5A 전부 safe + 조합 효과 없음
  * 일반 직장/기술/취향 정보만 포함
- 질문 유형: 건강, 직장, 이사, 과거 사건, 취향 골고루
- confirm 메시지는 매번 다르게. 포함된 민감 정보 구체적으로 언급.

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

GENERATION_PROMPTS = {
    1: TASK1_PROMPT,
    2: TASK2_PROMPT,
    3: TASK3_PROMPT,
    4: TASK4_PROMPT,
    "5a": TASK5A_PROMPT,
    "5b": TASK5B_PROMPT,
}


def call_claude(prompt: str) -> str:
    """Call claude CLI with -p flag."""
    result = subprocess.run(
        [CLAUDE_CMD, "-p", "--model", CLAUDE_MODEL, prompt],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:300]}", file=sys.stderr)
        return ""
    return result.stdout.strip()


def strip_code_fence(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def parse_examples(raw: str) -> list[dict]:
    """Parse JSON array of {user, assistant} from Claude output."""
    raw = strip_code_fence(raw)
    if not raw:
        return []

    # Find first '[' to skip any leading text
    start = raw.find("[")
    if start == -1:
        print(f"  No JSON array found in response", file=sys.stderr)
        return []
    raw = raw[start:]

    # Strategy 1: raw_decode — handles "Extra data" (text after valid JSON)
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(raw)
        if isinstance(data, list):
            return [item for item in data if "user" in item and "assistant" in item]
    except json.JSONDecodeError:
        pass

    # Strategy 2: truncated array — find last complete item and close the array
    last_close = raw.rfind("},")
    if last_close == -1:
        last_close = raw.rfind("}")
    if last_close != -1:
        candidate = raw[:last_close + 1] + "]"
        try:
            data = json.loads(candidate)
            if isinstance(data, list):
                items = [item for item in data if "user" in item and "assistant" in item]
                if items:
                    print(f"  (recovered {len(items)} items from truncated response)", file=sys.stderr)
                    return items
        except json.JSONDecodeError:
            pass

    print(f"  JSON parse failed. Raw (first 400): {raw[:400]}", file=sys.stderr)
    return []


def make_training_entry(task_id, user: str, assistant: str) -> dict:
    """Format a single training example."""
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS[task_id]},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


# Domain rotation seeds — appended per batch to force diversity
DIVERSITY_SEEDS = {
    1: ["건강/신체", "직장/이직", "이사/거주지", "취향/습관", "관계/인간관계", "학습/프로젝트", "기기/장비"],
    2: ["날짜 부사 치환", "지시대명사 치환", "인칭대명사 치환", "장소 대명사 치환", "치환 불가 케이스"],
    3: ["건강 도메인 질문", "직장 도메인 질문", "거주지 도메인 질문", "음식/취향 도메인", "시간/과거 도메인", "시제 어미 허브 케이스"],
    4: ["건강/신체 질문", "직장/커리어 질문", "거주지/이동 질문", "음식/취향 질문", "기기/도구 질문", "학습/기술 질문", "복합/모호 질문"],
    "5a": ["건강 트리플", "재정 트리플", "위치 트리플", "관계 트리플", "일정 조합 트리플", "safe 경계 케이스"],
    "5b": ["건강 민감 컨텍스트", "재정 민감 컨텍스트", "위치 민감 컨텍스트", "safe 컨텍스트", "조합 효과 confirm 케이스"],
}


def generate_task(task_id, target: int, batch_size: int = 25, dry_run: bool = False, append: bool = False):
    """Generate data for a single task."""
    print(f"\n=== Task {task_id}: {OUTPUT_FILES[task_id]} (target: {target}) ===")

    out_path = DATA_DIR / OUTPUT_FILES[task_id]

    # Count existing examples when appending
    existing_count = 0
    existing_keys = set()
    if append and out_path.exists():
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    e = json.loads(line)
                    existing_keys.add(e["messages"][1]["content"])
                    existing_count += 1
        print(f"  Existing: {existing_count} unique, need {max(0, target - existing_count)} more")
        remaining = max(0, target - existing_count)
    else:
        remaining = target

    if dry_run:
        batches = (remaining + batch_size - 1) // batch_size if remaining > 0 else 0
        print(f"  [DRY RUN] ~{batches} claude calls ({CLAUDE_MODEL}), ~{remaining} new examples")
        return

    if remaining == 0:
        print(f"  Already at target ({existing_count}/{target}), skipping.")
        return existing_count

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    seeds = DIVERSITY_SEEDS.get(task_id, ["다양한 주제"])
    new_examples = []
    batch_num = 0
    seed_idx = 0

    while remaining > 0:
        batch_num += 1
        count = min(batch_size, remaining)
        prompt_template = GENERATION_PROMPTS[task_id]

        # Diversity seed rotation
        seed = seeds[seed_idx % len(seeds)]
        seed_idx += 1
        diversity_hint = f"\n\n이번 배치 집중 주제: **{seed}** — 이 주제 중심으로 다양하고 새로운 예시를 생성하세요."

        if task_id == 3:
            pass_count = round(count * 0.6)
            reject_count = count - pass_count
            prompt = prompt_template.format(count=count, pass_count=pass_count, reject_count=reject_count) + diversity_hint
        else:
            prompt = prompt_template.format(count=count) + diversity_hint

        print(f"  [{batch_num}] Requesting {count} ({seed})... ", end="", flush=True)
        raw = call_claude(prompt)
        if not raw:
            print("SKIP (empty response)")
            remaining -= count
            continue

        examples = parse_examples(raw)

        # Dedup against existing + already generated this run
        new_unique = []
        for ex in examples:
            key = ex["user"]
            if key not in existing_keys:
                existing_keys.add(key)
                new_unique.append(ex)

        got = len(new_unique)
        skipped = len(examples) - got
        print(f"→ {got} new (skipped {skipped} dupes)", end="")

        if got == 0:
            print(" (WARN: all dupes)")
            remaining -= count
            continue

        for ex in new_unique:
            entry = make_training_entry(task_id, ex["user"], ex["assistant"])
            new_examples.append(entry)

        remaining -= got
        if remaining < 0:
            remaining = 0
        print(f"  [new so far: {len(new_examples)}]")

    # Write (append or overwrite)
    mode = "a" if append and out_path.exists() else "w"
    with open(out_path, mode, encoding="utf-8") as f:
        for entry in new_examples:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    total = existing_count + len(new_examples)
    print(f"  ✓ +{len(new_examples)} new examples (total: {total}) → {out_path}")
    return total


def parse_task_ids(task_str: str) -> list:
    """Parse task ids from string. Supports '1', '1,3', '5a', '5b', 'all'."""
    if task_str == "all":
        return [1, 2, 3, 4, "5a", "5b"]
    result = []
    for t in task_str.split(","):
        t = t.strip()
        if t in ("5a", "5b"):
            result.append(t)
        else:
            result.append(int(t))
    return result


def main():
    parser = argparse.ArgumentParser(description="Generate Synapse fine-tuning datasets")
    parser.add_argument("--task", default="all", help="Task: 1|2|3|4|5a|5b|all or comma-separated")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--append", action="store_true", help="Append unique examples to reach target")
    args = parser.parse_args()

    tasks = parse_task_ids(args.task)

    print(f"Model: {CLAUDE_MODEL}")
    print(f"Tasks: {tasks}, batch_size={args.batch_size}, dry_run={args.dry_run}")
    print(f"Targets: { {t: TARGET_COUNTS[t] for t in tasks} }")

    totals = {}
    for task_id in tasks:
        target = TARGET_COUNTS[task_id]
        result = generate_task(task_id, target, args.batch_size, args.dry_run, args.append)
        if result is not None:
            totals[task_id] = result

    if not args.dry_run and totals:
        print("\n=== Summary ===")
        for task_id, count in totals.items():
            target = TARGET_COUNTS[task_id]
            status = "OK" if count >= target * 0.9 else "LOW"
            print(f"  Task {task_id}: {count}/{target} [{status}]")
        print(f"  Total: {sum(totals.values())} examples")


if __name__ == "__main__":
    main()

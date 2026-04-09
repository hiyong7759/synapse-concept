"""Generate fine-tuning datasets for Synapse org mode tasks using Claude CLI.

Tasks:
  0   Augment 필요 여부 판단  — 300건
  1   상태 변경 감지 (주어)   — 400건
  2   주어 해소               — 400건
  3   인출 필터 (조직)        — 600건
  4   인출 확장 (조직)        — 300건
  5a  트리플 민감도 마킹      — 500건
  5b  컨텍스트 민감도 판단    — 300건

Usage:
    python3 generate_org_data.py [--task 0|1|2|3|4|5a|5b|all] [--dry-run] [--batch-size 25]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "org"
CLAUDE_CMD = "claude"
CLAUDE_MODEL = "opus"

SYSTEM_PROMPTS = {
    0:   '당신은 지식 그래프 라우팅 엔진입니다. 사용자 질문을 보고 조직 컨텍스트 augment가 필요한지 판단하세요. 출력: personal_only 또는 augment_org (한 단어만)',
    1:   '당신은 지식 그래프 관리 엔진입니다. 조직 모드에서 사용자 입력과 기존 트리플을 보고, 상태가 변경된 엣지를 찾아 JSON으로 반환하세요. 변경이 없으면 빈 배열을 반환하세요. 출력 형식: {"inactive": [{"source": "...", "target": "..."}]}',
    2:   '당신은 지식 그래프 저장 엔진입니다. 조직 모드에서 발화의 주어를 특정하세요. 주어가 불명확하면 {"question": "..."}, 추론 가능하면 {"subject": "...", "text": "..."}, 주어가 불필요한 발화면 {"text": "..."}를 반환하세요.',
    3:   '당신은 지식 그래프 인출 필터입니다. 질문과 트리플을 보고, 이 트리플이 질문과 관련 있는지 판단하세요. 불확실하면 pass로 판단하세요 (제외보다 포함이 안전). 출력: pass 또는 reject (한 단어만)',
    4:   '당신은 지식 그래프 검색 엔진입니다. 조직 관련 질문을 보고 그래프에서 검색해야 할 관련 노드 후보를 생성하세요. 형태소 단위로 쪼개진 노드 이름으로 나열하세요. 출력 형식: ["노드1", "노드2", ...]',
    "5a": '당신은 지식 그래프 보안 엔진입니다. 조직 그래프 트리플 하나를 보고 민감정보 여부와 최소 열람 권한을 판단하세요. 출력 형식: safe 또는 sensitive:<카테고리>:<최소권한> (카테고리: personal_info|performance|trade_secret|internal_decision|client_confidential|legal_risk, 최소권한: team_lead|hr|executive)',
    "5b": '당신은 지식 그래프 보안 엔진입니다. 질의자 권한과 인출된 전체 트리플 컨텍스트(5A 마킹 포함)를 보고, 정보 제공 가능 여부를 판단하세요. 출력 형식: {"result": "safe"} 또는 {"result": "confirm", "message": "..."} 또는 {"result": "reject", "message": "..."}',
}

TARGET_COUNTS = {0: 300, 1: 400, 2: 400, 3: 600, 4: 300, "5a": 500, "5b": 300}
OUTPUT_FILES = {
    0:   "task0_augment_routing.jsonl",
    1:   "task1_state_change.jsonl",
    2:   "task2_subject_resolution.jsonl",
    3:   "task3_retrieval_filter.jsonl",
    4:   "task4_retrieval_expand.jsonl",
    "5a": "task5a_sensitivity_triple.jsonl",
    "5b": "task5b_sensitivity_context.jsonl",
}

# ---------------------------------------------------------------------------
# Generation prompts
# ---------------------------------------------------------------------------

TASK0_PROMPT = """\
Synapse 조직 모드의 "Augment 필요 여부 판단" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
개인 앱이 조직 서버에 연결되어 있을 때, 사용자 질문에 조직 컨텍스트를 추가 탐색해야 하는지 판단합니다.
개인 그래프는 항상 탐색. 조직 그래프는 관련 있을 때만 augment.

## 출력 형식 (JSON 배열)
[
  {{"user": "질문: <질문>", "assistant": "personal_only"}},
  {{"user": "질문: <질문>", "assistant": "augment_org"}},
  ...
]

## 판단 기준
- personal_only (50%):
  * 순수 개인 신체/건강: "허리 언제 나았지?", "요즘 잠을 못 자"
  * 개인 취향/감정: "좋아하는 음식 뭐야?", "오늘 기분이 안 좋아"
  * 개인 관계: "부모님 건강은 어때?", "친구 만날 때 뭐 먹지?"
  * 개인 소비: "어제 카페 어디 갔지?", "지난주 뭐 샀어?"

- augment_org (50%):
  * 일정/해야 할 일: "오늘 뭐 해야 해?", "이번 주 어때?", "내일 일정이 뭐야?"
  * 직장 관련: "요즘 힘들어", "이번 프로젝트 어떻게 됐어?", "팀 분위기 어때?"
  * 복합 상태: "근황이 뭐야?", "요즘 어때?", "뭐가 바빠?"
  * 업무 맥락 필요: "우리 팀 회의 언제야?", "마감이 언제지?", "담당자 누구야?"

## 다양성
- 구어체/문어체/반말/존댓말 혼합
- 동일 의도라도 다양한 표현으로

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK1_ORG_PROMPT = """\
Synapse 조직 그래프의 "상태 변경 감지 (주어 추적)" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
개인 모드와 구조 동일하지만 **주어가 명시**됩니다. 조직에서는 누가 변경되었는지가 핵심.
노드는 형태소 단위: 김민수, 개발팀, 마케팅팀, 대리, 과장, A프로젝트, 삼성전자

## 출력 형식 (JSON 배열)
[
  {{"user": "입력: <발화>\\n기존 트리플:\\n- <노드A> —[<라벨>]→ <노드B>\\n...", "assistant": "{{\\"inactive\\": [{{\\"source\\": \\"...\\", \\"target\\": \\"...\\"}}]}}"}},
  ...
]

## 조직 상태 변경 유형 (70% — inactive 있음)
- 인사이동: "김대리 개발팀으로 이동했어", "박과장 영업부로 전보됐대"
- 직급 변경: "이대리 과장으로 승진했어", "최부장 이사됐대"
- 퇴사/입사: "김팀장 퇴사했어", "신입 왔어 — 이민준씨"
- 프로젝트 변동: "A프로젝트 완료됐어", "B프로젝트 중단됐어", "C프로젝트 일정 변경됐어"
- 고객사 변동: "삼성전자 계약 종료됐어", "LG전자 신규 계약 체결됐어"
- 담당자 교체: "A계정 담당이 김대리에서 박대리로 바뀌었어"
- 조직 개편: "마케팅팀이 브랜드팀으로 이름 바꿨어", "개발1팀 해체됐어"

## 변경 없는 케이스 (30% — inactive 빈 배열)
- 현재 상태와 무관한 새 정보: "김대리 요즘 Python 공부해" (소속 트리플 변경 없음)
- 상태 변경 표현 없음: "내일 팀 회의 있어", "A프로젝트 예산 증가했어"

## 트리플 품질
- 2~4개, 라벨 있는 것 40% (—[소속]→, —[담당]→, —[직급]→, —[계약]→ 등)
- inactive 엣지: 1~2개만. 관련된 것만 정확히.
- 실제 기업에 있을 법한 자연스러운 조직명/이름 사용

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK2_ORG_PROMPT = """\
Synapse 조직 그래프의 "주어 해소 (Subject Resolution)" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
조직 모드에서는 발화의 주어(누가/무엇이)를 특정하는 것이 핵심입니다.
개인 모드의 대명사 치환과 다릅니다 — 조직에서는 주어 없으면 저장 불가.

## 출력 3가지
1. `{{"question": "..."}}` — 주어 불명확, 사용자에게 질문
2. `{{"subject": "...", "text": "..."}}` — 맥락으로 주어 추론 성공
3. `{{"text": "..."}}` — 주어가 발화 내 명확하거나 불필요한 경우

## 출력 형식 (JSON 배열)
[
  {{"user": "입력: <발화>\\n맥락: <맥락>", "assistant": "{{\\"question\\": \\"누가 팀 이동했나요?\\"}}"}},
  {{"user": "입력: <발화>\\n맥락: <맥락>", "assistant": "{{\\"subject\\": \\"김팀장\\", \\"text\\": \\"김팀장 승진했대\\"}}"}},
  {{"user": "입력: <발화>\\n맥락: <맥락>", "assistant": "{{\\"text\\": \\"A프로젝트 완료됐어\\"}}"}},
  ...
]

## 생성 규칙

### question (40%) — 주어 불명확
- "팀 이동했대" + 맥락 없음 → "누가 팀 이동했나요?"
- "퇴사했대" + 맥락 없음 → "누가 퇴사했나요?"
- "걔 승진 됐어?" + 맥락 없음 → "누구를 말씀하시는 건가요?"
- 질문은 자연스럽고 짧게

### subject 추론 (40%) — 맥락으로 특정
- "걔 승진했대" + "직전: 김팀장 얘기 들었어?" → subject: "김팀장"
- "그 사람 퇴사했어" + "직전: 개발팀 박차장" → subject: "박차장"
- "이번에 이동했대" + "직전: 이대리 인사발령 났다고" → subject: "이대리"

### text (20%) — 주어 이미 명확
- "A프로젝트 완료됐어" + 맥락 없음 → text 그대로 (A프로젝트가 주어)
- "삼성전자 계약 해지됐어" → text 그대로
- "내일 전사 회의 있어" → text 그대로 (주어 불필요)

## 맥락 줄 형식
- "맥락: 이전 발화 없음"
- "직전 대화 - 사용자: <발화>"
- "직전 대화 - 사용자: <A>. 사용자: <B>"

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK3_ORG_PROMPT = """\
Synapse 조직 그래프의 "인출 필터 (조직 도메인)" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
BFS 탐색 중 트리플이 질문과 관련 있는지 판단합니다. 조직 도메인 특화.
**doc_mode 트리플 포함이 핵심** — 취업규칙, 법령, 사규의 조항 트리플도 판단 대상.

## 출력 형식 (JSON 배열)
[
  {{"user": "질문: <질문>\\n트리플: <노드A> → <노드B>", "assistant": "pass"}},
  {{"user": "질문: <질문>\\n트리플: <노드A> —[<라벨>]→ <노드B>", "assistant": "reject"}},
  ...
]

## 비율: pass {pass_count}개 / reject {reject_count}개

## pass 케이스
1. 직접 관련: 질문 키워드와 트리플 노드 매칭
   - "연차 며칠이야?" + "35조 → 유급휴가" → pass
   - "A프로젝트 담당자 누구야?" + "김민수 —[담당]→ A프로젝트" → pass
2. doc_mode 구조 트리플: 관련 조항의 계층 구조
   - "연차 규정이 뭐야?" + "35조 —[항, seq=1]→ 35조①" → pass
   - "출근율 조항?" + "35조① → 출근율" → pass
3. 간접 관련: 같은 도메인 연관 개념
   - "프로젝트 마감 언제야?" + "A프로젝트 → 일정" → pass
   - "팀장 누구야?" + "개발팀 —[팀장]→ 김민수" → pass
4. 불확실 경계 → pass (안전 원칙)

## reject 케이스
1. 완전 다른 도메인:
   - "연차 며칠이야?" + "김민수 —[담당]→ A프로젝트" → reject
   - "팀장 누구야?" + "취업규칙 → 35조" → reject (규정 질문 아님)
2. 완전 무관:
   - "A프로젝트 일정?" + "복리후생 → 식대" → reject

## 트리플 유형 다양성
- 일반 조직 트리플 (60%): 사람-팀, 프로젝트-담당, 계약-고객사
- doc_mode 트리플 (30%): 35조 → 유급휴가, 제3항 → 출근율, 취업규칙 → 연차
- 라벨 있는 트리플 (30%): —[소속]→, —[담당]→, —[항]→, —[계약]→

## 질문 유형
조직 구조, 규정/정책, 프로젝트 현황, 담당자, 일정/마감, 인사 정보

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK4_ORG_PROMPT = """\
Synapse 조직 그래프의 "인출 확장 (조직 도메인)" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
조직 관련 질문을 받아 그래프에서 검색할 노드 후보를 생성합니다.
노드는 형태소 단위: 연차, 유급휴가, 35조, 취업규칙, 김민수, 개발팀, A프로젝트, 담당, 마감

## 출력 형식 (JSON 배열)
[
  {{"user": "질문: <조직 관련 질문>", "assistant": "[\\"노드1\\", \\"노드2\\", ...]"}},
  ...
]

## 질문 유형 (골고루)
1. 규정/정책: "연차 며칠이야?", "출산휴가 규정이 뭐야?", "식대 지원 얼마야?"
2. 조직 구조: "개발팀 팀장 누구야?", "어느 팀이 몇 명이야?", "기획팀 어디 있어?"
3. 프로젝트: "A프로젝트 담당자 누구야?", "B프로젝트 마감 언제야?", "진행 중인 프로젝트 뭐야?"
4. 인사: "이대리 어느 팀이야?", "김팀장 직급이 뭐야?", "신입 누가 들어왔어?"
5. 일정: "이번 주 회의 언제야?", "전사 워크숍 일정이 뭐야?"
6. 고객사: "삼성전자 담당 누구야?", "어떤 고객사랑 계약 중이야?"
7. 복합: "요즘 팀 어때?", "프로젝트 현황이 어떻게 돼?"

## 노드 후보 품질
- 형태소 단위. 조사/종결어미 제외.
- 관련 법령/조항 번호도 노드 후보 포함 (35조, 제3항 등)
- 동의어/관련어: 연차 → ["연차", "유급휴가", "취업규칙", "35조", "일수", "출근율"]
- 4~8개

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK5A_ORG_PROMPT = """\
Synapse 조직 그래프의 "트리플 민감도 마킹 (권한 포함)" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
조직 그래프 트리플의 민감도와 열람에 필요한 최소 권한을 동시에 마킹합니다.

## 민감도 카테고리 + 최소 권한
| 카테고리 | 설명 | 최소 권한 |
|----------|------|-----------|
| personal_info | 직원 연봉·주소·건강·가족사항 | hr |
| performance | 성과 평가·등급·KPI | team_lead |
| trade_secret | 계약금액·내부 단가·기술 노하우 | executive |
| internal_decision | 미발표 인사·전략 계획·구조조정 | executive |
| client_confidential | 고객사 기밀·미공개 프로젝트명 | executive |
| legal_risk | 계약 분쟁·규정 위반·소송 | hr |

## 출력 형식 (JSON 배열)
[
  {{"user": "트리플: <노드A> → <노드B>", "assistant": "safe"}},
  {{"user": "트리플: <노드A> —[<라벨>]→ <노드B>", "assistant": "sensitive:personal_info:hr"}},
  ...
]

## 생성 규칙
- safe 55% / sensitive 45% (카테고리 골고루)
- safe 예시:
  * 김민수 → 개발팀, A프로젝트 → 진행중, 개발팀 —[팀장]→ 이부장
  * 취업규칙 → 35조, 35조 → 유급휴가, 연차 → 15일
- sensitive 예시:
  * 김민수 → 연봉 → sensitive:personal_info:hr
  * 김민수 —[평가등급]→ C → sensitive:performance:team_lead
  * A계약 —[금액]→ 5억 → sensitive:trade_secret:executive
  * 구조조정 → 검토중 → sensitive:internal_decision:executive
  * 삼성전자 → 미공개프로젝트X → sensitive:client_confidential:executive
  * 계약분쟁 → 진행중 → sensitive:legal_risk:hr

## 경계 케이스 풍부하게
- 직급/팀명 → safe (공개 정보)
- 담당 프로젝트명 → safe (단, 미공개이면 sensitive)
- 연봉 등급 없이 단순 금액 → sensitive:financial:hr

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

TASK5B_ORG_PROMPT = """\
Synapse 조직 그래프의 "컨텍스트 민감도 판단 (권한 기반)" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
질의자 권한과 인출된 전체 트리플 컨텍스트(5A 마킹 포함)를 보고 정보 제공 가능 여부를 종합 판단합니다.

## 권한 레벨
employee < team_lead < hr < executive < admin

## 권한 판단 원칙
- 트리플 최소권한 > 질의자 권한 → reject
- 트리플 최소권한 ≤ 질의자 권한 → confirm (민감 정보는 항상 확인 요청)
- 전부 safe → safe
- 5A 전부 safe여도 조합 효과로 confirm 가능:
  * [safe] 김민수 → 성과등급 + [safe] 김민수 → 연봉협상 → 조합 시 개인 평가 식별 → confirm

## 출력 형식 (JSON 배열)
[
  {{
    "user": "질문: <질문>\\n질의자 권한: <권한>\\n컨텍스트:\\n- [<마킹>] <노드A> → <노드B>\\n...",
    "assistant": "{{\\"result\\": \\"safe\\"}}"
  }},
  {{
    "user": "질문: <질문>\\n질의자 권한: <권한>\\n컨텍스트:\\n- [sensitive:personal_info:hr] <노드A> → <노드B>\\n...",
    "assistant": "{{\\"result\\": \\"reject\\", \\"message\\": \\"해당 정보는 HR 담당자 이상만 열람 가능합니다.\\"}}"
  }},
  ...
]

## 비율: safe {safe_count}개 / confirm {confirm_count}개 / reject {reject_count}개

## 케이스 설계
### safe (35%)
- 전부 safe 트리플 + 권한 무관
- employee가 일반 조직 정보 조회

### confirm (35%)
- sensitive 트리플 있는데 질의자 권한이 최소 권한 이상
- team_lead가 팀원 performance 조회
- hr이 직원 연봉 조회
- executive가 전략 정보 조회
- 5A safe지만 조합 효과

### reject (30%)
- sensitive 트리플의 최소 권한 > 질의자 권한
- employee가 타인 연봉 조회 → reject
- team_lead가 trade_secret 조회 → reject
- hr이 executive 전략 조회 → reject

## confirm/reject 메시지
- 구체적으로: 어떤 정보가 왜 민감한지
- confirm: "팀원 성과 등급 정보가 포함됩니다. 열람하시겠습니까?"
- reject: "해당 정보는 임원 이상만 열람 가능합니다."

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""

GENERATION_PROMPTS = {
    0:    TASK0_PROMPT,
    1:    TASK1_ORG_PROMPT,
    2:    TASK2_ORG_PROMPT,
    3:    TASK3_ORG_PROMPT,
    4:    TASK4_ORG_PROMPT,
    "5a": TASK5A_ORG_PROMPT,
    "5b": TASK5B_ORG_PROMPT,
}

# ---------------------------------------------------------------------------
# Shared utilities (same as generate_task_data.py)
# ---------------------------------------------------------------------------

def call_claude(prompt: str) -> str:
    result = subprocess.run(
        [CLAUDE_CMD, "-p", "--model", CLAUDE_MODEL, prompt],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:300]}", file=sys.stderr)
        return ""
    return result.stdout.strip()


def strip_code_fence(text: str) -> str:
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
    raw = strip_code_fence(raw)
    if not raw:
        return []
    start = raw.find("[")
    if start == -1:
        print(f"  No JSON array found", file=sys.stderr)
        return []
    raw = raw[start:]

    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(raw)
        if isinstance(data, list):
            return [item for item in data if "user" in item and "assistant" in item]
    except json.JSONDecodeError:
        pass

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
                    print(f"  (recovered {len(items)} from truncated)", file=sys.stderr)
                    return items
        except json.JSONDecodeError:
            pass

    print(f"  JSON parse failed. Raw (first 400): {raw[:400]}", file=sys.stderr)
    return []


def make_training_entry(task_id, user: str, assistant: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS[task_id]},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


def generate_task(task_id, target: int, batch_size: int = 25, dry_run: bool = False, append: bool = False):
    print(f"\n=== Task {task_id}-org: {OUTPUT_FILES[task_id]} (target: {target}) ===")
    out_path = DATA_DIR / OUTPUT_FILES[task_id]

    # Count existing examples when appending
    existing_count = 0
    if append and out_path.exists():
        with open(out_path, "r", encoding="utf-8") as f:
            existing_count = sum(1 for line in f if line.strip())
        print(f"  Existing: {existing_count}, need {max(0, target - existing_count)} more")
        remaining = max(0, target - existing_count)
    else:
        remaining = target

    if dry_run:
        batches = (remaining + batch_size - 1) // batch_size if remaining > 0 else 0
        print(f"  [DRY RUN] ~{batches} claude calls ({CLAUDE_MODEL}), ~{remaining} examples")
        return

    if remaining == 0:
        print(f"  Already at target ({existing_count}/{target}), skipping.")
        return existing_count

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_examples = []
    batch_num = 0

    while remaining > 0:
        batch_num += 1
        count = min(batch_size, remaining)
        prompt_template = GENERATION_PROMPTS[task_id]

        # Tasks with custom ratio params
        if task_id == 3:
            pass_count = round(count * 0.6)
            reject_count = count - pass_count
            prompt = prompt_template.format(
                count=count, pass_count=pass_count, reject_count=reject_count
            )
        elif task_id == "5b":
            safe_count = round(count * 0.35)
            confirm_count = round(count * 0.35)
            reject_count = count - safe_count - confirm_count
            prompt = prompt_template.format(
                count=count,
                safe_count=safe_count,
                confirm_count=confirm_count,
                reject_count=reject_count,
            )
        else:
            prompt = prompt_template.format(count=count)

        print(f"  [{batch_num}] Requesting {count} examples... ", end="", flush=True)
        raw = call_claude(prompt)
        if not raw:
            print("SKIP (empty response)")
            remaining -= count
            continue

        examples = parse_examples(raw)
        got = len(examples)
        print(f"→ {got} parsed", end="")

        if got == 0:
            print(" (WARN: 0 parsed, skipping)")
            remaining -= count
            continue

        for ex in examples:
            entry = make_training_entry(task_id, ex["user"], ex["assistant"])
            all_examples.append(entry)

        remaining -= got
        if remaining < 0:
            remaining = 0
        print(f"  [total: {len(all_examples)}]")

    mode = "a" if append and out_path.exists() else "w"
    with open(out_path, mode, encoding="utf-8") as f:
        for entry in all_examples:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    total_written = existing_count + len(all_examples)
    print(f"  ✓ Written {len(all_examples)} new examples (total: {total_written}) → {out_path}")
    return total_written


def parse_task_ids(task_str: str) -> list:
    if task_str == "all":
        return [0, 1, 2, 3, 4, "5a", "5b"]
    result = []
    for t in task_str.split(","):
        t = t.strip()
        if t in ("5a", "5b"):
            result.append(t)
        else:
            result.append(int(t))
    return result


def main():
    parser = argparse.ArgumentParser(description="Generate Synapse org fine-tuning datasets")
    parser.add_argument("--task", default="all", help="Task: 0|1|2|3|4|5a|5b|all or comma-separated")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--append", action="store_true", help="Append to existing files to reach target")
    args = parser.parse_args()

    tasks = parse_task_ids(args.task)

    print(f"Mode: org")
    print(f"Model: {CLAUDE_MODEL}")
    print(f"Tasks: {tasks}, batch_size={args.batch_size}, dry_run={args.dry_run}")
    print(f"Output: {DATA_DIR}")
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
            print(f"  Task {task_id}-org: {count}/{target} [{status}]")
        print(f"  Total: {sum(totals.values())} examples")


if __name__ == "__main__":
    main()

"""Synapse LLM — MLX 서버 클라이언트.

MLX 서버: localhost:8765 (api/mlx_server.py)
환경변수 SYNAPSE_MLX_BASE 로 주소 변경 가능.
"""

from __future__ import annotations
import json
import os
import re
import urllib.request
import urllib.error
from typing import Optional

MLX_BASE = os.getenv("SYNAPSE_MLX_BASE", "http://127.0.0.1:8765")


class LLMError(RuntimeError):
    pass


# ── MLX 태스크별 시스템 프롬프트 ───────────────────────────
_MLX_SYSTEM: dict[str, str] = {
    "retrieve-filter": (
        "당신은 지식 그래프 인출 필터입니다. 질문과 트리플을 보고, 이 트리플이 질문과 관련 있는지 판단하세요. "
        "불확실하면 pass로 판단하세요 (제외보다 포함이 안전). 출력: pass 또는 reject (한 단어만)"
    ),
    "retrieve-expand": (
        "당신은 지식 그래프 검색 엔진입니다. 질문을 보고 그래프에서 검색해야 할 관련 노드 후보를 생성하세요. "
        '형태소 단위로 쪼개진 노드 이름으로 나열하세요. 출력 형식: ["노드1", "노드2", ...]'
    ),
    "retrieve-expand-org": (
        "당신은 지식 그래프 검색 엔진입니다. 조직 관련 질문을 보고 그래프에서 검색해야 할 관련 노드 후보를 생성하세요. "
        '형태소 단위로 쪼개진 노드 이름으로 나열하세요. 출력 형식: ["노드1", "노드2", ...]'
    ),
    "save-pronoun": (
        "당신은 지식 그래프 저장 엔진입니다. 텍스트에서 대명사와 부사를 구체적인 값으로 치환하세요. "
        '대화 맥락이 제공되면 활용하세요. 치환 불가능하면 {"question": "질문 내용"}을 반환하세요. '
        '출력 형식: {"text": "치환된 텍스트"} 또는 {"question": "..."}'
    ),
    "save-state-personal": (
        "당신은 지식 그래프 관리 엔진입니다. 사용자 입력과 기존 트리플을 보고, 상태가 변경된 엣지를 찾아 JSON으로 반환하세요. "
        '변경이 없으면 빈 배열을 반환하세요. 출력 형식: {"inactive": [{"source": "...", "target": "..."}]}'
    ),
    "save-state-org": (
        "당신은 지식 그래프 관리 엔진입니다. 조직 모드에서 사용자 입력과 기존 트리플을 보고, 상태가 변경된 엣지를 찾아 JSON으로 반환하세요. "
        '변경이 없으면 빈 배열을 반환하세요. 출력 형식: {"inactive": [{"source": "...", "target": "..."}]}'
    ),
    "save-subject-org": (
        "당신은 지식 그래프 저장 엔진입니다. 조직 모드에서 발화의 주어를 특정하세요. "
        '주어가 불명확하면 {"question": "..."}, 추론 가능하면 {"subject": "...", "text": "..."}, '
        '주어가 불필요한 발화면 {"text": "..."}를 반환하세요.'
    ),
    "security-personal": (
        "당신은 지식 그래프 보안 엔진입니다. 트리플 하나를 보고 민감정보 여부를 판단하세요. "
        "출력 형식: safe 또는 sensitive:<카테고리> "
        "(카테고리: health_detail | financial | location_precise | relationship_private | schedule_combined)"
    ),
    "security-org": (
        "당신은 지식 그래프 보안 엔진입니다. 조직 그래프 트리플 하나를 보고 민감정보 여부와 최소 열람 권한을 판단하세요. "
        "출력 형식: safe 또는 sensitive:<카테고리>:<최소권한> "
        "(카테고리: personal_info|performance|trade_secret|internal_decision|client_confidential|legal_risk, "
        "최소권한: team_lead|hr|executive)"
    ),
    "security-context": (
        "당신은 지식 그래프 보안 엔진입니다. 질문과 인출된 전체 트리플 컨텍스트(각 트리플의 5A 마킹 포함)를 보고, "
        '답변에 민감정보가 포함되는지 종합 판단하세요. 출력 형식: {"result": "safe"} 또는 '
        '{"result": "confirm", "message": "사용자에게 보여줄 확인 메시지"}'
    ),
    "security-access": (
        "당신은 지식 그래프 보안 엔진입니다. 질의자 권한과 인출된 전체 트리플 컨텍스트(5A 마킹 포함)를 보고, "
        '정보 제공 가능 여부를 판단하세요. 출력 형식: {"result": "safe"} 또는 '
        '{"result": "confirm", "message": "..."} 또는 {"result": "reject", "message": "..."}'
    ),
    "routing": (
        "당신은 지식 그래프 라우팅 엔진입니다. 사용자 질문을 보고 조직 컨텍스트 augment가 필요한지 판단하세요. "
        "출력: personal_only 또는 augment_org (한 단어만)"
    ),
    "extract": (
        "한국어 문장에서 지식 그래프의 노드와 엣지를 추출하라.\n"
        "JSON만 출력. 다른 텍스트 금지.\n\n"
        "출력 형식:\n"
        '{"nodes":[{"name":"노드명","category":"대분류.소분류"}],'
        '"edges":[{"source":"노드명","label":"조사","target":"노드명"}]}\n\n'
        "규칙:\n"
        "- 노드는 원자. 하나의 개념 = 하나의 노드.\n"
        "- 1인칭(나/내/저/제) → 항상 \"나\"(PER.individual)\n"
        "- 3인칭 주어는 나로 치환하지 말 것. 원문 그대로 노드로 추출.\n"
        "- 저장 불필요한 일상 대화 → {\"nodes\":[],\"edges\":[]}\n"
        "- 엣지 label은 원문의 조사 그대로 (에, 에서, 으로, 의, 를, 이/가, 와/과 등). 조사 없으면 null."
    ),
}


def _mlx_post(model: str, messages: list[dict], max_tokens: int, temperature: float = 0.0) -> str:
    """MLX 서버에 chat completions 요청. 응답 텍스트 반환."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    url = MLX_BASE + "/v1/chat/completions"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
        content = result["choices"][0]["message"]["content"].strip()
        # gemma4 thinking 블록 제거: 완결된 블록 또는 max_tokens로 잘린 블록 모두 처리
        content = re.sub(r"<\|channel>thought.*?<channel\|>", "", content, flags=re.DOTALL).strip()
        content = re.sub(r"<\|channel>thought.*", "", content, flags=re.DOTALL).strip()
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        content = re.sub(r"<think>.*", "", content, flags=re.DOTALL).strip()
        return content
    except urllib.error.URLError as e:
        raise LLMError(
            f"MLX 서버 연결 실패: {e}\n→ python api/mlx_server.py 로 서버를 실행하세요."
        ) from e


def mlx_chat(task: str, user: str, max_tokens: int = 256) -> str:
    """MLX 서버에 태스크별 추론 요청. 응답 텍스트 반환.

    task: _MLX_SYSTEM 키 (예: "retrieve-filter", "save-pronoun")
    """
    system = _MLX_SYSTEM.get(task, "")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return _mlx_post(f"synapse/{task}", messages, max_tokens)


def chat(
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 256,
    images: Optional[list[str]] = None,
    history: Optional[list[dict]] = None,
) -> str:
    """일반 채팅 요청 (베이스 모델). 응답 텍스트 반환."""
    messages: list[dict] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})
    return _mlx_post("synapse/chat", messages, max_tokens, temperature)


# 저장/인출에서 공통으로 쓰는 시스템 프롬프트

SYSTEM_SAVE = """당신은 한국어 지식 그래프 저장 전처리기입니다.
사용자 입력과 기존 그래프 트리플을 분석해 아래 JSON만 출력하세요. 다른 텍스트 금지.

출력 형식:
{"is_question": false, "retention": "memory"|"daily", "state_changes": [{"node": "노드명", "edge_label": "엣지라벨"}], "substitutions": [{"original": "원본", "replacement": "치환값"}], "question": null}

규칙:
0. is_question: 입력이 정보를 묻는 질문이면 true, 사실·상태·경험을 진술하는 문장이면 false. true이면 나머지 필드는 전부 기본값으로 출력.
1. retention: 입력 내용의 성격을 분류.
   - "memory": 잘 변하지 않는 사실·상태·관계·이력. 직업, 병명, 거주지, 소유물, 인간관계, 학력, 이직/입사/진단/이사/수술 같은 이벤트. "오늘"이 포함되어도 이직·입사·진단·이사·수술 같은 이벤트면 "memory".
   - "daily": 순간적 활동, 오늘의 감정, 일상 행동 (식사, 날씨 언급, 피곤함, 가벼운 외출 등).
2. state_changes: "나았어" "그만뒀어" "이사했어" "끊었어" 등 상태 변화 표현이 있을 때, 기존 트리플에서 해당 엣지를 비활성화 대상으로 지정.
3. substitutions: "이거" "그분" "거기" 같은 3인칭 대명사, "오늘" "내일" "어제" "그날" 같은 날짜 지시어만 구체 값으로 치환. 나/내/저/제(1인칭)는 절대 치환하지 않음. 나이는 반드시 출생연도로 치환 (예: 나이 49세 → 오늘 날짜 기준 출생연도 계산). 금액은 절대 치환하지 않음.
4. question: 어떤 노드인지 특정 불가할 때만 한국어로 질문 작성. 확실하면 null.

예시 0 (질문):
입력: "내 직업 뭐야"
출력: {"is_question": true, "retention": "memory", "state_changes": [], "substitutions": [], "question": null}

예시 1 (상태변화, memory):
입력: "허리 이제 나았어"
기존: ["허리 —(아프)→ 현재"]
출력: {"retention": "memory", "state_changes": [{"node": "허리", "edge_label": "아프"}], "substitutions": [], "question": null}

예시 2 (시간부사 치환, daily):
입력: "오늘 병원 다녀왔어" (오늘=2025-01-15)
기존: []
출력: {"retention": "daily", "state_changes": [], "substitutions": [{"original": "오늘", "replacement": "2025-01-15"}], "question": null}

예시 3 (모호성):
입력: "거기 결국 그만뒀어"
기존: ["A사 —(재직)→ 현재", "B학원 —(수강)→ 현재"]
출력: {"retention": "memory", "state_changes": [], "substitutions": [], "question": "어디를 그만두신 건가요? A사인가요, B학원인가요?"}

예시 4 (일상, daily):
입력: "맥북 샀어"
기존: []
출력: {"retention": "memory", "state_changes": [], "substitutions": [], "question": null}

예시 5 (오늘+이벤트, memory):
입력: "오늘 이직 첫날이야"
기존: []
출력: {"retention": "memory", "state_changes": [], "substitutions": [], "question": null}

예시 6 (나이→출생연도, memory):
입력: "나 49살이야" (오늘=2026-04-06)
기존: []
출력: {"retention": "memory", "state_changes": [], "substitutions": [{"original": "49살", "replacement": "1977년생"}], "question": null}"""

SYSTEM_RETRIEVE_EXPAND = """당신은 한국어 지식 그래프 검색 키워드 추출기입니다.
질문에서 그래프 노드로 존재할 법한 개념 키워드를 JSON 배열로만 출력하세요. 다른 텍스트 금지.

규칙:
- 인명, 지명, 회사명, 질병명, 물건명 등 고유명사 우선
- 형태소 분리 금지. 단어 전체를 그대로 추출
- 동사·형용사는 제외
- 나/내/저/제 → "나" 로 추출
- 최대 6개"""

SYSTEM_RETRIEVE_FILTER = """당신은 한국어 지식 그래프 필터입니다.
질문과 문장 목록을 보고 각 문장의 관련성을 true/false JSON 배열로만 출력하세요. 다른 텍스트 금지.

규칙:
- 질문의 핵심 주제와 직접 연관된 문장 → true
- 관련 없는 문장 → false
- 판단 불확실하면 → true (누락 방지 우선)
- 배열 길이는 문장 수와 반드시 동일

예시:
질문: "허리는 언제부터 아팠어?"
문장: ["나는 허리디스크 L4-L5 진단 받았어", "오늘 점심에 파스타 먹었어"]
출력: [true, false]"""

SYSTEM_CHAT = """당신은 사용자의 개인 비서입니다.
아래 지식 그래프 트리플이 사용자에 대해 알려진 사실입니다.
이 사실들을 근거로 질문에 자연스럽고 간결하게 한국어로 답변하세요.

주의사항:
- 트리플에 없는 내용은 "모르겠어요" 또는 "기록이 없어요"라고 답변
- 추측하거나 일반적인 정보를 보충하지 말 것
- 짧고 명확하게 답변 (2-3문장 이내)
- 반말/존댓말은 트리플 문맥에 맞게 판단"""

SYSTEM_IMAGE_EXTRACT = """이미지에서 텍스트를 읽어 한국어 단문으로 변환하세요.
- 표나 목록은 "X는 Y입니다" 형식 문장으로 변환하세요
- 해석하거나 내용을 추가하지 말고 원본 내용만 그대로 변환하세요
- 여러 항목이면 줄바꿈으로 나열하세요
- 다른 설명 없이 변환된 문장만 출력하세요"""


# ── 파이프라인 전용 함수 ──────────────────────────────────

def retrieve_expand(question: str) -> list[str]:
    """질문 → 노드 후보 키워드 목록."""
    try:
        raw = mlx_chat("retrieve-expand", f"질문: {question}", max_tokens=512)
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        return json.loads(match.group()) if match else []
    except Exception:
        return question.split()


def retrieve_filter_triple(question: str, triple_str: str) -> bool:
    """트리플 1개가 질문과 관련 있는지 판단. True=pass, False=reject."""
    try:
        user = f"질문: {question}\n트리플: {triple_str}"
        result = mlx_chat("retrieve-filter", user, max_tokens=8)
        return result.strip().lower() != "reject"
    except Exception:
        return True


def save_pronoun(text: str, context: str = "", today: str = "") -> dict:
    """대명사/부사 치환. {"text": ...} 또는 {"question": ...} 반환."""
    import re
    try:
        parts = []
        if today:
            parts.append(f"날짜: {today}")
        if context:
            parts.append(f"직전 대화 - {context}")
        parts.append(f"입력: {text}")
        raw = mlx_chat("save-pronoun", "\n".join(parts), max_tokens=128)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(match.group()) if match else {"text": text}
    except Exception:
        return {"text": text}


def llm_extract(text: str) -> dict:
    """LLM으로 노드/엣지/카테고리/상태변경/보관유형 추출 (task6 파인튜닝 모델).

    반환: {"retention": "memory|daily", "nodes": [...], "edges": [...], "deactivate": [...]}
    """
    try:
        raw = mlx_chat("extract", text, max_tokens=512)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {"retention": "memory", "nodes": [], "edges": [], "deactivate": []}
        result = json.loads(match.group())
        result.setdefault("retention", "memory")
        result.setdefault("nodes", [])
        result.setdefault("edges", [])
        result.setdefault("deactivate", [])
        return result
    except Exception:
        return {"retention": "memory", "nodes": [], "edges": [], "deactivate": []}


def save_state(text: str, existing_triples: list[str], org_mode: bool = False) -> list[dict]:
    """상태 변경 엣지 감지. [{"source": ..., "target": ...}] 반환."""
    import re
    try:
        task = "save-state-org" if org_mode else "save-state-personal"
        triples_str = "\n".join(f"- {t}" for t in existing_triples)
        user = f"입력: {text}\n기존 트리플:\n{triples_str}"
        raw = mlx_chat(task, user, max_tokens=256)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return []
        result = json.loads(match.group())
        return result.get("inactive", [])
    except Exception:
        return []


# 하위 호환을 위한 별칭
OllamaError = LLMError

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
        "당신은 지식 그래프 인출 필터입니다. 질문과 문장을 보고, 이 문장이 질문과 관련 있는지 판단하세요. "
        "불확실하면 pass로 판단하세요 (제외보다 포함이 안전). 출력: pass 또는 reject (한 단어만)"
    ),
    "retrieve-expand": (
        "당신은 지식 그래프 검색 엔진입니다. 질문을 보고 그래프에서 검색해야 할 관련 노드 후보를 생성하세요. "
        '형태소 단위로 쪼개진 노드 이름으로 나열하세요. 출력 형식: ["노드1", "노드2", ...]'
    ),
    "save-pronoun": (
        "당신은 지식 그래프 저장 엔진입니다. 텍스트에서 지시대명사와 부사를 구체적인 값으로 치환하세요.\n"
        "인칭대명사(나/내/저/제)는 치환하지 마세요.\n"
        "주어/목적어/장소가 생략되었으면 같은 게시물의 다른 문장을 참고하여 복원하세요.\n"
        "맥락이 제공되면 활용하세요.\n\n"
        "날짜 치환 규칙:\n"
        '- "날짜:" 값이 제공되면 그것이 오늘이다.\n'
        "- 오늘/어제/내일/모레/그저께/이번 주/지난주/다음 주/이번 달/지난달 등을 날짜 기준으로 계산하여 YYYY-MM-DD로 치환.\n"
        "- 요일(월~일)은 해당 주의 날짜로 변환. '지난 주 월요일'이면 직전 월요일 날짜.\n\n"
        "주어 불명확 규칙:\n"
        '- 주어가 완전히 생략되어 누가/무엇이 불분명하면 {"question": "확인 질문"}을 반환.\n'
        '- 예: "했대" → {"question": "누가 무엇을 했나요?"}\n\n'
        "치환 불가능한 지시어는 그대로 두고 unresolved 배열에 원형을 담으세요.\n"
        '출력 형식: {"text": "치환된 텍스트", "tokens": [{...}], "unresolved": [...]}\n'
        '또는 주어 불명확 시: {"question": "확인 질문"}'
    ),
    "extract": (
        "너는 형태소 분석기다.\n"
        "한국어 문장에서 노드를 추출하라.\n\n"
        "노드 원칙:\n"
        "- 노드는 원자. 하나의 개념 = 하나의 노드.\n"
        "- 품사 무관 (명사·동사·형용사·부정부사 모두 가능)\n"
        "- 조사·어미 제거 (예: \"허리디스크를\" → \"허리디스크\")\n"
        "- 1인칭 명시 시 반드시 \"나\"로 통일 (내/저/제도 \"나\"로)\n"
        "- 부정부사(안, 못)는 독립 노드\n"
        "- 법인 접두어(㈜, (주)) 포함 통째로 유지 (예: \"㈜한솔\" → \"㈜한솔\", 분리 금지)\n"
        "- 영문·숫자 포함 고유명사는 분리 금지 (예: \"A프로젝트\", \"L4-L5\", \"갤럭시 S25 울트라\")\n\n"
        '출력: {"nodes": ["노드1", "노드2", ...]}\n'
        "JSON 한 줄만 출력. 설명·주석 금지.\n\n"
        "예시:\n"
        "입력: 어제 김치찌개 먹었어\n"
        '출력: {"nodes":["김치찌개","먹"]}\n\n'
        "입력: 스타벅스 안 좋아\n"
        '출력: {"nodes":["스타벅스","안","좋"]}\n\n'
        "입력: 나 허리디스크 L4-L5 진단받았어\n"
        '출력: {"nodes":["나","허리디스크","L4-L5","진단받"]}\n\n'
        "입력: 내 맥북 고장났어\n"
        '출력: {"nodes":["나","맥북","고장나"]}\n\n'
        "입력: ㈜한솔이랑 B프로젝트 계약 체결했어\n"
        '출력: {"nodes":["㈜한솔","B프로젝트","계약","체결"]}\n\n'
        "입력: 안녕 잘 지내?\n"
        '출력: {"nodes":[]}'
    ),
    "extract-state": (
        "알려진 사실 목록에서 현재 입력으로 인해 더 이상 유효하지 않은 문장을 찾아 sentence_id를 반환하라.\n"
        "JSON만 출력. 다른 텍스트 금지.\n\n"
        "출력 형식:\n"
        '{"deactivate":[sentence_id, ...]}\n\n'
        "규칙:\n"
        "- 각 알려진 사실에는 [번호]가 붙어 있다.\n"
        "- 현재 입력이 기존 사실을 무효화하면 해당 번호를 deactivate에 포함.\n"
        "- 무효화할 사실이 없으면 {\"deactivate\":[]}.\n"
        "- 무효화 판단 기준: 동일 주체의 상태/소속/위치/습관 등이 바뀐 경우.\n"
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


# 베이스 모델 + 시스템 프롬프트로 전환 완료된 태스크 (어댑터 불필요)
_BASE_MODEL_TASKS = {"routing", "retrieve-filter", "security-context", "save-pronoun", "extract"}


def mlx_chat(task: str, user: str, max_tokens: int = 32768) -> str:
    """MLX 서버에 태스크별 추론 요청. 응답 텍스트 반환.

    task: _MLX_SYSTEM 키 (예: "retrieve-filter", "save-pronoun")

    _BASE_MODEL_TASKS 에 등록된 태스크는 베이스 모델(synapse/chat)로 직접 호출.
    나머지는 어댑터(synapse/{task}) 시도 후 404 시 베이스 모델로 fallback.
    """
    system = _MLX_SYSTEM.get(task, "")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if task in _BASE_MODEL_TASKS:
        return _mlx_post("synapse/chat", messages, max_tokens)
    try:
        return _mlx_post(f"synapse/{task}", messages, max_tokens)
    except LLMError as e:
        if "404" in str(e):
            return _mlx_post("synapse/chat", messages, max_tokens)
        raise


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


SYSTEM_CHAT = """당신은 사용자의 개인 비서입니다.
아래는 사용자에 대해 알려진 사실 문장들입니다.
이 사실들을 근거로 질문에 자연스럽고 간결하게 한국어로 답변하세요.

주의사항:
- 문장에 없는 내용은 "모르겠어요" 또는 "기록이 없어요"라고 답변
- 추측하거나 일반적인 정보를 보충하지 말 것
- 짧고 명확하게 답변 (2-3문장 이내)
- 반말/존댓말은 문장 문맥에 맞게 판단"""

SYSTEM_IMAGE_EXTRACT = """이미지에서 텍스트를 읽어 한국어 단문으로 변환하세요.
- 표나 목록은 "X는 Y입니다" 형식 문장으로 변환하세요
- 해석하거나 내용을 추가하지 말고 원본 내용만 그대로 변환하세요
- 여러 항목이면 줄바꿈으로 나열하세요
- 다른 설명 없이 변환된 문장만 출력하세요"""


# ── 파이프라인 전용 함수 ──────────────────────────────────

def retrieve_expand(question: str) -> list[str]:
    """질문 → 노드 후보 키워드 목록."""
    try:
        raw = mlx_chat("retrieve-expand", f"질문: {question}")
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        return json.loads(match.group()) if match else []
    except Exception:
        return question.split()


def retrieve_filter_sentence(question: str, sentence: str) -> bool:
    """문장 1개가 질문과 관련 있는지 판단. True=pass, False=reject."""
    try:
        user = f"질문: {question}\n문장: {sentence}"
        result = mlx_chat("retrieve-filter", user, max_tokens=8)
        return result.strip().lower() != "reject"
    except Exception:
        return True


def save_pronoun(text: str, context: str = "", today: str = "") -> dict:
    """대명사/부사 치환. v12 반환 구조:
    - {"text": ..., "unresolved": [...]}  (정상)
    - {"question": ...}  (모호성 → 즉시 되묻기)

    context는 "직전 대화"가 아니라 "같은 게시물의 다른 sentences".
    """
    import re
    try:
        parts = []
        if today:
            parts.append(f"날짜: {today}")
        if context:
            parts.append(f"같은 게시물의 다른 문장들 - {context}")
        parts.append(f"입력: {text}")
        raw = mlx_chat("save-pronoun", "\n".join(parts))
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {"text": text, "unresolved": []}
        data = json.loads(match.group())
        if "question" in data:
            return data
        # text + unresolved 정규화
        return {
            "text": data.get("text", text),
            "unresolved": [t for t in data.get("unresolved", []) if isinstance(t, str)],
        }
    except Exception:
        return {"text": text, "unresolved": []}


_STRUCTURE_SUGGEST_SYSTEM = (
    "한국어 평문을 마크다운 구조화된 게시물로 바꿔라.\n"
    "규칙:\n"
    "- 본문(사용자가 쓴 텍스트의 줄바꿈)은 절대 건드리지 마라. 줄을 합치거나 추가 쪼개기 금지.\n"
    "- 맨 앞에 heading 한 줄(`# 경로`)만 추가한다.\n"
    "- 가능하면 기존 사용자 카테고리 경로를 재사용. 알맞은 게 없으면 새 경로 제안 (예: `병원.2026-04-18`).\n"
    "- 형식은 '대분류' 또는 '대분류.소분류' 점 구분 경로.\n"
    "- 다른 설명 없이 마크다운 텍스트만 출력."
)


def structure_suggest(text: str, known_paths: Optional[list[str]] = None) -> str:
    """평문을 마크다운 구조화 초안으로 변환 (heading만 추가).

    PLAN Phase 2-2: 초기엔 base 모델(synapse/chat) + 프롬프트로 동작.
    정확도 낮으면 후속 WI에서 파인튜닝 어댑터 학습.
    """
    try:
        parts = []
        if known_paths:
            parts.append("기존 경로 목록: " + ", ".join(known_paths[:20]))
        parts.append("본문:\n" + text)
        raw = chat(
            _STRUCTURE_SUGGEST_SYSTEM,
            "\n\n".join(parts),
            temperature=0,
            max_tokens=1024,
        )
        # LLM 응답에서 마크다운 텍스트 추출 (backtick 블록 제거)
        cleaned = re.sub(r"^```(?:markdown)?\s*", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip() or text
    except Exception:
        return text


def llm_extract(text: str, context_sentences: Optional[list[tuple[int, str]]] = None) -> dict:
    """LLM으로 노드 추출 + 상태변경 탐지 (베이스 모델 전환).

    베이스 모델 전환 (2026-04-20):
    - extract: 노드 추출만 담당 (EXTRACT_SYSTEMPROMPT.md, 94.4%)
    - extract-state: deactivate만 담당 (별도 어댑터)
    - 카테고리·별칭은 백그라운드 워커 (engine/workers.py)

    context_sentences: retrieve에서 가져온 (sentence_id, text) 쌍. deactivate 판단용.
    반환: {"nodes": [{"name": str}, ...], "deactivate": [sentence_id, ...]}
    """
    try:
        # 노드 추출 (베이스 모델 + 시스템 프롬프트)
        raw = mlx_chat("extract", text, max_tokens=1024)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        nodes = []
        if match:
            result = json.loads(match.group())
            for n in result.get("nodes", []):
                if isinstance(n, dict) and n.get("name"):
                    nodes.append({"name": n["name"]})
                elif isinstance(n, str):
                    nodes.append({"name": n})

        # 상태변경 탐지 (extract-state 어댑터)
        deactivate: list[int] = []
        if context_sentences:
            ctx = "\n".join(f"- [{sid}] {s}" for sid, s in context_sentences)
            state_input = f"{text}\n알려진 사실:\n{ctx}"
            try:
                state_raw = mlx_chat("extract-state", state_input)
                state_match = re.search(r"\{.*\}", state_raw, re.DOTALL)
                if state_match:
                    state_result = json.loads(state_match.group())
                    deactivate = [s for s in state_result.get("deactivate", []) if isinstance(s, int)]
            except Exception:
                pass

        return {"nodes": nodes, "deactivate": deactivate}
    except Exception:
        return {"nodes": [], "deactivate": []}


# 하위 호환을 위한 별칭
OllamaError = LLMError

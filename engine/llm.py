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
        "당신은 지식 그래프 저장 엔진입니다. 텍스트에서 지시대명사와 부사를 구체적인 값으로 치환하세요. "
        "주어/목적어/장소가 생략되었으면 직전 대화를 참고하여 복원하세요. "
        "인칭대명사(나/내/저/제)는 치환하지 마세요. "
        '대화 맥락이 제공되면 활용하세요. 치환 불가능하면 {"question": "질문 내용"}을 반환하세요. '
        '출력 형식: {"text": "치환된 텍스트"} 또는 {"question": "..."}'
    ),
    "extract": (
        "한국어 문장에서 지식 그래프의 노드, 엣지, 카테고리, 상태변경, 보관 유형을 추출하라.\n"
        "JSON만 출력. 다른 텍스트 금지.\n\n"
        "출력 형식:\n"
        '{"retention":"memory|daily","nodes":[{"name":"노드명","category":"대분류.소분류"}],'
        '"edges":[{"source":"노드명","label":"조사","target":"노드명"}],'
        '"deactivate":[sentence_id, ...]}\n\n'
        "규칙:\n"
        "- 노드는 원자. 하나의 개념 = 하나의 노드.\n"
        "- 1인칭(나/내/저/제)이 문장에 명시된 경우 \"나\" 노드로 추출. 문장에 없는 1인칭 추가 금지.\n"
        "- 3인칭 주어는 원문 그대로 노드 추출.\n"
        "- 엣지 label = 원문의 조사 그대로 (에서, 으로, 의, 에, 를/을, 와/과, 고, 이/가 등). 조사 없으면 null.\n"
        "- 부정부사(안, 못)는 독립 노드다. 예: \"스타벅스 안 좋아\" → 스타벅스→안→좋아 (3노드, 2엣지 null).\n"
        "- 엣지의 source와 target은 반드시 nodes 배열에 있는 노드명과 정확히 일치해야 한다.\n"
        "- \"알려진 사실:\"이 제공된 경우: 각 문장에 [번호]가 붙어 있다. 현재 입력과 상충되는 문장의 번호를 deactivate에 포함. 없으면 [].\n"
        "- retention: 잘 변하지 않는 사실/상태/이력 → \"memory\". 순간적 활동/감정/일상 → \"daily\".\n"
        "- 추출할 노드/엣지가 없는 대화 → {\"retention\":\"daily\",\"nodes\":[],\"edges\":[],\"deactivate\":[]}\n\n"
        "카테고리는 반드시 '대분류.소분류' 형식 (예: PER.individual, WRK.role). 약어 금지.\n"
        "대분류(17개): PER BOD MND FOD LIV MON WRK TEC EDU LAW TRV NAT CUL HOB SOC REL REG\n"
        "소분류 예시: PER(individual,family,friend,colleague,public) BOD(disease,medical,part,sleep,exercise,nutrition) "
        "MND(mental,emotion,coping) WRK(workplace,role,jobchange) MON(income,spending,saving) "
        "LIV(housing,moving) TEC(device,software,infra) EDU(school,cert,study) LAW(statute,contract,rights,admin) "
        "TRV(domestic,abroad) FOD(ingredient,recipe,restaurant) HOB(sport,social) CUL(music,movie,book) "
        "SOC(issue,volunteer) REL(romance,comm) REG(practice,other,catholic) NAT(weather,animal,plant)"
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


def mlx_chat(task: str, user: str, max_tokens: int = 32768) -> str:
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
    """대명사/부사 치환. {"text": ...} 또는 {"question": ...} 반환."""
    import re
    try:
        parts = []
        if today:
            parts.append(f"날짜: {today}")
        if context:
            parts.append(f"직전 대화 - {context}")
        parts.append(f"입력: {text}")
        raw = mlx_chat("save-pronoun", "\n".join(parts))
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(match.group()) if match else {"text": text}
    except Exception:
        return {"text": text}


def llm_extract(text: str, context_sentences: Optional[list[tuple[int, str]]] = None) -> dict:
    """LLM으로 노드/엣지/카테고리/상태변경/보관유형 추출 (task6 파인튜닝 모델).

    context_sentences: retrieve에서 가져온 (sentence_id, text) 쌍. deactivate 판단에 사용.
    반환: {"retention": "memory|daily", "nodes": [...], "edges": [...], "deactivate": [sentence_id, ...]}
    """
    try:
        # ()[] 가 포함되면 2B 모델이 반복 루프에 빠짐 — 공백으로 치환
        text = re.sub(r"[()\[\]]", " ", text)
        if context_sentences:
            ctx = "\n".join(f"- [{sid}] {s}" for sid, s in context_sentences)
            input_text = f"{text}\n알려진 사실:\n{ctx}"
        else:
            input_text = text
        raw = mlx_chat("extract", input_text)
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


# 하위 호환을 위한 별칭
OllamaError = LLMError

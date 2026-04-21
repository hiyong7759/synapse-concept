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

from .prompts import load_prompt

MLX_BASE = os.getenv("SYNAPSE_MLX_BASE", "http://127.0.0.1:8765")


class LLMError(RuntimeError):
    pass


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
# v16: extract-merge 추가 — 2-step 파이프라인의 ③ LLM 병합 단계 (docs/EXTRACT_MERGE_SYSTEMPROMPT.md).
_BASE_MODEL_TASKS = {
    "retrieve-filter",
    "security-context",
    "save-pronoun",
    "extract",
    "extract-merge",
    "extract-state",
}


def mlx_chat(task: str, user: str, max_tokens: int = 32768) -> str:
    """MLX 서버에 태스크별 추론 요청. 응답 텍스트 반환.

    task: docs/{TASK}_SYSTEMPROMPT.md 파일명 키 (예: "retrieve-filter", "save-pronoun")

    _BASE_MODEL_TASKS 에 등록된 태스크는 베이스 모델(synapse/chat)로 직접 호출.
    나머지는 어댑터(synapse/{task}) 시도 후 404 시 베이스 모델로 fallback.
    """
    system = load_prompt(task)
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


def _parse_nodes_field(raw: str) -> list[dict]:
    """LLM 응답 텍스트에서 {"nodes":[...]} 를 뽑아 [{"name": str}] 로 정규화.

    노드 항목이 dict({"name":..}) 이든 str 이든 모두 {"name": str} 으로 통일한다.
    JSON 실패 시 빈 배열.
    """
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return []
    try:
        result = json.loads(match.group())
    except Exception:
        return []
    out: list[dict] = []
    for n in result.get("nodes", []):
        if isinstance(n, dict) and n.get("name"):
            out.append({"name": n["name"]})
        elif isinstance(n, str) and n:
            out.append({"name": n})
    return out


def llm_extract(text: str) -> dict:
    """① LLM 노드 추출 (2-step 파이프라인 ①단계, base 모델).

    원문 기반으로 외래어·고유명사 원형을 유지한 노드 후보를 뽑는다. 상태 전이
    판정은 llm_extract_state() 가 담당 (v16 에서 분리).

    반환: {"nodes": [{"name": str}, ...]}
    """
    try:
        raw = mlx_chat("extract", text, max_tokens=1024)
        return {"nodes": _parse_nodes_field(raw)}
    except Exception:
        return {"nodes": []}


def llm_extract_merge(
    text: str,
    llm_nodes: list[str],
    kiwi_nodes: list[str],
) -> list[dict]:
    """③ LLM 병합 (2-step 파이프라인 ③단계, base 모델).

    LLM extract 후보 · Kiwi 형태소 후보 두 리스트를 원문과 함께 입력해 최종
    노드를 결정한다. 프롬프트(docs/EXTRACT_MERGE_SYSTEMPROMPT.md) 가
    - 활용형 → Kiwi lemma 로 정규화
    - 외래어·복합명사 → LLM 원형 복원
    - 메타 대화·날짜 통짜 배제
    - 부정부사 '안'/'못' 포함
    규칙을 처리한다.

    반환: [{"name": str}, ...] — 병합 이후 최종 노드 배열
    """
    try:
        user = (
            f"원문: {text}\n"
            f"LLM 후보: {json.dumps(llm_nodes, ensure_ascii=False)}\n"
            f"Kiwi 후보: {json.dumps(kiwi_nodes, ensure_ascii=False)}"
        )
        raw = mlx_chat("extract-merge", user, max_tokens=512)
        return _parse_nodes_field(raw)
    except Exception:
        return []


def llm_extract_state(
    text: str,
    context_sentences: list[tuple[int, str]],
) -> dict:
    """④ 상태 전이 판정 (extract-state 태스크, base 모델).

    context_sentences: 같은 주체·주제의 기존 사실 목록 [(sentence_id, text), ...].
    현재 입력이 상태를 바꾸거나 충돌하면 deactivate / pending 으로 분류한다.

    v16 (L1): 프롬프트 포맷에 맞춰 **현재 입력과 각 알려진 사실 모두 Kiwi
    형태소 분석 결과(명사·용언 lemma)를 첨부**한다. 주체(명사) 공통 + 용언
    대립 판정을 모델이 문장 전체 재해석 대신 형태소 수준에서 직접 비교할 수
    있게 해서 base 모델 정확도를 올린다 (DESIGN_PIPELINE §④).

    반환: {"deactivate": [sentence_id, ...], "pending": [sentence_id, ...]}
    context_sentences 가 비어있으면 바로 빈 결과 반환(LLM 호출 생략).
    """
    if not context_sentences:
        return {"deactivate": [], "pending": []}

    from .tokenizer import extract_for_save as _kiwi
    cur = _kiwi(text)
    facts_lines: list[str] = []
    for sid, s in context_sentences:
        k = _kiwi(s)
        facts_lines.append(
            f"  [{sid}] 원문: {s}\n"
            f"        명사: [{', '.join(k['nouns'])}]\n"
            f"        용언: [{', '.join(k['lemmas'])}]"
        )
    state_input = (
        "현재 입력:\n"
        f"  원문: {text}\n"
        f"  명사: [{', '.join(cur['nouns'])}]\n"
        f"  용언: [{', '.join(cur['lemmas'])}]\n"
        "알려진 사실:\n" + "\n".join(facts_lines)
    )

    try:
        raw = mlx_chat("extract-state", state_input)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {"deactivate": [], "pending": []}
        result = json.loads(match.group())
        deactivate = [s for s in result.get("deactivate", []) if isinstance(s, int)]
        pending    = [s for s in result.get("pending",    []) if isinstance(s, int)]
        return {"deactivate": deactivate, "pending": pending}
    except Exception:
        return {"deactivate": [], "pending": []}


# 하위 호환을 위한 별칭
OllamaError = LLMError

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
# v17: extract·extract-merge·extract-state 폐기 (Kiwi 단독이 저장 기본 경로, 상태 레이어 제거).
#      meta-filter 신규 — 저장 파이프라인 진입부 메타 대화 필터 (docs/META_FILTER_SYSTEMPROMPT.md).
_BASE_MODEL_TASKS = {
    "retrieve-filter",
    "security-context",
    "save-pronoun",
    "meta-filter",
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
아래는 사용자에 대해 알려진 사실 문장들이며 **시간 순(오래된 것 → 최근)** 으로 정렬되어 있습니다. 각 줄 앞의 `[YYYY-MM-DD]` 는 그 사실이 기록된 날짜입니다.
이 사실들을 근거로 질문에 자연스럽고 간결하게 한국어로 답변하세요.

주의사항:
- 문장에 없는 내용은 "모르겠어요" 또는 "기록이 없어요"라고 답변
- 추측하거나 일반적인 정보를 보충하지 말 것
- **서로 충돌하는 사실이 있으면 최근 사실(아래쪽)을 우선 반영**. 단 과거 사실도 사라지지 않았으니 "지금은 X, 예전엔 Y" 처럼 시점을 구분해 설명
- "지금 어때?" 같은 현재형 질문은 가장 최근 기록을 근거로 답변
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


_META_Q_ENDING = re.compile(r"[\?？]\s*$")


def _rule_prefilter_meta(text: str, kiwi: dict) -> bool:
    """규칙 사전필터: Kiwi 명사 0개 + '?' 종결 → 메타 대화로 확정 (v17)."""
    return len(kiwi.get("nouns", [])) == 0 and bool(_META_Q_ENDING.search(text))


def llm_meta_filter(lines: list[str]) -> set[int]:
    """게시물 단위 메타 대화 필터 (v17 신설, B-v3 구조).

    각 줄을 검사해 "지식으로 저장할 가치 없는 메타 대화" 의 idx 집합을 반환.
    저장 파이프라인 진입부에서 1회 호출, 반환된 idx 는 sentence 저장 skip.

    구조:
    - (b) 규칙 사전필터 — Kiwi 명사 0개 + '?' 종결 → 즉시 메타 확정
    - (a) 나머지 줄은 1회 LLM 배치 호출 (prompt: META_FILTER_SYSTEMPROMPT.md)

    검증 (2026-04-22, 50문장 샘플): F1 1.00 (P=1.00, R=1.00).

    MLX 서버 다운 · JSON 파싱 실패 시 → 규칙 사전필터 결과만 반환 (과포함 허용).
    """
    from .tokenizer import extract_for_save as _kiwi

    rule_meta: set[int] = set()
    llm_items: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        try:
            k = _kiwi(line)
        except Exception:
            k = {"nouns": [], "lemmas": [], "negations": []}
        if _rule_prefilter_meta(line, k):
            rule_meta.add(i)
        else:
            llm_items.append((i, line))

    if not llm_items:
        return rule_meta

    try:
        body = "\n".join(f"[{i}] {t}" for i, t in llm_items)
        raw = mlx_chat("meta-filter", "입력:\n" + body, max_tokens=2048)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return rule_meta
        data = json.loads(match.group())
        llm_meta = {int(x) for x in data.get("meta", []) if isinstance(x, int)}
        return rule_meta | llm_meta
    except Exception:
        return rule_meta


# v17: llm_extract_state 폐기 (상태 레이어 제거). 모든 sentence 는 항상 active.


# 하위 호환을 위한 별칭
OllamaError = LLMError

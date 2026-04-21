"""Synapse 형태소 분석기 — Kiwi 래퍼 (v16).

서버(조직/API, Python)용 형태소 분석. 모바일·웹은 `lib/src/tokenizer.dart`
(kiwi-nlp WASM) 가 담당하되 토큰 경계·품사 태그·lemma 결과 스키마는 동일 유지.

품사 태그 (Kiwi) 정리:
- NNG: 일반명사, NNP: 고유명사, NP: 대명사 → 노드 후보 (명사)
- VV: 동사, VA: 형용사 → form 자체가 이미 lemma(원형) 로 나옴
- MAG: 일반부사 → 부정부사 '안'/'못' 만 노드 후보
- NNB/SN/NR: 의존명사·숫자 → 날짜·수량은 save.py 규칙이 분할 담당 (제외)
- SL: 외국어/영문 → Kiwi 가 글자 단위 분리할 수 있음. 여기서는 분리된 채로
  반환하고 LLM 병합 단계(engine/llm.py `llm_extract_merge`) 가 원문 원형 복원.

싱글턴 + 지연 초기화 — Kiwi 인스턴스 초기화가 ~300ms, ~50MB 상주. 프로세스당
한 번만 로드한다. import 시점에 로딩하지 않음.
"""

from __future__ import annotations
from typing import Optional

from kiwipiepy import Kiwi

NOUN_TAGS = frozenset({"NNG", "NNP", "NP"})
PREDICATE_TAGS = frozenset({"VV", "VA"})
NEGATION_WORDS = frozenset({"안", "못"})

_kiwi: Optional[Kiwi] = None


def _get_kiwi() -> Kiwi:
    global _kiwi
    if _kiwi is None:
        _kiwi = Kiwi()
    return _kiwi


def tokenize(text: str):
    """원시 Kiwi 결과 반환 (Token 리스트). 테스트·디버깅용."""
    return _get_kiwi().tokenize(text)


def extract_nouns(text: str) -> list[str]:
    """NNG/NNP/NP 명사 form 을 등장 순서대로, 중복 제거해 반환.

    SN/NNB(숫자·의존명사) 는 제외 — '2026년 4월 10일' 같은 날짜 통짜 노드를
    만들지 않기 위해서다. 날짜는 save._expand_date_tokens 규칙이 '2026년',
    '4월', '10일' 단위로 분할한다.
    """
    out: list[str] = []
    seen: set[str] = set()
    for t in _get_kiwi().tokenize(text):
        if t.tag in NOUN_TAGS and t.form not in seen:
            seen.add(t.form)
            out.append(t.form)
    return out


def extract_lemmas(text: str) -> list[str]:
    """VV/VA 용언 lemma(원형) 를 등장 순서대로, 중복 제거해 반환.

    kiwipiepy 는 용언 토큰의 `form` 필드에 이미 원형(어간) 을 담아 돌려준다
    (예: '아파서' → form='아프', tag='VA'). 별도 활용 복원 불필요.
    """
    out: list[str] = []
    seen: set[str] = set()
    for t in _get_kiwi().tokenize(text):
        if t.tag in PREDICATE_TAGS and t.form not in seen:
            seen.add(t.form)
            out.append(t.form)
    return out


def extract_negations(text: str) -> list[str]:
    """MAG 태그 중 '안'/'못' 만 부정부사 노드 후보로 반환.

    v15 까지 공백 기준 정규식으로 감지하던 것을 품사 태그 기반으로 전환.
    정규식은 '안녕'·'못쓸' 같은 2음절 이상 단어와 구별할 수 없었다.
    """
    out: list[str] = []
    seen: set[str] = set()
    for t in _get_kiwi().tokenize(text):
        if t.tag == "MAG" and t.form in NEGATION_WORDS and t.form not in seen:
            seen.add(t.form)
            out.append(t.form)
    return out


def extract_for_save(text: str) -> dict:
    """저장 파이프라인 한 번에 필요한 3종을 한 번의 tokenize 호출로 반환.

    반환: {"nouns": [...], "lemmas": [...], "negations": [...]}
    save.py 2-step 파이프라인의 ② Kiwi 단계 + Kiwi MAG 부정부사 감지가 모두
    이 결과에서 나온다. 같은 문장을 세 번 토큰화하지 않도록 한 번에 묶는다.
    """
    nouns: list[str] = []
    lemmas: list[str] = []
    negations: list[str] = []
    seen_n: set[str] = set()
    seen_l: set[str] = set()
    seen_g: set[str] = set()
    for t in _get_kiwi().tokenize(text):
        if t.tag in NOUN_TAGS:
            if t.form not in seen_n:
                seen_n.add(t.form)
                nouns.append(t.form)
        elif t.tag in PREDICATE_TAGS:
            if t.form not in seen_l:
                seen_l.add(t.form)
                lemmas.append(t.form)
        elif t.tag == "MAG" and t.form in NEGATION_WORDS:
            if t.form not in seen_g:
                seen_g.add(t.form)
                negations.append(t.form)
    return {"nouns": nouns, "lemmas": lemmas, "negations": negations}


def extract_for_retrieve(text: str) -> list[str]:
    """인출 파이프라인용 — 질문의 명사·용언 lemma 를 하나의 순서 리스트로.

    retrieve.py 시작 노드 매칭이 retrieve-expand 어댑터 결과와 합쳐 쓴다.
    조사·어미가 붙은 표현도 형태소 단위로 매칭 가능 (예: "커피가 맛있었나?"
    → ['커피', '맛있'])
    """
    out: list[str] = []
    seen: set[str] = set()
    for t in _get_kiwi().tokenize(text):
        if t.tag in NOUN_TAGS or t.tag in PREDICATE_TAGS:
            if t.form not in seen:
                seen.add(t.form)
                out.append(t.form)
    return out


def lemmatize_word(word: str) -> str:
    """단일 단어를 lemma 로 정규화. 용언이면 원형, 그 외엔 자기 자신.

    suspected_typos(L3) 가 '배고파/배고프' 같은 활용형 쌍을 자동 제외할 때
    각 노드 이름을 같은 lemma 로 정규화해 비교하는 용도.
    """
    tokens = _get_kiwi().tokenize(word)
    for t in tokens:
        if t.tag in PREDICATE_TAGS:
            return t.form
    return word


if __name__ == "__main__":
    samples = [
        "2026년 4월 10일 허리 아파서 병원 다녀왔어",
        "React Native 앱 만들고 있어",
        "MZ세대는 ASMR 좋아해",
        "안 먹었어 못 갔어",
        "할머니 영월군 동네 장군",
        "허리디스크 공황장애 50살 30만원",
        "커피가 맛있었나?",
    ]
    for s in samples:
        r = extract_for_save(s)
        print(f">> {s}")
        print(f"   nouns   : {r['nouns']}")
        print(f"   lemmas  : {r['lemmas']}")
        print(f"   negations: {r['negations']}")

"""한글 자모 분해 + Levenshtein 거리 유틸리티.

순수 파이썬, 외부 의존성 없음. 유니코드 수학으로 자모 분해.
"""

_HANGUL_BASE = 0xAC00
_HANGUL_END = 0xD7A3
_JUNG_COUNT = 21
_JONG_COUNT = 28

_CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
_JONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")


def decompose(text: str) -> str:
    """문자열을 자모 단위로 분해. 비한글은 그대로 유지."""
    result: list[str] = []
    for ch in text:
        cp = ord(ch)
        if _HANGUL_BASE <= cp <= _HANGUL_END:
            offset = cp - _HANGUL_BASE
            cho = offset // (_JUNG_COUNT * _JONG_COUNT)
            jung = (offset % (_JUNG_COUNT * _JONG_COUNT)) // _JONG_COUNT
            jong = offset % _JONG_COUNT
            result.append(_CHO[cho])
            result.append(_JUNG[jung])
            if jong > 0:
                result.append(_JONG[jong])
        else:
            result.append(ch)
    return "".join(result)


def levenshtein(s1: str, s2: str) -> int:
    """두 문자열의 Levenshtein 편집거리."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def jamo_distance(a: str, b: str) -> int:
    """두 문자열을 자모 분해 후 Levenshtein 거리 반환."""
    return levenshtein(decompose(a), decompose(b))


def is_typo_candidate(a: str, b: str, max_dist: int = 1, min_jamo_len: int = 6) -> bool:
    """자모 거리 기반 오타 후보 판정.

    조건: 양쪽 자모길이 >= min_jamo_len, 거리 <= max_dist, a != b.
    """
    if a == b:
        return False
    ja, jb = decompose(a), decompose(b)
    if len(ja) < min_jamo_len or len(jb) < min_jamo_len:
        return False
    if abs(len(ja) - len(jb)) > max_dist:
        return False
    return levenshtein(ja, jb) <= max_dist

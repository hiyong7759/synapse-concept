"""Task 6 파인튜닝 데이터 생성 v2.

변경사항:
  - "나" 노드 규칙 확정 (1인칭이 문장에 명시된 경우만 추출, 없으면 미생성 + 엣지 미사용)
  - deactivate 필드 추가 (상태변경 감지 통합)
  - input에 "알려진 사실:" 원본 문장 컨텍스트 포함 (deactivate 학습용)
  - 카테고리 그룹별 순차 생성 (그룹당 1회 Opus 호출)
  - v2.1: current_graph(트리플) → context_sentences(원본 문장) 포맷 변경

실행:
  python3 scripts/gen_task6_v2.py [--per-group 350]
  python3 scripts/gen_task6_v2.py --group a   # 그룹 하나만

출력:
  archive/finetune/data/task6_v2_a.jsonl  (PER, BOD, MND)
  archive/finetune/data/task6_v2_b.jsonl  (WRK, MON, TEC, EDU)
  archive/finetune/data/task6_v2_c.jsonl  (FOD, LIV, HOB, TRV, CUL)
  archive/finetune/data/task6_v2_d.jsonl  (LAW, NAT, SOC, REL, REG)
  archive/finetune/data/task6_v2_e.jsonl  (doc_mode — 조직 문서)
"""

import argparse
import json
import pathlib
import re
import subprocess

BASE = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE / "archive/finetune/data"

# ──────────────────────────────────────────────
# 시스템 프롬프트 (v2.1 — 문장 컨텍스트)
# ──────────────────────────────────────────────
SYSTEM = """\
한국어 문장에서 지식 그래프의 노드, 엣지, 카테고리, 상태변경, 보관 유형을 추출하라.
JSON만 출력. 다른 텍스트 금지.

출력 형식:
{"retention":"memory|daily","nodes":[{"name":"노드명","category":"대분류.소분류"}],"edges":[{"source":"노드명","label":"조사","target":"노드명"}],"deactivate":[{"source":"노드명","target":"노드명"}]}

규칙:
- 노드는 원자. 하나의 개념 = 하나의 노드.
- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출. 문장에 없는 1인칭을 추가하는 것은 금지.
- 3인칭 주어는 원문 그대로 노드 추출.
- 엣지 label = 원문의 조사 그대로 (에서, 으로, 의, 에, 를/을, 와/과, 고, 이/가 등). 조사 없으면 null.
- 부정부사(안, 못)는 독립 노드다. 예: "스타벅스 안 좋아" → 스타벅스→안→좋아 (3노드, 2엣지 null).
- 엣지의 source와 target은 반드시 nodes 배열에 있는 노드명과 정확히 일치해야 한다.
- "알려진 사실:"이 제공된 경우: 과거 문장들에서 저장된 노드/엣지를 파악하고, 현재 입력과 상충되는 것을 deactivate에 포함. 없으면 [].
- retention: 잘 변하지 않는 사실/상태/이력(직업·거주지·관계·질병 이력·기술 등) → "memory". 순간적 활동/감정/일상(오늘 뭐 먹었어·기분 등) → "daily".
- 추출할 노드/엣지가 없는 대화(인사·맞장구 등) → {"retention":"daily","nodes":[],"edges":[],"deactivate":[]}

카테고리 대분류(17개): PER BOD MND FOD LIV MON WRK TEC EDU LAW TRV NAT CUL HOB SOC REL REG

예시:
입력:
나는 조용희야
알려진 사실: 없음
출력: {"retention":"memory","nodes":[{"name":"나","category":"PER.individual"},{"name":"조용희","category":"PER.individual"}],"edges":[{"source":"나","label":null,"target":"조용희"}],"deactivate":[]}

입력:
나 쿠팡에서 물류 기획 담당하고 있어
알려진 사실: 없음
출력: {"retention":"memory","nodes":[{"name":"나","category":"PER.individual"},{"name":"쿠팡","category":"WRK.workplace"},{"name":"물류 기획","category":"WRK.role"}],"edges":[{"source":"나","label":"에서","target":"쿠팡"},{"source":"나","label":null,"target":"물류 기획"}],"deactivate":[]}

입력:
강남세브란스 정형외과 다니고 있어
알려진 사실: 없음
출력: {"retention":"memory","nodes":[{"name":"강남세브란스","category":"BOD.medical"},{"name":"정형외과","category":"BOD.medical"}],"edges":[{"source":"강남세브란스","label":"의","target":"정형외과"}],"deactivate":[]}

입력:
허리 다 나았어
알려진 사실:
- 나는 허리디스크 L4-L5 진단받았어
- 허리 너무 아파서 병원 다니고 있어
출력: {"retention":"memory","nodes":[],"edges":[],"deactivate":[{"source":"허리디스크","target":"아프"},{"source":"허리디스크","target":"L4-L5"}]}

입력:
박지수가 개발팀장으로 승진했어
알려진 사실:
- 박지수가 팀원으로 들어왔어
- 박지수 마케팅팀 소속이야
출력: {"retention":"memory","nodes":[{"name":"박지수","category":"PER.colleague"},{"name":"개발팀장","category":"WRK.role"}],"edges":[{"source":"박지수","label":"으로","target":"개발팀장"}],"deactivate":[{"source":"박지수","target":"팀원"},{"source":"박지수","target":"마케팅팀"}]}

입력:
오늘 삼겹살 먹었어
알려진 사실: 없음
출력: {"retention":"daily","nodes":[{"name":"삼겹살","category":"FOD.ingredient"}],"edges":[],"deactivate":[]}

입력:
안녕 잘 지내?
알려진 사실: 없음
출력: {"retention":"daily","nodes":[],"edges":[],"deactivate":[]}\
"""

# ──────────────────────────────────────────────
# 그룹 정의
# ──────────────────────────────────────────────
GROUPS = {
    "a": {
        "name": "PER, BOD, MND",
        "categories": "PER(인물), BOD(신체/건강), MND(정신/감정)",
        "output": "task6_v2_a.jsonl",
        "deactivate_ratio": 0.25,
        "topics": [
            "가족, 친구, 직장동료, 지인 관계",
            "질병, 약, 병원, 수술, 검사",
            "건강 상태 변화 (나았어, 재발했어) — 과거 문장 2~5개 포함",
            "스트레스, 번아웃, 우울, 감정 상태",
            "심리 상담, 명상, 수면 문제",
        ],
    },
    "b": {
        "name": "WRK, MON, TEC, EDU",
        "categories": "WRK(직업/업무), MON(금융/소비), TEC(기술/기기), EDU(교육/학습)",
        "output": "task6_v2_b.jsonl",
        "deactivate_ratio": 0.25,
        "topics": [
            "직장, 직무, 이직, 승진, 퇴사, 팀",
            "월급, 지출, 저축, 투자, 대출",
            "스마트폰, 노트북, 앱, 개발 환경",
            "학교, 자격증, 강의, 공부",
            "직장 상태 변화 (이직했어, 퇴사했어, 승진했어) — 과거 문장 2~5개 포함",
        ],
    },
    "c": {
        "name": "FOD, LIV, HOB, TRV, CUL",
        "categories": "FOD(음식), LIV(생활/주거), HOB(취미/운동), TRV(여행), CUL(문화/예술)",
        "output": "task6_v2_c.jsonl",
        "deactivate_ratio": 0.20,
        "topics": [
            "좋아하는 음식, 맛집, 식습관",
            "이사, 집, 동네, 인테리어",
            "운동, 독서, 게임, 반려동물",
            "여행지, 숙소, 항공편",
            "영화, 음악, 전시, 책",
            "취향 변화 (요즘 좋아/싫어졌어) — 과거 문장 2~5개 포함",
        ],
    },
    "d": {
        "name": "LAW, NAT, SOC, REL, REG",
        "categories": "LAW(법률/규정), NAT(자연/환경), SOC(사회/시사), REL(관계/소통), REG(종교/신앙)",
        "output": "task6_v2_d.jsonl",
        "deactivate_ratio": 0.35,
        "topics": [
            "계약, 법적 문제, 소송, 규정",
            "날씨, 계절, 환경, 자연재해, 동식물",
            "뉴스, 사회 이슈, 정치, 커뮤니티",
            "연인, 이별, 결혼, 이혼, 갈등 — 과거 문장 2~5개 포함",
            "종교, 신앙, 예배, 기도, 절, 성당, 교회",
            "관계 상태 변화 (헤어졌어, 탈퇴했어) — 과거 문장 2~5개 포함",
            "저장 불필요한 일상 대화 (빈 결과)",
            "복합 문장 (두 가지 이상 주제)",
        ],
    },
    "e": {
        "name": "doc_mode (조직 문서)",
        "categories": "LAW(법령/규정), WRK(업무규정), MON(급여/복리후생)",
        "output": "task6_v2_e.jsonl",
        "doc_mode": True,
    },
}


# ──────────────────────────────────────────────
# 생성 프롬프트
# ──────────────────────────────────────────────
def build_gen_prompt_docmode(n: int) -> str:
    """doc_mode 전용 생성 프롬프트 — 조직 문서(조항) 추출."""
    deactivate_n = max(2, int(n * 0.10))
    normal_n = n - deactivate_n

    return f"""\
Synapse 조직 그래프 파인튜닝 데이터를 생성하라. 대상: 취업규칙·계약서·사내규정 등 조직 문서(doc_mode).

아래 형식으로 정확히 {n}개 예시를 JSON 배열로 출력하라. 다른 텍스트 금지.

[
  {{
    "sentence": "문서 조항 텍스트 (제N조, ①②, N호 패턴 포함)",
    "context_sentences": ["이전에 저장된 관련 조항 문장1", "관련 조항 문장2"],
    "answer": {{
      "retention": "memory",
      "nodes": [{{"name":"노드명","category":"대분류.소분류"}}],
      "edges": [{{"source":"노드명","label":"조사or항목기호or null","target":"노드명"}}],
      "deactivate": [{{"source":"노드명","target":"노드명"}}]
    }}
  }}
]

생성 비율:
- 신규 조항 추출 (context_sentences=[]): {normal_n}개
- 조항 개정 (deactivate 있음 — 기존 조항 문장이 context_sentences에 포함, 새 내용으로 대체): {deactivate_n}개

doc_mode 추출 규칙:
- 앵커 노드: 제N조, 제N조①, 제N조② 형태로 계층 분리
- 계층 엣지: 제N조 →(항)→ 제N조①, 제N조 →(호)→ 제N조제1호
- 내용 노드: 조항의 핵심 개념 (유급휴가, 근무시간, 15일 등)
- 엣지 label: 계층 기호(항/호/조)이거나 원문 조사(의/에/으로 등). 없으면 null.
- 1인칭 없음 (문서 내용이므로). 주어는 직원/회사/조항 등 명시됨.
- deactivate: 개정 시 context_sentences의 기존 조항에서 파악한 노드→노드 엣지를 비활성화.
- 엣지의 source와 target은 반드시 nodes 배열에 있는 노드명과 정확히 일치해야 한다. nodes에 없는 노드를 엣지에 사용하는 것은 절대 금지.

예시:
sentence: "제3조(유급휴가) ① 직원은 연간 15일의 유급휴가를 받는다. ② 출근율 80% 이상인 경우에 한한다."
context_sentences: []
answer: {{
  "retention": "memory",
  "nodes": [
    {{"name":"제3조","category":"LAW.statute"}},
    {{"name":"제3조①","category":"LAW.statute"}},
    {{"name":"제3조②","category":"LAW.statute"}},
    {{"name":"유급휴가","category":"LAW.rights"}},
    {{"name":"15일","category":"LAW.contract"}},
    {{"name":"출근율","category":"WRK.workplace"}},
    {{"name":"80%","category":"LAW.statute"}}
  ],
  "edges": [
    {{"source":"제3조","label":"항","target":"제3조①"}},
    {{"source":"제3조","label":"항","target":"제3조②"}},
    {{"source":"제3조①","label":"의","target":"유급휴가"}},
    {{"source":"유급휴가","label":null,"target":"15일"}},
    {{"source":"제3조②","label":"의","target":"출근율"}},
    {{"source":"출근율","label":null,"target":"80%"}}
  ],
  "deactivate": []
}}

다양한 조직 문서 주제: 취업규칙(근무/휴가/징계/급여), 계약서(기간/보수/해지), 사내규정(출장/복리/인사)
문장은 실제 한국 기업 문서 스타일로. 조항 번호는 다양하게.

카테고리 소분류 (공식 목록에서만 선택):
LAW: statute, contract, admin, rights, tax
WRK: workplace, role, jobchange, business, cert, tool
MON: income, spending, invest, payment, loan, insurance
PER: individual, family, friend, colleague, public, org
"""


def build_gen_prompt(group: dict, n: int) -> str:
    deactivate_n = int(n * group["deactivate_ratio"])
    empty_n = max(3, int(n * 0.08))
    normal_n = n - deactivate_n - empty_n

    topics_str = "\n".join(f"  - {t}" for t in group["topics"])

    return f"""\
Synapse 지식 그래프 파인튜닝 데이터를 생성하라.
대상 카테고리: {group['categories']}
주제 가이드:
{topics_str}

아래 형식으로 정확히 {n}개 예시를 JSON 배열로 출력하라. 다른 텍스트 금지.

[
  {{
    "sentence": "한국어 문장",
    "context_sentences": ["과거에 저장된 관련 문장1", "관련 문장2"],
    "answer": {{
      "retention": "memory|daily",
      "nodes": [{{"name":"노드명","category":"대분류.소분류"}}],
      "edges": [{{"source":"노드명","label":"조사or null","target":"노드명"}}],
      "deactivate": [{{"source":"노드명","target":"노드명"}}]
    }}
  }}
]

생성 비율:
- 일반 추출 (context_sentences=[], retention="memory"): {normal_n}개
- 상태변경 포함 (deactivate 있음, context_sentences에 과거 문장 2~5개 포함): {deactivate_n}개
  → 상태변경은 복합적으로: 한 문장이 여러 과거 사실을 동시에 바꾸는 경우 포함 (deactivate 2개 이상)
  → context_sentences는 실제 대화처럼 자연스러운 과거 문장으로. 트리플이 아닌 완전한 문장.
- 그래프 추출 없음 또는 daily (인사·일상 활동·순간 감정): {empty_n}개

핵심 규칙:
- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출. 문장에 없는 1인칭을 추가하는 것은 금지.
- 엣지 label = 원문 조사 그대로 (에서/으로/의/에/를/과/고 등). 조사 없으면 null.
- 부정부사(안, 못)는 독립 노드: "스타벅스 안 좋아" → 스타벅스→안→좋아.
- 엣지의 source와 target은 반드시 nodes 배열에 있는 노드명과 정확히 일치해야 한다.
- 상태변경: context_sentences의 과거 문장에서 파악되는 노드/엣지 중 현재 입력과 상충되는 것을 deactivate에 명시.
- retention: 잘 변하지 않는 사실/이력 → "memory". 순간 활동/감정/일상 → "daily".
- 문장은 구어체 한국어로. 실제 대화처럼 자연스럽게.
- 중복 문장 없이 다양하게 생성.

복합 상태변경 예시:
sentence: "나 삼성 그만두고 네이버로 이직했어"
context_sentences: ["나 삼성에서 백엔드 개발자로 일하고 있어", "나 삼성 3년째야", "연봉은 6000이야"]
answer: {{
  "retention": "memory",
  "nodes": [{{"name":"나","category":"PER.individual"}},{{"name":"네이버","category":"WRK.workplace"}}],
  "edges": [{{"source":"나","label":"으로","target":"네이버"}}],
  "deactivate": [{{"source":"나","target":"삼성"}},{{"source":"나","target":"백엔드 개발자"}}]
}}

카테고리 소분류 (공식 목록에서 선택):
PER: individual, family, friend, colleague, public, org
BOD: part, disease, medical, exercise, nutrition, sleep
MND: emotion, personality, mental, motivation, coping
FOD: ingredient, recipe, restaurant, drink, product
LIV: housing, appliance, interior, supply, maintenance, moving
MON: income, spending, invest, payment, loan, insurance
WRK: workplace, role, jobchange, business, cert, tool
TEC: sw, hw, ai, infra, data, security
EDU: school, online, language, academic, reading, exam
LAW: statute, contract, admin, rights, tax
TRV: domestic, abroad, transport, stay, flight, place
NAT: animal, plant, weather, terrain, ecology, space
CUL: film, music, book, art, show, media
HOB: sport, outdoor, game, craft, sing, collect, social
SOC: politics, international, incident, economy, issue, news
REL: romance, conflict, comm, manner, online
REG: christianity, buddhism, catholic, islam, other, practice
"""


# ──────────────────────────────────────────────
# Claude CLI 호출
# ──────────────────────────────────────────────
def call_claude(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "-p", "--model", "opus", prompt],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        print(f"  [CLI 오류] returncode={result.returncode}")
        if result.stderr:
            print(f"  stderr: {result.stderr[:200]}")
        return ""
    return result.stdout.strip()


# ──────────────────────────────────────────────
# 응답 파싱
# ──────────────────────────────────────────────
def parse_examples(raw: str) -> list[dict]:
    """응답에서 JSON 배열 추출 및 파싱. 잘린 배열도 부분 복구."""
    raw = re.sub(r"```(?:json)?\s*", "", raw)
    raw = re.sub(r"```", "", raw)

    start = raw.find("[")
    if start == -1:
        return []
    raw = raw[start:]

    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict) and "sentence" in x and "answer" in x]
    except json.JSONDecodeError:
        pass

    # 잘린 배열 부분 복구
    last_close = raw.rfind("},")
    if last_close == -1:
        last_close = raw.rfind("}")
    if last_close != -1:
        candidate = raw[:last_close + 1] + "]"
        try:
            data = json.loads(candidate)
            if isinstance(data, list):
                items = [x for x in data if isinstance(x, dict) and "sentence" in x and "answer" in x]
                if items:
                    print(f"  (잘린 배열 복구: {len(items)}건)", file=__import__("sys").stderr)
                    return items
        except json.JSONDecodeError:
            pass

    print(f"  JSON 파싱 실패. 앞 400자: {raw[:400]}", file=__import__("sys").stderr)
    return []


def make_user_content(sentence: str, context_sentences: list[str]) -> str:
    if not context_sentences:
        return f"{sentence}\n알려진 사실: 없음"
    lines = "\n".join(f"- {s}" for s in context_sentences)
    return f"{sentence}\n알려진 사실:\n{lines}"


def to_jsonl_record(example: dict) -> str | None:
    try:
        sentence = example["sentence"].strip()
        context_sentences = example.get("context_sentences", [])
        if isinstance(context_sentences, list):
            context_sentences = [s for s in context_sentences if isinstance(s, str) and s.strip()]
        else:
            context_sentences = []
        answer = example["answer"]

        # 필수 필드 확인
        if "nodes" not in answer or "edges" not in answer:
            return None
        if "deactivate" not in answer:
            answer["deactivate"] = []
        if "retention" not in answer:
            answer["retention"] = "memory"

        user_content = make_user_content(sentence, context_sentences)
        answer_str = json.dumps(answer, ensure_ascii=False)

        record = {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": answer_str},
            ]
        }
        return json.dumps(record, ensure_ascii=False)
    except Exception:
        return None


# ──────────────────────────────────────────────
# 그룹 생성
# ──────────────────────────────────────────────
BATCH_SIZE = 25  # 호출당 생성 목표 건수


def generate_group(group_key: str, group: dict, per_group: int, dry_run: bool = False) -> int:
    """그룹 전체를 BATCH_SIZE 단위로 순차 호출해 per_group건 생성."""
    out_file = DATA_DIR / group["output"]

    # 중단 시 재개: 기존 문장 로드
    done_sentences: set[str] = set()
    if out_file.exists():
        for line in out_file.read_text().splitlines():
            try:
                rec = json.loads(line)
                sentence = rec["messages"][1]["content"].split("\n")[0]
                done_sentences.add(sentence)
            except Exception:
                pass

    generated = len(done_sentences)
    if generated >= per_group:
        print(f"[{group_key.upper()}] 이미 완료 ({generated}건)")
        return generated

    remaining = per_group - generated
    batches = (remaining + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"[{group_key.upper()}] 시작: {generated}/{per_group}건 완료 — {batches}회 호출 예정")

    if dry_run:
        print(f"  [DRY RUN] {batches}회 × ~{BATCH_SIZE}건")
        return generated

    MAX_RETRIES = 3
    with open(out_file, "a", encoding="utf-8") as fp:
        retry = 0
        while generated < per_group:
            remaining = per_group - generated
            batch_n = min(BATCH_SIZE, remaining)

            if group.get("doc_mode"):
                prompt = build_gen_prompt_docmode(batch_n)
            else:
                prompt = build_gen_prompt(group, batch_n)

            print(f"  [{group_key.upper()}] {generated}/{per_group}건 — {batch_n}건 요청 중...")
            raw = call_claude(prompt)
            examples = parse_examples(raw)

            if not examples:
                retry += 1
                print(f"  [{group_key.upper()}] 파싱 실패 — 재시도 {retry}/{MAX_RETRIES}")
                if retry >= MAX_RETRIES:
                    print(f"  [{group_key.upper()}] 최대 재시도 초과, 중단")
                    break
                continue
            retry = 0

            new_count = 0
            for ex in examples:
                sentence = ex.get("sentence", "").strip()
                if not sentence or sentence in done_sentences:
                    continue
                record = to_jsonl_record(ex)
                if record:
                    fp.write(record + "\n")
                    fp.flush()
                    done_sentences.add(sentence)
                    generated += 1
                    new_count += 1

            print(f"  [{group_key.upper()}] +{new_count}건 저장 (누계 {generated}/{per_group}건)")

    print(f"[{group_key.upper()}] 완료: {generated}건 → {out_file.name}")
    return generated


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Task 6 v2 파인튜닝 데이터 생성")
    parser.add_argument("--per-group", type=int, default=350, help="그룹당 목표 건수")
    parser.add_argument("--group", choices=list(GROUPS.keys()), help="특정 그룹만 실행")
    parser.add_argument("--dry-run", action="store_true", help="호출 없이 계획만 출력")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 실행할 그룹
    groups_to_run = {args.group: GROUPS[args.group]} if args.group else GROUPS

    print(f"목표: 그룹당 {args.per_group}건 / batch={BATCH_SIZE} / dry_run={args.dry_run}")
    print()

    total = 0
    for k, g in groups_to_run.items():
        try:
            total += generate_group(k, g, args.per_group, args.dry_run)
        except Exception as e:
            print(f"[{k.upper()}] 오류: {e}")

    print(f"\n전체 완료: {total}건")
    print("파일:")
    for g in groups_to_run.values():
        f = DATA_DIR / g["output"]
        if f.exists():
            lines = len(f.read_text().splitlines())
            print(f"  {f.name}: {lines}건")


if __name__ == "__main__":
    main()

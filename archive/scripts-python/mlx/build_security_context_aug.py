#!/usr/bin/env python3
"""security-context 수동 증강 데이터 빌더.

기존: 365건 (confirm 57% / safe 43%)
증강 목표: 공식 5 카테고리 균형 보강 + "컨텍스트엔 민감 있지만 답변 무관" safe 케이스 보강

50건 작성:
  confirm (28):
    health_detail        × 5
    financial            × 5
    location_precise     × 5
    relationship_private × 5
    schedule_combined    × 5
    복합 카테고리        × 3
  safe (22):
    전부 safe 트리플     × 10
    민감 있지만 답변 무관 × 8
    boundary (safe 판정) × 4

5A 카테고리: health_detail | financial | location_precise |
              relationship_private | schedule_combined

사용:
  python scripts/mlx/build_security_context_aug.py build
  python scripts/mlx/build_security_context_aug.py stats
  python scripts/mlx/build_security_context_aug.py merge
"""
import argparse
import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
TASK_DIR = ROOT / "data/finetune/tasks/security-context"
AUG_DIR = ROOT / "data/finetune/aug/security-context"
AUG_FILE = AUG_DIR / "aug_manual.jsonl"

SYSTEM = "당신은 지식 그래프 보안 엔진입니다. 질문과 인출된 전체 트리플 컨텍스트(각 트리플의 5A 마킹 포함)를 보고, 답변에 민감정보가 포함되는지 종합 판단하세요. 출력 형식: {\"result\": \"safe\"} 또는 {\"result\": \"confirm\", \"message\": \"사용자에게 보여줄 확인 메시지\"}"


# (질문, [(마킹, 트리플), ...], 결과, 메시지 or None)
SAMPLES: list[tuple[str, list[tuple[str, str]], str, str | None]] = [
    # ========== health_detail × confirm (5) ==========
    ("최근 병원 진료 내역 보여줘",
     [("safe", "병원 —[방문]→ 2026-04-02"),
      ("sensitive:health_detail", "진료 —[과]→ 신경외과"),
      ("sensitive:health_detail", "진단 —[병명]→ 경추 추간판탈출"),
      ("sensitive:health_detail", "처방 —[약물]→ 트라마돌")],
     "confirm", "진단명(경추 추간판탈출)과 처방약(트라마돌) 정보가 포함됩니다. 답변에 포함할까요?"),
    ("체지방률이 어떻게 변했지?",
     [("sensitive:health_detail", "인바디 —[체지방률]→ 2025-11 24.3%"),
      ("sensitive:health_detail", "인바디 —[체지방률]→ 2026-04 20.1%"),
      ("safe", "인바디 —[측정]→ 헬스장")],
     "confirm", "체성분 측정값은 건강 상세정보입니다. 답변에 포함할까요?"),
    ("요즘 건강검진 결과 알려줘",
     [("sensitive:health_detail", "건강검진 —[혈압]→ 145/92"),
      ("sensitive:health_detail", "건강검진 —[공복혈당]→ 118"),
      ("sensitive:health_detail", "건강검진 —[LDL]→ 162"),
      ("safe", "건강검진 —[기관]→ 강남세브란스")],
     "confirm", "혈압·혈당·콜레스테롤 수치 등 건강검진 상세 수치가 포함됩니다. 답변에 포함할까요?"),
    ("먹던 영양제 뭐뭐였지?",
     [("sensitive:health_detail", "영양제 —[복용]→ 오메가3"),
      ("sensitive:health_detail", "영양제 —[복용]→ 비타민D"),
      ("sensitive:health_detail", "영양제 —[목적]→ 심혈관 예방"),
      ("safe", "영양제 —[구매처]→ 쿠팡")],
     "confirm", "복용 영양제와 복용 목적은 건강 관련 민감정보입니다. 답변에 포함할까요?"),
    ("최근 상담 기록 어땠어?",
     [("sensitive:health_detail", "상담 —[횟수]→ 월 2회"),
      ("sensitive:health_detail", "상담 —[주제]→ 불안 관리"),
      ("sensitive:health_detail", "상담 —[상담사]→ 김서현 선생"),
      ("safe", "상담 —[센터]→ 마음숲")],
     "confirm", "정신건강 상담 주제와 상담사 정보는 매우 민감한 건강정보입니다. 답변에 포함할까요?"),

    # ========== financial × confirm (5) ==========
    ("월 지출 어떻게 돼?",
     [("sensitive:financial", "지출 —[월평균]→ 420만원"),
      ("sensitive:financial", "지출 —[카드결제]→ 280만원"),
      ("sensitive:financial", "지출 —[고정비]→ 140만원"),
      ("safe", "지출 —[관리]→ 가계부앱")],
     "confirm", "월 지출 총액과 카드·고정비 상세 내역이 포함됩니다. 답변에 포함할까요?"),
    ("주식 수익률 어때?",
     [("sensitive:financial", "주식계좌 —[총자산]→ 8200만원"),
      ("sensitive:financial", "주식계좌 —[수익률]→ +12.4%"),
      ("sensitive:financial", "주식계좌 —[주요종목]→ 엔비디아"),
      ("safe", "주식계좌 —[증권사]→ 미래에셋")],
     "confirm", "자산 규모와 수익률 상세는 민감 금융정보입니다. 답변에 포함할까요?"),
    ("대출 상환 얼마나 남았어?",
     [("sensitive:financial", "주담대 —[잔액]→ 2.8억"),
      ("sensitive:financial", "주담대 —[월상환]→ 185만원"),
      ("sensitive:financial", "주담대 —[금리]→ 4.2%"),
      ("safe", "주담대 —[은행]→ 국민은행")],
     "confirm", "대출 잔액·월상환·금리 등 금융 상세 정보가 포함됩니다. 답변에 포함할까요?"),
    ("이번 달 얼마 벌었어?",
     [("sensitive:financial", "월급 —[입금]→ 620만원"),
      ("sensitive:financial", "부업 —[수입]→ 140만원"),
      ("sensitive:financial", "소득 —[월합계]→ 760만원")],
     "confirm", "월급·부업 수입 등 소득 상세 정보입니다. 답변에 포함할까요?"),
    ("세금 환급 얼마 받았어?",
     [("sensitive:financial", "연말정산 —[환급]→ 286만원"),
      ("sensitive:financial", "연말정산 —[공제]→ 의료비 420만"),
      ("safe", "연말정산 —[처리]→ 홈택스")],
     "confirm", "환급액과 의료비 공제액(건강 간접 정보)이 포함됩니다. 답변에 포함할까요?"),

    # ========== location_precise × confirm (5) ==========
    ("주로 어디서 운동해?",
     [("sensitive:location_precise", "헬스장 —[주소]→ 서울 강남구 테헤란로 152 8층"),
      ("safe", "헬스장 —[이름]→ 피트니스킹"),
      ("sensitive:location_precise", "운동 —[요일]→ 매주 화/목")],
     "confirm", "운동 장소 정확 주소와 방문 패턴은 위치·일정 민감정보입니다. 답변에 포함할까요?"),
    ("단골 카페 어디야?",
     [("sensitive:location_precise", "블루보틀 —[매장]→ 성수동 대림창고점"),
      ("sensitive:location_precise", "블루보틀 —[방문]→ 매주 토 오전"),
      ("safe", "블루보틀 —[메뉴]→ 니트로콜드브루")],
     "confirm", "특정 매장과 방문 요일·시간대 패턴이 포함됩니다. 답변에 포함할까요?"),
    ("자주 가는 병원 위치 알려줘",
     [("sensitive:location_precise", "분당서울대병원 —[주소]→ 경기 성남 분당구 구미로 173번길 82"),
      ("sensitive:health_detail", "분당서울대병원 —[진료과]→ 신경외과"),
      ("safe", "분당서울대병원 —[교통]→ 지하철")],
     "confirm", "병원 정확 위치와 진료과 정보가 함께 포함됩니다. 답변에 포함할까요?"),
    ("집 주소가 어떻게 되지?",
     [("sensitive:location_precise", "집 —[주소]→ 서울 마포구 연남로 67-3 301호"),
      ("sensitive:location_precise", "집 —[층수]→ 3층"),
      ("safe", "집 —[형태]→ 빌라")],
     "confirm", "거주지 상세 주소는 위치 민감정보입니다. 답변에 포함할까요?"),
    ("회사 위치 어디야?",
     [("sensitive:location_precise", "회사 —[주소]→ 서울 강남구 봉은사로 524 11층"),
      ("sensitive:schedule_combined", "회사 —[출근시간]→ 매일 9시"),
      ("safe", "회사 —[분야]→ 핀테크")],
     "confirm", "회사 정확 위치와 출근 시간대 조합은 스토킹 위험이 있는 민감정보입니다. 답변에 포함할까요?"),

    # ========== relationship_private × confirm (5) ==========
    ("배우자랑 사이는 어때?",
     [("sensitive:relationship_private", "배우자 —[관계]→ 갈등"),
      ("sensitive:relationship_private", "배우자 —[상담]→ 부부상담 검토"),
      ("safe", "배우자 —[직업]→ 회사원")],
     "confirm", "부부 관계 상세와 상담 검토 정보가 포함됩니다. 답변에 포함할까요?"),
    ("친구 민수랑 어떻게 지내?",
     [("sensitive:relationship_private", "민수 —[최근]→ 절교"),
      ("sensitive:relationship_private", "민수 —[사유]→ 돈 문제"),
      ("safe", "민수 —[고등학교]→ 동창")],
     "confirm", "친구와의 갈등 사유 상세 정보가 포함됩니다. 답변에 포함할까요?"),
    ("형이랑 연락해?",
     [("sensitive:relationship_private", "형 —[연락]→ 5년 단절"),
      ("sensitive:relationship_private", "형 —[사유]→ 유산 분쟁"),
      ("safe", "형 —[거주]→ 부산")],
     "confirm", "가족 내 갈등과 유산 분쟁 사유는 매우 민감한 관계정보입니다. 답변에 포함할까요?"),
    ("연애 어떻게 돼가?",
     [("sensitive:relationship_private", "연인 —[기간]→ 8개월"),
      ("sensitive:relationship_private", "연인 —[관계상태]→ 권태기"),
      ("safe", "연인 —[직업]→ 간호사")],
     "confirm", "연애 관계 상태 상세 정보가 포함됩니다. 답변에 포함할까요?"),
    ("직장 동료들과 어때?",
     [("sensitive:relationship_private", "팀장 —[갈등]→ 업무지시 충돌"),
      ("sensitive:relationship_private", "팀장 —[평가]→ 본인에게 부정적"),
      ("safe", "팀장 —[이름]→ 박이사")],
     "confirm", "상사와의 갈등·평가 세부는 민감한 관계정보입니다. 답변에 포함할까요?"),

    # ========== schedule_combined × confirm (5) ==========
    ("다음 주 일정 좀 정리해줘",
     [("sensitive:schedule_combined", "일정 —[월]→ 강남 세브란스 9시"),
      ("sensitive:schedule_combined", "일정 —[화]→ 자택 재택근무"),
      ("sensitive:schedule_combined", "일정 —[수]→ 김포공항 출국 6시"),
      ("safe", "일정 —[관리]→ 캘린더")],
     "confirm", "요일별 위치·시간대 상세 일정은 결합 민감정보입니다. 답변에 포함할까요?"),
    ("이번 주말 동선 정리해줘",
     [("sensitive:schedule_combined", "토요일 —[오전]→ 분당 헬스장"),
      ("sensitive:schedule_combined", "토요일 —[저녁]→ 성수동 식사"),
      ("sensitive:schedule_combined", "일요일 —[낮]→ 본가 방문"),
      ("safe", "주말 —[루틴]→ 일정함")],
     "confirm", "주말 시간대별 이동 패턴이 포함됩니다. 답변에 포함할까요?"),
    ("운동 언제 해?",
     [("sensitive:schedule_combined", "운동 —[화/목]→ 저녁 7시 강남 헬스장"),
      ("sensitive:schedule_combined", "운동 —[토]→ 오전 10시 한강 러닝"),
      ("safe", "운동 —[목표]→ 체력 개선")],
     "confirm", "운동 요일·시간·장소 조합은 결합 민감정보입니다. 답변에 포함할까요?"),
    ("이번 출장 일정 어떻게 돼?",
     [("sensitive:schedule_combined", "출장 —[출발]→ 2026-04-20 김포 7시"),
      ("sensitive:schedule_combined", "출장 —[호텔]→ 도쿄 신주쿠 힐튼 501호"),
      ("sensitive:schedule_combined", "출장 —[복귀]→ 2026-04-23 하네다 19시")],
     "confirm", "출장 일정·숙박지 상세는 결합 민감정보입니다. 답변에 포함할까요?"),
    ("매일 루틴 알려줘",
     [("sensitive:schedule_combined", "평일 —[기상]→ 6시 자택"),
      ("sensitive:schedule_combined", "평일 —[출근]→ 7시 지하철 9호선"),
      ("sensitive:schedule_combined", "평일 —[퇴근]→ 19시 강남역"),
      ("safe", "루틴 —[유지]→ 2년")],
     "confirm", "일상 시간대·이동 경로 상세는 개인 안전 관련 민감정보입니다. 답변에 포함할까요?"),

    # ========== 복합 카테고리 × confirm (3) ==========
    ("최근에 병원비 얼마 썼어?",
     [("sensitive:health_detail", "진료 —[병원]→ 강남세브란스 정형외과"),
      ("sensitive:financial", "진료 —[비용]→ 280만원"),
      ("sensitive:health_detail", "진료 —[병명]→ 요추 수술"),
      ("sensitive:financial", "보험 —[환급]→ 150만원")],
     "confirm", "병명·진료비·보험 환급 등 건강+금융 상세 정보가 결합되어 있습니다. 답변에 포함할까요?"),
    ("전 회사 왜 그만뒀지?",
     [("sensitive:relationship_private", "전 직장 —[퇴사사유]→ 팀장 갈등"),
      ("sensitive:financial", "전 직장 —[연봉]→ 7800만원"),
      ("sensitive:health_detail", "전 직장 —[스트레스]→ 번아웃 진단"),
      ("safe", "전 직장 —[이름]→ A사")],
     "confirm", "퇴사 사유·연봉·건강 상태 등 여러 민감 카테고리가 결합됩니다. 답변에 포함할까요?"),
    ("이번 주말 약속 알려줘",
     [("sensitive:schedule_combined", "약속 —[토요일]→ 청담동 19시"),
      ("sensitive:relationship_private", "약속 —[상대]→ 전 연인 재회"),
      ("sensitive:financial", "약속 —[예산]→ 식사 30만원")],
     "confirm", "일정·관계·금전 정보가 결합된 민감 조합입니다. 답변에 포함할까요?"),

    # ========== safe — 전부 safe 트리플 (10) ==========
    ("지금 읽고 있는 책 뭐지?",
     [("safe", "책 —[읽는중]→ 클린 아키텍처"),
      ("safe", "책 —[저자]→ Robert Martin"),
      ("safe", "책 —[분야]→ 소프트웨어"),
      ("safe", "책 —[진도]→ 3장")],
     "safe", None),
    ("쓰는 에디터가 뭐야?",
     [("safe", "에디터 —[사용]→ VSCode"),
      ("safe", "에디터 —[테마]→ Monokai"),
      ("safe", "에디터 —[확장]→ Vim 모드")],
     "safe", None),
    ("좋아하는 음식 뭐 있어?",
     [("safe", "음식 —[좋아함]→ 평양냉면"),
      ("safe", "음식 —[좋아함]→ 파스타"),
      ("safe", "음식 —[알레르기]→ 없음")],
     "safe", None),
    ("지금 하는 프로젝트가 뭐지?",
     [("safe", "프로젝트 —[진행]→ synapse"),
      ("safe", "synapse —[언어]→ Python"),
      ("safe", "synapse —[상태]→ 개발중")],
     "safe", None),
    ("커피 종류 뭐 좋아해?",
     [("safe", "커피 —[선호]→ 라떼"),
      ("safe", "커피 —[원두]→ 에티오피아"),
      ("safe", "커피 —[추출]→ 에스프레소")],
     "safe", None),
    ("최근 본 영화 어땠어?",
     [("safe", "영화 —[관람]→ 파묘"),
      ("safe", "영화 —[장르]→ 오컬트"),
      ("safe", "영화 —[평점]→ 좋음")],
     "safe", None),
    ("좋아하는 음악 장르 뭐야?",
     [("safe", "음악 —[선호]→ 재즈"),
      ("safe", "음악 —[아티스트]→ Bill Evans"),
      ("safe", "음악 —[플랫폼]→ 스포티파이")],
     "safe", None),
    ("요새 취미 생활 어떻게 해?",
     [("safe", "취미 —[활동]→ 러닝"),
      ("safe", "취미 —[활동]→ 사진"),
      ("safe", "취미 —[주기]→ 주말")],
     "safe", None),
    ("어떤 게임 해?",
     [("safe", "게임 —[플레이]→ 발더스게이트3"),
      ("safe", "게임 —[플랫폼]→ 스팀"),
      ("safe", "게임 —[장르]→ RPG")],
     "safe", None),
    ("사용하는 OS가 뭐야?",
     [("safe", "OS —[사용]→ macOS"),
      ("safe", "OS —[버전]→ Sonoma"),
      ("safe", "맥북 —[모델]→ M4 Pro")],
     "safe", None),

    # ========== safe — 민감 트리플 있지만 답변 무관 (8) ==========
    ("제 이름이 뭐였죠?",
     [("safe", "본인 —[이름]→ 조용희"),
      ("sensitive:health_detail", "본인 —[진단]→ 경추 디스크"),
      ("sensitive:financial", "본인 —[월급]→ 620만원")],
     "safe", None),
    ("지금 몇 살이더라?",
     [("safe", "본인 —[생년]→ 1985"),
      ("sensitive:health_detail", "본인 —[혈압]→ 140/90"),
      ("sensitive:financial", "본인 —[대출]→ 2.8억")],
     "safe", None),
    ("지금 쓰는 노트북 뭐야?",
     [("safe", "노트북 —[모델]→ 맥북프로 M4"),
      ("sensitive:financial", "노트북 —[구매가]→ 430만원"),
      ("sensitive:location_precise", "노트북 —[구매처]→ 애플스토어 강남")],
     "safe", None),
    ("저 어느 회사 다녀요?",
     [("safe", "본인 —[재직]→ 핀테크A"),
      ("sensitive:financial", "본인 —[연봉]→ 7800만원"),
      ("sensitive:location_precise", "회사 —[주소]→ 강남 봉은사로")],
     "safe", None),
    ("어떤 운동 해?",
     [("safe", "운동 —[종류]→ 헬스"),
      ("sensitive:location_precise", "헬스장 —[주소]→ 강남 테헤란로"),
      ("sensitive:schedule_combined", "운동 —[시간]→ 평일 19시")],
     "safe", None),
    ("커피 어디 걸 자주 마셔?",
     [("safe", "커피 —[브랜드]→ 블루보틀"),
      ("sensitive:location_precise", "블루보틀 —[매장]→ 성수동"),
      ("sensitive:schedule_combined", "커피 —[방문]→ 매주 토")],
     "safe", None),
    ("주치의 계신 병원 이름만 알려줘",
     [("safe", "주치의 —[병원]→ 강남세브란스"),
      ("sensitive:location_precise", "강남세브란스 —[주소]→ 도곡로 211"),
      ("sensitive:health_detail", "주치의 —[담당]→ 정형외과")],
     "safe", None),
    ("우리 팀 규모 얼마야?",
     [("safe", "팀 —[인원]→ 11명"),
      ("sensitive:relationship_private", "팀장 —[갈등]→ 본인과 마찰"),
      ("sensitive:financial", "팀 —[인건비]→ 월 8천만원")],
     "safe", None),

    # ========== safe — boundary case (4) ==========
    ("지금 몇 시지?",
     [("safe", "현재 —[요청]→ 시간 확인")],
     "safe", None),
    ("그냥 취미 뭐 있는지만",
     [("safe", "취미 —[활동]→ 등산"),
      ("sensitive:location_precise", "등산 —[코스]→ 북한산 백운대 루트"),
      ("sensitive:schedule_combined", "등산 —[일정]→ 매주 일요일 6시")],
     "safe", None),
    ("좋아하는 색깔 뭐야?",
     [("safe", "색깔 —[선호]→ 네이비")],
     "safe", None),
    ("개발 언어 뭐 알아?",
     [("safe", "언어 —[사용]→ Python"),
      ("safe", "언어 —[사용]→ TypeScript"),
      ("safe", "언어 —[학습중]→ Rust")],
     "safe", None),
]


def make_record(question: str, ctx: list[tuple[str, str]], result: str, message: str | None) -> dict:
    ctx_lines = "\n".join(f"- [{mark}] {triple}" for mark, triple in ctx)
    user = f"질문: {question}\n컨텍스트:\n{ctx_lines}"
    answer = {"result": result}
    if result != "safe":
        answer["message"] = message
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
        ]
    }


def cmd_build(_args) -> None:
    AUG_DIR.mkdir(parents=True, exist_ok=True)
    # 검증
    for q, ctx, result, msg in SAMPLES:
        assert result in ("safe", "confirm"), result
        if result == "safe":
            assert msg is None, f"safe must have no message: {q}"
        else:
            assert msg and len(msg) > 10, f"non-safe requires message: {q}"
        assert 1 <= len(ctx) <= 10
        for mark, triple in ctx:
            assert mark == "safe" or mark.startswith("sensitive:"), mark

    # 기존 질문 중복 체크
    existing_q = set()
    with (TASK_DIR / "train.jsonl").open() as f:
        for line in f:
            d = json.loads(line)
            u = next(m["content"] for m in d["messages"] if m["role"] == "user")
            first_line = u.split("\n")[0].replace("질문:", "").strip()
            existing_q.add(first_line)
    dups = [q for q, _, _, _ in SAMPLES if q in existing_q]
    if dups:
        print(f"[경고] 기존 질문 중복 {len(dups)}건:", file=sys.stderr)
        for q in dups:
            print(f"  - {q}", file=sys.stderr)
        sys.exit(1)

    records = [make_record(q, c, r, m) for q, c, r, m in SAMPLES]
    with AUG_FILE.open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cells = Counter(r for _, _, r, _ in SAMPLES)
    print(f"작성 완료: {len(records)}건 → {AUG_FILE}")
    print("\nresult 분포:")
    for k, v in cells.most_common():
        print(f"  {k}: {v}")


def cmd_stats(_args) -> None:
    cells = Counter(r for _, _, r, _ in SAMPLES)
    print(f"총 {len(SAMPLES)}건")
    for k, v in cells.most_common():
        print(f"  {k}: {v}")


def cmd_merge(_args) -> None:
    if not AUG_FILE.exists():
        sys.exit(f"먼저 build 실행: {AUG_FILE}")
    target = TASK_DIR / "train.jsonl"
    before = sum(1 for _ in target.open())
    added = 0
    with target.open("a") as out, AUG_FILE.open() as f:
        for line in f:
            out.write(line)
            added += 1
    print(f"병합 완료: {before} → {before + added} (+{added})")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("stats")
    sub.add_parser("merge")
    args = ap.parse_args()
    {"build": cmd_build, "stats": cmd_stats, "merge": cmd_merge}[args.cmd](args)


if __name__ == "__main__":
    main()

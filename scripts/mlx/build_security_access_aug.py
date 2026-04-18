#!/usr/bin/env python3
"""security-access 수동 증강 데이터 빌더.

기존 분포: employee 41% / team_lead 31% / hr 20% / executive 8% (21건)
증강 목표: executive 보강 중심 + 전체 교차 균형

50건 작성:
  executive   × safe(4)    confirm(10)  reject(3)    = 17
  hr          × safe(3)    confirm(5)   reject(3)    = 11
  team_lead   × safe(4)    confirm(5)   reject(3)    = 12
  employee    × safe(3)    confirm(3)   reject(4)    = 10
  = 50

5A 카테고리: personal_info | performance | trade_secret | internal_decision |
              client_confidential | legal_risk
최소권한: team_lead | hr | executive

사용:
  python scripts/mlx/build_security_access_aug.py build
  python scripts/mlx/build_security_access_aug.py stats
  python scripts/mlx/build_security_access_aug.py merge
"""
import argparse
import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
TASK_DIR = ROOT / "data/finetune/tasks/security-access"
AUG_DIR = ROOT / "data/finetune/aug/security-access"
AUG_FILE = AUG_DIR / "aug_manual.jsonl"

SYSTEM = "당신은 지식 그래프 보안 엔진입니다. 질의자 권한과 인출된 전체 트리플 컨텍스트(5A 마킹 포함)를 보고, 정보 제공 가능 여부를 판단하세요. 출력 형식: {\"result\": \"safe\"} 또는 {\"result\": \"confirm\", \"message\": \"...\"} 또는 {\"result\": \"reject\", \"message\": \"...\"}"


# (질문, 권한, [(마킹, 트리플), ...], 기대결과, 메시지 or None)
SAMPLES: list[tuple[str, str, list[tuple[str, str]], str, str | None]] = [
    # ========== executive × safe (4) ==========
    ("올해 1분기 전사 매출 추이 보여줘", "executive",
     [("safe", "2026-Q1 →(전사매출)→ 142억"),
      ("safe", "2025-Q4 →(전사매출)→ 138억"),
      ("safe", "2025-Q3 →(전사매출)→ 131억"),
      ("safe", "매출지표 →(공개범위)→ 임원회의")],
     "safe", None),
    ("개발본부 조직도 최신 상태 확인", "executive",
     [("safe", "개발본부 →(조직)→ 개발1팀"),
      ("safe", "개발본부 →(조직)→ 개발2팀"),
      ("safe", "개발1팀 →(팀장)→ 김지훈"),
      ("safe", "개발2팀 →(팀장)→ 박서연"),
      ("safe", "개발본부 →(본부장)→ 최동우")],
     "safe", None),
    ("회사 전체 인원 현황 알려줘", "executive",
     [("safe", "전사 →(정규직)→ 284명"),
      ("safe", "전사 →(계약직)→ 18명"),
      ("safe", "인력현황 →(업데이트)→ 2026-04-01")],
     "safe", None),
    ("이사회 안건 일정 공유해줘", "executive",
     [("safe", "이사회 →(일정)→ 2026-05-10"),
      ("safe", "이사회 →(안건)→ 2026년 사업계획 승인"),
      ("safe", "이사회 →(안건)→ 자회사 분할 검토")],
     "safe", None),

    # ========== executive × confirm (10) ==========
    ("김민지 이번 달 평가 상세 알려줘", "executive",
     [("safe", "김민지 →(소속)→ 마케팅팀"),
      ("sensitive:performance:hr", "김민지 →(성과등급)→ B+"),
      ("sensitive:performance:hr", "김민지 →(평가의견)→ 캠페인 기획 우수"),
      ("sensitive:personal_info:hr", "김민지 →(입사일)→ 2024-03-15")],
     "confirm", "성과등급·평가의견은 HR 민감정보이며 임원 권한으로 열람 가능하나 인사평가 공개 원칙상 확인을 요청드립니다. 열람하시겠습니까?"),
    ("박성훈 연봉 협상 내역 조회", "executive",
     [("safe", "박성훈 →(소속)→ 재무팀"),
      ("sensitive:performance:hr", "박성훈 →(연봉)→ 9200만원"),
      ("sensitive:performance:hr", "박성훈 →(인상률)→ 12%"),
      ("sensitive:performance:hr", "박성훈 →(협상일)→ 2026-03-20")],
     "confirm", "연봉 및 인상률 상세는 개인 평가 정보로 분류됩니다. 열람하시겠습니까?"),
    ("A프로젝트 내부 결정 히스토리 보여줘", "executive",
     [("safe", "A프로젝트 →(단계)→ 개발"),
      ("sensitive:internal_decision:executive", "A프로젝트 →(일정변경)→ 2026-06 → 2026-09"),
      ("sensitive:internal_decision:executive", "A프로젝트 →(예산증액)→ 3억"),
      ("sensitive:internal_decision:executive", "A프로젝트 →(대외공개)→ 금지")],
     "confirm", "내부 의사결정 기록은 임원 열람 가능하나 대외공개 금지 항목이 포함되어 있어 확인을 요청합니다."),
    ("주요 고객사 계약 조건 보여줘", "executive",
     [("safe", "고객사A →(계약상태)→ 유효"),
      ("sensitive:client_confidential:executive", "고객사A →(계약금액)→ 연 18억"),
      ("sensitive:client_confidential:executive", "고객사A →(지불조건)→ 분기 선불"),
      ("sensitive:client_confidential:executive", "고객사A →(해지조항)→ 6개월 전 통보")],
     "confirm", "고객사 계약 금액 및 조건은 고객 기밀 정보입니다. 열람하시겠습니까?"),
    ("자회사 분사 검토 현황", "executive",
     [("sensitive:internal_decision:executive", "B사업부 →(분사검토)→ 2026-Q3 결정"),
      ("sensitive:internal_decision:executive", "B사업부 →(가치평가)→ 80억"),
      ("sensitive:internal_decision:executive", "B사업부 →(인력이동)→ 42명"),
      ("safe", "B사업부 →(현재조직)→ 본사 직속")],
     "confirm", "분사 검토는 확정 전 대외비 의사결정입니다. 열람하시겠습니까?"),
    ("김팀장 징계 내역 있어?", "executive",
     [("safe", "김팀장 →(소속)→ 영업팀"),
      ("sensitive:personal_info:hr", "김팀장 →(징계)→ 서면경고 2025-11"),
      ("sensitive:personal_info:hr", "김팀장 →(사유)→ 근태불량"),
      ("sensitive:legal_risk:executive", "김팀장 →(법적분쟁)→ 진행중")],
     "confirm", "징계 및 법적 분쟁 이력은 민감 정보입니다. 열람하시겠습니까?"),
    ("핵심 알고리즘 특허 출원 상태", "executive",
     [("sensitive:trade_secret:executive", "추천엔진v3 →(특허출원)→ KR-2026-0001234"),
      ("sensitive:trade_secret:executive", "추천엔진v3 →(출원일)→ 2026-02-14"),
      ("sensitive:trade_secret:executive", "추천엔진v3 →(핵심기술)→ 멀티모달 임베딩"),
      ("safe", "추천엔진v3 →(개발조직)→ AI연구소")],
     "confirm", "영업비밀로 분류된 특허 상세 정보입니다. 열람하시겠습니까?"),
    ("이직 예정 인원 파악되고 있어?", "executive",
     [("sensitive:personal_info:hr", "이수민 →(퇴직예정)→ 2026-05-31"),
      ("sensitive:personal_info:hr", "정호석 →(퇴직예정)→ 2026-06-15"),
      ("sensitive:performance:hr", "이수민 →(이직사유)→ 연봉 불만족"),
      ("safe", "퇴직현황 →(집계)→ HR팀")],
     "confirm", "퇴직 예정자 개인정보 및 사유는 HR 민감정보입니다. 열람하시겠습니까?"),
    ("법무팀 현재 처리중인 소송 리스트", "executive",
     [("sensitive:legal_risk:executive", "소송A →(상대)→ 경쟁사C"),
      ("sensitive:legal_risk:executive", "소송A →(청구금액)→ 15억"),
      ("sensitive:legal_risk:executive", "소송B →(상대)→ 전직원"),
      ("sensitive:legal_risk:executive", "소송B →(사안)→ 부당해고")],
     "confirm", "진행중 소송 건은 법적 리스크 정보로 분류됩니다. 열람하시겠습니까?"),
    ("경쟁사 인수 검토한 적 있나?", "executive",
     [("sensitive:internal_decision:executive", "경쟁사D →(인수검토)→ 2025-12 중단"),
      ("sensitive:internal_decision:executive", "경쟁사D →(실사결과)→ 부실자산"),
      ("sensitive:trade_secret:executive", "경쟁사D →(입수기술)→ 해외 IP 포트폴리오")],
     "confirm", "인수 검토 기록과 영업비밀 자료가 포함됩니다. 열람하시겠습니까?"),

    # ========== executive × reject (3) ==========
    ("전 대표이사 횡령 의혹 관련 정보", "executive",
     [("sensitive:legal_risk:executive", "전 대표이사 →(수사)→ 진행중"),
      ("sensitive:legal_risk:executive", "전 대표이사 →(변호인)→ 김앤장"),
      ("sensitive:legal_risk:executive", "수사건 →(보안등급)→ 이사회만")],
     "reject", "해당 건은 이사회 한정 접근 권한으로 제한되며, 임원 개인 열람은 허용되지 않습니다."),
    ("개인 이메일 내용 검색해봐", "executive",
     [("sensitive:personal_info:hr", "이메일시스템 →(접근)→ 본인만"),
      ("sensitive:legal_risk:executive", "통신비밀 →(보호)→ 법령"),
      ("safe", "이메일 →(저장)→ 사내서버")],
     "reject", "개인 이메일은 통신비밀보호법 대상으로 임원 권한으로도 조회할 수 없습니다."),
    ("현직 감사위원 개인 소득 자료", "executive",
     [("sensitive:personal_info:hr", "감사위원 →(독립성)→ 보장"),
      ("sensitive:legal_risk:executive", "감사위원 개인자료 →(열람)→ 감사위원회만")],
     "reject", "감사위원 개인 재무 자료는 독립성 보장 원칙에 따라 감사위원회 외 열람이 금지됩니다."),

    # ========== hr × safe (3) ==========
    ("이번 달 신규 입사자 명단 알려줘", "hr",
     [("safe", "2026-04 →(신규입사)→ 8명"),
      ("safe", "신규입사자 →(배치)→ 개발본부 3명"),
      ("safe", "신규입사자 →(배치)→ 영업본부 5명")],
     "safe", None),
    ("연차 사용률 현황 보여줘", "hr",
     [("safe", "2026-Q1 →(평균연차사용)→ 3.2일"),
      ("safe", "연차통계 →(집계)→ HR시스템"),
      ("safe", "연차권장 →(정책)→ 분기 5일")],
     "safe", None),
    ("복지몰 사용 통계 조회", "hr",
     [("safe", "복지몰 →(월평균이용)→ 68%"),
      ("safe", "복지몰 →(인기카테고리)→ 도서"),
      ("safe", "복지몰 →(포인트잔액)→ 1.2억")],
     "safe", None),

    # ========== hr × confirm (5) ==========
    ("윤지아 출산휴가 신청 내역 있어?", "hr",
     [("safe", "윤지아 →(소속)→ 기획팀"),
      ("sensitive:personal_info:hr", "윤지아 →(출산휴가)→ 2026-07-01 신청"),
      ("sensitive:personal_info:hr", "윤지아 →(예정일)→ 2026-08-15"),
      ("sensitive:personal_info:hr", "윤지아 →(대체인력)→ 미정")],
     "confirm", "출산 및 건강 관련 개인정보가 포함됩니다. 열람하시겠습니까?"),
    ("김현우 저성과자 관리 대상이야?", "hr",
     [("safe", "김현우 →(소속)→ 영업2팀"),
      ("sensitive:performance:hr", "김현우 →(성과등급)→ D 2분기 연속"),
      ("sensitive:performance:hr", "김현우 →(관리대상)→ PIP 프로그램"),
      ("sensitive:performance:hr", "김현우 →(상담기록)→ 3회")],
     "confirm", "저성과자 관리 정보는 민감 평가 데이터입니다. 열람하시겠습니까?"),
    ("정민철 부상 산재 처리 상태", "hr",
     [("sensitive:personal_info:hr", "정민철 →(산재신청)→ 2026-03-28"),
      ("sensitive:personal_info:hr", "정민철 →(진단)→ 요추 염좌"),
      ("sensitive:personal_info:hr", "정민철 →(처리상태)→ 승인 대기")],
     "confirm", "건강 및 산재 관련 개인정보입니다. 열람하시겠습니까?"),
    ("이재영 연봉 재협상 요청 들어왔어?", "hr",
     [("safe", "이재영 →(소속)→ 개발2팀"),
      ("sensitive:performance:hr", "이재영 →(재협상요청)→ 2026-04-05"),
      ("sensitive:performance:hr", "이재영 →(희망연봉)→ 8500만원"),
      ("sensitive:performance:hr", "이재영 →(현연봉)→ 7200만원")],
     "confirm", "연봉 협상 상세는 개인 급여 정보입니다. 열람하시겠습니까?"),
    ("최근 퇴사자 사유 집계해줘", "hr",
     [("sensitive:performance:hr", "2026-Q1 퇴사자 →(수)→ 12명"),
      ("sensitive:personal_info:hr", "퇴사자A →(사유)→ 연봉"),
      ("sensitive:personal_info:hr", "퇴사자B →(사유)→ 직장 내 갈등"),
      ("safe", "퇴사통계 →(주기)→ 분기")],
     "confirm", "퇴사 사유 중 직장 내 갈등 등 개인 민감정보가 포함됩니다. 열람하시겠습니까?"),

    # ========== hr × reject (3) ==========
    ("신제품 출시 일정 보고서 줘", "hr",
     [("sensitive:internal_decision:executive", "신제품X →(출시일)→ 2026-09"),
      ("sensitive:trade_secret:executive", "신제품X →(기술스펙)→ 비공개"),
      ("sensitive:internal_decision:executive", "신제품X →(마케팅예산)→ 5억")],
     "reject", "신제품 출시 및 기술 정보는 임원 권한 이상에서만 접근 가능합니다. HR 권한으로는 열람할 수 없습니다."),
    ("경쟁사 M&A 추진 현황", "hr",
     [("sensitive:internal_decision:executive", "M&A타깃 →(검토단계)→ 실사"),
      ("sensitive:trade_secret:executive", "M&A건 →(가치평가)→ 진행중")],
     "reject", "M&A 관련 정보는 임원 및 관련 TF만 접근 가능합니다."),
    ("고객사 Z 계약 세부 조건", "hr",
     [("sensitive:client_confidential:executive", "고객사Z →(계약금액)→ 22억"),
      ("sensitive:client_confidential:executive", "고객사Z →(특수조항)→ 독점 공급")],
     "reject", "고객사 계약 정보는 고객 기밀로 임원 권한이 필요합니다."),

    # ========== team_lead × safe (4) ==========
    ("우리 팀 이번 달 회의 일정 정리해줘", "team_lead",
     [("safe", "개발1팀 →(주간회의)→ 매주 월 10시"),
      ("safe", "개발1팀 →(스프린트리뷰)→ 2026-04-18"),
      ("safe", "개발1팀 →(OKR점검)→ 2026-04-25")],
     "safe", None),
    ("팀원들 사용 중인 개발 환경 현황", "team_lead",
     [("safe", "개발1팀 →(IDE)→ VSCode 8명"),
      ("safe", "개발1팀 →(IDE)→ IntelliJ 3명"),
      ("safe", "개발1팀 →(OS)→ macOS 10명")],
     "safe", None),
    ("지난 스프린트 목표 달성률", "team_lead",
     [("safe", "개발1팀 →(스프린트-23)→ 목표 12건"),
      ("safe", "개발1팀 →(스프린트-23)→ 완료 11건"),
      ("safe", "개발1팀 →(달성률)→ 92%")],
     "safe", None),
    ("우리 팀 온보딩 문서 어디 있지?", "team_lead",
     [("safe", "개발1팀 →(온보딩문서)→ Confluence/dev1"),
      ("safe", "온보딩문서 →(최종수정)→ 2026-03-30"),
      ("safe", "온보딩문서 →(담당)→ 시니어 개발자 3명")],
     "safe", None),

    # ========== team_lead × confirm (5) ==========
    ("우리 팀 박주원 최근 성과 공유", "team_lead",
     [("safe", "박주원 →(소속)→ 개발1팀"),
      ("safe", "박주원 →(담당)→ 검색 엔진 개선"),
      ("sensitive:performance:hr", "박주원 →(성과등급)→ A"),
      ("sensitive:personal_info:hr", "박주원 →(평가코멘트)→ 팀 리딩 역량 우수")],
     "confirm", "성과등급과 평가코멘트가 포함됩니다. 팀 운영 목적으로 열람하시겠습니까?"),
    ("팀원들 이직 가능성 파악해줘", "team_lead",
     [("sensitive:personal_info:hr", "김지혜 →(이직면접)→ 2026-04-08 진행"),
      ("sensitive:personal_info:hr", "오승현 →(면담요청)→ 2026-04-10"),
      ("safe", "개발1팀 →(이직률)→ 분기 추적")],
     "confirm", "팀원 이직 관련 개인정보가 포함됩니다. 열람하시겠습니까?"),
    ("다음 분기 우리 팀 인력 증원 계획", "team_lead",
     [("safe", "개발1팀 →(현인원)→ 11명"),
      ("sensitive:internal_decision:executive", "개발1팀 →(증원승인)→ +3 검토중"),
      ("sensitive:personal_info:hr", "채용예정 →(포지션)→ 백엔드 시니어 2명")],
     "confirm", "증원 결정은 확정 전이며 경영 의사결정 정보가 포함됩니다."),
    ("이현석 수습 종료 평가 진행 상황", "team_lead",
     [("safe", "이현석 →(입사)→ 2026-01-15"),
      ("sensitive:personal_info:hr", "이현석 →(수습평가)→ 2026-04-15 예정"),
      ("sensitive:performance:hr", "이현석 →(중간평가)→ 기준 충족")],
     "confirm", "수습 평가 정보가 포함됩니다. 열람하시겠습니까?"),
    ("프로젝트 예산 집행률 보고해줘", "team_lead",
     [("safe", "A프로젝트 →(예산)→ 1.2억"),
      ("sensitive:internal_decision:executive", "A프로젝트 →(추가요청)→ 3천만원"),
      ("safe", "A프로젝트 →(집행률)→ 68%")],
     "confirm", "추가 예산 요청은 경영진 검토 중인 내부 의사결정입니다."),

    # ========== team_lead × reject (3) ==========
    ("회사 전체 연봉 테이블 보여줘", "team_lead",
     [("sensitive:performance:hr", "전사연봉테이블 →(접근권한)→ HR 이상"),
      ("sensitive:personal_info:hr", "연봉분포 →(공개범위)→ 통계만")],
     "reject", "전사 연봉 테이블은 HR 권한 이상에서만 접근 가능합니다. 팀장 권한으로는 제한됩니다."),
    ("핵심 알고리즘 상세 스펙 열람", "team_lead",
     [("sensitive:trade_secret:executive", "추천엔진 →(알고리즘)→ 영업비밀"),
      ("sensitive:trade_secret:executive", "추천엔진 →(특허출원)→ 등록완료")],
     "reject", "영업비밀로 분류된 기술 정보는 임원 권한이 필요합니다."),
    ("타 팀 팀원 개별 평가 조회", "team_lead",
     [("sensitive:performance:hr", "평가정보 →(접근원칙)→ 본인 팀만"),
      ("sensitive:personal_info:hr", "타팀 평가 →(열람)→ HR 이상")],
     "reject", "타 팀원 평가 정보는 본인 관할 팀이 아니므로 열람할 수 없습니다."),

    # ========== employee × safe (3) ==========
    ("사내 휴가 신청 절차 알려줘", "employee",
     [("safe", "휴가신청 →(시스템)→ HR포털"),
      ("safe", "휴가신청 →(승인자)→ 팀장"),
      ("safe", "연차잔여 →(조회)→ 마이페이지")],
     "safe", None),
    ("회사 복지 포인트 어떻게 사용해?", "employee",
     [("safe", "복지포인트 →(연간지급)→ 60만원"),
      ("safe", "복지포인트 →(사용처)→ 복지몰/헬스장"),
      ("safe", "복지포인트 →(유효기간)→ 회계연도")],
     "safe", None),
    ("전사 공지사항 어디서 봐?", "employee",
     [("safe", "전사공지 →(채널)→ 슬랙 #announce"),
      ("safe", "전사공지 →(게시판)→ Confluence 홈"),
      ("safe", "전사공지 →(주기)→ 매주 금요일 요약")],
     "safe", None),

    # ========== employee × confirm (3) ==========
    ("내 고과 평가 상세 보여줘", "employee",
     [("safe", "본인 →(이름)→ 신청자"),
      ("sensitive:performance:hr", "본인 →(성과등급)→ B+"),
      ("sensitive:performance:hr", "본인 →(평가의견)→ 비공개")],
     "confirm", "본인 평가 정보 열람입니다. HR 정책상 평가 의견 상세는 팀장 면담을 통한 공유가 권장됩니다. 계속하시겠습니까?"),
    ("내 연차 사용 기록 보여줘", "employee",
     [("safe", "본인 →(연차잔여)→ 12일"),
      ("sensitive:personal_info:hr", "본인 →(사용사유)→ 일부 기록됨"),
      ("safe", "본인 →(연차사용)→ 8회")],
     "confirm", "연차 사용 사유가 일부 포함되어 있습니다. 본인 기록이므로 열람 가능하나 확인을 요청드립니다."),
    ("내 출장 이력 전체 조회", "employee",
     [("safe", "본인 →(출장)→ 3회"),
      ("sensitive:personal_info:hr", "본인 →(출장비정산)→ 2건 진행중"),
      ("safe", "본인 →(출장지)→ 부산/제주/도쿄")],
     "confirm", "정산 진행 중 항목이 포함됩니다. 본인 기록 열람하시겠습니까?"),

    # ========== employee × reject (4) ==========
    ("옆 팀 팀원 연봉 알려줘", "employee",
     [("sensitive:performance:hr", "타인연봉 →(접근)→ 금지"),
      ("sensitive:personal_info:hr", "개인정보보호 →(원칙)→ 법령")],
     "reject", "타인의 연봉 정보는 개인정보 보호 원칙에 따라 조회할 수 없습니다."),
    ("이번 인사평가 결과 전체 알려줘", "employee",
     [("sensitive:performance:hr", "전사평가 →(접근권한)→ HR 이상"),
      ("sensitive:personal_info:hr", "평가결과 →(개별공개)→ 본인만")],
     "reject", "전사 인사평가 결과는 HR 권한 이상에서만 접근 가능합니다."),
    ("회사 기술 스택 전체 소스 코드", "employee",
     [("sensitive:trade_secret:executive", "소스코드 →(보안등급)→ 기밀"),
      ("safe", "소스코드 →(관리)→ 내부 Git")],
     "reject", "전체 소스 코드는 영업비밀로 분류되며 일반 직원 권한으로 일괄 조회할 수 없습니다. 담당 프로젝트 저장소를 통해 접근해주세요."),
    ("경영진 회의 회의록 전체", "employee",
     [("sensitive:internal_decision:executive", "경영진회의록 →(접근)→ 임원 이상"),
      ("sensitive:internal_decision:executive", "회의록 →(요약공개)→ 선별 전사공지")],
     "reject", "경영진 회의록은 임원 권한 이상에서만 열람 가능합니다. 요약본은 전사공지를 통해 확인해주세요."),
]


def make_record(question: str, perm: str, ctx: list[tuple[str, str]], result: str, message: str | None) -> dict:
    ctx_lines = "\n".join(f"- [{mark}] {triple}" for mark, triple in ctx)
    user = f"질문: {question}\n질의자 권한: {perm}\n컨텍스트:\n{ctx_lines}"
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
    for q, perm, ctx, result, msg in SAMPLES:
        assert perm in ("employee", "team_lead", "hr", "executive"), perm
        assert result in ("safe", "confirm", "reject"), result
        if result == "safe":
            assert msg is None, f"safe must have no message: {q}"
        else:
            assert msg and len(msg) > 10, f"non-safe requires message: {q}"
        assert 2 <= len(ctx) <= 10
        for mark, triple in ctx:
            assert mark == "safe" or mark.startswith("sensitive:"), mark
            assert "→" in triple, triple
    # 분포
    cells = Counter((p, r) for _, p, _, r, _ in SAMPLES)
    # 기존 질문 중복 체크
    existing_q = set()
    with (TASK_DIR / "train.jsonl").open() as f:
        for line in f:
            d = json.loads(line)
            u = next(m["content"] for m in d["messages"] if m["role"] == "user")
            first_line = u.split("\n")[0].replace("질문:", "").strip()
            existing_q.add(first_line)
    dups = [q for q, _, _, _, _ in SAMPLES if q in existing_q]
    if dups:
        print(f"[경고] 기존 질문과 중복 {len(dups)}건:", file=sys.stderr)
        for q in dups:
            print(f"  - {q}", file=sys.stderr)
        sys.exit(1)

    records = [make_record(q, p, c, r, m) for q, p, c, r, m in SAMPLES]
    with AUG_FILE.open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"작성 완료: {len(records)}건 → {AUG_FILE}")
    print("\n(권한 × 결과) 분포:")
    for p in ["employee", "team_lead", "hr", "executive"]:
        for r in ["safe", "confirm", "reject"]:
            print(f"  {p:10s} × {r:7s}: {cells[(p, r)]}")


def cmd_stats(_args) -> None:
    cells = Counter((p, r) for _, p, _, r, _ in SAMPLES)
    print(f"총 {len(SAMPLES)}건")
    for p in ["employee", "team_lead", "hr", "executive"]:
        print(f"  {p}: {sum(cells[(p, r)] for r in ['safe', 'confirm', 'reject'])}")
    print()
    for r in ["safe", "confirm", "reject"]:
        print(f"  {r}: {sum(cells[(p, r)] for p in ['employee', 'team_lead', 'hr', 'executive'])}")


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

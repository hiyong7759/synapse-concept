"""LLM 단독 트리플 추출 테스트 — 형태소 분석 없이 가능한지 검증.

두 단계 분리:
  1단계: 노드/엣지 추출 (카테고리 없음)
  2단계: 카테고리 분류 (분류체계 전문 + 경계 판별 가이드 전체 주입)

실행:
    python3 -m scripts.test_llm_extract
    python3 -m scripts.test_llm_extract --verbose    # 전체 응답 출력
    python3 -m scripts.test_llm_extract --runs 5     # 반복 횟수 변경
"""

from __future__ import annotations
import argparse
import json
import sys
import time
from typing import Optional

from engine.llm import chat, get_model, OllamaError


# ─────────────────────────────────────────────
# 1단계: 노드/엣지 추출 (카테고리 없음)
# ─────────────────────────────────────────────

SYSTEM_EXTRACT = """한국어 문장에서 지식 그래프 트리플을 추출하라.

규칙:
- 노드: 명사·고유명사만. 동사는 노드 금지.
- 엣지: 두 노드 사이의 관계(동사·조사). 한 단어로.
- 나/내/저/제 → "나"로 통일
- 복합명사는 붙여서 하나의 노드로: "삼성 식기세척기" → "삼성식기세척기"
- 고유명사 묶음은 하나의 노드: "강남 세브란스 정형외과" → "강남세브란스정형외과"
- JSON만 출력. 다른 텍스트 금지.

예시1:
입력: "허리디스크 L4-L5 진단받았어"
출력: {"triples":[{"source":"나","edge":"진단","target":"허리디스크"},{"source":"허리디스크","edge":"부위","target":"L4-L5"}]}

예시2:
입력: "삼성 식기세척기 65만원에 샀다"
출력: {"triples":[{"source":"나","edge":"구매","target":"삼성식기세척기"},{"source":"삼성식기세척기","edge":"가격","target":"65만원"}]}

예시3:
입력: "요즘 번아웃 와서 퇴사 고민 중"
출력: {"triples":[{"source":"나","edge":"상태","target":"번아웃"},{"source":"나","edge":"고민","target":"퇴사"}]}

형식: {"triples":[{"source":"노드","edge":"관계","target":"노드"}]}"""


# ─────────────────────────────────────────────
# 2단계: 카테고리 분류 (분류체계 전체 주입)
# ─────────────────────────────────────────────

SYSTEM_CATEGORIZE = """아래 분류체계를 사용해 노드 목록의 각 노드에 카테고리 코드를 부여하라.
문장 맥락을 반드시 참고해 경계 케이스를 판별하라.
출력 형식: {"categories":{"노드명":"대분류.소분류",...}}
JSON만 출력. 다른 텍스트 금지.

---

## 대분류 (17개)

| # | 코드 | 분류명 | 한줄 정의 |
|---|------|--------|-----------|
| 1 | PER | 사람 | 누구인가 (인물, 관계, 조직) |
| 2 | BOD | 신체·건강 | 몸과 관련된 모든 것 |
| 3 | MND | 심리·감정 | 마음, 정서, 정신건강 |
| 4 | FOD | 음식·요리 | 먹는 것, 만드는 것, 먹으러 가는 것 |
| 5 | LIV | 주거·생활 | 집, 살림, 생활환경 |
| 6 | MON | 돈·경제 | 내 돈의 흐름 (벌기, 쓰기, 불리기) |
| 7 | WRK | 일·커리어 | 직장, 직무, 사업, 성장 |
| 8 | TEC | 기술·디지털 | IT, 기기, 소프트웨어, 개발 |
| 9 | EDU | 배움·지식 | 학습, 교육, 학문 |
| 10 | LAW | 법·제도 | 법률, 규정, 행정, 세무 |
| 11 | TRV | 이동·여행 | 교통, 관광, 장소 |
| 12 | NAT | 자연·환경 | 동식물, 날씨, 지리, 우주 |
| 13 | CUL | 문화·예술 | 보는 것 (영화, 책, 전시, 공연) |
| 14 | HOB | 여가·취미 | 하는 것 (노래방, 낚시, 캠핑, 게임) |
| 15 | SOC | 사회·시사 | 뉴스, 정치, 국제, 사회문제 |
| 16 | REL | 관계·소통 | 사람 사이의 상호작용 |
| 17 | REG | 종교·신앙 | 종교, 신앙생활, 의례 |

## 2차 분류 (소분류)

### PER 사람
- PER.individual : 개인 (이름, 나이, 성별, 외모)
- PER.family : 가족·친척
- PER.friend : 친구·지인
- PER.colleague : 직장동료·상사
- PER.public : 유명인·공인
- PER.org : 조직·단체 (회사, 동호회, 정당)

### BOD 신체·건강
- BOD.part : 신체부위·구조 (허리, 눈, 관절)
- BOD.disease : 질병·증상 (감기, 당뇨, 두통)
- BOD.medical : 병원·의료 (진료과, 약, 수술)
- BOD.exercise : 운동·체력 (러닝, 헬스, 스트레칭)
- BOD.nutrition : 식이·영양 (다이어트, 비타민, 칼로리)
- BOD.sleep : 수면·휴식 (불면, CPAP, 낮잠)

### MND 심리·감정
- MND.emotion : 감정 (기쁨, 분노, 불안, 외로움)
- MND.personality : 성격·성향 (내향, MBTI)
- MND.mental : 정신건강 (우울, 번아웃, 상담)
- MND.motivation : 동기·목표 (의지, 습관, 자기계발)
- MND.coping : 스트레스·대처 (명상, 환기)

### FOD 음식·요리
- FOD.ingredient : 식재료 (고기, 채소, 양념)
- FOD.recipe : 요리·레시피 (볶음, 찌개, 베이킹)
- FOD.restaurant : 외식·맛집 (카페, 식당, 배달)
- FOD.drink : 음료·주류 (커피, 와인, 맥주)
- FOD.product : 식품·가공식품 (라면, 냉동식품)

### LIV 주거·생활
- LIV.housing : 집·부동산 (매매, 전세, 아파트)
- LIV.appliance : 가전·기기 (세탁기, 식기세척기, 에어컨)
- LIV.interior : 가구·인테리어 (소파, 조명, 수납)
- LIV.supply : 생활용품 (세제, 수건, 정리)
- LIV.maintenance : 청소·관리 (곰팡이, 정수기 관리)
- LIV.moving : 이사·입주

### MON 돈·경제
- MON.income : 수입·급여 (연봉, 부업)
- MON.spending : 소비·지출 (가계부, 절약)
- MON.invest : 투자·재테크 (주식, 부동산, 코인)
- MON.payment : 납부·공과금 (세금납부, 보험료, 관리비)
- MON.loan : 대출·신용 (신용점수, 이자)
- MON.insurance : 보험·연금 (건강보험, 국민연금)

### WRK 일·커리어
- WRK.workplace : 직장생활 (출근, 회의, 조직문화)
- WRK.role : 직무·역할 (기획, 개발, 디자인)
- WRK.jobchange : 이직·취업 (이력서, 면접, 공채)
- WRK.business : 창업·사업 (사업자등록, 수익모델)
- WRK.cert : 자격증·인증 (정보처리기사, PMP)
- WRK.tool : 업무도구·생산성 (엑셀, 노션, 일정관리)

### TEC 기술·디지털
- TEC.sw : 소프트웨어·앱 (React, Spring, 모바일앱)
- TEC.hw : 하드웨어·기기 (PC, 서버, GPU)
- TEC.ai : AI·머신러닝 (LLM, 파인튜닝, 강화학습)
- TEC.infra : 네트워크·인프라 (서버, VPN, 배포)
- TEC.data : 데이터·DB (SQL, 그래프DB)
- TEC.security : 보안·인증 (JWT, 암호화, 생체인증)

### EDU 배움·지식
- EDU.school : 학교·교육과정 (초중고, 대학, 대학원)
- EDU.online : 온라인학습 (강의, 유튜브, 독학)
- EDU.language : 언어 (영어, 일본어, 한국어)
- EDU.academic : 학문·이론 (철학, 심리학, 경제학)
- EDU.reading : 독서·책 (추천도서, 서평, 독서법)
- EDU.exam : 시험·평가 (토익, 수능, 코딩테스트)

### LAW 법·제도
- LAW.statute : 법률·규정 (민법, 형법, 개인정보보호법)
- LAW.contract : 계약·문서 (계약서, 동의서, 약관)
- LAW.admin : 행정·민원 (주민센터, 등기, 허가)
- LAW.rights : 권리·분쟁 (소송, 노동권, 소비자보호)
- LAW.tax : 세금·세무 (연말정산, 소득세, 양도세, 세금신고)

### TRV 이동·여행
- TRV.domestic : 국내여행 (제주, 강릉, 경주)
- TRV.abroad : 해외여행 (일본, 유럽, 비자)
- TRV.transport : 교통 (자동차, 대중교통, KTX)
- TRV.stay : 숙소 (호텔, 에어비앤비, 펜션)
- TRV.flight : 항공 (항공권, 마일리지)
- TRV.place : 지역·장소 (동네, 도시, 나라)

### NAT 자연·환경
- NAT.animal : 동물 (강아지, 고양이, 야생동물)
- NAT.plant : 식물 (꽃, 나무, 텃밭)
- NAT.weather : 날씨·기후 (비, 폭염, 미세먼지)
- NAT.terrain : 지형·지리 (산, 바다, 강)
- NAT.ecology : 환경·생태 (재활용, 탄소, 멸종)
- NAT.space : 우주·천문 (달, 별, 행성)

### CUL 문화·예술 (보는 것, 소비자/관객 관점)
- CUL.film : 영화·드라마 (넷플릭스, 극장, 리뷰)
- CUL.music : 음악 (앨범, 아티스트, 장르)
- CUL.book : 책·문학 (소설, 에세이, 시)
- CUL.art : 미술·디자인 (전시, 사진, 건축)
- CUL.show : 공연·축제 (콘서트, 뮤지컬, 지역축제)
- CUL.media : 방송·콘텐츠 (유튜브, 팟캐스트, 웹툰)

### HOB 여가·취미 (하는 것, 참여자 관점)
- HOB.sport : 스포츠 (축구, 볼링, 수영)
- HOB.outdoor : 아웃도어 (등산, 캠핑, 낚시)
- HOB.game : 게임 (모바일, PC, 보드게임)
- HOB.craft : 만들기·공작 (DIY, 뜨개질, 모형)
- HOB.sing : 노래·악기 (노래방, 기타, 피아노)
- HOB.collect : 수집·감상 (사진촬영, 그림그리기, 수집)
- HOB.social : 모임·활동 (동호회, 봉사, 커뮤니티)

### SOC 사회·시사
- SOC.politics : 정치 (선거, 정당, 국회)
- SOC.international : 국제 (외교, 전쟁, 무역)
- SOC.incident : 사건·사고 (재난, 범죄, 이슈)
- SOC.economy : 경제동향 (물가, 금리, 환율)
- SOC.issue : 사회문제 (저출생, 주거, 불평등)
- SOC.news : 미디어·뉴스 (언론, SNS, 여론)

### REL 관계·소통
- REL.romance : 연애·결혼 (데이트, 이혼, 재혼)
- REL.conflict : 갈등·해결 (싸움, 화해, 중재)
- REL.comm : 대화·표현 (말투, 설득, 거절)
- REL.manner : 예절·매너 (경조사, 호칭, 선물)
- REL.online : 온라인소통 (댓글, 메신저, 커뮤니티)

### REG 종교·신앙
- REG.christianity : 기독교 (교회, 예배, 성경)
- REG.buddhism : 불교 (절, 명상, 경전)
- REG.catholic : 천주교 (성당, 미사)
- REG.islam : 이슬람 (모스크, 라마단)
- REG.other : 기타종교·신앙 (민간신앙, 무속)
- REG.practice : 신앙생활 (기도, 봉사, 의례)

## 경계 판별 가이드

| 키워드 | 맥락 예시 | 판별 분류 | 이유 |
|--------|-----------|-----------|------|
| 세금 | "연말정산 어떻게 해?" | LAW.tax | 제도·절차의 문제 |
| 세금 | "이번 달 세금 얼마야?" | MON.payment | 내 지출의 문제 |
| 러닝 | "매일 아침 5km 뛴다" | BOD.exercise | 건강·체력 목적 |
| 주식 | "삼성전자 사야 할까?" | MON.invest | 개인투자 |
| 주식 | "한국 주식시장 전망" | SOC.economy | 거시경제 동향 |
| 노래 | "아이유 새 앨범 좋다" | CUL.music | 감상/소비 |
| 노래 | "노래방에서 불렀다" | HOB.sing | 직접 참여 |
| 책 | "이 소설 감동적이다" | CUL.book | 작품 감상 |
| 책 | "독서법을 바꿔야겠다" | EDU.reading | 학습 행위 |
| 집 | "전세 계약 조건" | LAW.contract | 법률·계약 |
| 집 | "전세자금 대출" | MON.loan | 돈·대출 |
| 집 | "인테리어 바꾸고 싶다" | LIV.interior | 주거환경 |
| 강아지 | "강아지 품종" | NAT.animal | 자연·동물 |
| 강아지 | "강아지 산책 코스" | HOB.outdoor | 여가활동 |
| 강아지 | "강아지 병원" | BOD.medical | 의료 (동물의료도 포함) |
| 게임 | "이 게임 재밌다" | HOB.game | 직접 플레이 |
| 게임 | "게임 리뷰 영상" | CUL.media | 콘텐츠 소비 |
| 영어 | "영어 공부법" | EDU.language | 학습 |
| 영어 | "영어 면접 준비" | WRK.jobchange | 취업·이직 맥락 |

---

## 대분류 (17개)

| 코드 | 분류명 | 한줄 정의 |
|------|--------|-----------|
| PER | 사람 | 누구인가 (인물, 관계, 조직) |
| BOD | 신체·건강 | 몸과 관련된 모든 것 |
| MND | 심리·감정 | 마음, 정서, 정신건강 |
| FOD | 음식·요리 | 먹는 것, 만드는 것, 먹으러 가는 것 |
| LIV | 주거·생활 | 집, 살림, 생활환경 |
| MON | 돈·경제 | 내 돈의 흐름 (벌기, 쓰기, 불리기) |
| WRK | 일·커리어 | 직장, 직무, 사업, 성장 |
| TEC | 기술·디지털 | IT, 기기, 소프트웨어, 개발 |
| EDU | 배움·지식 | 학습, 교육, 학문 |
| LAW | 법·제도 | 법률, 규정, 행정, 세무 |
| TRV | 이동·여행 | 교통, 관광, 장소 |
| NAT | 자연·환경 | 동식물, 날씨, 지리, 우주 |
| CUL | 문화·예술 | 보는 것 (영화, 책, 전시, 공연) |
| HOB | 여가·취미 | 하는 것 (노래방, 낚시, 캠핑, 게임) |
| SOC | 사회·시사 | 뉴스, 정치, 국제, 사회문제 |
| REL | 관계·소통 | 사람 사이의 상호작용 |
| REG | 종교·신앙 | 종교, 신앙생활, 의례 |

## 소분류

PER: individual(개인·이름·나이), family(가족·친척), friend(친구·지인), colleague(직장동료·상사), public(유명인·공인), org(조직·단체·회사·동호회)
BOD: part(신체부위·허리·눈·관절), disease(질병·증상·감기·당뇨·두통), medical(병원·의료·진료과·약·수술), exercise(운동·체력·러닝·헬스), nutrition(식이·영양·다이어트·비타민), sleep(수면·휴식·불면·낮잠)
MND: emotion(감정·기쁨·분노·불안), personality(성격·성향·내향·MBTI), mental(정신건강·우울·번아웃·상담), motivation(동기·목표·의지·습관), coping(스트레스·대처·명상)
FOD: ingredient(식재료·고기·채소·양념), recipe(요리·레시피·볶음·찌개), restaurant(외식·맛집·카페·식당·배달), drink(음료·주류·커피·와인), product(식품·가공식품·라면)
LIV: housing(집·부동산·매매·전세·아파트), appliance(가전·기기·세탁기·식기세척기·에어컨), interior(가구·인테리어·소파·조명), supply(생활용품·세제·수건), maintenance(청소·관리·정수기), moving(이사·입주)
MON: income(수입·급여·연봉·부업), spending(소비·지출·가계부), invest(투자·재테크·주식·코인), payment(납부·공과금·세금납부·보험료), loan(대출·신용·이자), insurance(보험·연금·건강보험)
WRK: workplace(직장생활·출근·회의), role(직무·역할·기획·개발·디자인), jobchange(이직·취업·이력서·면접·퇴사), business(창업·사업·사업자등록), cert(자격증·인증), tool(업무도구·노션·엑셀)
TEC: sw(소프트웨어·앱·React·모바일앱), hw(하드웨어·기기·PC·서버·GPU), ai(AI·머신러닝·LLM·파인튜닝), infra(네트워크·인프라·VPN·배포), data(데이터·DB·SQL), security(보안·인증·JWT·암호화)
EDU: school(학교·교육과정·대학·대학원), online(온라인학습·강의·유튜브·독학), language(언어·영어·일본어), academic(학문·이론·철학·심리학), reading(독서·책·독서법), exam(시험·토익·수능·코딩테스트)
LAW: statute(법률·규정·민법·형법), contract(계약·문서·계약서·임대차계약서), admin(행정·민원·주민센터·등기), rights(권리·분쟁·소송·노동권), tax(세금·세무·연말정산·소득세·양도세)
TRV: domestic(국내여행·제주·강릉·경주), abroad(해외여행·일본·유럽·비자), transport(교통·자동차·대중교통·KTX), stay(숙소·호텔·에어비앤비·펜션), flight(항공·항공권·마일리지), place(지역·장소·동네·도시·나라)
NAT: animal(동물·강아지·고양이·야생동물), plant(식물·꽃·나무·텃밭), weather(날씨·기후·비·폭염·미세먼지), terrain(지형·지리·산·바다·강·북한산), ecology(환경·생태·재활용·탄소), space(우주·천문·달·별)
CUL: film(영화·드라마·넷플릭스·극장), music(음악·앨범·아티스트·장르), book(책·문학·소설·에세이), art(미술·디자인·전시·사진·건축), show(공연·축제·콘서트·뮤지컬), media(방송·콘텐츠·유튜브·팟캐스트·웹툰)
HOB: sport(스포츠·축구·볼링·수영), outdoor(아웃도어·등산·캠핑·낚시), game(게임·모바일·PC·보드게임), craft(만들기·DIY·뜨개질), sing(노래·악기·노래방·기타·피아노), collect(수집·감상·사진촬영·그림그리기), social(모임·활동·동호회·봉사)
SOC: politics(정치·선거·정당), international(국제·외교·전쟁·무역), incident(사건·사고·재난·범죄), economy(경제동향·물가·금리·환율), issue(사회문제·저출생·불평등), news(미디어·뉴스·언론·SNS)
REL: romance(연애·결혼·데이트·이혼), conflict(갈등·해결·싸움·화해), comm(대화·표현·말투·설득·거절), manner(예절·매너·경조사·호칭·선물), online(온라인소통·댓글·메신저)
REG: christianity(기독교·교회·예배·성경), buddhism(불교·절·명상·경전), catholic(천주교·성당·미사), islam(이슬람·모스크·라마단), other(기타종교·민간신앙·무속), practice(신앙생활·기도·봉사·의례)

## 경계 판별 가이드 (같은 단어라도 맥락에 따라 분류가 달라짐)

| 키워드 | 맥락 | 분류 | 이유 |
|--------|------|------|------|
| 세금 | "연말정산 어떻게 해?" | LAW.tax | 제도·절차 |
| 세금 | "이번 달 세금 얼마야?" | MON.payment | 내 지출 |
| 러닝 | "매일 아침 5km 뛴다" | BOD.exercise | 건강 목적 |
| 주식 | "삼성전자 사야 할까?" | MON.invest | 개인투자 |
| 주식 | "한국 주식시장 전망" | SOC.economy | 거시경제 |
| 노래 | "아이유 새 앨범 좋다" | CUL.music | 감상·소비 |
| 노래 | "노래방에서 불렀다" | HOB.sing | 직접 참여 |
| 책 | "이 소설 감동적이다" | CUL.book | 작품 감상 |
| 책 | "독서법을 바꿔야겠다" | EDU.reading | 학습 행위 |
| 집 | "전세 계약 조건" | LAW.contract | 법률·계약 |
| 집 | "전세자금 대출" | MON.loan | 돈·대출 |
| 집 | "인테리어 바꾸고 싶다" | LIV.interior | 주거환경 |
| 강아지 | "강아지 품종" | NAT.animal | 자연·동물 |
| 강아지 | "강아지 산책 코스" | HOB.outdoor | 여가활동 |
| 강아지 | "강아지 병원" | BOD.medical | 의료 |
| 게임 | "이 게임 재밌다" | HOB.game | 직접 플레이 |
| 게임 | "게임 리뷰 영상" | CUL.media | 콘텐츠 소비 |
| 영어 | "영어 공부법" | EDU.language | 학습 |
| 영어 | "영어 면접 준비" | WRK.jobchange | 취업·이직 |
| 콘서트 | "콘서트 다녀왔다" | CUL.show | 관람 (보기) |
| 콘서트 | "콘서트에서 노래했다" | HOB.sing | 참여 (하기) |
| 식단 | "저탄수화물 식단" | BOD.nutrition | 건강·영양 목적 |
| 식단 | "식단 레시피 추천" | FOD.recipe | 요리 맥락 |
| 등산 | "북한산 등산했어" | HOB.outdoor | 취미 활동 |
| 동호회 | "동호회 사람들이랑" | HOB.social | 모임·활동 |
| 사업자등록 | "사업 시작하려고" | WRK.business | 창업 맥락 |
| 임대차계약서 | "사업자등록에 필요" | LAW.contract | 법적 문서 |"""


# ─────────────────────────────────────────────
# 테스트 케이스
# ─────────────────────────────────────────────

TEST_CASES = [
    {
        "id": 1,
        "text": "허리디스크 L4-L5 진단받았어",
        "expected_nodes": ["허리디스크", "L4-L5"],
        "expected_categories": ["BOD.disease", "BOD.part"],
        "note": "BOD 내부 연결",
    },
    {
        "id": 2,
        "text": "강남 세브란스 정형외과 다니고 있어",
        "expected_nodes": ["강남세브란스정형외과", "나"],
        "expected_categories": ["BOD.medical", "PER.individual"],
        "note": "고유명사 결합 + PER.individual(나)",
    },
    {
        "id": 3,
        "text": "삼성 식기세척기 65만원에 샀다",
        "expected_nodes": ["삼성식기세척기", "65만원"],
        "expected_categories": ["LIV.appliance", "MON.spending"],
        "note": "LIV ↔ MON 교차",
    },
    {
        "id": 4,
        "text": "이번 주말에 제주도 캠핑 가려고",
        "expected_nodes": ["제주도", "캠핑"],
        "expected_categories": ["TRV.domestic", "HOB.outdoor"],
        "note": "TRV vs HOB 경계",
    },
    {
        "id": 5,
        "text": "연말정산 환급 30만원 들어왔다",
        "expected_nodes": ["연말정산", "환급"],
        "expected_categories": ["LAW.tax", "MON.payment"],
        "note": "LAW ↔ MON 교차",
    },
    {
        "id": 6,
        "text": "요즘 번아웃 와서 퇴사 고민 중",
        "expected_nodes": ["번아웃", "퇴사"],
        "expected_categories": ["MND.mental", "WRK.jobchange"],
        "note": "MND ↔ WRK 교차",
    },
    {
        "id": 7,
        "text": "아이유 콘서트 다녀왔는데 노래방에서 따라 불렀다",
        "expected_nodes": ["아이유 콘서트", "노래방"],
        "expected_categories": ["CUL.show", "HOB.sing"],
        "note": "CUL vs HOB (보기 vs 하기)",
    },
    {
        "id": 8,
        "text": "사업자등록하려면 임대차계약서 필요하대",
        "expected_nodes": ["사업자등록", "임대차계약서"],
        "expected_categories": ["WRK.business", "LAW.contract"],
        "note": "WRK → LAW 참조 관계",
    },
    {
        "id": 9,
        "text": "당뇨 있어서 저탄수화물 식단으로 바꿨어",
        "expected_nodes": ["당뇨", "저탄수화물 식단"],
        "expected_categories": ["BOD.disease", "BOD.nutrition"],
        "note": "BOD vs FOD 경계",
    },
    {
        "id": 10,
        "text": "동호회 사람들이랑 북한산 등산했어",
        "expected_nodes": ["동호회", "북한산", "등산"],
        "expected_categories": ["HOB.social", "NAT.terrain", "HOB.outdoor"],
        "note": "HOB + NAT + PER 교차",
    },
]


# ─────────────────────────────────────────────
# 파서
# ─────────────────────────────────────────────

def _strip_codeblock(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()
    return text


def _try_parse(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def parse_json(raw: str) -> Optional[dict]:
    text = _strip_codeblock(raw)

    result = _try_parse(text)
    if result is not None:
        return result

    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        result = _try_parse(text[start:end])
        if result is not None:
            return result

    # 닫히지 않은 중괄호 보완
    candidate = text[start:] if start != -1 else text
    open_count = candidate.count("{") - candidate.count("}")
    if open_count > 0:
        fixed = candidate + "}" * open_count
        result = _try_parse(fixed)
        if result is not None:
            return result

    return None


# ─────────────────────────────────────────────
# 평가 함수
# ─────────────────────────────────────────────

def node_match(extracted: list[str], expected: list[str]) -> int:
    count = 0
    for exp in expected:
        exp_clean = exp.replace(" ", "").lower()
        for ext in extracted:
            ext_clean = ext.replace(" ", "").lower()
            if exp_clean in ext_clean or ext_clean in exp_clean:
                count += 1
                break
    return count


def category_match(result_map: dict[str, str], extracted_nodes: list[str], expected_cats: list[str]) -> int:
    """result_map: {노드명: 카테고리코드}. extracted_nodes와 교차해서 expected_cats 커버 수."""
    assigned = list(result_map.values())
    return sum(1 for ec in expected_cats if ec in assigned)


# ─────────────────────────────────────────────
# 메인 테스트 루프
# ─────────────────────────────────────────────

def run_tests(runs: int = 3, verbose: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"  LLM 2단계 추출 테스트  (반복 {runs}회 × {len(TEST_CASES)}문장)")
    print(f"  1단계: 노드/엣지  |  2단계: 카테고리 분류")
    print(f"{'='*60}")

    try:
        model = get_model()
        print(f"  모델: {model}\n")
    except OllamaError as e:
        print(f"[오류] {e}")
        sys.exit(1)

    # 집계 — 1단계
    s1_total = s1_ok = 0
    s1_node_hits = s1_node_total = 0
    s1_consistency_ok = 0

    # 집계 — 2단계
    s2_total = s2_ok = 0
    s2_cat_hits = s2_cat_total = 0
    s2_consistency_ok = 0

    for tc in TEST_CASES:
        print(f"\n[{tc['id']:02d}] {tc['text']}")
        print(f"      기대 노드: {tc['expected_nodes']}")
        print(f"      기대 분류: {tc['expected_categories']}  ({tc['note']})")

        nodes_per_run: list[list[str]] = []
        cats_correct_per_run: list[bool] = []

        for r in range(runs):
            # ── 1단계: 노드/엣지 추출 ──
            s1_total += 1
            t0 = time.time()
            try:
                raw1 = chat(SYSTEM_EXTRACT, tc["text"], temperature=0, max_tokens=512, model=model)
            except OllamaError as e:
                print(f"    run {r+1}: [1단계 오류] {e}")
                nodes_per_run.append([])
                cats_correct_per_run.append(False)
                continue

            t1 = time.time()
            parsed1 = parse_json(raw1)

            if parsed1 is None:
                print(f"    run {r+1}: [1단계 JSON 실패] ({t1-t0:.1f}s)  raw={raw1[:120]}")
                nodes_per_run.append([])
                cats_correct_per_run.append(False)
                continue

            s1_ok += 1
            extracted_nodes = list({
                node
                for tr in parsed1.get("triples", [])
                for node in (tr.get("source", ""), tr.get("target", ""))
                if node
            })
            nodes_per_run.append(extracted_nodes)
            n_hit = node_match(extracted_nodes, tc["expected_nodes"])
            s1_node_hits += n_hit
            s1_node_total += len(tc["expected_nodes"])

            n_status = "✓" if n_hit == len(tc["expected_nodes"]) else "△" if n_hit > 0 else "✗"

            if verbose:
                print(f"    run {r+1} [1단계] 노드{n_status}({n_hit}/{len(tc['expected_nodes'])})  ({t1-t0:.1f}s)")
                for tr in parsed1.get("triples", []):
                    print(f"      {tr.get('source','')} —({tr.get('edge','')})→ {tr.get('target','')}")

            # ── 2단계: 카테고리 분류 ──
            if not extracted_nodes:
                cats_correct_per_run.append(False)
                continue

            s2_total += 1
            node_list = "\n".join(f"- {n}" for n in extracted_nodes)
            user2 = f"문장: {tc['text']}\n\n노드 목록:\n{node_list}"
            t2 = time.time()
            try:
                raw2 = chat(SYSTEM_CATEGORIZE, user2, temperature=0, max_tokens=512, model=model)
            except OllamaError as e:
                print(f"    run {r+1}: [2단계 오류] {e}")
                cats_correct_per_run.append(False)
                continue

            t3 = time.time()
            parsed2 = parse_json(raw2)

            if parsed2 is None:
                print(f"    run {r+1}: [2단계 JSON 실패] ({t3-t2:.1f}s)  raw={raw2[:120]}")
                cats_correct_per_run.append(False)
                continue

            s2_ok += 1
            cat_map: dict[str, str] = parsed2.get("categories", {})
            c_hit = category_match(cat_map, extracted_nodes, tc["expected_categories"])
            s2_cat_hits += c_hit
            s2_cat_total += len(tc["expected_categories"])
            c_status = "✓" if c_hit == len(tc["expected_categories"]) else "△" if c_hit > 0 else "✗"
            cats_correct_per_run.append(c_hit == len(tc["expected_categories"]))

            if verbose:
                print(f"    run {r+1} [2단계] 분류{c_status}({c_hit}/{len(tc['expected_categories'])})  ({t3-t2:.1f}s)")
                for node, cat in cat_map.items():
                    print(f"      {node} → {cat}")
            else:
                n_status_short = "✓" if n_hit == len(tc["expected_nodes"]) else "△" if n_hit > 0 else "✗"
                print(f"    run {r+1}: 노드{n_status_short}({n_hit}/{len(tc['expected_nodes'])}) "
                      f"분류{c_status}({c_hit}/{len(tc['expected_categories'])})  "
                      f"({t1-t0:.1f}s + {t3-t2:.1f}s)")

        # 일관성
        s1_consistent = (
            sum(1 for n in nodes_per_run if n) == runs and
            all(node_match(n, tc["expected_nodes"]) == len(tc["expected_nodes"]) for n in nodes_per_run if n)
        )
        s2_consistent = sum(cats_correct_per_run) == runs

        if s1_consistent:
            s1_consistency_ok += 1
        if s2_consistent:
            s2_consistency_ok += 1

        print(f"      일관성: 노드={'✓' if s1_consistent else '✗'}  분류={'✓' if s2_consistent else '✗'}")

    # ─────────────────────────────────────────────
    # 최종 리포트
    # ─────────────────────────────────────────────
    N = len(TEST_CASES)
    print(f"\n{'='*60}")
    print(f"  최종 결과")
    print(f"{'='*60}")
    print(f"\n  [1단계 — 노드/엣지 추출]")
    print(f"    JSON 파싱 성공:  {s1_ok}/{s1_total} = {s1_ok/s1_total*100:.0f}%  (기준 90%)")
    print(f"    노드 정확도:     {s1_node_hits}/{s1_node_total} = {s1_node_hits/s1_node_total*100:.0f}%  (기준 80%)")
    print(f"    일관성:          {s1_consistency_ok}/{N} = {s1_consistency_ok/N*100:.0f}%  (기준 80%)")

    if s2_total > 0:
        print(f"\n  [2단계 — 카테고리 분류]")
        print(f"    JSON 파싱 성공:  {s2_ok}/{s2_total} = {s2_ok/s2_total*100:.0f}%  (기준 90%)")
        print(f"    카테고리 정확도: {s2_cat_hits}/{s2_cat_total} = {s2_cat_hits/s2_cat_total*100:.0f}%  (기준 70%)")
        print(f"    일관성:          {s2_consistency_ok}/{N} = {s2_consistency_ok/N*100:.0f}%  (기준 80%)")

    s1_pass = (s1_ok/s1_total >= 0.9) and (s1_node_hits/s1_node_total >= 0.8) and (s1_consistency_ok/N >= 0.8)
    s2_pass = s2_total > 0 and (s2_ok/s2_total >= 0.9) and (s2_cat_hits/s2_cat_total >= 0.7) and (s2_consistency_ok/N >= 0.8)

    print(f"\n  판정:")
    print(f"    1단계 (노드/엣지): {'✅ 합격' if s1_pass else '❌ 불합격'}")
    print(f"    2단계 (카테고리):  {'✅ 합격' if s2_pass else '❌ 불합격'}")

    if s1_pass and s2_pass:
        print(f"\n  ✅ 전체 합격 → 형태소 분석 제거, LLM 2단계 파이프라인으로 전환 가능")
    elif s1_pass and not s2_pass:
        print(f"\n  ⚠️  노드/엣지는 LLM으로 전환 가능, 카테고리는 키워드 사전 매칭 검토")
    elif not s1_pass:
        print(f"\n  ❌ 노드/엣지 추출 불안정 → 형태소 분석 유지")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM 2단계 추출 테스트")
    parser.add_argument("--runs", type=int, default=3, help="문장당 반복 횟수 (기본: 3)")
    parser.add_argument("--verbose", "-v", action="store_true", help="전체 트리플/카테고리 출력")
    args = parser.parse_args()
    run_tests(runs=args.runs, verbose=args.verbose)

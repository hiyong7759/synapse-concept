# Synapse 설계 — 카테고리 분류체계

**최종 업데이트**: 2026-04-19 (v2 분류 + v15 스키마 — 엣지 테이블 폐기, 카테고리가 연결 기준)

## 목적

v15부터 카테고리는 **연결 기준 그 자체**다. 별도 엣지 테이블이 없으므로, 노드 간 "의미적 연결"은 ① 같은 문장 바구니(`node_mentions`) 공출현 또는 ② **같은 카테고리 바구니(`node_categories`) 공유** + 인접 맵 한 홉 확장으로만 드러난다. 카테고리는 세 가지 역할을 한다.

**1. 연결 기준 (v15 핵심 역할)**
같은 카테고리를 공유하는 노드들은 서로 연결된 것으로 간주한다. 예: `스타벅스`와 `투썸` 두 노드가 `FOD.restaurant` 카테고리를 공유하면, 스타벅스가 언급된 질문에도 투썸 관련 sentence가 후보로 떠오른다.

**2. BFS 연결 부재 보완**
파편화된 입력으로 인해 같은 문장 바구니로 연결되지 않는 노드를 같은 카테고리 기준으로 추가 조회.
```
"허리디스크 L4-L5 진단받았어"  → 저장
"강남세브란스 정형외과 다니고 있어"  → 별도 문장으로 저장 → BFS 미연결
"허리 아파?" 질문 → BOD 카테고리 보완 → 강남세브란스 도달 가능
```

**3. 소형 모델의 인출 범위 한계 보완**
2B 모델은 질문 의도에서 인접 카테고리까지 추론하기 어렵다.
카테고리 인접 맵을 코드에 하드코딩하여 모델 판단 없이 탐색 범위를 자동 확장.

---

## 저장 방식 (v15)

카테고리는 `node_categories` 테이블에 **자동 저장**되며 `origin` 컬럼으로 출처를 식별한다. 사용자는 `/review`의 `ai_generated`/`rule_generated` 목록 뷰에서 잘못된 분류를 즉시 삭제할 수 있다.

| origin | 생성 경로 | 예시 |
|--------|-----------|------|
| `user` | 마크다운 heading 경로 (사용자 명시) | `# 더나은\n## 개발팀` → `더나은.개발팀` |
| `ai` | extract 어댑터 추론 | `허리디스크` 노드 → `BOD.disease` |
| `rule` | 결정론적 규칙 | 날짜 분할(`4월` → `TIM.month`), 부정부사(`안/못` 표식) |

한 노드가 여러 카테고리를 가질 수 있으므로(다대다), 동일 노드에 대해 `user` / `ai` / `rule` origin이 공존 가능.

---

## 분류체계 (v2 — 19개 대분류)

형식: `대분류코드.소분류코드` (영문 소문자)
예시: `BOD.disease`, `TEC.hw`, `MON.spending`

| # | 코드 | 분류명 | 한줄 정의 | 소분류 |
|---|------|--------|-----------|--------|
| 1 | **PER** | 사람 | 누구인가 (인물, 관계, 조직) | `individual` `family` `friend` `colleague` `public` `org` |
| 2 | **BOD** | 신체·건강 | 몸과 관련된 모든 것 | `part` `disease` `medical` `exercise` `nutrition` `sleep` |
| 3 | **MND** | 심리·감정 | 마음, 정서, 정신건강 | `emotion` `personality` `mental` `motivation` `coping` |
| 4 | **FOD** | 음식·요리 | 먹는 것, 만드는 것, 먹으러 가는 것 | `ingredient` `recipe` `restaurant` `drink` `product` |
| 5 | **LIV** | 주거·생활 | 집, 살림, 생활환경 | `housing` `appliance` `interior` `supply` `maintenance` `moving` |
| 6 | **MON** | 돈·경제 | 내 돈의 흐름 (벌기, 쓰기, 불리기) | `income` `spending` `invest` `payment` `loan` `insurance` |
| 7 | **WRK** | 일·커리어 | 직장, 직무, 사업, 성장 | `workplace` `role` `jobchange` `business` `cert` `tool` |
| 8 | **TEC** | 기술·디지털 | IT, 기기, 소프트웨어, 개발 | `sw` `hw` `ai` `infra` `data` `security` |
| 9 | **EDU** | 배움·지식 | 학습, 교육, 학문 | `school` `online` `language` `academic` `reading` `exam` |
| 10 | **LAW** | 법·제도 | 법률, 규정, 행정, 세무 | `statute` `contract` `admin` `rights` `tax` |
| 11 | **TRV** | 이동·여행 | 교통, 관광, 장소 | `domestic` `abroad` `transport` `stay` `flight` `place` |
| 12 | **NAT** | 자연·환경 | 동식물, 날씨, 지리, 우주 | `animal` `plant` `weather` `terrain` `ecology` `space` |
| 13 | **CUL** | 문화·예술 | 보는 것 (영화, 책, 전시, 공연) | `film` `music` `book` `art` `show` `media` |
| 14 | **HOB** | 여가·취미 | 하는 것 (노래방, 낚시, 캠핑, 게임) | `sport` `outdoor` `game` `craft` `sing` `collect` `social` |
| 15 | **SOC** | 사회·시사 | 뉴스, 정치, 국제, 사회문제 | `politics` `international` `incident` `economy` `issue` `news` |
| 16 | **REL** | 관계·소통 | 사람 사이의 상호작용 | `romance` `conflict` `comm` `manner` `online` |
| 17 | **REG** | 종교·신앙 | 종교, 신앙생활, 의례 | `christianity` `buddhism` `catholic` `islam` `other` `practice` |
| 18 | **TIM** | 시간 | 언제 (날짜, 시점, 기간) | `year` `month` `day` `date` `time` `relative` `period` |
| 19 | **ACT** | 행동·동작 | 무엇을 하는가 (동사로 추출된 개념) | `eat` `move` `use` `make` `talk` `think` `rest` `work` |

---

## 소분류 상세

### PER — 사람
노드 자체가 "누구"인 경우. 조직 포함.
- `individual` — 특정 개인 (조용희, 박지수)
- `family` — 가족 (엄마, 딸)
- `friend` — 친구, 지인
- `colleague` — 직장동료, 팀원
- `public` — 유명인, 공인
- `org` — 회사, 기관, 단체 (삼성, 강남세브란스)

### BOD — 신체·건강
- `part` — 신체 부위 (허리, L4-L5, 무릎)
- `disease` — 질병, 증상 (허리디스크, 감기, 두통)
- `medical` — 치료, 병원, 약 (강남세브란스, 물리치료, 이부프로펜)
- `exercise` — 운동 종류 (데드리프트, 수영)
- `nutrition` — 식이, 영양 (저탄수, 비타민D)
- `sleep` — 수면 (불면증, 수면무호흡)

### MND — 심리·감정
- `emotion` — 감정 (불안, 기쁨, 우울)
- `personality` — 성격, 기질 (MBTI, 내향적)
- `mental` — 정신건강 상태 (번아웃, 공황)
- `motivation` — 동기, 목표 의식
- `coping` — 대처 방법 (명상, 일기쓰기)

### FOD — 음식·요리
- `ingredient` — 식재료 (닭가슴살, 고수)
- `recipe` — 요리법, 메뉴
- `restaurant` — 식당, 카페 (스타벅스, 을지로 순대국)
- `drink` — 음료, 주류
- `product` — 가공식품, 제품

### LIV — 주거·생활
- `housing` — 집, 주거 형태 (원룸, 아파트)
- `appliance` — 가전 (식기세척기, 에어프라이어)
- `interior` — 가구, 인테리어 (시디즈T80)
- `supply` — 생활용품, 소모품
- `maintenance` — 수리, 관리
- `moving` — 이사, 이전

### MON — 돈·경제
- `income` — 수입, 급여
- `spending` — 지출, 소비
- `invest` — 투자 (주식, 부동산)
- `payment` — 결제 수단, 청구
- `loan` — 대출, 부채
- `insurance` — 보험

### WRK — 일·커리어
- `workplace` — 회사, 근무지 (더나은, 네이버)
- `role` — 직책, 직무 (개발팀장, PM)
- `jobchange` — 이직, 퇴사, 취업
- `business` — 사업, 창업
- `cert` — 자격증, 면허
- `tool` — 업무 도구 (Jira, Slack)

### TEC — 기술·디지털
- `sw` — 소프트웨어, 앱, 프레임워크 (React, Docker)
- `hw` — 하드웨어, 기기 (맥미니, M4)
- `ai` — AI 모델, 서비스 (ChatGPT, Claude)
- `infra` — 인프라, 서버, 클라우드
- `data` — 데이터, DB
- `security` — 보안

### EDU — 배움·지식
- `school` — 학교, 전공 (컴퓨터공학, 연세대)
- `online` — 온라인 강의 (인프런, 유데미)
- `language` — 언어 학습 (영어, 일본어)
- `academic` — 학문 분야, 논문
- `reading` — 독서, 도서 (학습 목적)
- `exam` — 시험, 수험

### LAW — 법·제도
- `statute` — 법령, 조문
- `contract` — 계약
- `admin` — 행정 처리 (등기, 신고)
- `rights` — 권리, 의무
- `tax` — 세금, 세무, 연말정산

### TRV — 이동·여행
- `domestic` — 국내 여행, 지역
- `abroad` — 해외 여행, 국가
- `transport` — 교통수단 (버스, KTX)
- `stay` — 숙박 (호텔, 에어비앤비)
- `flight` — 항공
- `place` — 장소, 지명 (진천, 강남역)

### NAT — 자연·환경
- `animal` — 동물, 반려동물
- `plant` — 식물
- `weather` — 날씨, 기후
- `terrain` — 지형, 지리
- `ecology` — 환경, 생태
- `space` — 우주, 천문

### CUL — 문화·예술 ("보는" 소비)
- `film` — 영화, 드라마
- `music` — 음악 감상
- `book` — 책 (소비로서의 독서)
- `art` — 전시, 미술
- `show` — 공연, 전시
- `media` — 유튜브, 팟캐스트

### HOB — 여가·취미 ("하는" 활동)
- `sport` — 스포츠 (수영, 테니스)
- `outdoor` — 야외 활동 (등산, 캠핑, 낚시)
- `game` — 게임
- `craft` — 만들기 (DIY, 뜨개질)
- `sing` — 노래방, 악기 연주
- `collect` — 수집, 덕질
- `social` — 모임, 동호회

### SOC — 사회·시사
- `politics` — 정치
- `international` — 국제 관계
- `incident` — 사건, 사고
- `economy` — 거시 경제 (개인 재무가 아닌 것)
- `issue` — 사회 이슈
- `news` — 뉴스

### REL — 관계·소통
- `romance` — 연애, 결혼
- `conflict` — 갈등, 다툼
- `comm` — 소통 방식, 대화
- `manner` — 예절, 에티켓
- `online` — 온라인 관계, SNS

### REG — 종교·신앙
- `christianity` `buddhism` `catholic` `islam` `other` — 종파
- `practice` — 신앙 활동 (예배, 기도, 성지순례)

### TIM — 시간
CLAUDE.md 날짜 분할 규칙과 직결. 시간 단위를 독립 노드로 분해하여 `node_mentions` 교집합으로 시간 범위 쿼리를 지원한다.
- `year` — 연 단위 (`2026년`)
- `month` — 월 단위 (`4월`)
- `day` — 일 단위 (`18일`)
- `date` — 통째 날짜 노드 (`2026년 4월 18일`)
- `time` — 시각 (`오전 10시`, `14:30`)
- `relative` — 상대 시간 (오늘, 어제, 내일, 이번주)
- `period` — 기간·시간대 (오전, 오후, 새벽, 봄, 여름)

### ACT — 행동·동작
동사로 추출된 개념. **대상(명사)과 행위(동사)는 각자 별도 노드**로 분리된다.
- `eat` — 먹다, 마시다 (식사·음용 행위)
- `move` — 가다, 오다, 이동하다
- `use` — 쓰다, 사용하다 (도구·기기 조작)
- `make` — 만들다, 제작하다
- `talk` — 말하다, 대화하다
- `think` — 생각하다, 고민하다
- `rest` — 쉬다, 휴식하다
- `work` — 일하다, 작업하다

---

## 분류 경계 규칙

자주 헷갈리는 경계:

| 상황 | 분류 | 이유 |
|------|------|------|
| 영화 감상 | CUL.film | 보는 것 |
| 영화 제작 참여 | HOB.craft | 하는 것 |
| 음악 감상 | CUL.music | 보는 것 |
| 기타 치기, 노래방 | HOB.sing | 하는 것 |
| 독서 (취미·소비) | CUL.book | 보는 것 |
| 독서 (학습 목적) | EDU.reading | 배움 |
| 수영 (건강 목적) | BOD.exercise | 몸 관리 |
| 수영 (취미 목적) | HOB.sport | 여가 |
| 세금·연말정산 (제도) | LAW.tax | 법·행정 |
| 세금·연말정산 (내 돈) | MON.payment | 개인 재무 |
| 강남세브란스 (병원 기관) | PER.org → BOD.medical 중 BOD.medical | 건강 맥락 우선 |
| 거시 경제 뉴스 | SOC.economy | 개인 재무 아님 |
| 내 주식 수익 | MON.invest | 개인 재무 |
| "운동했다" (행위) vs "데드리프트" (종목) | 각각 ACT.rest / BOD.exercise | 대상 = BOD, 행위 = ACT (각자 별도 노드) |
| "스타벅스 갔다" | FOD.restaurant + ACT.move | 대상·행위 각자 |
| "2026-04-18" 날짜 | TIM.date (+ year/month/day 분할 노드) | 시간 단위는 교집합 쿼리용으로 분해 |

---

## 카테고리 인접 맵 (Cross-Category Affinity)

하나의 개념이 여러 카테고리에 걸치거나, 질문 의도와 연관된 다른 카테고리를 함께 탐색해야 맥락이 풍부해지는 관계.

BFS 보완 시 같은 대분류 외에 인접 소분류도 추가 조회한다.

### 설계 원칙

인접 맵 구성 5개 원칙은 **`docs/DESIGN_PRINCIPLES.md §4` 카테고리·인접 맵 원칙** 참고.
(소분류 레벨 · 크로스 대분류만 · 단방향 정의·양방향 적용 · 약한 연관 제외 · 데이터 기반 검증)

### 인접 맵 (v2 — 소분류 레벨)

```
# BOD (신체·건강)
BOD.disease   ↔ MND.mental      만성질환 ↔ 번아웃·우울 (몸이 아프면 마음도)
BOD.sleep     ↔ MND.mental      수면 장애 ↔ 정신건강
BOD.sleep     ↔ MND.coping      수면 ↔ 명상·루틴 등 대처법
BOD.exercise  ↔ HOB.sport       건강 목적 운동 ↔ 운동 취미
BOD.nutrition ↔ FOD.ingredient  영양 관리 ↔ 식재료
BOD.nutrition ↔ FOD.product     영양 관리 ↔ 건강식품
BOD.medical   ↔ MON.insurance   병원·치료 ↔ 의료보험

# MND (심리·감정)
MND.emotion   ↔ REL.romance     감정 ↔ 연애 감정
MND.emotion   ↔ REL.conflict    감정 ↔ 갈등·다툼
MND.motivation ↔ WRK.jobchange  동기 ↔ 이직 결심
MND.motivation ↔ EDU.online     배우고 싶다는 동기 ↔ 강의 탐색
MND.coping    ↔ HOB.sport       스트레스 해소 ↔ 운동
MND.coping    ↔ HOB.outdoor     스트레스 해소 ↔ 등산·캠핑
MND.coping    ↔ REG.practice    대처법 ↔ 기도·명상 신앙 활동

# HOB (여가·취미)
HOB.sing      ↔ CUL.music       노래방·악기 ↔ 음악 감상·아티스트
HOB.outdoor   ↔ TRV.domestic    등산·캠핑 ↔ 국내 여행지
HOB.outdoor   ↔ NAT.terrain     야외 활동 ↔ 지형·산
HOB.outdoor   ↔ NAT.weather     야외 계획 ↔ 날씨
HOB.game      ↔ TEC.sw          게임 ↔ 플랫폼·앱
HOB.game      ↔ TEC.hw          게임 ↔ PC·콘솔
HOB.craft     ↔ LIV.supply      DIY·만들기 ↔ 재료·용품
HOB.collect   ↔ CUL.art         수집·덕질 ↔ 예술품
HOB.collect   ↔ MON.spending    수집 ↔ 지출 (얼마 썼는지)
HOB.social    ↔ REL.comm        모임·동호회 ↔ 소통 방식
HOB.social    ↔ TRV.place       모임 ↔ 장소

# CUL (문화·예술)
CUL.book      ↔ EDU.reading     책 소비 ↔ 학습 독서
CUL.book      ↔ EDU.academic    책 ↔ 학문·논문
CUL.art       ↔ HOB.collect     예술품 ↔ 수집
CUL.media     ↔ TEC.sw          유튜브·팟캐스트 ↔ 플랫폼·앱
CUL.show      ↔ TRV.place       공연·전시 ↔ 장소

# WRK (일·커리어)
WRK.workplace ↔ PER.colleague   직장 ↔ 동료
WRK.workplace ↔ MON.income      직장 ↔ 급여
WRK.workplace ↔ LAW.rights      직장 ↔ 근로권리·취업규칙
WRK.jobchange ↔ MND.motivation  이직 ↔ 동기·감정
WRK.jobchange ↔ MON.income      이직 ↔ 연봉 협상
WRK.cert      ↔ EDU.exam        자격증 ↔ 시험 준비
WRK.cert      ↔ EDU.online      자격증 ↔ 온라인 강의
WRK.business  ↔ MON.income      사업 ↔ 수입
WRK.business  ↔ LAW.contract    사업 ↔ 계약
WRK.tool      ↔ TEC.sw          업무 도구 ↔ 소프트웨어
WRK.tool      ↔ TEC.ai          업무 도구 ↔ AI 서비스

# MON (돈·경제)
MON.income    ↔ LAW.tax         급여 ↔ 세금·연말정산
MON.payment   ↔ LAW.tax         납부 ↔ 세금
MON.loan      ↔ LIV.housing     대출 ↔ 집·부동산
MON.loan      ↔ LAW.contract    대출 ↔ 계약서
MON.insurance ↔ LAW.contract    보험 ↔ 계약
MON.invest    ↔ SOC.economy     투자 ↔ 거시경제·금리

# LAW (법·제도)
LAW.contract  ↔ LIV.housing     계약 ↔ 전세·부동산
LAW.contract  ↔ MON.loan        계약 ↔ 대출
LAW.contract  ↔ WRK.business    계약 ↔ 사업·거래
LAW.rights    ↔ TEC.security    개인정보 권리 ↔ 보안
LAW.statute   ↔ WRK.workplace   법령·취업규칙 ↔ 직장
LAW.admin     ↔ LIV.moving      행정 처리 ↔ 이사

# EDU (배움·지식)
EDU.school    ↔ WRK.cert        전공·학교 ↔ 자격증
EDU.online    ↔ TEC.sw          온라인 강의 ↔ 플랫폼
EDU.language  ↔ TRV.abroad      언어 학습 ↔ 해외여행
EDU.reading   ↔ CUL.book        학습 독서 ↔ 책 소비
EDU.academic  ↔ CUL.book        학문 ↔ 책

# TRV (이동·여행)
TRV.domestic  ↔ FOD.restaurant  국내 여행 ↔ 맛집
TRV.domestic  ↔ HOB.outdoor     국내 여행지 ↔ 야외 활동
TRV.domestic  ↔ NAT.weather     국내 여행 ↔ 날씨
TRV.abroad    ↔ FOD.restaurant  해외여행 ↔ 현지 음식
TRV.abroad    ↔ EDU.language    해외여행 ↔ 언어
TRV.abroad    ↔ SOC.international 해외여행 ↔ 국제 정세
TRV.place     ↔ NAT.terrain     장소 ↔ 지형
TRV.place     ↔ CUL.show        장소 ↔ 공연·전시
TRV.place     ↔ HOB.social      장소 ↔ 모임

# NAT (자연·환경)
NAT.animal    ↔ LIV.supply      반려동물 ↔ 용품·사료
NAT.weather   ↔ HOB.outdoor     날씨 ↔ 야외 활동
NAT.weather   ↔ TRV.domestic    날씨 ↔ 국내 여행
NAT.terrain   ↔ HOB.outdoor     지형 ↔ 등산·캠핑
NAT.terrain   ↔ TRV.place       지형 ↔ 장소
NAT.ecology   ↔ SOC.issue       환경 ↔ 사회 이슈

# LIV (주거·생활)
LIV.housing   ↔ MON.loan        집 ↔ 대출·담보
LIV.housing   ↔ LAW.contract    집 ↔ 전세·계약
LIV.appliance ↔ TEC.hw          가전 ↔ 기기·전자제품
LIV.appliance ↔ TEC.sw          가전 ↔ 연동 앱·스마트홈
LIV.moving    ↔ TRV.place       이사 ↔ 지역·장소
LIV.moving    ↔ LAW.admin       이사 ↔ 행정 처리
LIV.supply    ↔ HOB.craft       생활용품 ↔ DIY 재료
LIV.supply    ↔ NAT.animal      용품 ↔ 반려동물

# TEC (기술·디지털)
TEC.hw        ↔ LIV.appliance   기기 ↔ 가전
TEC.hw        ↔ HOB.game        PC·콘솔 ↔ 게임
TEC.sw        ↔ WRK.tool        소프트웨어 ↔ 업무 도구
TEC.sw        ↔ HOB.game        앱·플랫폼 ↔ 게임
TEC.sw        ↔ EDU.online      플랫폼 ↔ 온라인 강의
TEC.sw        ↔ CUL.media       앱 ↔ 유튜브·팟캐스트
TEC.ai        ↔ WRK.tool        AI ↔ 업무 도구
TEC.ai        ↔ SOC.issue       AI ↔ 사회 이슈
TEC.security  ↔ LAW.rights      보안 ↔ 개인정보 권리

# PER (사람)
PER.colleague ↔ WRK.workplace   동료 ↔ 직장
PER.org       ↔ WRK.workplace   기관·회사 ↔ 직장
PER.family    ↔ REL.romance     가족 ↔ 연애·결혼
PER.friend    ↔ REL.comm        친구 ↔ 소통·관계

# REL (관계·소통)
REL.romance   ↔ MND.emotion     연애 ↔ 감정
REL.romance   ↔ PER.family      연애·결혼 ↔ 가족
REL.conflict  ↔ MND.emotion     갈등 ↔ 감정
REL.conflict  ↔ WRK.workplace   직장 내 갈등 ↔ 직장
REL.comm      ↔ WRK.workplace   소통 ↔ 직장
REL.online    ↔ TEC.sw          온라인 관계 ↔ SNS·앱
REL.online    ↔ SOC.issue       온라인 ↔ 사회 이슈

# SOC (사회·시사)
SOC.economy   ↔ MON.invest      거시경제 ↔ 개인 투자
SOC.issue     ↔ NAT.ecology     사회 이슈 ↔ 환경
SOC.issue     ↔ TEC.ai          사회 이슈 ↔ AI
SOC.issue     ↔ REL.online      사회 이슈 ↔ 온라인
SOC.international ↔ TRV.abroad  국제 정세 ↔ 해외여행
SOC.politics  ↔ LAW.statute     정치 ↔ 법령

# REG (종교·신앙)
REG.practice  ↔ MND.coping      신앙 활동 ↔ 심리적 대처

# FOD (음식·요리)
FOD.restaurant ↔ TRV.domestic   맛집 ↔ 국내 여행
FOD.restaurant ↔ TRV.abroad     현지 음식 ↔ 해외여행
FOD.ingredient ↔ BOD.nutrition  식재료 ↔ 영양 관리
FOD.product   ↔ BOD.nutrition   건강식품 ↔ 영양 관리

# ACT (행동·동작) — 대상 카테고리와 연결
ACT.eat       ↔ FOD.restaurant  먹는 행위 ↔ 식당
ACT.eat       ↔ FOD.ingredient  먹는 행위 ↔ 식재료
ACT.move      ↔ TRV.transport   이동 ↔ 교통수단
ACT.move      ↔ TRV.place       이동 ↔ 장소
ACT.use       ↔ TEC.hw          사용 ↔ 하드웨어
ACT.use       ↔ TEC.sw          사용 ↔ 소프트웨어
ACT.make      ↔ HOB.craft       만들기 ↔ 공예·DIY
ACT.talk      ↔ REL.comm        대화 ↔ 소통
ACT.think     ↔ MND.motivation  사고·고민 ↔ 동기
ACT.rest      ↔ BOD.sleep       휴식 ↔ 수면
ACT.work      ↔ WRK.role        일 ↔ 직무
```

### 독립 소분류 (인접 없음)

인접 맵에 없는 소분류 — 카테고리 보완 조회 자체가 발생하지 않음.
(대분류 전체 탐색은 하지 않는다. 인접 맵에 있는 소분류만 보완 조회.)

```
BOD.part        신체 부위 (L4-L5, 무릎) — 독립적
MND.personality 성격·기질 — 독립적
FOD.recipe      요리법 — 독립적
FOD.drink       음료·주류 — 독립적
TRV.transport   교통수단 — 독립적
TRV.stay        숙박 — 독립적
TRV.flight      항공 — 독립적
NAT.plant       식물 — 독립적
NAT.space       우주 — 독립적
LIV.interior    가구·인테리어 — 독립적
LIV.maintenance 수리·관리 — 독립적
TEC.infra       서버·클라우드 — 독립적
TEC.data        데이터·DB — 독립적
PER.individual  특정 개인 — 독립적
PER.public      유명인 — 독립적
REL.manner      예절·에티켓 — 독립적
SOC.incident    사건·사고 — 독립적
SOC.news        뉴스 — 독립적
REG.*           종파 구분 — 독립적 (practice 제외)
TIM.*           시간 전 소분류 — 독립적 (year/month/day/date/time/relative/period)
                사유: 시간은 모든 주제와 얽혀 인접 정의 시 노이즈 폭증.
                      검색은 node_mentions 교집합으로 이미 해결됨 (CLAUDE.md 인출 예시).
```

### 코드 표현 (engine/retrieve.py)

단방향으로 정의, 코드에서 역방향 자동 포함.

```python
# 단방향 정의 목록 — 코드에서 양방향으로 전개
_ADJACENT_PAIRS: list[tuple[str, str]] = [
    # BOD
    ("BOD.disease",    "MND.mental"),
    ("BOD.sleep",      "MND.mental"),
    ("BOD.sleep",      "MND.coping"),
    ("BOD.exercise",   "HOB.sport"),
    ("BOD.nutrition",  "FOD.ingredient"),
    ("BOD.nutrition",  "FOD.product"),
    ("BOD.medical",    "MON.insurance"),
    # MND
    ("MND.emotion",    "REL.romance"),
    ("MND.emotion",    "REL.conflict"),
    ("MND.motivation", "WRK.jobchange"),
    ("MND.motivation", "EDU.online"),
    ("MND.coping",     "HOB.sport"),
    ("MND.coping",     "HOB.outdoor"),
    ("MND.coping",     "REG.practice"),
    # HOB
    ("HOB.sing",       "CUL.music"),
    ("HOB.outdoor",    "TRV.domestic"),
    ("HOB.outdoor",    "NAT.terrain"),
    ("HOB.outdoor",    "NAT.weather"),
    ("HOB.game",       "TEC.sw"),
    ("HOB.game",       "TEC.hw"),
    ("HOB.craft",      "LIV.supply"),
    ("HOB.collect",    "CUL.art"),
    ("HOB.collect",    "MON.spending"),
    ("HOB.social",     "REL.comm"),
    ("HOB.social",     "TRV.place"),
    # CUL
    ("CUL.book",       "EDU.reading"),
    ("CUL.book",       "EDU.academic"),
    ("CUL.media",      "TEC.sw"),
    ("CUL.show",       "TRV.place"),
    # WRK
    ("WRK.workplace",  "PER.colleague"),
    ("WRK.workplace",  "MON.income"),
    ("WRK.workplace",  "LAW.rights"),
    ("WRK.jobchange",  "MON.income"),
    ("WRK.cert",       "EDU.exam"),
    ("WRK.cert",       "EDU.online"),
    ("WRK.business",   "MON.income"),
    ("WRK.business",   "LAW.contract"),
    ("WRK.tool",       "TEC.sw"),
    ("WRK.tool",       "TEC.ai"),
    # MON
    ("MON.income",     "LAW.tax"),
    ("MON.payment",    "LAW.tax"),
    ("MON.loan",       "LIV.housing"),
    ("MON.loan",       "LAW.contract"),
    ("MON.insurance",  "LAW.contract"),
    ("MON.invest",     "SOC.economy"),
    # LAW
    ("LAW.contract",   "LIV.housing"),
    ("LAW.rights",     "TEC.security"),
    ("LAW.statute",    "WRK.workplace"),
    ("LAW.admin",      "LIV.moving"),
    # EDU
    ("EDU.school",     "WRK.cert"),
    ("EDU.online",     "TEC.sw"),
    ("EDU.language",   "TRV.abroad"),
    # TRV
    ("TRV.domestic",   "FOD.restaurant"),
    ("TRV.domestic",   "HOB.outdoor"),
    ("TRV.domestic",   "NAT.weather"),
    ("TRV.abroad",     "FOD.restaurant"),
    ("TRV.abroad",     "SOC.international"),
    ("TRV.place",      "NAT.terrain"),
    # NAT
    ("NAT.animal",     "LIV.supply"),
    ("NAT.ecology",    "SOC.issue"),
    # LIV
    ("LIV.housing",    "MON.loan"),
    ("LIV.housing",    "LAW.contract"),
    ("LIV.appliance",  "TEC.hw"),
    ("LIV.appliance",  "TEC.sw"),
    ("LIV.moving",     "TRV.place"),
    # TEC
    ("TEC.ai",         "SOC.issue"),
    # PER
    ("PER.colleague",  "WRK.workplace"),
    ("PER.org",        "WRK.workplace"),
    ("PER.family",     "REL.romance"),
    ("PER.friend",     "REL.comm"),
    # REL
    ("REL.conflict",   "WRK.workplace"),
    ("REL.online",     "SOC.issue"),
    # SOC
    ("SOC.international", "TRV.abroad"),
    ("SOC.politics",   "LAW.statute"),
    # REG
    ("REG.practice",   "MND.coping"),
    # ACT (행동·동작) — TIM은 독립 대분류라 인접 없음
    ("ACT.eat",        "FOD.restaurant"),
    ("ACT.eat",        "FOD.ingredient"),
    ("ACT.move",       "TRV.transport"),
    ("ACT.move",       "TRV.place"),
    ("ACT.use",        "TEC.hw"),
    ("ACT.use",        "TEC.sw"),
    ("ACT.make",       "HOB.craft"),
    ("ACT.talk",       "REL.comm"),
    ("ACT.think",      "MND.motivation"),
    ("ACT.rest",       "BOD.sleep"),
    ("ACT.work",       "WRK.role"),
]

def _build_adjacent_map(pairs: list[tuple[str, str]]) -> dict[str, list[str]]:
    """단방향 쌍 목록에서 양방향 딕셔너리 생성."""
    result: dict[str, list[str]] = {}
    for a, b in pairs:
        result.setdefault(a, []).append(b)
        result.setdefault(b, []).append(a)
    return result

ADJACENT_SUBCATEGORIES: dict[str, list[str]] = _build_adjacent_map(_ADJACENT_PAIRS)
```

### 미래 계획 — 데이터 기반 보완

데이터가 쌓이면 카테고리 간 **문장 바구니 공출현 빈도**로 인접 맵을 검증·보완한다.

```sql
-- 카테고리 간 공출현(node_mentions 기반) 빈도 쿼리
-- v15: edges 테이블 폐기, node_categories 다대다 테이블만 사용
SELECT
    c1.category AS cat_a,
    c2.category AS cat_b,
    COUNT(DISTINCT m1.sentence_id) AS cooccur_count
FROM node_mentions m1
JOIN node_mentions m2 ON m1.sentence_id = m2.sentence_id
                     AND m1.node_id < m2.node_id
JOIN node_categories c1 ON c1.node_id = m1.node_id
JOIN node_categories c2 ON c2.node_id = m2.node_id
WHERE c1.category != c2.category
GROUP BY cat_a, cat_b
ORDER BY cooccur_count DESC;
```

인접 맵 조정 기준:
- cooccur_count 상위 → 인접 추가 검토
- 현재 인접이지만 cooccur_count 낮음 → 제거 검토
- 조정 시 이 문서와 코드 동시 업데이트

---

## 참조

- 스키마: `docs/DESIGN_HYPERGRAPH.md` — `node_categories` 테이블 (다대다, 카테고리 하이퍼엣지 멤버십)
- 인출 파이프라인: `docs/DESIGN_PIPELINE.md` — 카테고리 보완 조회
- 파인튜닝 데이터: `data/finetune/tasks/extract-core/train.jsonl`
- 구현: `engine/retrieve.py` — `_get_category_supplement_nodes()`

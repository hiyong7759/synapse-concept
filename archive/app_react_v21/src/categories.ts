/**
 * v12 카테고리 / 의미 관계 한글·의미 매핑.
 * 17개 대분류 + 약 80개 소분류 + 의미 관계 5종.
 *
 * 사용:
 *   labelOfCategory("BOD.disease") → "신체.질병"
 *   descOfCategory("BOD.disease")  → "병·진단·증상"
 */

export type CategoryEntry = { label: string; desc: string };

// ─── 의미 관계 (edges.label) ───────────────────────────────
export const RELATION_LABELS: Record<string, CategoryEntry> = {
  similar: { label: '유사',   desc: '같거나 비슷한 개념' },
  cause:   { label: '원인',   desc: 'A가 B를 일으킴' },
  contain: { label: '포함',   desc: 'A가 B를 품음' },
  avoid:   { label: '회피',   desc: '관련 있지만 피하는' },
  cooccur: { label: '공출현', desc: '같은 맥락에 자주 함께 등장' },
};

export function labelOfRelation(code: string): string {
  return RELATION_LABELS[code]?.label ?? code;
}
export function descOfRelation(code: string): string | undefined {
  return RELATION_LABELS[code]?.desc;
}

// ─── 카테고리 (node_categories.category) ──────────────────
//
// 키:
//   - 대분류 단독 (3글자 영문): "BOD"
//   - 대/소 점 구분: "BOD.disease"
//
// 사용자 정의 경로(예: "병원.2026-04-18", "더나은.개발팀")는 매핑에 없으므로 원형 그대로 표시.
export const CATEGORY_LABELS: Record<string, CategoryEntry> = {
  // ── 대분류 17개 ──────────────────────────────────────────
  PER: { label: '인물', desc: '사람과 관계 대상' },
  BOD: { label: '신체', desc: '몸·건강·운동' },
  MND: { label: '정신', desc: '감정·생각·심리' },
  FOD: { label: '음식', desc: '재료·요리·식당' },
  LIV: { label: '생활', desc: '주거·살림·이사' },
  MON: { label: '금융', desc: '수입·지출·투자' },
  WRK: { label: '직장', desc: '회사·업무·이직' },
  TEC: { label: '기술', desc: '디바이스·소프트웨어·AI' },
  EDU: { label: '교육', desc: '학교·학습·자격' },
  LAW: { label: '법/제도', desc: '법령·계약·권리·세금' },
  TRV: { label: '여행/장소', desc: '국내·해외·장소' },
  NAT: { label: '자연', desc: '날씨·동식물·지형' },
  CUL: { label: '문화', desc: '음악·영화·책·예술' },
  HOB: { label: '취미', desc: '스포츠·게임·공예' },
  SOC: { label: '사회', desc: '이슈·정치·국제' },
  REL: { label: '관계', desc: '연애·친교·갈등' },
  REG: { label: '종교', desc: '신앙·수행·천주교' },

  // ── PER ─────────────────────────────────────────────────
  'PER.individual': { label: '인물.개인',   desc: '특정 한 사람' },
  'PER.family':     { label: '인물.가족',   desc: '가족 구성원' },
  'PER.friend':     { label: '인물.친구',   desc: '친구 관계' },
  'PER.colleague':  { label: '인물.동료',   desc: '직장 동료·상사' },
  'PER.public':     { label: '인물.공인',   desc: '공인·유명인' },
  'PER.org':        { label: '인물.조직',   desc: '회사·단체' },

  // ── BOD ─────────────────────────────────────────────────
  'BOD.disease':   { label: '신체.질병',   desc: '병·진단·증상' },
  'BOD.medical':   { label: '신체.의료',   desc: '병원·약·처방' },
  'BOD.part':      { label: '신체.부위',   desc: '신체 부위' },
  'BOD.sleep':     { label: '신체.수면',   desc: '잠·휴식·피로' },
  'BOD.exercise':  { label: '신체.운동',   desc: '운동·체력' },
  'BOD.nutrition': { label: '신체.영양',   desc: '영양·섭취·식습관' },

  // ── MND ─────────────────────────────────────────────────
  'MND.mental':     { label: '정신.정신건강', desc: '정신건강·진단' },
  'MND.emotion':    { label: '정신.감정',     desc: '기분·감정 상태' },
  'MND.coping':     { label: '정신.대처',     desc: '스트레스 대처·회복' },
  'MND.motivation': { label: '정신.동기',     desc: '의욕·동기 부여' },

  // ── FOD ─────────────────────────────────────────────────
  'FOD.ingredient': { label: '음식.재료',   desc: '식재료' },
  'FOD.recipe':     { label: '음식.요리',   desc: '레시피·조리' },
  'FOD.restaurant': { label: '음식.식당',   desc: '맛집·외식' },
  'FOD.product':    { label: '음식.가공',   desc: '가공식품·제품' },

  // ── LIV ─────────────────────────────────────────────────
  'LIV.housing':   { label: '생활.주거',   desc: '집·전월세·매매' },
  'LIV.moving':    { label: '생활.이사',   desc: '이사·이주' },
  'LIV.appliance': { label: '생활.가전',   desc: '가전제품' },
  'LIV.supply':    { label: '생활.용품',   desc: '생활용품·소모품' },

  // ── MON ─────────────────────────────────────────────────
  'MON.income':    { label: '금융.수입',   desc: '월급·수입' },
  'MON.spending':  { label: '금융.지출',   desc: '소비·지출' },
  'MON.saving':    { label: '금융.저축',   desc: '저축·예금' },
  'MON.payment':   { label: '금융.결제',   desc: '결제·청구' },
  'MON.loan':      { label: '금융.대출',   desc: '대출·이자' },
  'MON.insurance': { label: '금융.보험',   desc: '보험' },
  'MON.invest':    { label: '금융.투자',   desc: '투자·주식' },

  // ── WRK ─────────────────────────────────────────────────
  'WRK.workplace': { label: '직장.업무',   desc: '회사·업무·미팅' },
  'WRK.role':      { label: '직장.직책',   desc: '직책·역할' },
  'WRK.jobchange': { label: '직장.이직',   desc: '이직·취업' },
  'WRK.cert':      { label: '직장.자격',   desc: '자격증·인증' },
  'WRK.business':  { label: '직장.사업',   desc: '창업·사업' },
  'WRK.tool':      { label: '직장.도구',   desc: '업무 도구' },

  // ── TEC ─────────────────────────────────────────────────
  'TEC.device':   { label: '기술.기기',   desc: '디바이스 일반' },
  'TEC.hw':       { label: '기술.하드웨어', desc: '하드웨어' },
  'TEC.sw':       { label: '기술.소프트웨어', desc: '소프트웨어·앱' },
  'TEC.infra':    { label: '기술.인프라', desc: '서버·네트워크' },
  'TEC.ai':       { label: '기술.AI',     desc: '인공지능·LLM' },
  'TEC.security': { label: '기술.보안',   desc: '보안·암호화' },

  // ── EDU ─────────────────────────────────────────────────
  'EDU.school':   { label: '교육.학교',   desc: '학교·학과' },
  'EDU.cert':     { label: '교육.자격',   desc: '자격증·시험' },
  'EDU.study':    { label: '교육.학습',   desc: '공부·학습' },
  'EDU.online':   { label: '교육.온라인', desc: '온라인 강의' },
  'EDU.exam':     { label: '교육.시험',   desc: '시험 준비' },
  'EDU.language': { label: '교육.언어',   desc: '외국어 학습' },
  'EDU.reading':  { label: '교육.독서',   desc: '책 읽기' },
  'EDU.academic': { label: '교육.학문',   desc: '학문·연구' },

  // ── LAW ─────────────────────────────────────────────────
  'LAW.statute':  { label: '법.법령',     desc: '법령·규정' },
  'LAW.contract': { label: '법.계약',     desc: '계약·약관' },
  'LAW.rights':   { label: '법.권리',     desc: '권리·의무' },
  'LAW.admin':    { label: '법.행정',     desc: '행정 절차' },
  'LAW.tax':      { label: '법.세금',     desc: '세금·세무' },

  // ── TRV ─────────────────────────────────────────────────
  'TRV.domestic': { label: '여행.국내',   desc: '국내 여행' },
  'TRV.abroad':   { label: '여행.해외',   desc: '해외 여행' },
  'TRV.place':    { label: '여행.장소',   desc: '특정 장소' },

  // ── NAT ─────────────────────────────────────────────────
  'NAT.weather': { label: '자연.날씨',   desc: '날씨·기후' },
  'NAT.animal':  { label: '자연.동물',   desc: '동물·반려' },
  'NAT.plant':   { label: '자연.식물',   desc: '식물·정원' },
  'NAT.terrain': { label: '자연.지형',   desc: '지형·지리' },
  'NAT.ecology': { label: '자연.생태',   desc: '생태·환경' },

  // ── CUL ─────────────────────────────────────────────────
  'CUL.music':  { label: '문화.음악',   desc: '음악·노래' },
  'CUL.movie':  { label: '문화.영화',   desc: '영화' },
  'CUL.book':   { label: '문화.책',     desc: '책·도서' },
  'CUL.art':    { label: '문화.예술',   desc: '미술·전시' },
  'CUL.media':  { label: '문화.미디어', desc: '방송·미디어' },
  'CUL.show':   { label: '문화.공연',   desc: '공연·무대' },

  // ── HOB ─────────────────────────────────────────────────
  'HOB.sport':   { label: '취미.스포츠', desc: '운동 취미' },
  'HOB.social':  { label: '취미.모임',   desc: '동호회·모임' },
  'HOB.outdoor': { label: '취미.아웃도어', desc: '캠핑·등산' },
  'HOB.game':    { label: '취미.게임',   desc: '게임' },
  'HOB.craft':   { label: '취미.공예',   desc: '공예·DIY' },
  'HOB.collect': { label: '취미.수집',   desc: '수집' },
  'HOB.sing':    { label: '취미.노래',   desc: '노래·악기' },

  // ── SOC ─────────────────────────────────────────────────
  'SOC.issue':         { label: '사회.이슈',   desc: '사회 이슈' },
  'SOC.volunteer':     { label: '사회.봉사',   desc: '봉사 활동' },
  'SOC.politics':      { label: '사회.정치',   desc: '정치' },
  'SOC.economy':       { label: '사회.경제',   desc: '경제 동향' },
  'SOC.international': { label: '사회.국제',   desc: '국제 정세' },

  // ── REL ─────────────────────────────────────────────────
  'REL.romance':  { label: '관계.연애',   desc: '연애·결혼' },
  'REL.comm':     { label: '관계.소통',   desc: '소통·연락' },
  'REL.conflict': { label: '관계.갈등',   desc: '갈등·다툼' },
  'REL.online':   { label: '관계.온라인', desc: '온라인 관계' },

  // ── REG ─────────────────────────────────────────────────
  'REG.practice': { label: '종교.수행',   desc: '신앙 생활·수행' },
  'REG.catholic': { label: '종교.천주교', desc: '천주교' },
  'REG.other':    { label: '종교.기타',   desc: '기타 종교' },
};

const CATEGORY_RE = /^([A-Z]{3})(?:\.(.+))?$/;

export function labelOfCategory(path: string): string {
  const entry = CATEGORY_LABELS[path];
  if (entry) return entry.label;
  // 사용자 정의 경로 또는 매핑 누락 — 원형 그대로
  return path;
}

export function descOfCategory(path: string): string | undefined {
  return CATEGORY_LABELS[path]?.desc;
}

/** 시스템 코드(BOD.disease 등)인지 사용자 정의 경로(병원.2026-04-18 등)인지 구분. */
export function isSystemCategory(path: string): boolean {
  return CATEGORY_RE.test(path);
}

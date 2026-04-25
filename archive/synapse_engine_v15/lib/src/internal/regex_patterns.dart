/// Regex patterns for preprocessing — port of save.py patterns.

/// Date words that trigger save-pronoun LLM call.
/// Synced with engine/save.py _DATE_WORDS + _PRONOUN_WORDS time subset.
const dateWords = [
  // 일
  '어제', '그제', '그저께', '엊그제', '그끄제', '오늘', '내일', '모레', '글피', '그글피',
  // 주
  '이번주', '이번 주', '지난주', '저번주', '다음주', '다음 주',
  // 월
  '이번달', '지난달', '다음달',
  // 연
  '올해', '작년', '내년', '재작년', '내후년',
];

/// Pronoun words that trigger save-pronoun LLM call.
/// Synced with engine/save.py _PRONOUN_WORDS.
const pronounWords = [
  // 사물
  '이거', '그거', '저거', '이것', '그것', '저것',
  // 장소
  '거기', '여기', '저기', '이곳', '그곳', '저곳',
  // 방향
  '이쪽', '그쪽', '저쪽', '이리', '저리',
  // 인물 — 존대
  '이분', '그분', '저분',
  // 인물 — 비존대
  '걔', '쟤', '얘', '그사람', '그 사람', '그애', '그 애', '그녀',
  // 지시형용사/부사
  '이런', '그런', '저런', '이러한', '그러한', '저러한',
  '이렇게', '그렇게', '저렇게',
  // 모호 시간 (LLM 판단)
  '방금', '아까', '지금', '요즘', '최근', '이번에',
  '그날', '그때', '당시', '주말',
  // 요일
  '월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일',
];

/// Date word detection regex.
final dateWordPattern = RegExp(
  '(?:${dateWords.join("|")})',
  caseSensitive: false,
);

/// Pronoun word detection regex.
final pronounWordPattern = RegExp(
  '(?:${pronounWords.join("|")})',
  caseSensitive: false,
);

/// Age pattern: "XX살", "XX세".
final agePattern = RegExp(r'(\d{1,3})\s*(?:살|세)');

/// Negation pattern: 안/못 followed by a word.
final negPattern = RegExp(r'(안|못)\s+(\S+)');

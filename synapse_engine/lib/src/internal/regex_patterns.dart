/// Regex patterns for preprocessing — port of save.py patterns.

/// Date words that trigger save-pronoun LLM call.
const dateWords = [
  '어제', '그제', '그저께', '오늘', '내일', '모레', '글피',
  '이번주', '지난주', '다음주', '이번달', '지난달', '다음달',
  '올해', '작년', '내년', '재작년',
  '아까', '방금', '좀전', '조금전',
];

/// Pronoun words that trigger save-pronoun LLM call.
const pronounWords = [
  '거기', '여기', '저기', '이곳', '그곳', '저곳',
  '걔', '쟤', '얘', '그녀', '그', '그사람', '그분',
  '그거', '이거', '저거',
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

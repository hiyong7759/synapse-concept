// Demonstratives + ambiguous adverbs that can't be resolved at save time
// in a session-less system. Detected and recorded into `unresolved_tokens`
// for the user to clear via /review later.
//
// Mirrors `engine/suggestions.py` DEMONSTRATIVE_TOKENS so Python and Dart
// produce the same `unresolved_tokens` rows.

const Set<String> timeTokens = {
  '요즘', '최근', '그때', '당시', '주말', '이번에',
};
const Set<String> placeTokens = {
  '여기', '거기', '저기', '이곳', '그곳', '저곳',
};
const Set<String> personTokens = {
  '이분', '그분', '저분', '걔', '쟤', '얘', '그녀',
};
const Set<String> thingTokens = {
  '이거', '그거', '저거', '이것', '그것', '저것',
};

/// Union of all demonstrative tokens.
const Set<String> demonstrativeTokens = {
  ...timeTokens,
  ...placeTokens,
  ...personTokens,
  ...thingTokens,
};

final RegExp _eojeolSplit = RegExp(r'\s+');
final RegExp _trimPunct = RegExp(r'^[.,!?()\[\]"' "'" r'“”‘’]+|[.,!?()\[\]"' "'" r'“”‘’]+\$');

/// Detects demonstrative / ambiguous tokens in [text]. Mirrors
/// `_detect_unresolved_tokens` in `engine/save.py`: split by whitespace,
/// trim punctuation, and accept a token only if the eojeol starts with the
/// dictionary entry and what follows is empty or a Hangul syllable
/// (particle / suffix).
List<String> detectUnresolvedTokens(String text) {
  final found = <String>[];
  for (final raw in text.split(_eojeolSplit)) {
    final word = raw.replaceAll(_trimPunct, '');
    if (word.isEmpty) continue;
    for (final tok in demonstrativeTokens) {
      if (word.startsWith(tok)) {
        final rest = word.substring(tok.length);
        if (rest.isEmpty || _isHangul(rest.runes.first)) {
          if (!found.contains(tok)) found.add(tok);
          break;
        }
      }
    }
  }
  return found;
}

bool _isHangul(int codePoint) =>
    codePoint >= 0xAC00 && codePoint <= 0xD7AF;

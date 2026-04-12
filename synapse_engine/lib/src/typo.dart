/// Jamo-based typo correction — port of save.py typo correction.
///
/// Compares extracted node names against existing nodes + aliases
/// using jamo (Korean consonant/vowel) Levenshtein distance.
/// If distance == 1, auto-corrects to existing name.

// Korean Unicode decomposition constants
const _hangulBase = 0xAC00;
const _hangulEnd = 0xD7A3;
const _choCount = 21;
const _jungCount = 28;

const _cho = [
  'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ',
  'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
];
const _jung = [
  'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ', 'ㅙ',
  'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ',
];
const _jong = [
  '', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ',
  'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ',
  'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ',
];

/// Decompose Korean text into jamo sequence.
String toJamo(String text) {
  final buf = StringBuffer();
  for (final code in text.runes) {
    if (code >= _hangulBase && code <= _hangulEnd) {
      final offset = code - _hangulBase;
      final choIdx = offset ~/ (_choCount * _jungCount);
      final jungIdx = (offset % (_choCount * _jungCount)) ~/ _jungCount;
      final jongIdx = offset % _jungCount;
      buf.write(_cho[choIdx]);
      buf.write(_jung[jungIdx]);
      if (jongIdx > 0) buf.write(_jong[jongIdx]);
    } else {
      buf.writeCharCode(code);
    }
  }
  return buf.toString();
}

/// Levenshtein distance on jamo-decomposed strings.
int jamoDistance(String a, String b) {
  final ja = toJamo(a.toLowerCase());
  final jb = toJamo(b.toLowerCase());

  if (ja == jb) return 0;
  if (ja.isEmpty) return jb.length;
  if (jb.isEmpty) return ja.length;

  final m = ja.length;
  final n = jb.length;

  // Single-row optimization
  var prev = List.generate(n + 1, (i) => i);
  var curr = List.filled(n + 1, 0);

  for (var i = 1; i <= m; i++) {
    curr[0] = i;
    for (var j = 1; j <= n; j++) {
      final cost = ja[i - 1] == jb[j - 1] ? 0 : 1;
      curr[j] = [
        prev[j] + 1, // deletion
        curr[j - 1] + 1, // insertion
        prev[j - 1] + cost, // substitution
      ].reduce((a, b) => a < b ? a : b);
    }
    final tmp = prev;
    prev = curr;
    curr = tmp;
  }

  return prev[n];
}

/// Correct typos in extracted node names against existing nodes + aliases.
///
/// [existingEdgeCounts] maps lowercase node/alias name → edge count (tiebreaker).
/// Returns list of (original, corrected) for each correction made.
List<(String, String)> correctTypos(
  List<Map<String, dynamic>> nodes,
  Map<String, int> existingEdgeCounts,
) {
  final corrections = <(String, String)>[];

  for (final node in nodes) {
    final name = node['name'] as String;
    if (existingEdgeCounts.containsKey(name.toLowerCase())) continue;

    final jamoName = toJamo(name);
    if (jamoName.length < 6) continue;

    String? bestMatch;
    int bestEdges = -1;
    for (final existing in existingEdgeCounts.keys) {
      final jamoExisting = toJamo(existing);
      if ((jamoName.length - jamoExisting.length).abs() > 1) continue;
      if (jamoDistance(name, existing) == 1) {
        final ec = existingEdgeCounts[existing] ?? 0;
        if (ec > bestEdges) {
          bestMatch = existing;
          bestEdges = ec;
        }
      }
    }

    if (bestMatch != null) {
      corrections.add((name, bestMatch));
      node['name'] = bestMatch;
    }
  }

  return corrections;
}

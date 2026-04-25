// Hangul jamo decomposition + Levenshtein distance.
// Port of engine/jamo.py — pure Dart, no external dependencies.

const int _hangulBase = 0xAC00;
const int _hangulEnd = 0xD7A3;
const int _jungCount = 21;
const int _jongCount = 28;

const List<String> _cho = [
  'ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ','ㅅ',
  'ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ',
];
const List<String> _jung = [
  'ㅏ','ㅐ','ㅑ','ㅒ','ㅓ','ㅔ','ㅕ','ㅖ','ㅗ','ㅘ',
  'ㅙ','ㅚ','ㅛ','ㅜ','ㅝ','ㅞ','ㅟ','ㅠ','ㅡ','ㅢ','ㅣ',
];
const List<String> _jong = [
  '','ㄱ','ㄲ','ㄳ','ㄴ','ㄵ','ㄶ','ㄷ','ㄹ','ㄺ',
  'ㄻ','ㄼ','ㄽ','ㄾ','ㄿ','ㅀ','ㅁ','ㅂ','ㅄ','ㅅ',
  'ㅆ','ㅇ','ㅈ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ',
];

/// Decomposes Hangul syllables into their cho/jung/jong jamo. Non-Hangul
/// characters are passed through unchanged.
String decompose(String text) {
  final buf = StringBuffer();
  for (final cp in text.runes) {
    if (cp >= _hangulBase && cp <= _hangulEnd) {
      final offset = cp - _hangulBase;
      final cho = offset ~/ (_jungCount * _jongCount);
      final jung = (offset % (_jungCount * _jongCount)) ~/ _jongCount;
      final jong = offset % _jongCount;
      buf.write(_cho[cho]);
      buf.write(_jung[jung]);
      if (jong > 0) buf.write(_jong[jong]);
    } else {
      buf.writeCharCode(cp);
    }
  }
  return buf.toString();
}

/// Standard iterative Levenshtein distance over code units.
int levenshtein(String s1, String s2) {
  if (s1.length < s2.length) return levenshtein(s2, s1);
  if (s2.isEmpty) return s1.length;

  var prev = List<int>.generate(s2.length + 1, (i) => i);
  for (var i = 0; i < s1.length; i++) {
    final curr = <int>[i + 1];
    for (var j = 0; j < s2.length; j++) {
      final cost = s1.codeUnitAt(i) == s2.codeUnitAt(j) ? 0 : 1;
      final ins = curr[j] + 1;
      final del = prev[j + 1] + 1;
      final sub = prev[j] + cost;
      var best = ins < del ? ins : del;
      if (sub < best) best = sub;
      curr.add(best);
    }
    prev = curr;
  }
  return prev.last;
}

/// Decomposes both strings to jamo, then compares with Levenshtein.
int jamoDistance(String a, String b) =>
    levenshtein(decompose(a), decompose(b));

/// Typo-candidate predicate. Both strings must be at least [minJamoLen]
/// jamo long after decomposition, the lengths must differ by at most
/// [maxDist], and the jamo distance must be ≤ [maxDist]. Identical strings
/// are never candidates.
bool isTypoCandidate(
  String a,
  String b, {
  int maxDist = 1,
  int minJamoLen = 6,
}) {
  if (a == b) return false;
  final ja = decompose(a);
  final jb = decompose(b);
  if (ja.length < minJamoLen || jb.length < minJamoLen) return false;
  if ((ja.length - jb.length).abs() > maxDist) return false;
  return levenshtein(ja, jb) <= maxDist;
}

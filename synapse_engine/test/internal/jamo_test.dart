import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_engine/src/internal/jamo.dart';

void main() {
  group('decompose', () {
    test('breaks Hangul syllables into cho+jung[+jong] jamo', () {
      expect(decompose('가'), 'ㄱㅏ');
      expect(decompose('각'), 'ㄱㅏㄱ');
      expect(decompose('안녕'), 'ㅇㅏㄴㄴㅕㅇ');
    });

    test('passes non-Hangul characters through', () {
      expect(decompose('hello'), 'hello');
      expect(decompose('가1나2'), 'ㄱㅏ1ㄴㅏ2');
    });

    test('is empty for an empty input', () {
      expect(decompose(''), '');
    });
  });

  group('levenshtein', () {
    test('returns 0 for equal strings', () {
      expect(levenshtein('abc', 'abc'), 0);
    });

    test('counts inserts, deletes, and substitutions', () {
      expect(levenshtein('kitten', 'sitting'), 3);
      expect(levenshtein('a', ''), 1);
      expect(levenshtein('', 'abc'), 3);
    });
  });

  group('isTypoCandidate', () {
    test('flags 스타벅스 vs 스타벅시 (one jamo apart, ≥6 jamo)', () {
      expect(isTypoCandidate('스타벅스', '스타벅시'), isTrue);
    });

    test('rejects identical strings', () {
      expect(isTypoCandidate('스타벅스', '스타벅스'), isFalse);
    });

    test('rejects strings shorter than minJamoLen', () {
      // "감기" → 4 jamo; below the default 6.
      expect(isTypoCandidate('감기', '감자'), isFalse);
    });

    test('rejects pairs whose jamo lengths differ by more than maxDist', () {
      expect(isTypoCandidate('스타벅스', '스타벅스점'), isFalse);
    });

    test('jamoDistance is symmetric', () {
      expect(jamoDistance('스타벅스', '스타벅시'),
          jamoDistance('스타벅시', '스타벅스'));
    });
  });
}

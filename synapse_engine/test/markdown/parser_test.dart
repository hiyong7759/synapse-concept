import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_engine/src/markdown/parser.dart';

void main() {
  group('parseMarkdown', () {
    test('headings stack and child lines inherit the path', () {
      const input = '''
# 더나은
## 개발팀
- 팀장:: 박지수
- 프론트엔드 김민수
오늘 회의가 세 개 연속이었다.
''';
      final lines = parseMarkdown(input);
      // h1, h2, kv, list, free
      expect(lines.length, 5);
      expect(lines[0].kind, ParsedKind.heading);
      expect(lines[0].text, '더나은');
      expect(lines[0].headingPath, ['더나은']);

      expect(lines[1].kind, ParsedKind.heading);
      expect(lines[1].text, '개발팀');
      expect(lines[1].headingPath, ['더나은', '개발팀']);

      expect(lines[2].kind, ParsedKind.keyValue);
      expect(lines[2].text, '팀장:: 박지수');
      expect(lines[2].key, '팀장');
      expect(lines[2].value, '박지수');
      expect(lines[2].headingPath, ['더나은', '개발팀']);

      expect(lines[3].kind, ParsedKind.list);
      expect(lines[3].text, '프론트엔드 김민수');
      expect(lines[3].headingPath, ['더나은', '개발팀']);

      expect(lines[4].kind, ParsedKind.free);
      expect(lines[4].text, '오늘 회의가 세 개 연속이었다.');
      expect(lines[4].headingPath, ['더나은', '개발팀']);
    });

    test('descending heading depth pops the stack', () {
      const input = '''
# A
## B
text under B
# C
text under C
''';
      final lines = parseMarkdown(input);
      // h1 A, h2 B, free under B, h1 C, free under C
      expect(lines[2].headingPath, ['A', 'B']);
      expect(lines[3].headingPath, ['C']);
      expect(lines[4].headingPath, ['C']);
    });

    test('numeric lists become list kind', () {
      const input = '1. one\n2. two';
      final lines = parseMarkdown(input);
      expect(lines.map((l) => l.kind),
          [ParsedKind.list, ParsedKind.list]);
      expect(lines.map((l) => l.text), ['one', 'two']);
    });

    test('blank lines are dropped', () {
      const input = 'a\n\n\nb';
      final lines = parseMarkdown(input);
      expect(lines.length, 2);
      expect(lines.map((l) => l.text), ['a', 'b']);
    });

    test('headings and bullets without space do not match', () {
      // "#A" (no space) is a regular line per markdown grammar.
      const input = '#A\n-B';
      final lines = parseMarkdown(input);
      expect(lines.map((l) => l.kind),
          [ParsedKind.free, ParsedKind.free]);
    });

    test('empty input produces empty result', () {
      expect(parseMarkdown(''), isEmpty);
    });
  });
}

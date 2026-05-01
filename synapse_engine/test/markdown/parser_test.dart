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

    test('heading separator-intent chars collapse to a single space', () {
      const input = '''
## 만화/라이트노벨
- 슬램덩크
''';
      final lines = parseMarkdown(input);
      expect(lines[0].kind, ParsedKind.heading);
      expect(lines[0].text, '만화 라이트노벨');
      expect(lines[0].headingPath, ['만화 라이트노벨']);
      expect(lines[1].headingPath, ['만화 라이트노벨']);
    });

    test('heading reserved chars are kept verbatim', () {
      const input = '## 제13조 (구성)';
      final lines = parseMarkdown(input);
      expect(lines[0].text, '제13조 (구성)');
      expect(lines[0].headingPath, ['제13조 (구성)']);
    });

    test('. inside a heading splits into multi-step path and resets stack',
        () {
      const input = '''
# 취업규칙.제1장 총칙.제1조 (목적)
이 규칙은 ... 목적으로 한다.
''';
      final lines = parseMarkdown(input);
      // single emitted heading + one free line
      expect(lines[0].kind, ParsedKind.heading);
      expect(lines[0].text, '제1조 (목적)');
      expect(lines[0].headingPath, ['취업규칙', '제1장 총칙', '제1조 (목적)']);
      expect(lines[1].kind, ParsedKind.free);
      expect(lines[1].headingPath,
          ['취업규칙', '제1장 총칙', '제1조 (목적)']);
    });

    test('. heading ignores # depth — same result for # and ###', () {
      final shallow = parseMarkdown('# A.B.C\nx');
      final deep = parseMarkdown('### A.B.C\nx');
      expect(shallow[1].headingPath, deep[1].headingPath);
      expect(shallow[1].headingPath, ['A', 'B', 'C']);
    });

    test('empty segments inside . path are skipped', () {
      // '..' between segments and trailing dot collapse to non-empty pieces.
      const input = '# A..B.\nx';
      final lines = parseMarkdown(input);
      expect(lines[1].headingPath, ['A', 'B']);
    });

    test('table mode — tab-headed `#` line zips rows into multi-pair sentences',
        () {
      // Excel paste — heading has tabs, rows have tabs.
      final input = [
        '# 연번\t상품명\t구매자\t위치',
        '- 180\t처음 배우는 스프링 부트 2\t김대훈\t본사',
        '- 185\t비전공자도 이해할 수 있는 AI 지식\t정윤수\t본사',
      ].join('\n');
      final lines = parseMarkdown(input);
      // table heading is consumed (no category), only two rows emitted.
      expect(lines, hasLength(2));
      expect(lines[0].kind, ParsedKind.keyValue);
      expect(
        lines[0].text,
        '연번:: 180 상품명:: 처음 배우는 스프링 부트 2 '
        '구매자:: 김대훈 위치:: 본사',
      );
      expect(lines[0].headingPath, isEmpty,
          reason: 'tab heading does not register a category');
      expect(
        lines[1].text,
        '연번:: 185 상품명:: 비전공자도 이해할 수 있는 AI 지식 '
        '구매자:: 정윤수 위치:: 본사',
      );
    });

    test('table mode — empty cells skipped within a row', () {
      final input = [
        '# 제목\t구매자\t위치',
        '- 책A\t\t본사',
      ].join('\n');
      final lines = parseMarkdown(input);
      // 구매자 cell empty → that pair is skipped.
      expect(lines.single.text, '제목:: 책A 위치:: 본사');
    });

    test('table mode — extra cells beyond column count are ignored', () {
      final input = [
        '# 제목\t구매자',
        '- 책A\t김대훈\t잡음',
      ].join('\n');
      final lines = parseMarkdown(input);
      expect(lines.single.text, '제목:: 책A 구매자:: 김대훈');
    });

    test('table mode — plain heading exits table mode', () {
      final input = [
        '# 제목\t구매자',
        '- 책A\t김대훈',
        '## 영화',
        '- 어떤 영화',
      ].join('\n');
      final lines = parseMarkdown(input);
      // table row + heading + list under the heading.
      expect(lines, hasLength(3));
      expect(lines[0].text, '제목:: 책A 구매자:: 김대훈');
      expect(lines[1].kind, ParsedKind.heading);
      expect(lines[1].headingPath, ['영화']);
      expect(lines[2].kind, ParsedKind.list);
      expect(lines[2].headingPath, ['영화']);
    });

    test('table mode — non-tab list row falls through to normal list', () {
      final input = [
        '# 제목\t구매자',
        '- 그냥 줄',
      ].join('\n');
      final lines = parseMarkdown(input);
      expect(lines.single.kind, ParsedKind.list);
      expect(lines.single.text, '그냥 줄');
    });
  });
}

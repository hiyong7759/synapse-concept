// Markdown parser for the v22 note grammar.
//
// Port of `engine/markdown.py:parse_markdown`. Single source:
// docs/DESIGN_PIPELINE.md §의미 처리 파이프라인 — heading / key_value /
// list / free 분기.
//
// `# heading` keeps a category path stack. Each subsequent non-heading
// line inherits the current path. `- key:: value` is treated separately
// from plain list items because the saved sentence text keeps the literal
// `"key:: value"` form.

enum ParsedKind { heading, keyValue, list, free }

class ParsedLine {
  const ParsedLine({
    required this.kind,
    required this.text,
    required this.headingPath,
    this.key,
    this.value,
  });

  /// Line type.
  final ParsedKind kind;

  /// Stored sentence text. For `keyValue`, this is the literal form
  /// `"$key:: $value"`. For `heading`, this is the heading title (no `#`).
  final String text;

  /// Heading-stack path inherited by this line. Empty list = no heading
  /// scope yet.
  final List<String> headingPath;

  /// Populated only for [ParsedKind.keyValue].
  final String? key;

  /// Populated only for [ParsedKind.keyValue].
  final String? value;
}

final RegExp _headingRe = RegExp(r'^(#{1,})\s+(.+)$');
final RegExp _keyValueRe = RegExp(r'^-\s+(.+?)\s*::\s+(.+)$');
final RegExp _listUnorderedRe = RegExp(r'^[-*]\s+(.+)$');
final RegExp _listOrderedRe = RegExp(r'^\d+\.\s+(.+)$');

/// Parses [source] into a list of lines with inherited heading context.
///
/// Blank lines are dropped. Headings are emitted (so callers can register
/// the path with `categories`) but should NOT be saved as `sentences` —
/// only `keyValue`, `list`, and `free` produce sentence rows.
List<ParsedLine> parseMarkdown(String source) {
  final out = <ParsedLine>[];
  final stack = <_HeadingFrame>[];

  List<String> currentPath() =>
      List<String>.unmodifiable(stack.map((f) => f.name));

  for (final raw in source.split('\n')) {
    final line = raw.trim();
    if (line.isEmpty) continue;

    // ── heading ───────────────────────────────────────
    final hm = _headingRe.firstMatch(line);
    if (hm != null) {
      final depth = hm.group(1)!.length;
      final name = hm.group(2)!.trim();
      // Pop frames at this depth or deeper, then push.
      while (stack.isNotEmpty && stack.last.depth >= depth) {
        stack.removeLast();
      }
      stack.add(_HeadingFrame(depth: depth, name: name));
      out.add(ParsedLine(
        kind: ParsedKind.heading,
        text: name,
        headingPath: currentPath(),
      ));
      continue;
    }

    // ── key:: value (must run before plain list) ──────
    final kvm = _keyValueRe.firstMatch(line);
    if (kvm != null) {
      final key = kvm.group(1)!.trim();
      final value = kvm.group(2)!.trim();
      if (key.isNotEmpty && value.isNotEmpty) {
        out.add(ParsedLine(
          kind: ParsedKind.keyValue,
          text: '$key:: $value',
          headingPath: currentPath(),
          key: key,
          value: value,
        ));
        continue;
      }
      // Empty key/value → fall through to the list branch.
    }

    // ── list ─────────────────────────────────────────
    final um = _listUnorderedRe.firstMatch(line);
    if (um != null) {
      out.add(ParsedLine(
        kind: ParsedKind.list,
        text: um.group(1)!.trim(),
        headingPath: currentPath(),
      ));
      continue;
    }
    final om = _listOrderedRe.firstMatch(line);
    if (om != null) {
      out.add(ParsedLine(
        kind: ParsedKind.list,
        text: om.group(1)!.trim(),
        headingPath: currentPath(),
      ));
      continue;
    }

    // ── free ─────────────────────────────────────────
    out.add(ParsedLine(
      kind: ParsedKind.free,
      text: line,
      headingPath: currentPath(),
    ));
  }
  return out;
}

class _HeadingFrame {
  const _HeadingFrame({required this.depth, required this.name});
  final int depth;
  final String name;
}

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

/// Heading-name characters whose intent is "separate concepts." We replace
/// them with a single space so they cannot collide with the `.` step
/// separator or smear into a single category name.
///
/// Reserved (kept verbatim because they are commonly part of a category
/// name itself): `-` `_` `()` `[]` `{}` `"` `'` `:` `?` `!`
final RegExp _headingSeparatorChars = RegExp(r'[/|\\·,;&+~→]');
final RegExp _multiSpace = RegExp(r'\s+');

/// Trim, collapse separator-intent chars to space, then collapse runs of
/// whitespace. Returns empty string if nothing meaningful is left.
String _normalizeHeadingSegment(String raw) {
  return raw
      .replaceAll(_headingSeparatorChars, ' ')
      .replaceAll(_multiSpace, ' ')
      .trim();
}

/// Parses [source] into a list of lines with inherited heading context.
///
/// Blank lines are dropped. Headings are emitted (so callers can register
/// the path with `categories`) but should NOT be saved as `sentences` —
/// only `keyValue`, `list`, and `free` produce sentence rows.
///
/// **Table mode** — when a heading line contains tab characters, it's not a
/// category but a column header for a tab-separated table block. Subsequent
/// `- val\tval\t...` rows are zipped with the column names and emitted as
/// a single multi-pair `keyValue` sentence (`"col1:: val1 col2:: val2 ..."`).
/// Useful for pasting Excel exports verbatim. Table mode resets when a
/// non-tab heading is encountered.
List<ParsedLine> parseMarkdown(String source) {
  final out = <ParsedLine>[];
  final stack = <_HeadingFrame>[];
  List<String>? tableColumns;

  List<String> currentPath() =>
      List<String>.unmodifiable(stack.map((f) => f.name));

  for (final raw in source.split('\n')) {
    // Don't trim before checking — table cells often have surrounding
    // spaces (Excel paste). Strip the trailing newline only.
    final line = raw.trimRight();
    if (line.trim().isEmpty) continue;

    // ── heading ───────────────────────────────────────
    final hm = _headingRe.firstMatch(line.trimLeft());
    if (hm != null) {
      final depth = hm.group(1)!.length;
      final rawName = hm.group(2)!;

      // Table-mode marker: heading with tabs = column header. No category
      // emitted; subsequent tabbed list rows zip into multi-pair sentences.
      if (rawName.contains('\t')) {
        tableColumns = rawName
            .split('\t')
            .map((c) => c.trim())
            .where((c) => c.isNotEmpty)
            .toList(growable: false);
        continue;
      }

      // Plain heading exits table mode.
      tableColumns = null;

      // `.` is the multi-step path separator: `# A.B.C` → ["A","B","C"].
      // Each segment is then normalized (separator-intent chars → space).
      final segments = rawName
          .split('.')
          .map(_normalizeHeadingSegment)
          .where((s) => s.isNotEmpty)
          .toList(growable: false);
      if (segments.isEmpty) continue; // empty/whitespace-only heading

      if (segments.length > 1) {
        // Multi-step path resets the stack — `#` count is ignored.
        stack
          ..clear()
          ..addAll([
            for (var i = 0; i < segments.length; i++)
              _HeadingFrame(depth: i + 1, name: segments[i]),
          ]);
      } else {
        // Single segment: standard depth-based pop + push.
        while (stack.isNotEmpty && stack.last.depth >= depth) {
          stack.removeLast();
        }
        stack.add(_HeadingFrame(depth: depth, name: segments.first));
      }
      out.add(ParsedLine(
        kind: ParsedKind.heading,
        text: segments.last,
        headingPath: currentPath(),
      ));
      continue;
    }

    // ── table row (only inside table mode) ───────────
    if (tableColumns != null) {
      final stripped = _listUnorderedRe.firstMatch(line.trim());
      if (stripped != null && stripped.group(1)!.contains('\t')) {
        final values = stripped.group(1)!.split('\t');
        final pairs = <String>[];
        for (var i = 0;
            i < tableColumns.length && i < values.length;
            i++) {
          final v = values[i].trim();
          if (v.isEmpty) continue;
          pairs.add('${tableColumns[i]}:: $v');
        }
        if (pairs.isNotEmpty) {
          out.add(ParsedLine(
            kind: ParsedKind.keyValue,
            text: pairs.join(' '),
            headingPath: currentPath(),
          ));
        }
        continue;
      }
      // Non-tabbed line inside table mode → fall through to normal handling.
    }

    final trimmed = line.trim();

    // ── key:: value (must run before plain list) ──────
    final kvm = _keyValueRe.firstMatch(trimmed);
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
    final um = _listUnorderedRe.firstMatch(trimmed);
    if (um != null) {
      out.add(ParsedLine(
        kind: ParsedKind.list,
        text: um.group(1)!.trim(),
        headingPath: currentPath(),
      ));
      continue;
    }
    final om = _listOrderedRe.firstMatch(trimmed);
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
      text: trimmed,
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

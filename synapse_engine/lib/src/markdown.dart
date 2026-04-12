/// Markdown parser — heading path + item separation.
///
/// Port of engine/markdown.py.

final _headingRe = RegExp(r'^(#{1,6})\s+(.+)$');
final _listUnorderedRe = RegExp(r'^[-*]\s+(.+)$');
final _listOrderedRe = RegExp(r'^\d+\.\s+(.+)$');

/// Parse markdown text into (categoryPath, itemText) pairs.
///
/// - Headings set the path. Unlimited depth.
/// - List items (-, 1.) are individual extraction targets.
/// - No headings → [(null, originalText)].
/// - `# 더나은.개발팀` dot-separated is a single-line path.
List<(String?, String)> parseMarkdown(String text) {
  final lines = text.split('\n');

  final hasHeading = lines.any((line) => _headingRe.hasMatch(line.trim()));
  if (!hasHeading) return [(null, text)];

  final result = <(String?, String)>[];
  final pathStack = <(int, String)>[]; // (depth, name)
  final pendingText = <String>[];

  String? currentPath() {
    if (pathStack.isEmpty) return null;
    return pathStack.map((e) => e.$2).join('.');
  }

  void flushPending() {
    if (pendingText.isNotEmpty) {
      final block = pendingText.join(' ').trim();
      if (block.isNotEmpty) {
        result.add((currentPath(), block));
      }
      pendingText.clear();
    }
  }

  for (final rawLine in lines) {
    final line = rawLine.trim();
    if (line.isEmpty) continue;

    // Heading match
    final hm = _headingRe.firstMatch(line);
    if (hm != null) {
      flushPending();
      final depth = hm.group(1)!.length;
      final name = hm.group(2)!.trim();

      if (name.contains('.')) {
        // Dot-separated path: # 더나은.개발부.개발팀
        pathStack.clear();
        final parts = name.split('.');
        for (var i = 0; i < parts.length; i++) {
          pathStack.add((i + 1, parts[i].trim()));
        }
      } else {
        // Pop back to same or higher depth
        while (pathStack.isNotEmpty && pathStack.last.$1 >= depth) {
          pathStack.removeLast();
        }
        pathStack.add((depth, name));
      }
      continue;
    }

    // List item match
    final um = _listUnorderedRe.firstMatch(line);
    final om = _listOrderedRe.firstMatch(line);
    if (um != null || om != null) {
      flushPending();
      final itemText = um != null ? um.group(1)! : line;
      result.add((currentPath(), itemText.trim()));
      continue;
    }

    // Plain text under heading
    pendingText.add(line);
  }

  flushPending();
  return result;
}

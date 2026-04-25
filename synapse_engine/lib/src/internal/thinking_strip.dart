// Thinking-block stripper. Removes reasoning blocks emitted by some
// chat templates so downstream parsers see only the final answer.
// Patterns mirror archive/synapse_engine_v15/lib/src/inference.dart.

final List<RegExp> _thinkingPatterns = [
  RegExp(r'<\|channel>thought.*?<channel\|>', dotAll: true),
  RegExp(r'<\|channel>thought.*', dotAll: true),
  RegExp(r'<think>.*?</think>', dotAll: true),
  RegExp(r'<think>.*', dotAll: true),
];

/// Removes thinking blocks and trims trailing whitespace.
/// Idempotent: passing already-clean text returns it (trimmed).
String stripThinking(String text) {
  var result = text;
  for (final pattern in _thinkingPatterns) {
    result = result.replaceAll(pattern, '');
  }
  return result.trim();
}

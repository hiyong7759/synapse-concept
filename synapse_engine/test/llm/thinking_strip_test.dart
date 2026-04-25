import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_engine/src/internal/thinking_strip.dart';

void main() {
  group('stripThinking', () {
    test('removes paired <think> blocks', () {
      const input =
          '<think>let me consider this</think>The answer is 42.';
      expect(stripThinking(input), 'The answer is 42.');
    });

    test('removes unterminated <think> at the end', () {
      const input = 'The answer is 42.\n<think>more reasoning';
      expect(stripThinking(input), 'The answer is 42.');
    });

    test('removes paired <|channel>thought blocks', () {
      const input = 'Pre.<|channel>thought reasoning here<channel|>Post.';
      expect(stripThinking(input), 'Pre.Post.');
    });

    test('removes unterminated <|channel>thought tail', () {
      const input = 'Result.<|channel>thought leftover...';
      expect(stripThinking(input), 'Result.');
    });

    test('returns clean text trimmed when no thinking is present', () {
      expect(stripThinking('  hello  '), 'hello');
    });

    test('handles multiline thinking blocks', () {
      const input = '<think>\nlots\nof\nlines\n</think>final';
      expect(stripThinking(input), 'final');
    });
  });
}

import 'dart:io' show Platform;

import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_engine/synapse_engine.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';

/// Real Kiwi tokenization. Skipped unless `SYNAPSE_TEST_KIWI=1` is set,
/// because flutter_kiwi_nlp needs the platform-specific native library
/// (built during `pod install` on macOS, `flutter build` on Android, etc.)
/// which isn't always available in a bare `flutter test` run.
///
/// To exercise this group:
///   SYNAPSE_TEST_KIWI=1 flutter test test/kiwi/kiwi_test.dart --tags integration
void main() {
  group('InMemoryKiwiBackend (always runs)', () {
    test('returns seeded tokens', () async {
      final backend = InMemoryKiwiBackend()
        ..seed('hello', const [
          KiwiToken(
              surface: 'hello',
              tag: 'SL',
              lemma: 'hello',
              start: 0,
              length: 5),
        ]);
      final tokens = await backend.tokenize('hello');
      expect(tokens, hasLength(1));
      expect(tokens.first.tag, 'SL');
    });

    test('nouns filters by NNG/NNP/NR/VV/VA + 안/못 only', () async {
      final backend = InMemoryKiwiBackend()
        ..seed('나는 안 가', const [
          KiwiToken(surface: '나', tag: 'NP', lemma: '나', start: 0, length: 1),
          KiwiToken(surface: '는', tag: 'JX', lemma: '는', start: 1, length: 1),
          KiwiToken(surface: '안', tag: 'MAG', lemma: '안', start: 3, length: 1),
          KiwiToken(surface: '가다', tag: 'VV', lemma: '가다', start: 5, length: 2),
        ]);
      expect(await backend.nouns('나는 안 가'), ['안', '가다']);
    });

    test('nouns deduplicates case-insensitively', () async {
      final backend = InMemoryKiwiBackend()
        ..seed('FastAPI fastapi', const [
          KiwiToken(
              surface: 'FastAPI',
              tag: 'NNP',
              lemma: 'FastAPI',
              start: 0,
              length: 7),
          KiwiToken(
              surface: 'fastapi',
              tag: 'NNP',
              lemma: 'fastapi',
              start: 8,
              length: 7),
        ]);
      final result = await backend.nouns('FastAPI fastapi');
      expect(result, hasLength(1));
    });
  });

  final runRealKiwi = Platform.environment['SYNAPSE_TEST_KIWI'] == '1';
  final skipReason = runRealKiwi
      ? null
      : 'SYNAPSE_TEST_KIWI=1 not set — real Kiwi tokenization skipped';

  group('FlutterKiwiBackend (real Kiwi)', () {
    late FlutterKiwiBackend backend;

    setUpAll(() async {
      if (!runRealKiwi) return;
      TestWidgetsFlutterBinding.ensureInitialized();
      backend = await FlutterKiwiBackend.load();
    });

    tearDownAll(() async {
      if (!runRealKiwi) return;
      await backend.dispose();
    });

    test('tokenizes simple Korean sentence', () async {
      final tokens = await backend.tokenize('나는 학교에 갔다');
      expect(tokens, isNotEmpty);
    }, skip: skipReason, timeout: const Timeout(Duration(seconds: 30)));

    test('nouns extracts nouns + verb lemma', () async {
      final result = await backend.nouns('스타벅스에서 커피를 마셨다');
      // We don't assert exact ordering — Kiwi internals — only that the
      // expected lemmas appear.
      expect(result.any((s) => s.contains('스타벅스')), isTrue);
    }, skip: skipReason, timeout: const Timeout(Duration(seconds: 30)));
  });
}

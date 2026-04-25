import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_engine/src/internal/date_normalize.dart';
import 'package:synapse_engine/src/kiwi/kiwi_wasm.dart';
import 'package:synapse_engine/src/kiwi/tokens.dart';

/// Test KiwiBackend that lets us hand-craft tag streams. Real Kiwi
/// runs in tests/kiwi/kiwi_test.dart under the SYNAPSE_TEST_KIWI gate.
class _ScriptedKiwi implements KiwiBackend {
  _ScriptedKiwi(this._scripts);
  final Map<String, List<KiwiToken>> _scripts;

  @override
  Future<List<KiwiToken>> tokenize(String text) async =>
      _scripts[text] ??
      // Fallback: tag every space as a clause-internal break (no boundaries).
      // This is enough for ISO and bare-adverb tests that don't depend on
      // sentence-final / connective endings.
      const [];

  @override
  Future<List<String>> nouns(String text) async => const [];

  @override
  Future<void> dispose() async {}
}

KiwiToken _ef(String form, int start, int length) =>
    KiwiToken(surface: form, tag: 'EF', lemma: form, start: start, length: length);

KiwiToken _ec(String form, int start, int length) =>
    KiwiToken(surface: form, tag: 'EC', lemma: form, start: start, length: length);

KiwiToken _maj(String form, int start) =>
    KiwiToken(surface: form, tag: 'MAJ', lemma: form, start: start, length: form.length);

void main() {
  // 2026-04-26 is a Sunday. Most tests anchor on this for predictable
  // weekday arithmetic.
  final reference = DateTime(2026, 4, 26);
  const normalizer = DateNormalizer();

  group('relative day adverbs (single clause, no Kiwi structure needed)', () {
    final kiwi = _ScriptedKiwi(const {});

    test('어제 → 2026년 4월 25일', () async {
      final r = await normalizer.normalize(
        '어제 만났다',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '2026년 4월 25일 만났다');
      expect(r.splitNodes,
          ['2026년', '4월', '25일', '2026년 4월 25일']);
    });

    test('오늘 / 내일 / 모레 / 글피 / 그저께 / 그글피', () async {
      final cases = {
        '오늘': '2026년 4월 26일',
        '내일': '2026년 4월 27일',
        '모레': '2026년 4월 28일',
        '글피': '2026년 4월 29일',
        '그저께': '2026년 4월 24일',
        '그글피': '2026년 4월 30일',
      };
      for (final entry in cases.entries) {
        final r = await normalizer.normalize(
          '${entry.key} 메모',
          kiwi: kiwi,
          reference: reference,
        );
        expect(r.text.startsWith(entry.value), isTrue,
            reason: '${entry.key} → ${entry.value}');
      }
    });

    test('엊그제 maps to the same offset as 그저께', () async {
      final r = await normalizer.normalize(
        '엊그제 일',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '2026년 4월 24일 일');
    });
  });

  group('ISO dates', () {
    final kiwi = _ScriptedKiwi(const {});

    test('YYYY-MM-DD → 한국어 표기', () async {
      final r = await normalizer.normalize(
        '2026-04-18에 진단',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '2026년 4월 18일에 진단');
      expect(r.splitNodes, ['2026년', '4월', '18일', '2026년 4월 18일']);
    });

    test('YYYY.MM.DD and YYYY/MM/DD also normalised', () async {
      final r1 = await normalizer.normalize(
        '2026.04.18 기록',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r1.text, '2026년 4월 18일 기록');

      final r2 = await normalizer.normalize(
        '2026/04/18 기록',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r2.text, '2026년 4월 18일 기록');
    });

    test('YYYY-MM (no day) → year+month only', () async {
      final r = await normalizer.normalize(
        '2026-04 기록',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '2026년 4월 기록');
      expect(r.splitNodes, ['2026년', '4월', '2026년 4월']);
    });
  });

  group('relative weekdays', () {
    final kiwi = _ScriptedKiwi(const {});

    test('이번 주 금요일 (reference Sun 4/26 → Fri 4/24 of same ISO week)',
        () async {
      // ISO weeks start Monday, so 'this week Friday' relative to a
      // Sunday-anchored reference resolves via _relativeWeekdayRegex
      // logic: same week base → friday of that week (Apr 24, 2026).
      final r = await normalizer.normalize(
        '이번 주 금요일에 만나',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '2026년 4월 24일에 만나');
    });

    test('다음 주 월요일', () async {
      final r = await normalizer.normalize(
        '다음 주 월요일 회의',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '2026년 4월 27일 회의');
    });

    test('지난 주 수요일', () async {
      final r = await normalizer.normalize(
        '지난 주 수요일 메모',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '2026년 4월 15일 메모');
    });
  });

  group('recurrence preservation (single-clause, no boundary needed)', () {
    final kiwi = _ScriptedKiwi(const {});

    test('매주 금요일 — left untouched', () async {
      final r = await normalizer.normalize(
        '매주 금요일 회의',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '매주 금요일 회의');
      expect(r.splitNodes, isEmpty);
    });

    test('매월 1일 — left untouched', () async {
      final r = await normalizer.normalize(
        '매월 1일 결제',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '매월 1일 결제');
    });

    test('격주 화요일 — left untouched', () async {
      final r = await normalizer.normalize(
        '격주 화요일 운동',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '격주 화요일 운동');
    });

    test('항상 / 자주 / 종종 — left untouched (단음절 "늘" 은 의도적으로 제외 — 오늘과 충돌)', () async {
      for (final marker in ['항상', '자주', '종종']) {
        final r = await normalizer.normalize(
          '$marker 어제 같은 카페',
          kiwi: kiwi,
          reference: reference,
        );
        expect(r.text, contains('어제'),
            reason: '$marker should preserve "어제"');
      }
    });

    test('"3일마다" — N-unit recurrence preserved', () async {
      final r = await normalizer.normalize(
        '3일마다 운동',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '3일마다 운동');
    });

    test('"매년 12월 25일" — left untouched', () async {
      final r = await normalizer.normalize(
        '매년 12월 25일은 크리스마스',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '매년 12월 25일은 크리스마스');
    });
  });

  group('clause splitting (Kiwi-driven)', () {
    test('EF separates clauses — first preserved, second rewritten',
        () async {
      // "매주 금 만난다. 어제 X 했어"
      // Kiwi tags: 만난다(VV+EP+EF '다'), 어제(MAG)…
      // We script just the EF token to mark the boundary right after "다".
      const text = '매주 금 만난다. 어제 X 했어';
      final efPos = text.indexOf('다.') + 1; // after the 다, before .
      final kiwi = _ScriptedKiwi({
        text: [_ef('다', efPos - 1, 1)],
      });
      final r = await normalizer.normalize(
        text,
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, contains('매주 금'));
      expect(r.text, contains('2026년 4월 25일'));
      expect(r.text, isNot(contains('어제')));
    });

    test('EC separates clauses — same outcome for "-고"', () async {
      // "매주 금 만나고 어제 X 했어"
      const text = '매주 금 만나고 어제 X 했어';
      final ecPos = text.indexOf('고');
      final kiwi = _ScriptedKiwi({
        text: [_ec('고', ecPos, 1)],
      });
      final r = await normalizer.normalize(
        text,
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, startsWith('매주 금 만나고'));
      expect(r.text, contains('2026년 4월 25일'));
    });

    test('strong conjunction (그리고) is a clause boundary', () async {
      const text = '매주 금 만난다 그리고 어제 X 했어';
      final majPos = text.indexOf('그리고');
      final efPos = text.indexOf('다 ');
      final kiwi = _ScriptedKiwi({
        text: [_ef('다', efPos, 1), _maj('그리고', majPos)],
      });
      final r = await normalizer.normalize(
        text,
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, contains('2026년 4월 25일'));
    });

    test('-서 connective (any EC) also splits', () async {
      // The user case: "어제 가서 만났다" — splitting at -서 still produces
      // the right rewrite because the second clause has no time adverb.
      const text = '어제 가서 만났다';
      final ecPos = text.indexOf('서');
      final kiwi = _ScriptedKiwi({
        text: [_ec('서', ecPos, 1)],
      });
      final r = await normalizer.normalize(
        text,
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '2026년 4월 25일 가서 만났다');
    });

    test('mixed clauses: 매주 금요일에 가서 만났었는데 어제도 가서 만났다',
        () async {
      const text = '매주 금요일에 가서 만났었는데 어제도 가서 만났다';
      // EC boundaries at -서, -서, -는데. EF at -다.
      final boundaries = [
        _ec('서', text.indexOf('서'), 1),
        _ec('는데', text.indexOf('는데'), 2),
        _ec('서', text.indexOf('서', text.indexOf('어제')), 1),
        _ef('다', text.length - 1, 1),
      ];
      final kiwi = _ScriptedKiwi({text: boundaries});
      final r = await normalizer.normalize(
        text,
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, contains('매주 금요일에 가서'),
          reason: 'recurrence clause must be preserved');
      expect(r.text, contains('2026년 4월 25일'),
          reason: '"어제" should be rewritten to absolute date');
      expect(r.text, isNot(contains('어제')));
    });
  });

  group('edge cases', () {
    final kiwi = _ScriptedKiwi(const {});

    test('empty input', () async {
      final r = await normalizer.normalize(
        '',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '');
      expect(r.splitNodes, isEmpty);
    });

    test('no time adverb / no marker — verbatim', () async {
      final r = await normalizer.normalize(
        '점심에 김밥 먹었다',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '점심에 김밥 먹었다');
      expect(r.splitNodes, isEmpty);
    });

    test('partial date rewrite collects partial split nodes', () async {
      final r = await normalizer.normalize(
        '2026-04 분기 회고',
        kiwi: kiwi,
        reference: reference,
      );
      expect(r.text, '2026년 4월 분기 회고');
      // No 'NN일' nor 'YYYY년 MM월 NN일' since day is absent.
      expect(r.splitNodes, ['2026년', '4월', '2026년 4월']);
    });
  });
}

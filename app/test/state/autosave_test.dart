import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/src/state/autosave.dart';

void main() {
  group('autosaveStatusLabel', () {
    test('idle without prior save → empty', () {
      expect(autosaveStatusLabel(const AutosaveState()), '');
    });

    test('dirty → "입력 중" (dots are appended by the widget)', () {
      const state = AutosaveState(status: AutosaveStatus.dirty);
      expect(autosaveStatusLabel(state), '입력 중');
    });

    test('saving → "저장 중..."', () {
      const state = AutosaveState(status: AutosaveStatus.saving);
      expect(autosaveStatusLabel(state), '저장 중...');
    });

    test('saved → "저장됨" (time lives in the sidebar, not here)', () {
      const state = AutosaveState(status: AutosaveStatus.saved);
      expect(autosaveStatusLabel(state), '저장됨');
    });

    test('idle with a prior save also reads as "저장됨"', () {
      final state = AutosaveState(
        status: AutosaveStatus.idle,
        lastSavedAt: DateTime(2026, 4, 26, 12, 0, 0),
      );
      expect(autosaveStatusLabel(state), '저장됨');
    });

    test('error overrides any status', () {
      final state = AutosaveState(
        status: AutosaveStatus.dirty,
        error: StateError('disk full'),
      );
      expect(autosaveStatusLabel(state), '저장 실패 — 다시 시도 중');
    });
  });

  group('formatSaveTimestamp', () {
    test('within a minute → "N초 전"', () {
      final now = DateTime(2026, 4, 26, 12, 0, 0);
      expect(
        formatSaveTimestamp(now.subtract(const Duration(seconds: 30)), now),
        '30초 전',
      );
    });

    test('within an hour → "N분 전"', () {
      final now = DateTime(2026, 4, 26, 12, 0, 0);
      expect(
        formatSaveTimestamp(now.subtract(const Duration(minutes: 12)), now),
        '12분 전',
      );
    });

    test('past the hour but same day → "오늘 HH:MM"', () {
      final now = DateTime(2026, 4, 26, 14, 30, 0);
      expect(
        formatSaveTimestamp(DateTime(2026, 4, 26, 9, 5, 0), now),
        '오늘 09:05',
      );
    });

    test('yesterday → "어제 HH:MM"', () {
      final now = DateTime(2026, 4, 26, 9, 0, 0);
      expect(
        formatSaveTimestamp(DateTime(2026, 4, 25, 22, 15, 0), now),
        '어제 22:15',
      );
    });

    test('older → absolute date', () {
      final now = DateTime(2026, 4, 26, 9, 0, 0);
      expect(
        formatSaveTimestamp(DateTime(2026, 4, 20, 18, 45, 0), now),
        '2026-04-20 18:45',
      );
    });
  });
}

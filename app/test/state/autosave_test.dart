import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/src/state/autosave.dart';

void main() {
  group('autosaveStatusLabel', () {
    test('idle without prior save → empty', () {
      expect(autosaveStatusLabel(const AutosaveState()), '');
    });

    test('dirty → "입력 중" (dots are added by the widget)', () {
      const state = AutosaveState(status: AutosaveStatus.dirty);
      expect(autosaveStatusLabel(state), '입력 중');
    });

    test('saving → "저장 중..."', () {
      const state = AutosaveState(status: AutosaveStatus.saving);
      expect(autosaveStatusLabel(state), '저장 중...');
    });

    test('saved → "✓ 저장됨 (방금)"', () {
      const state = AutosaveState(status: AutosaveStatus.saved);
      expect(autosaveStatusLabel(state), '✓ 저장됨 (방금)');
    });

    test('idle within the minute uses seconds', () {
      final now = DateTime(2026, 4, 26, 12, 0, 0);
      final state = AutosaveState(
        status: AutosaveStatus.idle,
        lastSavedAt: now.subtract(const Duration(seconds: 30)),
      );
      expect(autosaveStatusLabel(state, now: now), '✓ 저장됨 30초 전');
    });

    test('idle within the hour uses minutes', () {
      final now = DateTime(2026, 4, 26, 12, 0, 0);
      final state = AutosaveState(
        status: AutosaveStatus.idle,
        lastSavedAt: now.subtract(const Duration(minutes: 12)),
      );
      expect(autosaveStatusLabel(state, now: now), '✓ 저장됨 12분 전');
    });

    test('idle past the hour but same day → "오늘 HH:MM"', () {
      final now = DateTime(2026, 4, 26, 14, 30, 0);
      final state = AutosaveState(
        status: AutosaveStatus.idle,
        lastSavedAt: DateTime(2026, 4, 26, 9, 5, 0),
      );
      expect(autosaveStatusLabel(state, now: now), '✓ 저장됨 오늘 09:05');
    });

    test('idle yesterday → "어제 HH:MM"', () {
      final now = DateTime(2026, 4, 26, 9, 0, 0);
      final state = AutosaveState(
        status: AutosaveStatus.idle,
        lastSavedAt: DateTime(2026, 4, 25, 22, 15, 0),
      );
      expect(autosaveStatusLabel(state, now: now), '✓ 저장됨 어제 22:15');
    });

    test('idle older than yesterday → absolute date', () {
      final now = DateTime(2026, 4, 26, 9, 0, 0);
      final state = AutosaveState(
        status: AutosaveStatus.idle,
        lastSavedAt: DateTime(2026, 4, 20, 18, 45, 0),
      );
      expect(autosaveStatusLabel(state, now: now), '✓ 저장됨 2026-04-20 18:45');
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
    test('older than a minute on the same day uses "오늘"', () {
      final now = DateTime(2026, 4, 26, 14, 30, 0);
      expect(
        formatSaveTimestamp(DateTime(2026, 4, 26, 13, 0, 0), now),
        '오늘 13:00',
      );
    });

    test('two days ago uses absolute date', () {
      final now = DateTime(2026, 4, 26, 9, 0, 0);
      expect(
        formatSaveTimestamp(DateTime(2026, 4, 24, 7, 30, 0), now),
        '2026-04-24 07:30',
      );
    });
  });
}

import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/src/state/autosave.dart';

void main() {
  group('autosaveStatusLabel', () {
    test('idle without prior save → empty', () {
      expect(autosaveStatusLabel(const AutosaveState()), '');
    });

    test('dirty → "변경됨"', () {
      const state = AutosaveState(status: AutosaveStatus.dirty);
      expect(autosaveStatusLabel(state), '변경됨');
    });

    test('saving → "저장 중..."', () {
      const state = AutosaveState(status: AutosaveStatus.saving);
      expect(autosaveStatusLabel(state), '저장 중...');
    });

    test('saved → "✓ 저장됨 (방금)"', () {
      const state = AutosaveState(status: AutosaveStatus.saved);
      expect(autosaveStatusLabel(state), '✓ 저장됨 (방금)');
    });

    test('idle with recent save uses relative time', () {
      final now = DateTime(2026, 4, 26, 12, 0, 0);
      final state = AutosaveState(
        status: AutosaveStatus.idle,
        lastSavedAt: now.subtract(const Duration(seconds: 30)),
      );
      expect(autosaveStatusLabel(state, now: now), '✓ 저장됨 (30초 전)');
    });

    test('idle with save older than an hour shows hours', () {
      final now = DateTime(2026, 4, 26, 12, 0, 0);
      final state = AutosaveState(
        status: AutosaveStatus.idle,
        lastSavedAt: now.subtract(const Duration(hours: 2)),
      );
      expect(autosaveStatusLabel(state, now: now), '✓ 저장됨 (2시간 전)');
    });

    test('error → 실패 라벨 (status 무시)', () {
      final state = AutosaveState(
        status: AutosaveStatus.dirty,
        error: StateError('disk full'),
      );
      expect(autosaveStatusLabel(state), '저장 실패 — 다시 시도 중');
    });
  });
}

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:synapse_engine/synapse_engine.dart';

import 'note_state.dart';

/// One of four lifecycle phases for the editor's autosave.
/// `idle`     — nothing pending; controller is in sync with DB.
/// `dirty`    — user typed; debounce timer is counting down.
/// `saving`   — flush is in flight (Timer fired or `flush()` called).
/// `saved`    — most recent flush succeeded; fades back to `idle` later.
enum AutosaveStatus { idle, dirty, saving, saved }

class AutosaveState {
  const AutosaveState({
    this.status = AutosaveStatus.idle,
    this.lastSavedAt,
    this.error,
  });

  final AutosaveStatus status;
  final DateTime? lastSavedAt;
  final Object? error;

  AutosaveState copyWith({
    AutosaveStatus? status,
    DateTime? lastSavedAt,
    Object? error,
  }) =>
      AutosaveState(
        status: status ?? this.status,
        lastSavedAt: lastSavedAt ?? this.lastSavedAt,
        error: error,
      );
}

/// Debounced autosave coordinator.
///
/// Editor wires user input to [schedule]; the controller cancels any pending
/// timer, waits [debounce], and then runs `flow.noteAutosave` for the post
/// id supplied at the time of scheduling. [flush] runs the same write
/// synchronously — used when the user navigates away, the app pauses, or
/// the sidebar selection changes (so the source load can't race past an
/// in-flight edit).
class AutosaveController extends StateNotifier<AutosaveState> {
  AutosaveController(
    this._ref, {
    Duration? debounce,
    Duration? savedHold,
  })  : _debounce = debounce ?? const Duration(milliseconds: 1500),
        _savedHold = savedHold ?? const Duration(seconds: 5),
        super(const AutosaveState());

  final Ref _ref;
  final Duration _debounce;
  final Duration _savedHold;

  Timer? _timer;
  Timer? _holdTimer; // saved → idle 전환 타이머
  int? _pendingPostId;
  String? _pendingSource;

  /// Queue an autosave for [postId] with the latest [source]. Resets the
  /// debounce window if a save was already pending.
  void schedule({required int postId, required String source}) {
    _pendingPostId = postId;
    _pendingSource = source;
    _holdTimer?.cancel();
    state = state.copyWith(status: AutosaveStatus.dirty);
    _timer?.cancel();
    _timer = Timer(_debounce, _runPendingSave);
  }

  /// Run the pending save now and `await` the DB write. Safe to call when
  /// nothing is pending — returns immediately.
  Future<void> flush() async {
    _timer?.cancel();
    _timer = null;
    await _runPendingSave();
  }

  Future<void> _runPendingSave() async {
    final postId = _pendingPostId;
    final source = _pendingSource;
    if (postId == null || source == null) return;

    _pendingPostId = null;
    _pendingSource = null;
    state = state.copyWith(status: AutosaveStatus.saving);

    try {
      final engine = await _ref.read(engineProvider.future);
      final flow = engine.flow;
      if (flow == null) {
        throw StateError('SynapseFlow not available — autosave skipped');
      }
      await flow.noteAutosave(postId: postId, source: source);
      // Refresh the sidebar so updated_at sort sees the bump and the
      // newly auto-filled title shows up.
      _ref.invalidate(postListProvider);
      final savedAt = DateTime.now();
      state = AutosaveState(
        status: AutosaveStatus.saved,
        lastSavedAt: savedAt,
      );
      // After the brief "saved (방금)" pulse, fall back to idle so the
      // status bar switches to the "✓ 저장됨 14:30" timestamp form.
      _holdTimer?.cancel();
      _holdTimer = Timer(_savedHold, () {
        if (!mounted) return;
        if (state.status == AutosaveStatus.saved) {
          state = state.copyWith(status: AutosaveStatus.idle);
        }
      });
    } catch (e) {
      state = state.copyWith(status: AutosaveStatus.dirty, error: e);
    }
  }

  /// Drop any pending save without running it. Used after a successful
  /// flush from `selectedPostIdProvider` listener so the next note's edits
  /// don't carry over a stale [_pendingPostId].
  void clear() {
    _timer?.cancel();
    _timer = null;
    _holdTimer?.cancel();
    _holdTimer = null;
    _pendingPostId = null;
    _pendingSource = null;
    state = const AutosaveState();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _holdTimer?.cancel();
    super.dispose();
  }
}

final autosaveProvider =
    StateNotifierProvider<AutosaveController, AutosaveState>((ref) {
  return AutosaveController(ref);
});

/// Map a save state to the human-readable label that appears on the
/// status bar. Pulled out so the UI widget stays declarative and so we
/// can unit-test the logic without spinning up a controller.
///
/// Time formatting is hybrid: short relative ("방금" / "30초 전" / "5분 전")
/// while the save is recent enough to feel immediate, then absolute
/// timestamps ("오늘 14:30" / "어제 14:30" / "2026-04-25 14:30") so a
/// note saved yesterday reads as "yesterday at 14:30" rather than
/// "23 hours ago" — long horizons need calendar context, not a counter.
String autosaveStatusLabel(AutosaveState state, {DateTime? now}) {
  if (state.error != null) return '저장 실패 — 다시 시도 중';
  switch (state.status) {
    case AutosaveStatus.idle:
      final saved = state.lastSavedAt;
      if (saved == null) return '';
      return '✓ 저장됨 ${formatSaveTimestamp(saved, now ?? DateTime.now())}';
    case AutosaveStatus.dirty:
      return '입력 중';
    case AutosaveStatus.saving:
      return '저장 중...';
    case AutosaveStatus.saved:
      return '✓ 저장됨 (방금)';
  }
}

/// Hybrid timestamp — short relative within the hour, absolute past that.
/// Public so the sidebar (`updated_at`) can use the same formatting.
String formatSaveTimestamp(DateTime t, DateTime now) {
  final delta = now.difference(t);
  if (delta.isNegative) return _absolute(t, now);
  if (delta.inSeconds < 5) return '방금';
  if (delta.inSeconds < 60) return '${delta.inSeconds}초 전';
  if (delta.inMinutes < 60) return '${delta.inMinutes}분 전';
  return _absolute(t, now);
}

String _absolute(DateTime t, DateTime now) {
  final today = DateTime(now.year, now.month, now.day);
  final that = DateTime(t.year, t.month, t.day);
  final dayDelta = today.difference(that).inDays;
  final clock = '${_pad(t.hour)}:${_pad(t.minute)}';
  if (dayDelta == 0) return '오늘 $clock';
  if (dayDelta == 1) return '어제 $clock';
  return '${t.year}-${_pad(t.month)}-${_pad(t.day)} $clock';
}

String _pad(int n) => n < 10 ? '0$n' : '$n';

/// Public helper used by NotePage / app lifecycle listeners.
Future<void> flushAutosave(WidgetRef ref) =>
    ref.read(autosaveProvider.notifier).flush();

/// Convenience for keeping the engine import out of UI files. The lifecycle
/// observer needs an engine reference to ensure the SynapseFlow exists; we
/// hand it back through this helper.
Future<SynapseEngine> readEngine(WidgetRef ref) =>
    ref.read(engineProvider.future);

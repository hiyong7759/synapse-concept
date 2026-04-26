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
  AutosaveController(this._ref, {Duration? debounce})
      : _debounce = debounce ?? const Duration(milliseconds: 1500),
        super(const AutosaveState());

  final Ref _ref;
  final Duration _debounce;

  Timer? _timer;
  int? _pendingPostId;
  String? _pendingSource;

  /// Queue an autosave for [postId] with the latest [source]. Resets the
  /// debounce window if a save was already pending.
  void schedule({required int postId, required String source}) {
    _pendingPostId = postId;
    _pendingSource = source;
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
      // Refresh the sidebar so updated_at sort sees the bump.
      _ref.invalidate(postListProvider);
      state = AutosaveState(
        status: AutosaveStatus.saved,
        lastSavedAt: DateTime.now(),
      );
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
    _pendingPostId = null;
    _pendingSource = null;
    state = const AutosaveState();
  }

  @override
  void dispose() {
    _timer?.cancel();
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
String autosaveStatusLabel(AutosaveState state, {DateTime? now}) {
  if (state.error != null) return '저장 실패 — 다시 시도 중';
  switch (state.status) {
    case AutosaveStatus.idle:
      final saved = state.lastSavedAt;
      if (saved == null) return '';
      return '✓ 저장됨 ${_relativeTime(saved, now ?? DateTime.now())}';
    case AutosaveStatus.dirty:
      return '변경됨';
    case AutosaveStatus.saving:
      return '저장 중...';
    case AutosaveStatus.saved:
      return '✓ 저장됨 (방금)';
  }
}

String _relativeTime(DateTime t, DateTime now) {
  final delta = now.difference(t);
  if (delta.inSeconds < 5) return '(방금)';
  if (delta.inSeconds < 60) return '(${delta.inSeconds}초 전)';
  if (delta.inMinutes < 60) return '(${delta.inMinutes}분 전)';
  return '(${delta.inHours}시간 전)';
}

/// Public helper used by NotePage / app lifecycle listeners.
Future<void> flushAutosave(WidgetRef ref) =>
    ref.read(autosaveProvider.notifier).flush();

/// Convenience for keeping the engine import out of UI files. The lifecycle
/// observer needs an engine reference to ensure the SynapseFlow exists; we
/// hand it back through this helper.
Future<SynapseEngine> readEngine(WidgetRef ref) =>
    ref.read(engineProvider.future);

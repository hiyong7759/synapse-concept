import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:synapse_engine/synapse_engine.dart';

import 'note_state.dart';

/// One of four lifecycle phases for the editor's autosave.
/// `idle`     — nothing pending; controller is in sync with DB.
/// `dirty`    — user typed; debounce timer is counting down.
/// `saving`   — flush is in flight (Timer fired or `flush()` called).
/// `saved`    — most recent flush succeeded.
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
///
/// Both `source` and `title` ride the same debouncer so the user can edit
/// both fields and end up with one DB UPDATE per pause.
class AutosaveController extends StateNotifier<AutosaveState> {
  AutosaveController(this._ref, {Duration? debounce})
      : _debounce = debounce ?? const Duration(milliseconds: 1500),
        super(const AutosaveState());

  final Ref _ref;
  final Duration _debounce;

  Timer? _timer;
  int? _pendingPostId;
  String? _pendingSource;
  // `null` means "don't touch title" — the engine keeps existing title or
  // applies first-line auto-fill. An empty string clears the title.
  String? _pendingTitle;
  bool _titleIncluded = false;

  /// Queue an autosave for [postId]. Either or both of [source] / [title]
  /// can be supplied. Resets the debounce window if a save was already
  /// pending.
  ///
  /// If [source] is omitted (e.g. the user is only editing the title),
  /// we fall back to the latest [editorDraftProvider] value so the DB
  /// always sees a consistent (source, title) pair.
  void schedule({
    required int postId,
    String? source,
    String? title,
  }) {
    _pendingPostId = postId;
    _pendingSource = source ?? _ref.read(editorDraftProvider);
    if (title != null) {
      _pendingTitle = title;
      _titleIncluded = true;
    }
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

    final title = _titleIncluded ? _pendingTitle : null;
    _pendingPostId = null;
    _pendingSource = null;
    _pendingTitle = null;
    _titleIncluded = false;
    state = state.copyWith(status: AutosaveStatus.saving);

    try {
      final engine = await _ref.read(engineProvider.future);
      final flow = engine.flow;
      if (flow == null) {
        throw StateError('SynapseFlow not available — autosave skipped');
      }
      await flow.noteAutosave(postId: postId, source: source, title: title);
      // Refresh the sidebar so updated_at sort sees the bump and the
      // newly auto-filled title shows up.
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
    _pendingTitle = null;
    _titleIncluded = false;
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
/// status bar above the editor. Three phases — "입력 중" / "저장 중..." /
/// "저장됨". Time-of-save is shown only in the sidebar (one source of truth
/// per surface), so this label stays stable across long idle windows.
String autosaveStatusLabel(AutosaveState state) {
  if (state.error != null) return '저장 실패 — 다시 시도 중';
  switch (state.status) {
    case AutosaveStatus.idle:
      return state.lastSavedAt == null ? '' : '저장됨';
    case AutosaveStatus.dirty:
      return '입력 중';
    case AutosaveStatus.saving:
      return '저장 중...';
    case AutosaveStatus.saved:
      return '저장됨';
  }
}

/// Hybrid timestamp — short relative within the hour, absolute past that.
/// Used by the sidebar to show "방금" / "5분 전" / "오늘 14:30" /
/// "어제 14:30" / "2026-04-25 14:30" against `posts.updated_at`.
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

/// Convenience for keeping the engine import out of UI files.
Future<SynapseEngine> readEngine(WidgetRef ref) =>
    ref.read(engineProvider.future);

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:synapse_engine/synapse_engine.dart';

import 'hypergraph_state.dart';
import 'note_state.dart';

/// Lifecycle phases for the user-triggered ⌘S meaning pass.
enum NoteProcessStatus { idle, processing, done, error }

class NoteProcessState {
  const NoteProcessState({
    this.status = NoteProcessStatus.idle,
    this.lastProcessedAt,
    this.result,
    this.error,
  });

  final NoteProcessStatus status;
  final DateTime? lastProcessedAt;

  /// The most recent successful run's result. UI renders the
  /// `corrections` list as inline cards below the editor.
  final NoteProcessResult? result;
  final Object? error;

  NoteProcessState copyWith({
    NoteProcessStatus? status,
    DateTime? lastProcessedAt,
    NoteProcessResult? result,
    Object? error,
  }) =>
      NoteProcessState(
        status: status ?? this.status,
        lastProcessedAt: lastProcessedAt ?? this.lastProcessedAt,
        result: result ?? this.result,
        error: error,
      );
}

/// Coordinates `flow.noteProcess(postId, source)` calls. Triggered by ⌘S
/// (or the "정리" button in the title row); not debounced — user has to
/// ask for it explicitly.
///
/// The controller does NOT call autosave first; the caller (NotePage's
/// shortcut handler) is responsible for `flushAutosave()` so that what
/// the engine reprocesses matches what's already in the DB.
class NoteProcessController extends StateNotifier<NoteProcessState> {
  NoteProcessController(this._ref) : super(const NoteProcessState());

  final Ref _ref;

  Future<void> run({required int postId, required String source}) async {
    state = state.copyWith(status: NoteProcessStatus.processing);
    try {
      final engine = await _ref.read(engineProvider.future);
      final flow = engine.flow;
      if (flow == null) {
        throw StateError('SynapseFlow not enabled');
      }
      final result = await flow.noteProcess(postId: postId, source: source);
      // The sidebar's updated_at and any cached graph snapshot need the
      // fresh data. The hypergraph snapshot also misses the new nodes /
      // mentions until invalidated — categorize colors fill in later as
      // the async queue drains.
      _ref.invalidate(postListProvider);
      _ref.invalidate(hypergraphGraphProvider);
      state = NoteProcessState(
        status: NoteProcessStatus.done,
        lastProcessedAt: DateTime.now(),
        result: result,
      );
    } catch (e) {
      state = state.copyWith(
        status: NoteProcessStatus.error,
        error: e,
      );
    }
  }

  /// Drop the current state — used after applying / dismissing all
  /// corrections, or when the user moves to a different post.
  void clear() {
    state = const NoteProcessState();
  }
}

final noteProcessProvider =
    StateNotifierProvider<NoteProcessController, NoteProcessState>((ref) {
  return NoteProcessController(ref);
});

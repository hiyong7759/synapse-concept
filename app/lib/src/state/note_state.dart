import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, TargetPlatform;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart' as sqflite;
import 'package:sqflite_common_ffi/sqflite_ffi.dart' as ffi;
import 'package:synapse_engine/synapse_engine.dart';

/// Shared SynapseEngine instance. Other providers (sidebar list, selected
/// post, editor draft) hang off it. The provider is `FutureProvider` because
/// engine creation is async (DB file open + migration).
final engineProvider = FutureProvider<SynapseEngine>((ref) async {
  // Desktop platforms need the FFI factory; mobile uses sqflite's built-in
  // platform plugin. iOS/Android are auto-handled by sqflite itself.
  if (_needsFfi) {
    ffi.sqfliteFfiInit();
    sqflite.databaseFactory = ffi.databaseFactoryFfi;
  }

  final dir = await getApplicationDocumentsDirectory();
  final dbPath = '${dir.path}/synapse.db';

  final engine = await SynapseEngine.create(
    EngineConfig(
      appName: 'synapse_app',
      allowedKinds: const ['note', 'synapse', 'insight'],
      reservedKinds: const ['synapse', 'insight'],
      dbPath: dbPath,
      categorySeed: CategorySeed.synapse19(),
    ),
    // F7a uses the in-memory Kiwi backend so the screen renders even
    // before the production WASM binding is wired in. Switching to the
    // real backend is a one-liner once F7c needs noun extraction.
    kiwiOverride: InMemoryKiwiBackend(),
  );

  ref.onDispose(engine.dispose);
  return engine;
});

bool get _needsFfi {
  switch (defaultTargetPlatform) {
    case TargetPlatform.macOS:
    case TargetPlatform.windows:
    case TargetPlatform.linux:
      return true;
    default:
      return false;
  }
}

/// Sidebar post list. Refresh by calling `ref.invalidate(postListProvider)`
/// after a post is added / deleted.
final postListProvider = FutureProvider<List<PostMeta>>((ref) async {
  final engine = await ref.watch(engineProvider.future);
  final flow = engine.flow;
  if (flow == null) return const [];
  return flow.listPosts();
});

/// Currently selected post id — `null` means the editor shows an empty
/// "no post selected" state. F7b will populate it on sidebar tap or after
/// "+ 새 노트".
final selectedPostIdProvider = StateProvider<int?>((ref) => null);

/// Editor draft text — local UI state only at F7a. F7b will pipe this
/// into the autosave debouncer.
final editorDraftProvider = StateProvider<String>((ref) => '');

/// Source text for the currently selected post — re-fetched whenever the
/// selection changes. Returns `null` when no post is selected. The editor
/// uses `ref.listen` on this to push the loaded text into its
/// [TextEditingController] without breaking the user's cursor.
final noteSourceProvider = FutureProvider.autoDispose<String?>((ref) async {
  final id = ref.watch(selectedPostIdProvider);
  if (id == null) return null;
  final engine = await ref.watch(engineProvider.future);
  final flow = engine.flow;
  if (flow == null) return null;
  final detail = await flow.getPost(id);
  return detail.source;
});

/// Creates a new empty note, refreshes the sidebar, and selects it.
/// Returns the new post id so the caller can focus / hand off.
Future<int> createNote(WidgetRef ref) async {
  final engine = await ref.read(engineProvider.future);
  final flow = engine.flow;
  if (flow == null) {
    throw StateError('SynapseFlow not enabled — note creation unavailable');
  }
  final id = await flow.createPost(kind: 'note');
  ref.invalidate(postListProvider);
  ref.read(selectedPostIdProvider.notifier).state = id;
  return id;
}

/// Deletes [postId] and refreshes the sidebar. If the deleted post was
/// the active selection, clears it back to "no post selected".
Future<void> deleteNote(WidgetRef ref, int postId) async {
  final engine = await ref.read(engineProvider.future);
  final flow = engine.flow;
  if (flow == null) {
    throw StateError('SynapseFlow not enabled — note deletion unavailable');
  }
  await flow.deletePost(postId);
  if (ref.read(selectedPostIdProvider) == postId) {
    ref.read(selectedPostIdProvider.notifier).state = null;
  }
  ref.invalidate(postListProvider);
}

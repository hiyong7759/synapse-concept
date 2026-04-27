import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/autosave.dart';
import '../state/note_process.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';
import 'empty_editor_guide.dart';

/// Single-input markdown editor.
///
/// F7b-2 wires the editor into the autosave controller:
///   - keystrokes go to `autosaveProvider.notifier.schedule(...)`
///   - sidebar selection changes flush the previous note before the new
///     source is poured into the controller (no input loss across notes)
///   - lifecycle / route flushes are owned by [NotePage] so the editor
///     itself doesn't have to know about WidgetsBindingObserver.
class NoteEditor extends ConsumerStatefulWidget {
  const NoteEditor({super.key});

  @override
  ConsumerState<NoteEditor> createState() => _NoteEditorState();
}

class _NoteEditorState extends ConsumerState<NoteEditor> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: ref.read(editorDraftProvider));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _applyLoadedSource(String? source) {
    final next = source ?? '';
    if (_controller.text == next) return;
    _controller.value = TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(offset: next.length),
    );
    ref.read(editorDraftProvider.notifier).state = next;
  }

  @override
  Widget build(BuildContext context) {
    final selectedId = ref.watch(selectedPostIdProvider);

    // Sidebar selection change → flush in-flight edits, then apply the
    // newly-loaded source. Done as an async sequence inside the listener
    // to make sure no keystroke escapes between the two.
    ref.listen<AsyncValue<String?>>(noteSourceProvider, (_, next) {
      next.whenData((source) async {
        await ref.read(autosaveProvider.notifier).flush();
        ref.read(autosaveProvider.notifier).clear();
        // The previous note's "정리됨" badge shouldn't carry over to a
        // freshly opened post.
        ref.read(noteProcessProvider.notifier).clear();
        _applyLoadedSource(source);
      });
    });

    if (selectedId == null) {
      return const EmptyEditorGuide();
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        SynapseTokens.spaceL,
        SynapseTokens.spaceS,
        SynapseTokens.spaceL,
        SynapseTokens.spaceL,
      ),
      child: TextField(
        controller: _controller,
        maxLines: null,
        expands: true,
        style: SynapseTokens.body,
        decoration: InputDecoration(
          border: InputBorder.none,
          hintText: '여기에 적으세요. 자동저장은 1.5초 후 적용됩니다.',
          hintStyle: SynapseTokens.caption,
        ),
        onChanged: (value) {
          ref.read(editorDraftProvider.notifier).state = value;
          ref.read(autosaveProvider.notifier).schedule(
                postId: selectedId,
                source: value,
              );
        },
      ),
    );
  }
}

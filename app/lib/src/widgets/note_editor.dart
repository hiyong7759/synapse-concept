import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Single-input markdown editor. F7b-1 wires the source-load path: when
/// the sidebar selection changes, the editor pulls `posts.source` from
/// the engine and shoves it into the [TextEditingController]. Saving
/// (debounced autosave) lands in F7b-2.
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

    // React to selection / source changes from outside the editor (sidebar
    // click, fresh "new note", etc.) by replacing the controller text.
    ref.listen<AsyncValue<String?>>(noteSourceProvider, (_, next) {
      next.whenData(_applyLoadedSource);
    });

    if (selectedId == null) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(SynapseTokens.spaceL),
          child: Text(
            '노트를 선택하거나 [+ 새 노트] 로 시작하세요.',
            style: SynapseTokens.caption,
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.all(SynapseTokens.spaceL),
      child: TextField(
        controller: _controller,
        maxLines: null,
        expands: true,
        style: SynapseTokens.body,
        decoration: const InputDecoration(
          border: InputBorder.none,
          hintText: '여기에 적으세요. (자동저장은 F7b-2 에서, ⌘S 정리는 F7c 에서)',
          hintStyle: SynapseTokens.caption,
        ),
        onChanged: (value) {
          ref.read(editorDraftProvider.notifier).state = value;
        },
      ),
    );
  }
}

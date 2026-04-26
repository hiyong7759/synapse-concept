import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Single-input markdown editor. F7a is the visual scaffold only — the
/// `TextField` writes into `editorDraftProvider` so the value survives
/// rebuilds, but no autosave / sentence processing fires yet (those land
/// in F7b and F7c respectively).
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

  @override
  Widget build(BuildContext context) {
    final selectedId = ref.watch(selectedPostIdProvider);

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
          hintText: '여기에 적으세요. (자동저장은 F7b 에서, ⌘S 정리는 F7c 에서)',
          hintStyle: SynapseTokens.caption,
        ),
        onChanged: (value) {
          ref.read(editorDraftProvider.notifier).state = value;
        },
      ),
    );
  }
}

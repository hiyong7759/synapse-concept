import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Header line above the editor body — single-line title field.
///
/// Shares the autosave debouncer with [NoteEditor], so editing either the
/// title or the body schedules one combined UPDATE per pause. Reading the
/// initial value comes from [noteTitleProvider]; once loaded, the local
/// [TextEditingController] owns the text and only resyncs when the
/// sidebar selection changes.
class TitleEditor extends ConsumerStatefulWidget {
  const TitleEditor({super.key});

  @override
  ConsumerState<TitleEditor> createState() => _TitleEditorState();
}

class _TitleEditorState extends ConsumerState<TitleEditor> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: ref.read(titleDraftProvider));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _applyLoadedTitle(String? title) {
    final next = title ?? '';
    if (_controller.text == next) return;
    _controller.value = TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(offset: next.length),
    );
    ref.read(titleDraftProvider.notifier).state = next;
  }

  @override
  Widget build(BuildContext context) {
    final selectedId = ref.watch(selectedPostIdProvider);

    ref.listen<AsyncValue<String?>>(noteTitleProvider, (_, next) {
      next.whenData(_applyLoadedTitle);
    });

    if (selectedId == null) return const SizedBox.shrink();

    return TextField(
      controller: _controller,
      style: SynapseTokens.display.copyWith(fontSize: 24),
      maxLines: 1,
      decoration: const InputDecoration(
        border: InputBorder.none,
        isCollapsed: true,
        hintText: '제목',
        hintStyle: TextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          color: SynapseTokens.onSurfaceMuted,
        ),
      ),
      onChanged: (value) {
        ref.read(titleDraftProvider.notifier).state = value;
        ref.read(autosaveProvider.notifier).schedule(
              postId: selectedId,
              title: value,
            );
      },
    );
  }
}

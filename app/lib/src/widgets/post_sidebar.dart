import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:synapse_engine/synapse_engine.dart';

import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';
import 'components.dart';

/// Sidebar listing every post grouped by kind (`note` / `synapse`),
/// matching DESIGN_UI §post 사이드바. Insight posts get the `✦` glyph and
/// an amber border. Hover (desktop) or long-press (mobile) reveals the
/// delete affordance.
class PostSidebar extends ConsumerWidget {
  const PostSidebar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final postsAsync = ref.watch(postListProvider);
    final selectedId = ref.watch(selectedPostIdProvider);

    return Container(
      decoration: const BoxDecoration(
        color: SynapseTokens.bg2,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _NewNoteButton(onPressed: () => createNote(ref)),
          Expanded(
            child: postsAsync.when(
              data: (posts) => _PostList(
                posts: posts,
                selectedId: selectedId,
                onSelect: (id) =>
                    ref.read(selectedPostIdProvider.notifier).state = id,
                onDelete: (post) => _confirmAndDelete(context, ref, post),
              ),
              loading: () => const Center(
                child: SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: SynapseTokens.accent,
                  ),
                ),
              ),
              error: (e, _) => Padding(
                padding: const EdgeInsets.all(SynapseTokens.s4),
                child: Text(
                  '목록 로드 실패: $e',
                  style: SynapseTokens.bodyStyle(
                    size: SynapseTokens.tSm,
                    color: SynapseTokens.danger,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmAndDelete(
    BuildContext context,
    WidgetRef ref,
    PostMeta post,
  ) async {
    final title = post.title?.trim().isNotEmpty == true
        ? post.title!.trim()
        : '제목 없음';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: SynapseTokens.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(SynapseTokens.rLg),
          side: const BorderSide(color: SynapseTokens.border),
        ),
        title: Text(
          '노트 삭제',
          style: SynapseTokens.bodyStyle(
            size: SynapseTokens.tLg,
            weight: FontWeight.w600,
            color: SynapseTokens.text,
          ),
        ),
        content: Text(
          '"$title" 을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.',
          style: SynapseTokens.bodyStyle(
            size: SynapseTokens.tBase,
            color: SynapseTokens.text2,
          ),
        ),
        actionsPadding: const EdgeInsets.fromLTRB(
          SynapseTokens.s4,
          0,
          SynapseTokens.s4,
          SynapseTokens.s4,
        ),
        actions: [
          SButton(
            label: '취소',
            variant: SButtonVariant.ghost,
            size: SButtonSize.sm,
            onPressed: () => Navigator.of(ctx).pop(false),
          ),
          const SizedBox(width: SynapseTokens.s2),
          SButton(
            label: '삭제',
            variant: SButtonVariant.danger,
            size: SButtonSize.sm,
            onPressed: () => Navigator.of(ctx).pop(true),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await deleteNote(ref, post.id);
    }
  }
}

/// Full-width pressable header — clicking anywhere in the row creates a new
/// note. Hovering tints the entire row, not just the inline button, so the
/// affordance is unambiguous.
class _NewNoteButton extends StatefulWidget {
  const _NewNoteButton({required this.onPressed});
  final VoidCallback onPressed;

  @override
  State<_NewNoteButton> createState() => _NewNoteButtonState();
}

class _NewNoteButtonState extends State<_NewNoteButton> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: widget.onPressed,
        child: AnimatedContainer(
          duration: SynapseTokens.durFast,
          curve: SynapseTokens.ease,
          height: 44,
          padding: const EdgeInsets.symmetric(horizontal: SynapseTokens.s4),
          decoration: BoxDecoration(
            color: _hover ? SynapseTokens.surface2 : Colors.transparent,
            border: const Border(
              bottom: BorderSide(color: SynapseTokens.border),
            ),
          ),
          child: Row(
            children: [
              Icon(
                Icons.add,
                size: 16,
                color: _hover ? SynapseTokens.accent : SynapseTokens.text2,
              ),
              const SizedBox(width: SynapseTokens.s2),
              Text(
                '새 노트',
                style: SynapseTokens.bodyStyle(
                  size: SynapseTokens.tSm,
                  weight: FontWeight.w500,
                  color: _hover ? SynapseTokens.text : SynapseTokens.text2,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PostList extends StatelessWidget {
  const _PostList({
    required this.posts,
    required this.selectedId,
    required this.onSelect,
    required this.onDelete,
  });

  final List<PostMeta> posts;
  final int? selectedId;
  final ValueChanged<int> onSelect;
  final ValueChanged<PostMeta> onDelete;

  @override
  Widget build(BuildContext context) {
    if (posts.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(SynapseTokens.s4),
          child: Text(
            '아직 노트가 없습니다.\n[+ 새 노트] 로 시작하세요.',
            textAlign: TextAlign.center,
            style: SynapseTokens.bodyStyle(
              size: SynapseTokens.tSm,
              color: SynapseTokens.text3,
              height: 1.6,
            ),
          ),
        ),
      );
    }

    final notes = posts.where((p) => p.kind == 'note').toList();
    final synapses = posts.where((p) => p.kind == 'synapse').toList();

    return ListView(
      padding: const EdgeInsets.symmetric(vertical: SynapseTokens.s3),
      children: [
        if (notes.isNotEmpty) ...[
          const _SectionLabel('── 노트 ──'),
          for (final post in notes)
            _PostTile(
              post: post,
              isSelected: post.id == selectedId,
              onTap: () => onSelect(post.id),
              onDelete: () => onDelete(post),
            ),
        ],
        if (synapses.isNotEmpty) ...[
          const SizedBox(height: SynapseTokens.s3),
          const _SectionLabel('── 시냅스 ──'),
          for (final post in synapses)
            _PostTile(
              post: post,
              isSelected: post.id == selectedId,
              onTap: () => onSelect(post.id),
              onDelete: () => onDelete(post),
              isSynapse: true,
            ),
        ],
      ],
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        SynapseTokens.s4,
        SynapseTokens.s3,
        SynapseTokens.s4,
        SynapseTokens.s2,
      ),
      child: Text(
        text,
        style: SynapseTokens.monoStyle(
          size: 10,
          color: SynapseTokens.text4,
          letterSpacing: 0.15 * 10,
        ),
      ),
    );
  }
}

class _PostTile extends StatefulWidget {
  const _PostTile({
    required this.post,
    required this.isSelected,
    required this.onTap,
    required this.onDelete,
    this.isSynapse = false,
  });

  final PostMeta post;
  final bool isSelected;
  final VoidCallback onTap;
  final VoidCallback onDelete;
  final bool isSynapse;

  @override
  State<_PostTile> createState() => _PostTileState();
}

class _PostTileState extends State<_PostTile> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final post = widget.post;
    final isInsight = post.kind == 'insight';
    final isSelected = widget.isSelected;
    final title = post.title?.trim().isNotEmpty == true
        ? post.title!.trim()
        : '제목 없음';
    final timestamp = formatSaveTimestamp(
      parsePostTimestamp(post.updatedAt),
      DateTime.now(),
    );

    final background = isInsight
        ? const Color(0x0DC8A96E)
        : isSelected
            ? SynapseTokens.surface
            : Colors.transparent;
    final leftBorderColor = isSelected
        ? SynapseTokens.accent
        : Colors.transparent;
    final insightBorder = isInsight
        ? const Border(
            top: BorderSide(color: SynapseTokens.accentLine),
            bottom: BorderSide(color: SynapseTokens.accentLine),
          )
        : null;

    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: widget.onTap,
        onLongPress: widget.onDelete,
        child: Container(
          decoration: BoxDecoration(
            color: background,
            border: insightBorder ??
                Border(
                  left: BorderSide(color: leftBorderColor, width: 2),
                ),
          ),
          padding: const EdgeInsets.fromLTRB(
            SynapseTokens.s3,
            SynapseTokens.s2,
            SynapseTokens.s3,
            SynapseTokens.s2,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              if (isInsight) ...[
                const Text(
                  '✦',
                  style: TextStyle(
                    color: SynapseTokens.accent,
                    fontSize: SynapseTokens.tBase,
                  ),
                ),
                const SizedBox(width: SynapseTokens.s2),
              ] else if (widget.isSynapse) ...[
                const Text(
                  '◯',
                  style: TextStyle(
                    color: SynapseTokens.text3,
                    fontSize: SynapseTokens.tSm,
                  ),
                ),
                const SizedBox(width: SynapseTokens.s2),
              ],
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: SynapseTokens.bodyStyle(
                        size: 13,
                        weight: isSelected
                            ? FontWeight.w500
                            : FontWeight.w400,
                        color: isSelected
                            ? SynapseTokens.text
                            : SynapseTokens.text2,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      timestamp,
                      style: SynapseTokens.monoStyle(
                        size: 10,
                        color: SynapseTokens.text4,
                      ),
                    ),
                  ],
                ),
              ),
              if (_hovered)
                IconButton(
                  icon: const Icon(
                    Icons.close,
                    size: 14,
                    color: SynapseTokens.text3,
                  ),
                  tooltip: '삭제',
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(
                    minWidth: 24,
                    minHeight: 24,
                  ),
                  onPressed: widget.onDelete,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

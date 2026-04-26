import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:synapse_engine/synapse_engine.dart';

import '../state/autosave.dart';
import '../state/note_state.dart';
import '../theme/tokens.dart';

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
      width: 220,
      color: SynapseTokens.surface,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(SynapseTokens.spaceM),
            child: ElevatedButton.icon(
              onPressed: () => createNote(ref),
              icon: const Icon(Icons.add),
              label: const Text('새 노트'),
            ),
          ),
          Expanded(
            child: postsAsync.when(
              data: (posts) => _PostList(
                posts: posts,
                selectedId: selectedId,
                onSelect: (id) =>
                    ref.read(selectedPostIdProvider.notifier).state = id,
                onDelete: (post) => _confirmAndDelete(context, ref, post),
                onRename: (post) => _promptRename(context, ref, post),
              ),
              loading: () =>
                  const Center(child: CircularProgressIndicator.adaptive()),
              error: (e, _) => Padding(
                padding: const EdgeInsets.all(SynapseTokens.spaceM),
                child: Text('목록 로드 실패: $e', style: SynapseTokens.caption),
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
        title: const Text('노트 삭제'),
        content: Text('"$title" 을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('취소'),
          ),
          TextButton(
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await deleteNote(ref, post.id);
    }
  }

  Future<void> _promptRename(
    BuildContext context,
    WidgetRef ref,
    PostMeta post,
  ) async {
    final controller = TextEditingController(text: post.title ?? '');
    final newTitle = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('제목 편집'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: '노트 제목'),
          onSubmitted: (v) => Navigator.of(ctx).pop(v.trim()),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: () =>
                Navigator.of(ctx).pop(controller.text.trim()),
            child: const Text('저장'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (newTitle != null && newTitle.isNotEmpty) {
      await renameNote(ref, post.id, newTitle);
    }
  }
}

class _PostList extends StatelessWidget {
  const _PostList({
    required this.posts,
    required this.selectedId,
    required this.onSelect,
    required this.onDelete,
    required this.onRename,
  });

  final List<PostMeta> posts;
  final int? selectedId;
  final ValueChanged<int> onSelect;
  final ValueChanged<PostMeta> onDelete;
  final ValueChanged<PostMeta> onRename;

  @override
  Widget build(BuildContext context) {
    if (posts.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(SynapseTokens.spaceM),
          child: Text(
            '아직 노트가 없습니다.\n[+ 새 노트] 로 시작하세요.',
            textAlign: TextAlign.center,
            style: SynapseTokens.caption,
          ),
        ),
      );
    }

    final notes = posts.where((p) => p.kind == 'note').toList();
    final synapses = posts.where((p) => p.kind == 'synapse').toList();

    return ListView(
      children: [
        if (notes.isNotEmpty) ...[
          const _SectionLabel('— 노트 —'),
          for (final post in notes)
            _PostTile(
              post: post,
              isSelected: post.id == selectedId,
              onTap: () => onSelect(post.id),
              onDelete: () => onDelete(post),
              onRename: () => onRename(post),
            ),
        ],
        if (synapses.isNotEmpty) ...[
          const SizedBox(height: SynapseTokens.spaceS),
          const _SectionLabel('— 시냅스 —'),
          for (final post in synapses)
            _PostTile(
              post: post,
              isSelected: post.id == selectedId,
              onTap: () => onSelect(post.id),
              onDelete: () => onDelete(post),
              onRename: () => onRename(post),
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
      padding: const EdgeInsets.symmetric(
        horizontal: SynapseTokens.spaceM,
        vertical: SynapseTokens.spaceS,
      ),
      child: Text(text, style: SynapseTokens.caption),
    );
  }
}

class _PostTile extends StatefulWidget {
  const _PostTile({
    required this.post,
    required this.isSelected,
    required this.onTap,
    required this.onDelete,
    required this.onRename,
  });

  final PostMeta post;
  final bool isSelected;
  final VoidCallback onTap;
  final VoidCallback onDelete;
  final VoidCallback onRename;

  @override
  State<_PostTile> createState() => _PostTileState();
}

class _PostTileState extends State<_PostTile> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final post = widget.post;
    final isInsight = post.kind == 'insight';
    final title = post.title?.trim().isNotEmpty == true
        ? post.title!.trim()
        : '제목 없음';
    final timestamp = formatSaveTimestamp(
      parsePostTimestamp(post.updatedAt),
      DateTime.now(),
    );
    final accent = isInsight ? SynapseTokens.insightAccent : null;

    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: Material(
        color: widget.isSelected
            ? SynapseTokens.background
            : SynapseTokens.surface,
        child: InkWell(
          onTap: widget.onTap,
          onLongPress: widget.onDelete,
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: SynapseTokens.spaceM,
              vertical: SynapseTokens.spaceS,
            ),
            decoration: BoxDecoration(
              border: accent == null
                  ? null
                  : Border(left: BorderSide(color: accent, width: 3)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                if (isInsight)
                  const Padding(
                    padding: EdgeInsets.only(right: SynapseTokens.spaceXs),
                    child: Text('✦',
                        style:
                            TextStyle(color: SynapseTokens.insightAccent)),
                  ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: SynapseTokens.body,
                      ),
                      const SizedBox(height: 2),
                      Text(timestamp, style: SynapseTokens.caption),
                    ],
                  ),
                ),
                if (_hovered) ...[
                  IconButton(
                    icon: const Icon(Icons.edit, size: 16),
                    tooltip: '제목 편집',
                    visualDensity: VisualDensity.compact,
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(
                      minWidth: 24,
                      minHeight: 24,
                    ),
                    onPressed: widget.onRename,
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 16),
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
              ],
            ),
          ),
        ),
      ),
    );
  }
}

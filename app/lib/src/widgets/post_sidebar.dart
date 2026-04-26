import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:synapse_engine/synapse_engine.dart';

import '../state/note_state.dart';
import '../theme/tokens.dart';

/// Sidebar listing every post grouped by kind (`note` / `synapse`),
/// matching DESIGN_UI §post 사이드바. Insight posts get the `✦` glyph and
/// an amber border. Hover surfaces a delete affordance — F7a wires the
/// click but the actual delete handler lands in F7b alongside autosave.
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
              onPressed: () {
                // F7b will create a fresh `kind='note'` post and select it.
              },
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
}

class _PostList extends StatelessWidget {
  const _PostList({
    required this.posts,
    required this.selectedId,
    required this.onSelect,
  });

  final List<PostMeta> posts;
  final int? selectedId;
  final ValueChanged<int> onSelect;

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

class _PostTile extends StatelessWidget {
  const _PostTile({
    required this.post,
    required this.isSelected,
    required this.onTap,
  });

  final PostMeta post;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isInsight = post.kind == 'insight';
    final title = post.title?.trim().isNotEmpty == true
        ? post.title!.trim()
        : '제목 없음';
    final accent = isInsight ? SynapseTokens.insightAccent : null;

    return Material(
      color: isSelected
          ? SynapseTokens.background
          : SynapseTokens.surface,
      child: InkWell(
        onTap: onTap,
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
            children: [
              if (isInsight)
                const Padding(
                  padding: EdgeInsets.only(right: SynapseTokens.spaceXs),
                  child: Text('✦',
                      style: TextStyle(color: SynapseTokens.insightAccent)),
                ),
              Expanded(
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: SynapseTokens.body,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/synapse_state.dart';
import '../theme/tokens.dart';
import 'a_card.dart';
import 'components.dart';
import 'q_card.dart';
import 'suggestion_chips.dart';

/// Centre column of `/synapse` — message list (`Q` / `A` cards) on top,
/// input bar on the bottom. Empty state surfaces dynamic suggestion
/// chips derived from the user's own recent activity (or a guidance
/// card when the DB has nothing yet). DESIGN_UI §/synapse.
class SynapseThread extends ConsumerStatefulWidget {
  const SynapseThread({super.key});

  @override
  ConsumerState<SynapseThread> createState() => _SynapseThreadState();
}

class _SynapseThreadState extends ConsumerState<SynapseThread> {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  late final ScrollController _scrollController;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController();
    _focusNode = FocusNode();
    _scrollController = ScrollController();
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _fillFromChip(String text) {
    _controller.text = text;
    // Today's chip texts plug recent node names directly so the
    // selection lands at the end. The placeholder branch stays so the
    // template-style chips F-future-block can drop a `[주제]` token and
    // have the input bar pre-select it.
    final placeholder = RegExp(r'\[[^\]]+\]').firstMatch(text);
    if (placeholder != null) {
      _controller.selection = TextSelection(
        baseOffset: placeholder.start,
        extentOffset: placeholder.end,
      );
    } else {
      _controller.selection = TextSelection.collapsed(offset: text.length);
    }
    _focusNode.requestFocus();
  }

  Future<void> _send() async {
    final question = _controller.text.trim();
    if (question.isEmpty) return;
    _controller.clear();
    try {
      await sendQuestion(ref, question);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!_scrollController.hasClients) return;
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: SynapseTokens.durBase,
          curve: SynapseTokens.ease,
        );
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('인출 실패: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final messages = ref.watch(synapseMessagesProvider);
    final loading = ref.watch(synapseLoadingProvider);

    return Container(
      color: SynapseTokens.bg,
      child: Column(
        children: [
          Expanded(
            child: messages.isEmpty
                ? _EmptyState(onPick: _fillFromChip)
                : _MessageList(
                    messages: messages,
                    showLoading: loading,
                    scrollController: _scrollController,
                  ),
          ),
          _InputBar(
            controller: _controller,
            focusNode: _focusNode,
            enabled: !loading,
            onSubmit: _send,
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.onPick});

  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(SynapseTokens.s6),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SBrandMark(size: 48, glow: true),
            const SizedBox(height: SynapseTokens.s4),
            Text(
              '어떤 걸 떠올려볼까요?',
              style: SynapseTokens.displayStyle(
                size: SynapseTokens.t2xl,
                color: SynapseTokens.text,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: SynapseTokens.s2),
            Text(
              '최근에 적은 내용에서 자주 마주친 주제를 모았어요.',
              style: SynapseTokens.bodyStyle(
                size: SynapseTokens.tSm,
                color: SynapseTokens.text3,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: SynapseTokens.s5),
            SuggestionChips(onPick: onPick),
          ],
        ),
      ),
    );
  }
}

class _MessageList extends StatelessWidget {
  const _MessageList({
    required this.messages,
    required this.showLoading,
    required this.scrollController,
  });

  final List<SynapseMessage> messages;
  final bool showLoading;
  final ScrollController scrollController;

  @override
  Widget build(BuildContext context) {
    final itemCount = messages.length + (showLoading ? 1 : 0);
    return ListView.builder(
      controller: scrollController,
      padding: const EdgeInsets.fromLTRB(
        SynapseTokens.s5,
        SynapseTokens.s5,
        SynapseTokens.s5,
        SynapseTokens.s2,
      ),
      itemCount: itemCount,
      itemBuilder: (_, i) {
        if (i == messages.length) {
          return const _LoadingIndicator();
        }
        final m = messages[i];
        return switch (m) {
          SynapseQuestion() => QCard(text: m.text),
          SynapseAnswer() => ACard(text: m.text),
        };
      },
    );
  }
}

class _LoadingIndicator extends StatelessWidget {
  const _LoadingIndicator();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
        vertical: SynapseTokens.s3,
        horizontal: SynapseTokens.s2,
      ),
      child: Row(
        children: [
          const SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: SynapseTokens.accent,
            ),
          ),
          const SizedBox(width: SynapseTokens.s3),
          Text(
            '탐색 중...',
            style: SynapseTokens.bodyStyle(
              size: SynapseTokens.tSm,
              color: SynapseTokens.text3,
            ),
          ),
        ],
      ),
    );
  }
}

class _InputBar extends StatelessWidget {
  const _InputBar({
    required this.controller,
    required this.focusNode,
    required this.enabled,
    required this.onSubmit,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool enabled;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        SynapseTokens.s5,
        SynapseTokens.s3,
        SynapseTokens.s5,
        SynapseTokens.s5,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              focusNode: focusNode,
              enabled: enabled,
              minLines: 1,
              maxLines: 4,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => enabled ? onSubmit() : null,
              style: SynapseTokens.bodyStyle(
                size: SynapseTokens.tMd,
                color: SynapseTokens.text,
              ),
              cursorColor: SynapseTokens.accent,
              decoration: InputDecoration(
                filled: true,
                fillColor: SynapseTokens.surface2,
                hintText: enabled ? '질문 입력...' : '응답 생성 중...',
                hintStyle: SynapseTokens.bodyStyle(
                  size: SynapseTokens.tMd,
                  color: SynapseTokens.text4,
                ),
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: SynapseTokens.s4,
                  vertical: SynapseTokens.s3,
                ),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(SynapseTokens.rLg),
                  borderSide: const BorderSide(color: SynapseTokens.border),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(SynapseTokens.rLg),
                  borderSide: const BorderSide(color: SynapseTokens.border),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(SynapseTokens.rLg),
                  borderSide: const BorderSide(color: SynapseTokens.accent),
                ),
              ),
            ),
          ),
          const SizedBox(width: SynapseTokens.s2),
          IconButton.filled(
            onPressed: enabled ? onSubmit : null,
            icon: const Icon(Icons.arrow_upward, size: 18),
            style: IconButton.styleFrom(
              backgroundColor: enabled
                  ? SynapseTokens.accent
                  : SynapseTokens.surface3,
              foregroundColor: enabled
                  ? SynapseTokens.bg
                  : SynapseTokens.text4,
              padding: const EdgeInsets.all(SynapseTokens.s3),
            ),
          ),
        ],
      ),
    );
  }
}

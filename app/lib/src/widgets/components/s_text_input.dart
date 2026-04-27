import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// Single-line dark text input with focus-tinted border.
///
/// Mirrors the React `TextInput` from the design bundle. Used for the
/// hypergraph search box, node-name lookups, and anywhere the editor itself
/// is too heavy. For multiline / autosaving prose use `NoteEditor`.
class STextInput extends StatefulWidget {
  const STextInput({
    super.key,
    this.controller,
    this.placeholder,
    this.onChanged,
    this.mono = false,
    this.autofocus = false,
    this.focusNode,
  });

  final TextEditingController? controller;
  final String? placeholder;
  final ValueChanged<String>? onChanged;

  /// Switch to JetBrains Mono — used for node-name search where the user is
  /// typing identifiers, not prose.
  final bool mono;

  final bool autofocus;
  final FocusNode? focusNode;

  @override
  State<STextInput> createState() => _STextInputState();
}

class _STextInputState extends State<STextInput> {
  late final FocusNode _focusNode;
  bool _ownsFocusNode = false;
  bool _focused = false;

  @override
  void initState() {
    super.initState();
    if (widget.focusNode != null) {
      _focusNode = widget.focusNode!;
    } else {
      _focusNode = FocusNode();
      _ownsFocusNode = true;
    }
    _focusNode.addListener(_onFocusChange);
  }

  @override
  void dispose() {
    _focusNode.removeListener(_onFocusChange);
    if (_ownsFocusNode) _focusNode.dispose();
    super.dispose();
  }

  void _onFocusChange() {
    setState(() => _focused = _focusNode.hasFocus);
  }

  @override
  Widget build(BuildContext context) {
    final textStyle = widget.mono
        ? SynapseTokens.monoStyle(
            size: 13,
            color: SynapseTokens.text,
          )
        : SynapseTokens.bodyStyle(
            size: 13,
            color: SynapseTokens.text,
          );

    return AnimatedContainer(
      duration: SynapseTokens.durFast,
      curve: SynapseTokens.ease,
      decoration: BoxDecoration(
        color: SynapseTokens.surface2,
        borderRadius: BorderRadius.circular(SynapseTokens.rMd),
        border: Border.all(
          color: _focused ? SynapseTokens.accentLine : SynapseTokens.border2,
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: TextField(
        controller: widget.controller,
        focusNode: _focusNode,
        autofocus: widget.autofocus,
        onChanged: widget.onChanged,
        style: textStyle,
        cursorColor: SynapseTokens.accent,
        decoration: InputDecoration(
          isCollapsed: true,
          border: InputBorder.none,
          hintText: widget.placeholder,
          hintStyle: textStyle.copyWith(color: SynapseTokens.text3),
        ),
      ),
    );
  }
}

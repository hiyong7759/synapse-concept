import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// Five visual variants — ordered roughly from "most attention" to "least".
enum SButtonVariant {
  /// Brand action. Amber fill, dark text, glow on hover.
  primary,

  /// Neutral filled button. Surface tone with subtle border.
  secondary,

  /// Borderless. Default for icon-only or low-key actions.
  ghost,

  /// Amber outline only. Used for "통찰로 승격" — important but reversible.
  outline,

  /// Red text on transparent. Destructive only.
  danger,
}

/// Three height tiers.
enum SButtonSize { sm, md, lg }

/// Synapse-themed button. Mirrors the React `Button` component in the design
/// bundle (`components.jsx`) — same variant matrix, same hover behaviour, same
/// `kbd` hint slot, same iconography hook.
class SButton extends StatefulWidget {
  const SButton({
    super.key,
    required this.label,
    this.onPressed,
    this.variant = SButtonVariant.ghost,
    this.size = SButtonSize.md,
    this.icon,
    this.kbd,
  });

  final String label;
  final VoidCallback? onPressed;
  final SButtonVariant variant;
  final SButtonSize size;

  /// Leading icon. Pass `Icon(Icons.add, size: 14)` etc. — the button does not
  /// re-style your icon, so set `size` and `color` to taste.
  final Widget? icon;

  /// Optional trailing keyboard hint, e.g. `'⌘S'`.
  final String? kbd;

  bool get _enabled => onPressed != null;

  @override
  State<SButton> createState() => _SButtonState();
}

class _SButtonState extends State<SButton> {
  bool _hover = false;

  _SizeSpec get _sizeSpec {
    switch (widget.size) {
      case SButtonSize.sm:
        return const _SizeSpec(
          height: 26,
          paddingH: 10,
          paddingV: 4,
          fontSize: SynapseTokens.tSm,
        );
      case SButtonSize.md:
        return const _SizeSpec(
          height: 32,
          paddingH: 12,
          paddingV: 6,
          fontSize: 13,
        );
      case SButtonSize.lg:
        return const _SizeSpec(
          height: 38,
          paddingH: 16,
          paddingV: 8,
          fontSize: SynapseTokens.tBase,
        );
    }
  }

  _VariantSpec get _variantSpec {
    final hover = _hover && widget._enabled;
    switch (widget.variant) {
      case SButtonVariant.primary:
        return _VariantSpec(
          background: hover ? SynapseTokens.accent2 : SynapseTokens.accent,
          foreground: const Color(0xFF1A1408),
          border: SynapseTokens.accent,
          glow: hover,
        );
      case SButtonVariant.secondary:
        return _VariantSpec(
          background:
              hover ? SynapseTokens.surface3 : SynapseTokens.surface2,
          foreground: SynapseTokens.text,
          border: SynapseTokens.border2,
        );
      case SButtonVariant.ghost:
        return _VariantSpec(
          background:
              hover ? SynapseTokens.surface2 : Colors.transparent,
          foreground: SynapseTokens.text2,
          border: Colors.transparent,
        );
      case SButtonVariant.outline:
        return _VariantSpec(
          background:
              hover ? SynapseTokens.accentSoft : Colors.transparent,
          foreground: SynapseTokens.accent,
          border: SynapseTokens.accentLine,
        );
      case SButtonVariant.danger:
        return _VariantSpec(
          background:
              hover ? const Color(0x2EC85D5D) : Colors.transparent,
          foreground: SynapseTokens.danger,
          border: Colors.transparent,
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    final spec = _variantSpec;
    final size = _sizeSpec;
    final enabled = widget._enabled;

    return MouseRegion(
      cursor:
          enabled ? SystemMouseCursors.click : SystemMouseCursors.forbidden,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedOpacity(
        opacity: enabled ? 1 : 0.5,
        duration: SynapseTokens.durFast,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: widget.onPressed,
          child: AnimatedContainer(
            duration: SynapseTokens.durFast,
            curve: SynapseTokens.ease,
            height: size.height,
            padding: EdgeInsets.symmetric(
              horizontal: size.paddingH,
              vertical: size.paddingV,
            ),
            decoration: BoxDecoration(
              color: spec.background,
              borderRadius: BorderRadius.circular(SynapseTokens.rMd),
              border: Border.all(color: spec.border),
              boxShadow: spec.glow ? SynapseTokens.glowAmberSm : null,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (widget.icon != null) ...[
                  IconTheme.merge(
                    data: IconThemeData(
                      color: spec.foreground,
                      size: 14,
                    ),
                    child: widget.icon!,
                  ),
                  const SizedBox(width: 6),
                ],
                Text(
                  widget.label,
                  style: SynapseTokens.bodyStyle(
                    size: size.fontSize,
                    weight: FontWeight.w500,
                    color: spec.foreground,
                    height: 1,
                  ),
                ),
                if (widget.kbd != null) ...[
                  const SizedBox(width: 6),
                  _KbdHint(text: widget.kbd!, color: spec.foreground),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _KbdHint extends StatelessWidget {
  const _KbdHint({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        color: const Color(0x4D000000),
        borderRadius: BorderRadius.circular(3),
        border: Border.all(color: const Color(0x14FFFFFF)),
      ),
      child: Text(
        text,
        style: SynapseTokens.monoStyle(
          size: 10,
          color: color.withValues(alpha: 0.7),
        ),
      ),
    );
  }
}

class _SizeSpec {
  const _SizeSpec({
    required this.height,
    required this.paddingH,
    required this.paddingV,
    required this.fontSize,
  });

  final double height;
  final double paddingH;
  final double paddingV;
  final double fontSize;
}

class _VariantSpec {
  const _VariantSpec({
    required this.background,
    required this.foreground,
    required this.border,
    this.glow = false,
  });

  final Color background;
  final Color foreground;
  final Color border;
  final bool glow;
}

import 'package:flutter/material.dart';

/// Global design tokens — single source for colour, typography, and spacing.
/// Pages should never hard-code values; they pull from here so the look stays
/// consistent across `/note`, `/synapse`, and the `/hypergraph` view that
/// will arrive in F8.
class SynapseTokens {
  const SynapseTokens._();

  // ── Colour ──────────────────────────────────────────────
  static const Color background = Color(0xFFF7F7F4);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color onSurface = Color(0xFF1A1A1A);
  static const Color onSurfaceMuted = Color(0xFF6B6B6B);
  static const Color accent = Color(0xFF2D6A4F);
  static const Color insightAccent = Color(0xFFB07209);

  // ── Spacing ─────────────────────────────────────────────
  static const double spaceXs = 4;
  static const double spaceS = 8;
  static const double spaceM = 16;
  static const double spaceL = 24;
  static const double spaceXl = 32;

  // ── Typography ──────────────────────────────────────────
  static const TextStyle display = TextStyle(
    fontSize: 28,
    fontWeight: FontWeight.w600,
    color: onSurface,
    letterSpacing: -0.5,
  );
  static const TextStyle title = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    color: onSurface,
  );
  static const TextStyle body = TextStyle(
    fontSize: 15,
    height: 1.5,
    color: onSurface,
  );
  static const TextStyle caption = TextStyle(
    fontSize: 13,
    color: onSurfaceMuted,
  );

  // ── Theme bundle ────────────────────────────────────────
  static ThemeData themeData() {
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: accent,
        surface: surface,
        onSurface: onSurface,
      ),
      scaffoldBackgroundColor: background,
      textTheme: const TextTheme(
        displayLarge: display,
        titleMedium: title,
        bodyMedium: body,
        labelSmall: caption,
      ),
    );
  }
}

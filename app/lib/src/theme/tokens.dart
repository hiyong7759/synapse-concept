import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Synapse design tokens — single source for colour, typography, spacing,
/// radius, shadow, and motion. Mirrors `tokens.css` from the design bundle.
///
/// Three layers:
///  - **Surface / Text / Brand / Semantic / Hypergraph** colour scales.
///  - **Typography** built on Playfair Display (display), Noto Sans KR
///    (body), and JetBrains Mono (mono) via google_fonts.
///  - **Spacing / Radius / Shadow / Motion** primitives.
///
/// Pages and widgets must read tokens from here. Hard-coded hex values or
/// pixel sizes are a smell — extend the token set instead.
class SynapseTokens {
  const SynapseTokens._();

  // ── Surface ─────────────────────────────────────────────
  static const Color bg = Color(0xFF0A0B0E);
  static const Color bg2 = Color(0xFF0E1014);
  static const Color surface = Color(0xFF141519);
  static const Color surface2 = Color(0xFF1A1C22);
  static const Color surface3 = Color(0xFF22252D);
  static const Color border = Color(0xFF252730);
  static const Color border2 = Color(0xFF2E313B);
  static const Color borderStrong = Color(0xFF3A3D4A);

  // ── Foreground ──────────────────────────────────────────
  static const Color text = Color(0xFFE8E4D9);
  static const Color text2 = Color(0xFFB8B4A9);
  static const Color text3 = Color(0xFF7A7B82);
  static const Color text4 = Color(0xFF555761);

  // ── Brand ───────────────────────────────────────────────
  static const Color accent = Color(0xFFC8A96E);
  static const Color accent2 = Color(0xFFD9BC83);
  static const Color accentSoft = Color(0x24C8A96E); // ~0.14 alpha
  static const Color accentLine = Color(0x66C8A96E); // ~0.40 alpha

  // ── Semantic ────────────────────────────────────────────
  static const Color success = Color(0xFF5DAB8A);
  static const Color danger = Color(0xFFC85D5D);
  static const Color warning = Color(0xFFD9A55D);
  static const Color info = Color(0xFF6E9DC8);

  // ── Hypergraph ──────────────────────────────────────────
  static const Color node = Color(0xFF8A8B92);
  static const Color nodeHub = Color(0xFFC8A96E);
  static const Color nodeInsight = Color(0xFFD9BC83);
  static const Color hyperedge = Color(0xFF3A3D4A);
  static const Color hyperedgeSoft = Color(0x803A3D4A); // ~0.50 alpha

  /// Seed-19 category colors (8 groups by adjacent domain hue).
  /// Single source for `primaryCategoryCode` → color mapping. WebView
  /// receives this map through the graph payload — no inline hex in
  /// `assets/graph/index.html`.
  static const Map<String, Color> categoryColors19 = {
    // 사람·관계·사회 (빨강)
    'PER': Color(0xFFC85D5D),
    'REL': Color(0xFFD87878),
    'SOC': Color(0xFFB85D5D),
    // 신체·심리 (보라)
    'BOD': Color(0xFFB68AC8),
    'MND': Color(0xFF9870B0),
    // 음식·생활 (주황·노랑)
    'FOD': Color(0xFFD9A55D),
    'LIV': Color(0xFFD9C58D),
    // 일·돈·법 (파랑)
    'WRK': Color(0xFF6E9DC8),
    'MON': Color(0xFF5D7DB0),
    'LAW': Color(0xFF4E68A8),
    // 기술·학습 (청자·녹)
    'TEC': Color(0xFF6E8DA8),
    'EDU': Color(0xFF5DAB8A),
    // 자연·이동·여행 (청록)
    'NAT': Color(0xFF8AC8B6),
    'TRV': Color(0xFF7AB89A),
    // 문화·취미 (자홍)
    'CUL': Color(0xFFC88AB8),
    'HOB': Color(0xFFC870A0),
    // 종교·시간·행동 (보·회)
    'REG': Color(0xFF8B7DA8),
    'TIM': Color(0xFF7A7B82),
    'ACT': Color(0xFF5D5E62),
  };

  // ── Spacing ─────────────────────────────────────────────
  static const double s1 = 4;
  static const double s2 = 8;
  static const double s3 = 12;
  static const double s4 = 16;
  static const double s5 = 20;
  static const double s6 = 24;
  static const double s8 = 32;
  static const double s10 = 40;
  static const double s12 = 48;

  // ── Radius ──────────────────────────────────────────────
  static const double rSm = 4;
  static const double rMd = 6;
  static const double rLg = 10;
  static const double rXl = 14;

  // ── Type scale (px) ─────────────────────────────────────
  static const double tXs = 11;
  static const double tSm = 12;
  static const double tBase = 14;
  static const double tMd = 15;
  static const double tLg = 17;
  static const double tXl = 20;
  static const double t2xl = 24;
  static const double t3xl = 32;
  static const double tDisplay = 48;

  // ── Type families ───────────────────────────────────────
  /// Display — Playfair Display. Headers, brand, italic pull-quotes.
  static TextStyle displayStyle({
    double size = t3xl,
    FontWeight weight = FontWeight.w600,
    Color color = text,
    double letterSpacing = -0.4,
    FontStyle? fontStyle,
    double? height,
  }) =>
      GoogleFonts.playfairDisplay(
        fontSize: size,
        fontWeight: weight,
        color: color,
        letterSpacing: letterSpacing,
        fontStyle: fontStyle,
        height: height,
      );

  /// Body — Noto Sans KR. Default for all Korean / Latin running text.
  static TextStyle bodyStyle({
    double size = tBase,
    FontWeight weight = FontWeight.w400,
    Color color = text,
    double height = 1.55,
    double letterSpacing = 0,
  }) =>
      GoogleFonts.notoSansKr(
        fontSize: size,
        fontWeight: weight,
        color: color,
        height: height,
        letterSpacing: letterSpacing,
      );

  /// Mono — JetBrains Mono. Node names, category codes, key bindings,
  /// meta labels, code samples.
  static TextStyle monoStyle({
    double size = tSm,
    FontWeight weight = FontWeight.w400,
    Color color = text2,
    double letterSpacing = 0,
  }) =>
      GoogleFonts.jetBrainsMono(
        fontSize: size,
        fontWeight: weight,
        color: color,
        letterSpacing: letterSpacing,
      );

  // ── Shadow / Glow ───────────────────────────────────────
  static const List<BoxShadow> shadow1 = [
    BoxShadow(color: Color(0x66000000), blurRadius: 2, offset: Offset(0, 1)),
  ];
  static const List<BoxShadow> shadow2 = [
    BoxShadow(color: Color(0x80000000), blurRadius: 16, offset: Offset(0, 4)),
  ];
  static const List<BoxShadow> shadow3 = [
    BoxShadow(color: Color(0x99000000), blurRadius: 40, offset: Offset(0, 12)),
  ];
  // Amber glow used **only on ignition / firing moments** — never as a
  // static highlight (see DESIGN_PRINCIPLES & design-bundle ColorCard).
  static const List<BoxShadow> glowAmber = [
    BoxShadow(color: Color(0x59C8A96E), blurRadius: 24),
  ];
  static const List<BoxShadow> glowAmberSm = [
    BoxShadow(color: Color(0x80C8A96E), blurRadius: 8),
  ];

  // ── Motion ──────────────────────────────────────────────
  static const Duration durFast = Duration(milliseconds: 120);
  static const Duration durBase = Duration(milliseconds: 200);
  static const Duration durSlow = Duration(milliseconds: 400);
  static const Curve ease = Cubic(0.2, 0.8, 0.2, 1);

  // ── Theme bundle ────────────────────────────────────────
  static ThemeData themeData() {
    final colorScheme = ColorScheme(
      brightness: Brightness.dark,
      primary: accent,
      onPrimary: const Color(0xFF1A1408),
      secondary: accent2,
      onSecondary: const Color(0xFF1A1408),
      surface: surface,
      onSurface: text,
      surfaceContainerHighest: surface3,
      error: danger,
      onError: text,
      outline: border2,
      outlineVariant: border,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: bg,
      canvasColor: bg,
      dividerColor: border,
      textTheme: TextTheme(
        displayLarge: displayStyle(size: t3xl),
        displayMedium: displayStyle(size: t2xl, weight: FontWeight.w500),
        titleLarge: bodyStyle(size: tLg, weight: FontWeight.w600),
        titleMedium: bodyStyle(size: tMd, weight: FontWeight.w500),
        bodyLarge: bodyStyle(size: tMd),
        bodyMedium: bodyStyle(size: tBase),
        bodySmall: bodyStyle(size: tSm, color: text2),
        labelMedium: monoStyle(size: tSm),
        labelSmall: monoStyle(size: tXs, color: text3),
      ),
      iconTheme: const IconThemeData(color: text2, size: 16),
    );
  }
}

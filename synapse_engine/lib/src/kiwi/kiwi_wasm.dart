import 'package:flutter_kiwi_nlp/flutter_kiwi_nlp.dart' as kn;

import 'tokens.dart';

/// Pluggable Kiwi morpheme analyzer. Two implementations:
///   - [FlutterKiwiBackend]   — production (flutter_kiwi_nlp, native FFI / WASM)
///   - [InMemoryKiwiBackend]  — tests, supplies pre-tokenised fixtures.
///
/// File name preserves the §1 layout (kiwi_wasm.dart) even though the
/// production backend is FFI on native platforms — DESIGN_ENGINE §4 calls
/// the binding "Kiwi WASM" because web is the canonical reference target.
abstract class KiwiBackend {
  /// Analyses [text] and returns morphemes as Synapse [KiwiToken]s. The
  /// best Kiwi candidate is used (top-1).
  Future<List<KiwiToken>> tokenize(String text);

  /// Returns the lemmas that should become graph nodes. Filters by
  /// noun / predicate / 안·못 negation tags per DESIGN_HYPERGRAPH §노드.
  /// Lower-cased and deduplicated to match identity rules
  /// (대소문자·공백 무시).
  Future<List<String>> nouns(String text);

  /// Frees underlying resources (FFI handle, WASM instance, …).
  Future<void> dispose();
}

/// Production backend backed by `flutter_kiwi_nlp`. Construct via
/// [load] which resolves the bundled model.
class FlutterKiwiBackend implements KiwiBackend {
  FlutterKiwiBackend._(this._analyzer);

  final kn.KiwiAnalyzer _analyzer;
  bool _closed = false;

  /// Loads the Kiwi analyzer. When [modelPath] is null the package's
  /// bundled default model is used.
  static Future<FlutterKiwiBackend> load({String? modelPath}) async {
    final analyzer = await kn.KiwiAnalyzer.create(modelPath: modelPath);
    return FlutterKiwiBackend._(analyzer);
  }

  @override
  Future<List<KiwiToken>> tokenize(String text) async {
    if (_closed) throw StateError('KiwiBackend is closed');
    final result = await _analyzer.analyze(text);
    if (result.candidates.isEmpty) return const [];
    final tokens = result.candidates.first.tokens;
    return tokens
        .map((t) => KiwiToken(
              surface: t.form,
              tag: t.tag,
              // Kiwi's Cong model already returns inflected forms in lemma
              // shape inside `form` for VV/VA, so we forward as-is. If a
              // future Kiwi build exposes a separate lemma field we'll
              // start preferring it here.
              lemma: t.form,
              start: t.start,
              length: t.length,
            ))
        .toList(growable: false);
  }

  @override
  Future<List<String>> nouns(String text) async {
    final tokens = await tokenize(text);
    final seen = <String>{};
    final out = <String>[];
    for (final t in tokens) {
      if (!(t.isNoun || t.isPredicate || t.isNegationAdverb)) continue;
      final norm = t.lemma.trim();
      if (norm.isEmpty) continue;
      // Identity rule: case + whitespace insensitive (DESIGN_HYPERGRAPH
      // §노드 정체성). For Korean this is a no-op, but ASCII tokens like
      // 'FastAPI' / 'fastapi' should collapse.
      final key = norm.toLowerCase();
      if (seen.add(key)) out.add(norm);
    }
    return out;
  }

  @override
  Future<void> dispose() async {
    if (_closed) return;
    await _analyzer.close();
    _closed = true;
  }
}

/// Test backend that returns whatever was pre-supplied for a given input.
/// Tokens unspecified for an input fall back to an empty list.
class InMemoryKiwiBackend implements KiwiBackend {
  InMemoryKiwiBackend({Map<String, List<KiwiToken>>? fixtures})
      : _fixtures = fixtures ?? <String, List<KiwiToken>>{};

  final Map<String, List<KiwiToken>> _fixtures;

  void seed(String text, List<KiwiToken> tokens) {
    _fixtures[text] = tokens;
  }

  @override
  Future<List<KiwiToken>> tokenize(String text) async =>
      _fixtures[text] ?? const [];

  @override
  Future<List<String>> nouns(String text) async {
    final tokens = await tokenize(text);
    final seen = <String>{};
    final out = <String>[];
    for (final t in tokens) {
      if (!(t.isNoun || t.isPredicate || t.isNegationAdverb)) continue;
      final key = t.lemma.toLowerCase();
      if (seen.add(key)) out.add(t.lemma);
    }
    return out;
  }

  @override
  Future<void> dispose() async {}
}

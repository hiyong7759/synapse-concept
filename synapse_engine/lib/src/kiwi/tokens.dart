/// One morpheme produced by [KiwiBackend.tokenize].
///
/// Held as a separate type from `flutter_kiwi_nlp`'s own `KiwiToken` so
/// the package version can churn without touching consumer code.
///
/// `lemma` mirrors `kiwipiepy` semantics: for verbs / adjectives / 안·못
/// adverbs, this is the dictionary form; for nouns and the rest, it
/// equals `surface`. Kiwi's Cong model already returns the lemma in its
/// `form` field for inflectional categories, so the wrapper just maps
/// `form` directly.
class KiwiToken {
  const KiwiToken({
    required this.surface,
    required this.tag,
    required this.lemma,
    required this.start,
    required this.length,
  });

  /// Surface form as it appeared in the source text (best-effort —
  /// Kiwi reports the morpheme form, which is the lemma for verbs).
  final String surface;

  /// Part-of-speech tag. NNG/NNP/NR for nouns, VV/VA for verbs/adjectives,
  /// MAG for adverbs (incl. 안·못), etc.
  final String tag;

  /// Dictionary form. Equals [surface] for nouns; the inflected stem for
  /// verbs and adjectives.
  final String lemma;

  /// UTF-16 code unit offset of [surface] within the original text.
  final int start;

  /// UTF-16 code unit length of [surface].
  final int length;

  /// True if this token's tag belongs to the noun family (NNG/NNP/NR).
  bool get isNoun => tag == 'NNG' || tag == 'NNP' || tag == 'NR';

  /// True for verbs and adjectives (lemma matters here).
  bool get isPredicate => tag == 'VV' || tag == 'VA';

  /// True for the negation adverbs the spec keeps as standalone nodes.
  bool get isNegationAdverb =>
      tag == 'MAG' && (surface == '안' || surface == '못');

  @override
  String toString() => 'KiwiToken($surface/$tag${lemma != surface ? "→$lemma" : ""})';
}

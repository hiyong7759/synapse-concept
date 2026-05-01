import 'dart:convert';

import 'package:flutter/foundation.dart' show kDebugMode;

import '../internal/thinking_strip.dart';
import '../prompts/loader.dart';
import 'inference_backend.dart';

/// Atomic LLM tasks. Owned by [SynapseEngine.llm] and freely callable from
/// any consumer (synapse app, gabjil, etc.). Single source: docs/DESIGN_ENGINE.md §2.2.
///
/// Adapter policy (DESIGN_ENGINE §5):
///   - All tasks   → base model + system prompt only. No LoRA adapter is
///                   currently bundled. The retired `retrieve-expand`
///                   adapter underperformed the v3 system prompt on the
///                   45-case evaluation set (PoC: REPORT-20260426-SYN-
///                   adapter-removal-h1.md). The hot-swap infrastructure
///                   in `LlamadartInferenceBackend` is kept so reuse apps
///                   (e.g. gabjil) can ship their own domain adapters.
///   - typoNormalize → F3 stub (UnimplementedError). Lands in a follow-up
///                     milestone alongside the alias-protection /
///                     jamo-distance pre-filter design.
///
/// Note: an earlier draft included a `savePronoun` task. Dropped — the
/// note-only v22 input pattern doesn't hit pronoun-resolution territory
/// often, and the date-adverb half is faster + safer in the deterministic
/// `DateNormalizer` (lib/src/internal/date_normalize.dart). Demonstrative
/// gaps are caught by the existing `unresolved_tokens` mechanism instead.
class LlmTasks {
  LlmTasks({required this.backend, required this.prompts});

  final InferenceBackend backend;
  final PromptLoader prompts;

  String? _activeAdapter;

  // ── metaFilter ───────────────────────────────────────────

  /// Marks each input as meta-talk (true) or substantive content (false).
  /// One LLM call per input — sequential to keep adapter state simple.
  Future<List<bool>> metaFilter(List<String> texts) async {
    await _switchTo(null);
    final system = await prompts.load(PromptKey.metaFilter);
    final results = <bool>[];
    for (final text in texts) {
      final raw = stripThinking(await backend.generate(
        systemPrompt: system,
        userPrompt: text,
        maxTokens: 8,
      ));
      results.add(_yesIsh(raw));
    }
    return results;
  }

  // ── retrieveExpand ───────────────────────────────────────

  /// Expands a question into BFS seed phrases. Falls back to whitespace-split
  /// of the question on parse failure.
  ///
  /// The `retrieve-expand` LoRA adapter that earlier drafts hot-swapped here
  /// has been retired — the v3 system prompt + base Gemma 4 E2B matched or
  /// outperformed the adapter on the 45-case evaluation set (PoC report:
  /// `deliverables/SYN/20260426/user/REPORT-20260426-SYN-adapter-removal-h1.md`).
  /// All tasks now run on the base model with their system prompt only.
  Future<List<String>> retrieveExpand(String question) async {
    await _switchTo(null);
    final system = await prompts.load(PromptKey.retrieveExpand);
    final raw = stripThinking(await backend.generate(
      systemPrompt: system,
      userPrompt: '질문: $question',
      maxTokens: 256,
    ));
    final match = RegExp(r'\[.*?\]', dotAll: true).firstMatch(raw);
    if (match == null) return question.split(RegExp(r'\s+'));
    try {
      final list = jsonDecode(match.group(0)!) as List<dynamic>;
      return list.cast<String>();
    } on FormatException {
      return question.split(RegExp(r'\s+'));
    }
  }

  // ── filterKeywords ───────────────────────────────────────

  /// Filters noise out of the keyword candidate list before the lookup
  /// stage. Replaces the per-sentence retrieve-filter (2026-04-30) — keyword
  /// noise creates the wrong matches in the first place, so cleaning the
  /// inputs is cheaper and preserves real co-mentions in the output.
  ///
  /// Response format: one bare `o` or `x` per line, in input order. The
  /// parser stays permissive (still accepts legacy `[o]`/`[x]` echo).
  /// Anything that isn't a clear `x` keeps the keyword (recall over
  /// precision — matches the prompt's "애매하면 o" rule).
  Future<List<bool>> filterKeywords(
    String question,
    List<String> keywords,
  ) async {
    if (keywords.isEmpty) return const [];
    await _switchTo(null);
    final system = await prompts.load(PromptKey.keywordFilter);
    final n = keywords.length;
    final numbered = <String>[];
    for (var i = 0; i < n; i++) {
      numbered.add('${i + 1}. ${keywords[i]}');
    }
    final raw = stripThinking(await backend.generate(
      systemPrompt: system,
      userPrompt: '질문: $question\n키워드 $n개:\n${numbered.join('\n')}',
      // One bare mark + newline per keyword.
      maxTokens: 4 * n,
    ));
    if (kDebugMode) {
      // ignore: avoid_print
      print('[filterKeywords RAW n=$n]\n${raw.substring(0, raw.length.clamp(0, 200))}\n---');
    }
    return _parseFilterMarks(raw, n);
  }

  static List<bool> _parseFilterMarks(String raw, int expected) {
    final lines = raw
        .split('\n')
        .map((l) => l.trim())
        .where((l) => l.isNotEmpty)
        .toList();
    final out = List<bool>.filled(expected, true);
    for (var i = 0; i < expected && i < lines.length; i++) {
      final line = lines[i].toLowerCase();
      // Accept both bare `o`/`x` (current prompt) and legacy `[o]`/`[x]`
      // echo lines so prompt iterations don't require a parser flip.
      final mark = line.startsWith('[') ? line.substring(1) : line;
      if (mark.startsWith('x')) out[i] = false;
    }
    return out;
  }

  // ── synapseAnswer ────────────────────────────────────────

  /// Produces a short Korean answer grounded in [contexts]. Caller is
  /// responsible for pre-trimming contexts to a sensible token budget.
  ///
  /// Each context is sorted by `createdAt` (oldest → newest) and rendered
  /// with a `[YYYY-MM-DD]` date prefix when available. Time-aware framing is
  /// the core of synapse's "최근 사실 우선" reasoning pattern (DESIGN_PIPELINE
  /// §인출), so any caller — synapse app or reuse app like gabjil — gets the
  /// same standard prompt shape by just supplying createdAt.
  Future<String> synapseAnswer({
    required String question,
    required List<ContextSentence> contexts,
  }) async {
    // Bypass the LLM entirely for empty contexts — small models tend to
    // paraphrase the system prompt instead of saying "기록 없어요" when
    // they have nothing to ground on. Deterministic fallback is both
    // cheaper and more honest.
    if (contexts.isEmpty) return '기록 없어요.';

    await _switchTo(null);
    final system = await prompts.load(PromptKey.synapseAnswer);
    final sorted = [...contexts]
      ..sort((a, b) => (a.createdAt ?? '').compareTo(b.createdAt ?? ''));
    final factsBlock = sorted.map((c) {
      final hint = c.dateHint;
      return hint == null ? '- ${c.text}' : '- [$hint] ${c.text}';
    }).join('\n');
    final userPrompt = '[사실]\n$factsBlock\n\n질문: $question';
    final raw = await backend.generate(
      systemPrompt: system,
      userPrompt: userPrompt,
      maxTokens: 4096,
      temperature: 0.3,
    );
    return stripThinking(raw);
  }

  // ── categorize ───────────────────────────────────────────

  /// Classifies a node into seed-19 sub categories (`BOD.disease`,
  /// `WRK.role`, ...) given a small set of sentences it appeared in.
  /// Output mirrors `assets/prompts/CATEGORY_SYSTEMPROMPT.md`:
  /// `{"categories": ["BOD.disease", ...]}`. Empty list when the model
  /// returns no categories or fails to produce parseable JSON — caller
  /// treats this as "leave the node uncategorized" (DESIGN_HYPERGRAPH
  /// §하이퍼엣지 ② — `node_category_mentions` 자동 등록은 origin='ai'
  /// 만이며, 확신 없으면 매핑하지 않는다).
  ///
  /// `contextSentences` is trimmed to 3 entries — the system prompt's
  /// disambiguation rules ("수영(건강) → BOD.exercise / 수영(취미) →
  /// HOB.sport") need at least one or two surrounding sentences to fire,
  /// but more than 3 wastes the small token budget without changing the
  /// answer.
  Future<List<String>> categorize({
    required String nodeName,
    List<String> contextSentences = const [],
  }) async {
    await _switchTo(null);
    final system = await prompts.load(PromptKey.category);
    final ctxBlock = contextSentences.isEmpty
        ? '(맥락 없음)'
        : contextSentences.take(3).map((s) => '- $s').join('\n');
    final userPrompt = '노드: $nodeName\n맥락 문장:\n$ctxBlock';
    final raw = stripThinking(await backend.generate(
      systemPrompt: system,
      userPrompt: userPrompt,
      maxTokens: 64,
    ));
    final match = RegExp(r'\{.*?\}', dotAll: true).firstMatch(raw);
    if (match == null) return const [];
    try {
      final obj = jsonDecode(match.group(0)!) as Map<String, dynamic>;
      final list = (obj['categories'] as List<dynamic>?) ?? const [];
      return list
          .whereType<String>()
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty)
          .toList(growable: false);
    } on FormatException {
      return const [];
    }
  }

  // ── typoNormalize (F3 stub) ──────────────────────────────

  /// Suggests typo corrections for [text]. The protected alias set must be
  /// honoured to avoid corrupting user-registered names.
  ///
  /// Stubbed in F3. Implementing this needs the alias-protection list +
  /// jamo-distance pre-filter spec (DESIGN_ENGINE §2.2 / DESIGN_PIPELINE
  /// §LLM 정정 후보) which is scheduled as a separate milestone.
  Future<List<Correction>> typoNormalize(
    String text, {
    required Set<String> protectedAliases,
  }) {
    throw UnimplementedError(
      'typoNormalize is scheduled for a follow-up milestone. '
      'F3 ships only the API surface.',
    );
  }

  // ── adapter control ──────────────────────────────────────

  /// Manually swap to a registered adapter (or null = base only).
  /// Most callers should rely on the per-task automatic swap; this is for
  /// reuse apps that drive llamadart directly.
  Future<void> swapAdapter(String? name) => _switchTo(name);

  // ── helpers ──────────────────────────────────────────────

  Future<void> _switchTo(String? name) async {
    if (_activeAdapter == name) return;
    await backend.switchAdapter(name);
    _activeAdapter = name;
  }

  bool _yesIsh(String raw) {
    final t = raw.trim().toLowerCase();
    return t == 'true' || t == 'yes' || t == 'meta' || t.startsWith('y');
  }
}

/// Single sentence pulled from retrieval, fed to [LlmTasks.synapseAnswer].
///
/// `createdAt` carries the original `sentences.created_at` so the answer
/// task can sort facts by time and prefix each line with a `[YYYY-MM-DD]`
/// hint. Callers should pass the raw DB string (e.g. `2026-04-26 14:30:00`);
/// only the leading date portion is shown.
class ContextSentence {
  const ContextSentence({
    required this.text,
    this.role = 'user',
    this.createdAt,
  });
  final String text;
  final String role;
  final String? createdAt;

  /// Date-only slice of [createdAt] — the part the LLM actually sees.
  /// Returns null when [createdAt] is null or shaped unexpectedly.
  String? get dateHint {
    final ts = createdAt;
    if (ts == null || ts.isEmpty) return null;
    final cut = ts.indexOf(' ');
    final slice = cut < 0 ? ts : ts.substring(0, cut);
    return slice.length >= 10 ? slice.substring(0, 10) : slice;
  }
}

/// One typo correction suggestion. Fields will likely grow when
/// [LlmTasks.typoNormalize] is implemented; today they are minimal so the
/// API surface is fixed for callers.
class Correction {
  const Correction({
    required this.originalToken,
    required this.suggested,
  });
  final String originalToken;
  final String suggested;
}

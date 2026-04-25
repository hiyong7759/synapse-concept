import 'dart:convert';

import '../internal/thinking_strip.dart';
import '../prompts/loader.dart';
import 'inference_backend.dart';

/// Atomic LLM tasks. Owned by [SynapseEngine.llm] and freely callable from
/// any consumer (synapse app, gabjil, etc.). Single source: docs/DESIGN_ENGINE.md §2.2.
///
/// Adapter policy (DESIGN_ENGINE §5):
///   - retrieveExpand → activates the bundled `retrieve-expand` adapter.
///   - All others    → base model + system prompt only.
///   - typoNormalize → F3 stub (UnimplementedError). Lands in a follow-up
///                     milestone alongside the alias-protection / jamo-distance
///                     pre-filter design.
class LlmTasks {
  LlmTasks({required this.backend, required this.prompts});

  final InferenceBackend backend;
  final PromptLoader prompts;

  String? _activeAdapter;

  // ── savePronoun ──────────────────────────────────────────

  /// Resolves pronouns and date references in [text]. Returns either
  /// `{"text": "...", "tokens": [...]}` (success) or `{"question": "..."}`
  /// (model wants clarification). Falls back to the original text on parse
  /// failure so saving never blocks.
  Future<Map<String, Object?>> savePronoun(
    String text, {
    String? context,
    String? today,
  }) async {
    await _switchTo(null);
    final system = await prompts.load(PromptKey.savePronoun);
    final parts = <String>[];
    if (today != null && today.isNotEmpty) parts.add('날짜: $today');
    if (context != null && context.isNotEmpty) parts.add('직전 대화 - $context');
    parts.add('입력: $text');
    final raw = stripThinking(await backend.generate(
      systemPrompt: system,
      userPrompt: parts.join('\n'),
      maxTokens: 256,
    ));
    return _parseJsonObject(raw, fallback: {'text': text});
  }

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

  /// Expands a question into BFS seed phrases. Activates the
  /// `retrieve-expand` adapter for this call. Falls back to whitespace-split
  /// of the question on parse failure (matches v15 behaviour).
  Future<List<String>> retrieveExpand(String question) async {
    await _switchTo('retrieve-expand');
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

  // ── retrieveFilter ───────────────────────────────────────

  /// Decides whether [sentence] is relevant to [question]. Bias toward
  /// pass — uncertain answers stay in (recall over precision).
  Future<bool> retrieveFilter(String question, String sentence) async {
    await _switchTo(null);
    final system = await prompts.load(PromptKey.retrieveFilter);
    final raw = stripThinking(await backend.generate(
      systemPrompt: system,
      userPrompt: '질문: $question\n문장: $sentence',
      maxTokens: 8,
    ));
    return raw.trim().toLowerCase() != 'reject';
  }

  // ── synapseAnswer ────────────────────────────────────────

  /// Produces a short Korean answer grounded in [contexts]. Caller is
  /// responsible for pre-trimming contexts to a sensible token budget.
  Future<String> synapseAnswer({
    required String question,
    required List<ContextSentence> contexts,
  }) async {
    await _switchTo(null);
    final system = await prompts.load(PromptKey.synapseAnswer);
    final factsBlock = contexts.isEmpty
        ? '(관련 사실 없음)'
        : contexts.map((c) => '- ${c.text}').join('\n');
    final userPrompt = '알려진 사실:\n$factsBlock\n\n질문: $question';
    final raw = await backend.generate(
      systemPrompt: system,
      userPrompt: userPrompt,
      maxTokens: 512,
      temperature: 0.3,
    );
    return stripThinking(raw);
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

  Map<String, Object?> _parseJsonObject(
    String raw, {
    required Map<String, Object?> fallback,
  }) {
    final match = RegExp(r'\{.*\}', dotAll: true).firstMatch(raw);
    if (match == null) return fallback;
    try {
      return jsonDecode(match.group(0)!) as Map<String, Object?>;
    } on FormatException {
      return fallback;
    }
  }

  bool _yesIsh(String raw) {
    final t = raw.trim().toLowerCase();
    return t == 'true' || t == 'yes' || t == 'meta' || t.startsWith('y');
  }
}

/// Single sentence pulled from retrieval, fed to [LlmTasks.synapseAnswer].
class ContextSentence {
  const ContextSentence({required this.text, this.role = 'user'});
  final String text;
  final String role;
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

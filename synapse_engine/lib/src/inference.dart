/// Synapse inference engine — llamadart wrapper.
///
/// Replaces api/mlx_server.py + engine/llm.py HTTP layer.
/// In-process inference, no network.
///
/// NOTE: llamadart dependency is deferred until the package is available.
/// This file defines the interface and a stub implementation.
/// When llamadart is added, swap the stub for real inference.

import 'dart:convert';

import 'models/engine_config.dart';

/// LLM inference error.
class LlmError implements Exception {
  final String message;
  const LlmError(this.message);
  @override
  String toString() => 'LlmError: $message';
}

// ── Task system prompts (from engine/llm.py _MLX_SYSTEM) ──

const _systemPrompts = <String, String>{
  'retrieve-filter':
      '당신은 지식 그래프 인출 필터입니다. 질문과 문장을 보고, 이 문장이 질문과 관련 있는지 판단하세요. '
      '불확실하면 pass로 판단하세요 (제외보다 포함이 안전). 출력: pass 또는 reject (한 단어만)',
  'retrieve-expand':
      '당신은 지식 그래프 검색 엔진입니다. 질문을 보고 그래프에서 검색해야 할 관련 노드 후보를 생성하세요. '
      '형태소 단위로 쪼개진 노드 이름으로 나열하세요. 출력 형식: ["노드1", "노드2", ...]',
  'save-pronoun':
      '당신은 지식 그래프 저장 엔진입니다. 텍스트에서 대명사와 부사를 구체적인 값으로 치환하세요. '
      '대화 맥락이 제공되면 활용하세요. 치환 불가능하면 {"question": "질문 내용"}을 반환하세요. '
      '출력 형식: {"text": "치환된 텍스트"} 또는 {"question": "..."}',
  'extract':
      '한국어 문장에서 지식 그래프의 노드, 엣지, 카테고리, 상태변경, 보관 유형을 추출하라.\n'
      'JSON만 출력. 다른 텍스트 금지.\n\n'
      '출력 형식:\n'
      '{"retention":"memory|daily","nodes":[{"name":"노드명","category":"대분류.소분류"}],'
      '"edges":[{"source":"노드명","label":"조사","target":"노드명"}],'
      '"deactivate":[{"source":"노드명","target":"노드명"}]}\n\n'
      '규칙:\n'
      '- 노드는 원자. 하나의 개념 = 하나의 노드.\n'
      '- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출. 문장에 없는 1인칭 추가 금지.\n'
      '- 3인칭 주어는 원문 그대로 노드 추출.\n'
      '- 엣지 label = 원문의 조사 그대로 (에서, 으로, 의, 에, 를/을, 와/과, 고, 이/가 등). 조사 없으면 null.\n'
      '- 부정부사(안, 못)는 독립 노드다. 예: "스타벅스 안 좋아" → 스타벅스→안→좋아 (3노드, 2엣지 null).\n'
      '- 엣지의 source와 target은 반드시 nodes 배열에 있는 노드명과 정확히 일치해야 한다.\n'
      '- "알려진 사실:"이 제공된 경우: 현재 입력과 상충되는 기존 문장을 파악해 deactivate에 포함. 없으면 [].\n'
      '- retention: 잘 변하지 않는 사실/상태/이력 → "memory". 순간적 활동/감정/일상 → "daily".\n'
      '- 추출할 노드/엣지가 없는 대화 → {"retention":"daily","nodes":[],"edges":[],"deactivate":[]}\n\n'
      '카테고리 대분류(17개): PER BOD MND FOD LIV MON WRK TEC EDU LAW TRV NAT CUL HOB SOC REL REG',
};

const systemChat =
    '당신은 사용자의 개인 비서입니다.\n'
    '아래는 사용자에 대해 알려진 사실 문장들입니다.\n'
    '이 사실들을 근거로 질문에 자연스럽고 간결하게 한국어로 답변하세요.\n\n'
    '주의사항:\n'
    '- 문장에 없는 내용은 "모르겠어요" 또는 "기록이 없어요"라고 답변\n'
    '- 추측하거나 일반적인 정보를 보충하지 말 것\n'
    '- 짧고 명확하게 답변 (2-3문장 이내)\n'
    '- 반말/존댓말은 문장 문맥에 맞게 판단';

// ── Thinking block stripping ─────────────────────────────

final _thinkingPatterns = [
  RegExp(r'<\|channel>thought.*?<channel\|>', dotAll: true),
  RegExp(r'<\|channel>thought.*', dotAll: true),
  RegExp(r'<think>.*?</think>', dotAll: true),
  RegExp(r'<think>.*', dotAll: true),
];

String stripThinking(String text) {
  var result = text;
  for (final pattern in _thinkingPatterns) {
    result = result.replaceAll(pattern, '');
  }
  return result.trim();
}

// ── Inference engine interface ───────────────────────────

/// Abstract inference backend.
/// Swap implementation: StubInference (testing) vs LlamadartInference (production).
abstract class InferenceBackend {
  Future<void> loadModel(String modelPath, String adapterDir);
  Future<void> switchAdapter(String? taskName);
  Future<String> generate(
    String systemPrompt,
    String userPrompt, {
    int maxTokens = 512,
    double temperature = 0.0,
  });
  Future<void> dispose();
}

/// Inference engine wrapping a backend with task-aware system prompts.
class InferenceEngine {
  final InferenceBackend _backend;
  final Map<String, String> _systemOverrides;
  final Map<String, int> _maxTokensOverrides;
  final Map<String, AdapterSpec> _customAdapters = {};

  InferenceEngine(
    this._backend, {
    Map<String, String>? systemOverrides,
    Map<String, int>? maxTokensOverrides,
  })  : _systemOverrides = systemOverrides ?? {},
        _maxTokensOverrides = maxTokensOverrides ?? {};

  Future<void> init(String modelPath, String adapterDir) =>
      _backend.loadModel(modelPath, adapterDir);

  void registerAdapter(AdapterSpec spec) {
    _customAdapters[spec.name] = spec;
  }

  /// Run inference with a task-specific adapter and system prompt.
  Future<String> run(String task, String userPrompt) async {
    // Check custom adapter first
    final custom = _customAdapters[task];
    if (custom != null) {
      await _backend.switchAdapter(task);
      final raw = await _backend.generate(
        custom.systemPrompt ?? '',
        userPrompt,
        maxTokens: custom.maxTokens,
        temperature: custom.temperature,
      );
      return stripThinking(raw);
    }

    // Built-in task
    final system = _systemOverrides[task] ?? _systemPrompts[task] ?? '';
    final maxTokens = _maxTokensOverrides[task] ?? _defaultMaxTokens(task);
    await _backend.switchAdapter(task);
    final raw = await _backend.generate(
      system,
      userPrompt,
      maxTokens: maxTokens,
    );
    return stripThinking(raw);
  }

  /// Chat with base model (no adapter).
  Future<String> chat(
    String systemPrompt,
    String userPrompt, {
    double temperature = 0.3,
    int maxTokens = 4096,
  }) async {
    await _backend.switchAdapter(null);
    final raw = await _backend.generate(
      systemPrompt,
      userPrompt,
      maxTokens: maxTokens,
      temperature: temperature,
    );
    return stripThinking(raw);
  }

  Future<void> dispose() => _backend.dispose();

  int _defaultMaxTokens(String task) {
    switch (task) {
      case 'retrieve-filter':
        return 8;
      case 'retrieve-expand':
        return 256;
      case 'save-pronoun':
        return 128;
      case 'extract':
        return 32768;
      default:
        return 256;
    }
  }
}

// ── Pipeline helper functions (port of engine/llm.py) ────

/// Expand a question into search keywords.
Future<List<String>> retrieveExpand(
    InferenceEngine engine, String question) async {
  try {
    final raw = await engine.run('retrieve-expand', '질문: $question');
    final match = RegExp(r'\[.*?\]', dotAll: true).firstMatch(raw);
    if (match == null) return question.split(' ');
    final list = jsonDecode(match.group(0)!) as List;
    return list.cast<String>();
  } catch (_) {
    return question.split(' ');
  }
}

/// Filter a single sentence for relevance.
Future<bool> retrieveFilterSentence(
    InferenceEngine engine, String question, String sentence) async {
  try {
    final result =
        await engine.run('retrieve-filter', '질문: $question\n문장: $sentence');
    return result.trim().toLowerCase() != 'reject';
  } catch (_) {
    return true;
  }
}

/// Resolve pronouns/dates in text.
Future<Map<String, dynamic>> savePronoun(
  InferenceEngine engine,
  String text, {
  String context = '',
  String today = '',
}) async {
  try {
    final parts = <String>[];
    if (today.isNotEmpty) parts.add('날짜: $today');
    if (context.isNotEmpty) parts.add('직전 대화 - $context');
    parts.add('입력: $text');
    final raw = await engine.run('save-pronoun', parts.join('\n'));
    final match = RegExp(r'\{.*\}', dotAll: true).firstMatch(raw);
    if (match == null) return {'text': text};
    return jsonDecode(match.group(0)!) as Map<String, dynamic>;
  } catch (_) {
    return {'text': text};
  }
}

/// Extract nodes/edges/category/deactivate from text.
Future<Map<String, dynamic>> llmExtract(
  InferenceEngine engine,
  String text, {
  List<String>? contextSentences,
}) async {
  const defaults = {
    'retention': 'memory',
    'nodes': <dynamic>[],
    'edges': <dynamic>[],
    'deactivate': <dynamic>[],
  };
  try {
    // Replace ()[] to prevent 2B model loop
    var cleaned = text.replaceAll(RegExp(r'[()\[\]]'), ' ');
    String inputText;
    if (contextSentences != null && contextSentences.isNotEmpty) {
      final ctx = contextSentences.map((s) => '- $s').join('\n');
      inputText = '$cleaned\n알려진 사실:\n$ctx';
    } else {
      inputText = cleaned;
    }
    final raw = await engine.run('extract', inputText);
    final match = RegExp(r'\{.*\}', dotAll: true).firstMatch(raw);
    if (match == null) return Map.from(defaults);
    final result = jsonDecode(match.group(0)!) as Map<String, dynamic>;
    for (final key in defaults.keys) {
      result.putIfAbsent(key, () => defaults[key]);
    }
    return result;
  } catch (_) {
    return Map.from(defaults);
  }
}

// ── Stub backend for testing without LLM ─────────────────

/// Stub backend that returns empty responses. For unit testing.
class StubInferenceBackend implements InferenceBackend {
  @override
  Future<void> loadModel(String modelPath, String adapterDir) async {}

  @override
  Future<void> switchAdapter(String? taskName) async {}

  @override
  Future<String> generate(
    String systemPrompt,
    String userPrompt, {
    int maxTokens = 512,
    double temperature = 0.0,
  }) async =>
      '';

  @override
  Future<void> dispose() async {}
}

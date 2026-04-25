import 'package:llamadart/llamadart.dart';

import 'inference_backend.dart';

/// llamadart-backed [InferenceBackend]. Loads a GGUF base model and
/// hot-swaps LoRA adapters without re-loading the base.
///
/// Adapted from archive/synapse_engine_v15/lib/src/llamadart_backend.dart
/// but uses an explicit name→path map (see registerAdapter) instead of the
/// v15 `adapterDir + ${name}.gguf` convention. EngineConfig.adapters drives
/// this map at engine creation time (see SynapseEngine.create).
class LlamadartInferenceBackend implements InferenceBackend {
  LlamadartInferenceBackend({this.contextSize = 4096, this.gpuLayers = 99});

  final int contextSize;

  /// Layer count to offload to GPU. -1 / 99 = "all that fit".
  final int gpuLayers;

  LlamaEngine? _engine;
  final Map<String, String> _adapters = {};
  String? _currentAdapter;

  @override
  Future<void> loadModel(String modelPath) async {
    final backend = LlamaBackend();
    final engine = LlamaEngine(backend);
    await engine.loadModel(
      modelPath,
      modelParams: ModelParams(
        contextSize: contextSize,
        gpuLayers: gpuLayers,
      ),
    );
    _engine = engine;
  }

  @override
  Future<void> registerAdapter(String name, String path) async {
    _adapters[name] = path;
  }

  @override
  Future<void> switchAdapter(String? name) async {
    final engine = _engine;
    if (engine == null) throw const LlmError('engine not loaded');
    if (name == _currentAdapter) return;

    await engine.clearLoras();
    if (name != null) {
      final path = _adapters[name];
      if (path == null) {
        throw LlmError('adapter not registered: $name');
      }
      await engine.setLora(path, scale: 1.0);
    }
    _currentAdapter = name;
  }

  @override
  Future<String> generate({
    required String systemPrompt,
    required String userPrompt,
    int maxTokens = 256,
    double temperature = 0.0,
  }) async {
    final engine = _engine;
    if (engine == null) throw const LlmError('engine not loaded');

    final session = ChatSession(engine);
    if (systemPrompt.isNotEmpty) {
      session.systemPrompt = systemPrompt;
    }

    final buffer = StringBuffer();
    await for (final chunk in session.create(
      [LlamaTextContent(userPrompt)],
      params: GenerationParams(
        maxTokens: maxTokens,
        temp: temperature,
        topK: temperature == 0.0 ? 1 : 40,
        topP: temperature == 0.0 ? 1.0 : 0.9,
      ),
      enableThinking: false,
    )) {
      for (final choice in chunk.choices) {
        final content = choice.delta.content;
        if (content != null) buffer.write(content);
      }
    }
    return buffer.toString();
  }

  @override
  Future<void> dispose() async {
    await _engine?.dispose();
    _engine = null;
    _currentAdapter = null;
    _adapters.clear();
  }
}

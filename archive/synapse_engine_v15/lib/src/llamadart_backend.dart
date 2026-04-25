/// LlamadartInferenceBackend — real inference using llamadart (llama.cpp).
///
/// Loads a GGUF base model, supports LoRA adapter hot-swapping.
/// For desktop testing, use with LlamaBackend() from llamadart.

import 'package:llamadart/llamadart.dart';

import 'inference.dart';

/// Real inference backend using llamadart.
class LlamadartInferenceBackend implements InferenceBackend {
  LlamaEngine? _engine;
  String? _adapterDir;
  String? _currentAdapter;

  @override
  Future<void> loadModel(String modelPath, String adapterDir) async {
    _adapterDir = adapterDir;
    final backend = LlamaBackend();
    _engine = LlamaEngine(backend);
    await _engine!.loadModel(
      modelPath,
      modelParams: const ModelParams(
        contextSize: 4096,
        gpuLayers: 99, // offload all layers to GPU
      ),
    );
  }

  @override
  Future<void> switchAdapter(String? taskName) async {
    if (_engine == null) throw LlmError('Engine not loaded');

    if (taskName == _currentAdapter) return;

    // Clear previous adapter
    await _engine!.clearLoras();

    // Load new adapter if specified
    if (taskName != null && _adapterDir != null) {
      final adapterPath = '$_adapterDir/$taskName.gguf';
      try {
        await _engine!.setLora(adapterPath, scale: 1.0);
      } catch (e) {
        // Adapter file not found — run with base model
      }
    }

    _currentAdapter = taskName;
  }

  @override
  Future<String> generate(
    String systemPrompt,
    String userPrompt, {
    int maxTokens = 512,
    double temperature = 0.0,
  }) async {
    if (_engine == null) throw LlmError('Engine not loaded');

    // Use ChatSession for proper chat template handling
    final session = ChatSession(_engine!);
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
      // Extract text content from completion chunk
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
  }
}

/// Pluggable LLM inference backend.
///
/// Two implementations land in F3:
///   - [LlamadartInferenceBackend] — production (llama.cpp via llamadart)
///   - [StubInferenceBackend]      — unit tests (returns empty strings)
///
/// Adapter handling is intentionally string-keyed so [LlmTasks] can swap by
/// name without leaking the backend's notion of paths or scaling.
abstract class InferenceBackend {
  /// Loads the base model and prepares the backend for inference.
  Future<void> loadModel(String modelPath);

  /// Registers a LoRA adapter under [name] backed by a GGUF file at [path].
  /// Multiple adapters can be registered; only one is active at a time.
  Future<void> registerAdapter(String name, String path);

  /// Activates the adapter previously registered as [name], or detaches all
  /// adapters when [name] is null. Calling with the currently-active name is
  /// a no-op.
  Future<void> switchAdapter(String? name);

  /// Generates a single completion. Returns the raw model output — callers
  /// are responsible for stripping thinking blocks via [stripThinking] when
  /// appropriate.
  Future<String> generate({
    required String systemPrompt,
    required String userPrompt,
    int maxTokens = 256,
    double temperature = 0.0,
  });

  Future<void> dispose();
}

class LlmError implements Exception {
  const LlmError(this.message);
  final String message;
  @override
  String toString() => 'LlmError: $message';
}

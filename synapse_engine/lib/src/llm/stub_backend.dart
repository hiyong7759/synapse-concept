import 'inference_backend.dart';

/// No-op backend for unit tests. Records the last call so tests can assert
/// the [LlmTasks] layer assembled the right system+user prompt and selected
/// the expected adapter, without actually loading a model.
class StubInferenceBackend implements InferenceBackend {
  StubInferenceBackend({Map<String, String>? canned})
      : canned = canned ?? <String, String>{};

  /// Optional pre-canned responses keyed by (currentAdapter, userPrompt).
  /// When a key matches the next [generate] call, the stored value is
  /// returned. Otherwise an empty string is returned.
  final Map<String, String> canned;

  String? activeAdapter;
  final List<String> registeredAdapters = [];
  String? lastSystemPrompt;
  String? lastUserPrompt;
  int generateCalls = 0;

  bool _modelLoaded = false;

  @override
  Future<void> loadModel(String modelPath) async {
    _modelLoaded = true;
  }

  @override
  Future<void> registerAdapter(String name, String path) async {
    registeredAdapters.add(name);
  }

  @override
  Future<void> switchAdapter(String? name) async {
    activeAdapter = name;
  }

  @override
  Future<String> generate({
    required String systemPrompt,
    required String userPrompt,
    int maxTokens = 256,
    double temperature = 0.0,
  }) async {
    if (!_modelLoaded) throw const LlmError('model not loaded');
    lastSystemPrompt = systemPrompt;
    lastUserPrompt = userPrompt;
    generateCalls++;
    final key = '${activeAdapter ?? ""}::$userPrompt';
    return canned[key] ?? '';
  }

  @override
  Future<void> dispose() async {
    _modelLoaded = false;
  }
}

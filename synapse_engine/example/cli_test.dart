/// Desktop CLI test — verify base model loading + inference.
///
/// Usage:
///   cd synapse_engine
///   dart run example/cli_test.dart /path/to/gemma-4-e2b.gguf
///
/// This test:
///   1. Loads a GGUF base model via llamadart
///   2. Runs a simple inference (no adapter)
///   3. Measures time
///   4. Tests adapter swap if adapter dir is provided

import 'dart:io';

import 'package:llamadart/llamadart.dart';

import '../lib/src/inference.dart';
import '../lib/src/llamadart_backend.dart';

Future<void> main(List<String> args) async {
  if (args.isEmpty) {
    print('Usage: dart run example/cli_test.dart <model.gguf> [adapter_dir]');
    print('');
    print('Example:');
    print('  dart run example/cli_test.dart ~/models/gemma-4-e2b-Q4_K_M.gguf');
    print('  dart run example/cli_test.dart ~/models/gemma-4-e2b-Q4_K_M.gguf ~/adapters/');
    exit(1);
  }

  final modelPath = args[0];
  final adapterDir = args.length > 1 ? args[1] : '';

  if (!File(modelPath).existsSync()) {
    print('ERROR: Model file not found: $modelPath');
    exit(1);
  }

  print('=== Synapse Engine CLI Test ===');
  print('Model: $modelPath');
  print('Adapter dir: ${adapterDir.isEmpty ? "(none)" : adapterDir}');
  print('');

  // 1. Load model
  print('[1/4] Loading model...');
  final sw = Stopwatch()..start();

  final backend = LlamadartInferenceBackend();
  final engine = InferenceEngine(backend);
  await engine.init(modelPath, adapterDir);

  print('  Loaded in ${sw.elapsedMilliseconds}ms');

  // 2. Simple inference (base model, no adapter)
  print('');
  print('[2/4] Base model inference test...');
  sw.reset();

  final testPrompt = '한국의 수도는?';
  final answer = await engine.chat(
    '짧게 답변하세요.',
    testPrompt,
    temperature: 0.0,
    maxTokens: 64,
  );

  print('  Prompt: $testPrompt');
  print('  Answer: $answer');
  print('  Time: ${sw.elapsedMilliseconds}ms');

  // 3. Extract task test (with system prompt, no adapter)
  print('');
  print('[3/4] Extract task test (base model, no adapter)...');
  sw.reset();

  final extractResult = await engine.run(
    'extract',
    '나 쿠팡에서 물류 기획 담당하고 있어\n알려진 사실: 없음',
  );

  print('  Input: 나 쿠팡에서 물류 기획 담당하고 있어');
  print('  Output: $extractResult');
  print('  Time: ${sw.elapsedMilliseconds}ms');

  // 4. Adapter swap test (if adapter dir provided)
  if (adapterDir.isNotEmpty) {
    print('');
    print('[4/4] Adapter swap test...');

    // Try loading extract adapter
    final extractAdapterPath = '$adapterDir/extract.gguf';
    if (File(extractAdapterPath).existsSync()) {
      sw.reset();
      await backend.switchAdapter('extract');
      print('  Adapter swap time: ${sw.elapsedMilliseconds}ms');

      sw.reset();
      final adapterResult = await engine.run(
        'extract',
        '나 쿠팡에서 물류 기획 담당하고 있어\n알려진 사실: 없음',
      );
      print('  Output with adapter: $adapterResult');
      print('  Time: ${sw.elapsedMilliseconds}ms');
    } else {
      print('  SKIP: $extractAdapterPath not found');
    }
  } else {
    print('');
    print('[4/4] SKIP: No adapter dir provided');
  }

  // Cleanup
  print('');
  print('Disposing...');
  await engine.dispose();
  print('Done.');
}

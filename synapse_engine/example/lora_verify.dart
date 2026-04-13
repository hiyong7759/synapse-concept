/// Verify LoRA adapter is actually being applied.
///
/// Runs the same prompt with and without adapter,
/// comparing outputs character by character.

import 'dart:io';

import 'package:llamadart/llamadart.dart';

import '../lib/src/inference.dart' show stripThinking;

Future<void> main(List<String> args) async {
  final modelPath = '/Volumes/macex/models/gemma-4-E2B-it-Q4_K_M.gguf';
  final adapterPath = '/Volumes/macex/workspace/claude-agentic-subagent-team/projects/synapse/archive/finetune/models/gguf/extract.gguf';

  if (!File(adapterPath).existsSync()) {
    print('Adapter not found: $adapterPath');
    exit(1);
  }
  print('Adapter file size: ${File(adapterPath).lengthSync()} bytes');

  final backend = LlamaBackend();
  final engine = LlamaEngine(backend);

  print('Loading model...');
  await engine.loadModel(
    modelPath,
    modelParams: const ModelParams(contextSize: 4096, gpuLayers: 99),
  );
  print('Model loaded.');

  const testInput = '나 쿠팡에서 물류 기획 담당하고 있어\n알려진 사실: 없음';
  const systemPrompt = '한국어 문장에서 지식 그래프의 노드, 엣지, 카테고리, 상태변경, 보관 유형을 추출하라.\n'
      'JSON만 출력. 다른 텍스트 금지.\n\n'
      '출력 형식:\n'
      '{"retention":"memory|daily","nodes":[{"name":"노드명","category":"대분류.소분류"}],'
      '"edges":[{"source":"노드명","label":"조사","target":"노드명"}],'
      '"deactivate":[{"source":"노드명","target":"노드명"}]}\n\n'
      '규칙:\n'
      '- 노드는 원자. 하나의 개념 = 하나의 노드.\n'
      '- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출.\n'
      '- 엣지 label = 원문의 조사 그대로. 조사 없으면 null.\n'
      '카테고리 대분류(17개): PER BOD MND FOD LIV MON WRK TEC EDU LAW TRV NAT CUL HOB SOC REL REG';

  // ── Run 1: WITHOUT adapter ──
  print('\n=== WITHOUT adapter ===');
  var session = ChatSession(engine);
  session.systemPrompt = systemPrompt;
  var sw = Stopwatch()..start();
  var buf = StringBuffer();
  await for (final chunk in session.create(
    [LlamaTextContent(testInput)],
    params: const GenerationParams(maxTokens: 4096, temp: 0.0, topK: 1),
    enableThinking: false,
  )) {
    for (final choice in chunk.choices) {
      if (choice.delta.content != null) buf.write(choice.delta.content);
    }
  }
  print('Time: ${sw.elapsedMilliseconds}ms');
  final outputWithout = stripThinking(buf.toString());
  print('Output: $outputWithout');

  // ── Apply LoRA ──
  print('\n=== Applying LoRA: $adapterPath ===');
  sw.reset();
  try {
    await engine.setLora(adapterPath, scale: 1.0);
    print('setLora completed in ${sw.elapsedMilliseconds}ms');
  } catch (e) {
    print('setLora FAILED: $e');
    await engine.dispose();
    exit(1);
  }

  // ── Run 2: WITH adapter ──
  print('\n=== WITH adapter ===');
  session = ChatSession(engine);  // new session to clear history
  session.systemPrompt = systemPrompt;
  sw.reset();
  buf = StringBuffer();
  await for (final chunk in session.create(
    [LlamaTextContent(testInput)],
    params: const GenerationParams(maxTokens: 4096, temp: 0.0, topK: 1),
    enableThinking: false,
  )) {
    for (final choice in chunk.choices) {
      if (choice.delta.content != null) buf.write(choice.delta.content);
    }
  }
  print('Time: ${sw.elapsedMilliseconds}ms');
  final outputWith = stripThinking(buf.toString());
  print('Output: $outputWith');

  // ── Compare ──
  print('\n=== Comparison ===');
  if (outputWithout == outputWith) {
    print('⚠️  IDENTICAL — adapter may NOT be applied');
  } else {
    print('✅ DIFFERENT — adapter IS applied');
    // Show diff
    print('Without: ${outputWithout.substring(0, outputWithout.length.clamp(0, 200))}');
    print('With:    ${outputWith.substring(0, outputWith.length.clamp(0, 200))}');
  }

  await engine.dispose();
}

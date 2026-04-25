import 'package:flutter_test/flutter_test.dart';
// ignore: unused_import
import 'package:synapse_engine/synapse_engine.dart';

void main() {
  test('package entry point imports without error', () {
    // The import above is the actual smoke check: if `synapse_engine.dart`
    // fails to parse or resolve, this test file won't compile.
    expect(true, isTrue);
  });
}

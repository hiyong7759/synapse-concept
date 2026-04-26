import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/main.dart';
import 'package:synapse_app/src/state/note_state.dart';
import 'package:synapse_engine/synapse_engine.dart';

void main() {
  testWidgets('shows boot screen while the engine future is pending',
      (tester) async {
    final pending = Completer<SynapseEngine>();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          engineProvider.overrideWith((ref) => pending.future),
        ],
        child: const SynapseApp(),
      ),
    );
    await tester.pump(); // first frame after the FutureProvider subscribes

    expect(find.text('엔진 준비 중...'), findsOneWidget);

    // Tearing down: complete the future so the test can finish cleanly.
    pending.completeError(StateError('test teardown — ignore'));
    await tester.pumpAndSettle();
  });
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/main.dart';

void main() {
  testWidgets('boots into /note placeholder', (tester) async {
    await tester.pumpWidget(const SynapseApp());
    await tester.pumpAndSettle();

    expect(find.text('/note'), findsOneWidget);
    expect(
      find.textContaining('F7 에서 구현'),
      findsOneWidget,
    );
  });

  testWidgets('routes to /synapse via the AppBar action', (tester) async {
    await tester.pumpWidget(const SynapseApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Synapse →'));
    await tester.pumpAndSettle();

    expect(find.text('/synapse'), findsOneWidget);
    expect(
      find.textContaining('F9 에서 구현'),
      findsOneWidget,
    );
  });
}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/main.dart';
import 'package:synapse_app/src/state/note_state.dart';
import 'package:synapse_app/src/widgets/note_editor.dart';
import 'package:synapse_app/src/widgets/post_sidebar.dart';
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
    await tester.pump();
    expect(find.text('엔진 준비 중...'), findsOneWidget);
    pending.completeError(StateError('test teardown — ignore'));
    await tester.pumpAndSettle();
  });

  testWidgets('NoteEditor pulls source through noteSourceProvider',
      (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          selectedPostIdProvider.overrideWith((ref) => 42),
          noteSourceProvider.overrideWith((ref) async => 'hello body'),
        ],
        child: const MaterialApp(home: Scaffold(body: NoteEditor())),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('hello body'), findsOneWidget);
  });

  testWidgets('PostSidebar shows the empty-state hint with no posts',
      (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          postListProvider.overrideWith((ref) async => const <PostMeta>[]),
        ],
        child: const MaterialApp(home: Scaffold(body: PostSidebar())),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('아직 노트가 없습니다'), findsOneWidget);
  });
}

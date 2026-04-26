import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'src/pages/note_page.dart';
import 'src/pages/synapse_page.dart';
import 'src/theme/tokens.dart';

void main() {
  runApp(const ProviderScope(child: SynapseApp()));
}

/// Top-level app — wires the global theme to the go_router config and
/// nothing else. Page contents live under `lib/src/pages/`; the router
/// declaration here is the one place that knows about all routes.
class SynapseApp extends StatelessWidget {
  const SynapseApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Synapse',
      theme: SynapseTokens.themeData(),
      routerConfig: _router,
      debugShowCheckedModeBanner: false,
    );
  }
}

final GoRouter _router = GoRouter(
  initialLocation: '/note',
  routes: [
    GoRoute(
      path: '/note',
      builder: (context, state) => const NotePage(),
    ),
    GoRoute(
      path: '/synapse',
      builder: (context, state) => const SynapsePage(),
    ),
  ],
);

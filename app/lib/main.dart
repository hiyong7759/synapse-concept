import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'src/pages/hypergraph_page.dart';
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

/// All three routes live inside a [StatefulShellRoute.indexedStack] so that
/// switching tabs keeps each branch's widget tree alive. Without this the
/// `/hypergraph` WebView would be disposed every time the user visits
/// `/note`, forcing a full vis-network stabilization (1500 iterations) on
/// every return — visible as a 1~2 second freeze. With the shell, the
/// WebView, its DataSet, and the hypergraph FutureProvider all stay
/// resident, so re-entering the route is instant.
final GoRouter _router = GoRouter(
  initialLocation: '/note',
  routes: [
    StatefulShellRoute.indexedStack(
      builder: (context, state, navigationShell) => navigationShell,
      branches: [
        StatefulShellBranch(routes: [
          GoRoute(path: '/note', builder: (_, __) => const NotePage()),
        ]),
        StatefulShellBranch(routes: [
          GoRoute(path: '/synapse', builder: (_, __) => const SynapsePage()),
        ]),
        StatefulShellBranch(routes: [
          GoRoute(
            path: '/hypergraph',
            builder: (_, __) => const HypergraphPage(),
          ),
        ]),
      ],
    ),
  ],
);

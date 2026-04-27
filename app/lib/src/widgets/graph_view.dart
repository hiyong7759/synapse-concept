import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:synapse_engine/synapse_engine.dart';

import '../theme/tokens.dart';

/// WebView host running `assets/graph/index.html` (vis-network).
///
/// Single shared graph widget for `/hypergraph` (F8), `/note` graph panel
/// (F7d), and `/synapse` graph panel (F9). Callers differ only in the
/// [GraphData] they pass — F7d filters by `postId`, F9 by retrieve-cache
/// `nodeIds`, F8 passes the full snapshot.
///
/// This milestone (F8'-2) only pushes data into JS — click / search /
/// filter live in F8'-3 and F8'-4.
class VisNetworkGraphView extends StatefulWidget {
  const VisNetworkGraphView({super.key, required this.data});
  final GraphData? data;

  @override
  State<VisNetworkGraphView> createState() => _VisNetworkGraphViewState();
}

class _VisNetworkGraphViewState extends State<VisNetworkGraphView> {
  InAppWebViewController? _controller;
  bool _ready = false;

  Future<void> _maybePush() async {
    final controller = _controller;
    if (!_ready || controller == null) return;
    final json = jsonEncode(_serialize(widget.data));
    final escaped = jsonEncode(json);
    await controller.evaluateJavascript(
      source: 'window.synapseSetGraph($escaped)',
    );
  }

  Map<String, Object?> _serialize(GraphData? data) {
    if (data == null) {
      return const {'nodes': [], 'sentences': [], 'mentions': []};
    }
    return {
      'nodes': [
        for (final n in data.nodes)
          {
            'id': n.id,
            'name': n.name,
            'degree': n.degree,
            'isInsight': n.isInsight,
            'primaryCategoryCode': n.primaryCategoryCode,
          },
      ],
      'sentences': [
        for (final s in data.sentences)
          {'id': s.id, 'postId': s.postId, 'origin': s.origin},
      ],
      'mentions': [
        for (final m in data.mentions)
          {'nodeId': m.nodeId, 'sentenceId': m.sentenceId},
      ],
    };
  }

  @override
  void didUpdateWidget(covariant VisNetworkGraphView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.data != widget.data) {
      _maybePush();
    }
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: SynapseTokens.bg,
      child: InAppWebView(
        initialFile: 'assets/graph/index.html',
        initialSettings: InAppWebViewSettings(
          transparentBackground: true,
          // macOS / iOS WKWebView — let JS make outbound requests to the
          // vis-network CDN. Default settings already allow https.
          allowsInlineMediaPlayback: false,
          // No need for over-zoom on a force-layout canvas.
          supportZoom: false,
        ),
        onWebViewCreated: (controller) {
          _controller = controller;
          controller.addJavaScriptHandler(
            handlerName: 'synapseReady',
            callback: (args) {
              _ready = true;
              _maybePush();
              return null;
            },
          );
        },
      ),
    );
  }
}

/// Test-only fallback — used by widget tests so the WebView channel doesn't
/// have to spin up. Renders a static caption with the node / sentence
/// counts so callers can still verify a [GraphData] reached the panel.
@visibleForTesting
class StaticGraphView extends StatelessWidget {
  const StaticGraphView({super.key, required this.data});
  final GraphData? data;

  @override
  Widget build(BuildContext context) {
    final d = data;
    final caption = d == null || d.isEmpty
        ? '노드 없음'
        : '노드 ${d.nodes.length} · 바구니 ${d.sentences.length}';
    return Container(
      color: SynapseTokens.bg,
      alignment: Alignment.center,
      child: Text(
        caption,
        style: SynapseTokens.monoStyle(
          size: SynapseTokens.tSm,
          color: SynapseTokens.text3,
        ),
      ),
    );
  }
}

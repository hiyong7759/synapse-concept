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
      return {
        'nodes': const [],
        'sentences': const [],
        'mentions': const [],
        'categories': const [],
        'sentenceCategories': const [],
        'theme': _theme(),
      };
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
      // Categories + sentence_categories so the JS layer can walk a
      // sentence to its user-heading root and pick a color distinct from
      // seed-19 node colors.
      'categories': [
        for (final c in data.categories)
          {
            'id': c.id,
            'name': c.name,
            'parentId': c.parentId,
            'code': c.code,
          },
      ],
      'sentenceCategories': [
        for (final sc in data.sentenceCategories)
          {'sentenceId': sc.sentenceId, 'categoryId': sc.categoryId},
      ],
      'theme': _theme(),
    };
  }

  /// Tokens crossing the WebView boundary. `tokens.dart` is the single
  /// source — `assets/graph/index.html` reads colors from this payload
  /// (DESIGN_SYSTEM.md §75, §78 — no inline hex in the WebView).
  Map<String, Object?> _theme() => {
    'categoryColors': {
      for (final e in SynapseTokens.categoryColors19.entries)
        e.key: _hex(e.value),
    },
  };

  static String _hex(Color c) =>
      '#${c.value.toRadixString(16).padLeft(8, '0').substring(2).toUpperCase()}';

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
          // Let the host page's own dark background show through. Setting
          // transparentBackground=true caused a fully black canvas on macOS
          // (WKWebView didn't repaint with the HTML's background).
          transparentBackground: false,
          allowsInlineMediaPlayback: false,
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

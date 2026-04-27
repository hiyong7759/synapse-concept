/// Shared base widgets — every page composes screens out of these.
///
/// Domain widgets (post sidebar, note editor, correction list, etc.) live
/// next to this file in `widgets/`. Components here have no Synapse-specific
/// state — just visual primitives expressed in design tokens.
library;

export 'components/s_badge.dart';
export 'components/s_brand_mark.dart';
export 'components/s_button.dart';
export 'components/s_node_glyph.dart';
export 'components/s_text_input.dart';

import 'package:flutter/widgets.dart';

/// Single breakpoint between mobile and desktop layouts. Synapse is
/// mobile-first (DESIGN_APP §우선순위), so anything narrower than [_desktopMin]
/// renders as the phone layout — even on a thin macOS window.
const double _desktopMin = 800;

enum SynapseFormFactor { mobile, desktop }

/// Pulls the form-factor decision into one place. UI code calls this and
/// branches once at the top of the widget tree, instead of checking
/// `MediaQuery.size.width` inline at every level.
SynapseFormFactor formFactorOf(BuildContext context) {
  final width = MediaQuery.sizeOf(context).width;
  return width >= _desktopMin
      ? SynapseFormFactor.desktop
      : SynapseFormFactor.mobile;
}

/// Convenience widget that picks one of two builders based on the form
/// factor. Keeps page widgets small and avoids ternary clutter.
class ResponsiveLayout extends StatelessWidget {
  const ResponsiveLayout({
    super.key,
    required this.mobile,
    required this.desktop,
  });

  final WidgetBuilder mobile;
  final WidgetBuilder desktop;

  @override
  Widget build(BuildContext context) {
    return formFactorOf(context) == SynapseFormFactor.mobile
        ? mobile(context)
        : desktop(context);
  }
}

import 'dart:js_interop';

@JS('uibInsets')
external JSString? _insets();

String insets() {
  try {
    return _insets()?.toDart ?? '';
  } catch (_) {
    return '';
  }
}

@JS('uibPaint')
external void _paint(JSString color);

void paint(String color) {
  try {
    _paint(color.toJS);
  } catch (_) {}
}

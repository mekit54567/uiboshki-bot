// PWA на iPhone листалась рывками (Никита 17.10): фон с подсветками в
// браузере — одна готовая картинка, а не три заливки на весь экран за кадр.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';
import 'package:uiboshki/widgets/common.dart';

Widget _app() => AppStyle(
      p: Palette.notebook,
      font: FontChoice.book,
      look: const Look(),
      design2: true,
      child: const MaterialApp(home: Backdrop(child: Text('пары'))),
    );

void main() {
  tearDown(() => Backdrop.cheap = false);

  testWidgets('в браузере фон — готовая картинка, подсветки не рисуются каждый кадр', (t) async {
    Backdrop.cheap = true;
    await t.pumpWidget(_app());
    // пока картинка готовится — цвет темы, без подсветок
    expect(find.byType(RawImage), findsNothing);
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
    await t.pump();
    expect(find.byType(RawImage), findsOneWidget);
    expect(find.text('пары'), findsOneWidget);
    bool glow(Widget w) => w is DecoratedBox && (w.decoration as BoxDecoration).gradient != null;
    expect(find.byWidgetPredicate(glow), findsNothing);
  });

  testWidgets('в приложении — подсветки как были', (t) async {
    await t.pumpWidget(_app());
    bool glow(Widget w) => w is DecoratedBox && w.decoration is BoxDecoration && (w.decoration as BoxDecoration).gradient is RadialGradient;
    expect(find.byWidgetPredicate(glow), findsNWidgets(2));
    expect(find.byType(RawImage), findsNothing);
  });
}

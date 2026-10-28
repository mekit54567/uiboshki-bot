// Согласие перед первым вопросом к ИИ на iPhone (App Store 5.1.2(i)): пока
// человек не согласился, вопрос никуда не уходит; согласился — уходит и
// больше не спрашиваем. На Android лист не показываем.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/ai_consent.dart';
import 'package:uiboshki/screens/chat.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.notebook,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

Future<void> ask(WidgetTester t, String q) async {
  await t.enterText(find.byType(TextField), q);
  await t.tap(find.byTooltip('Отправить'));
  await settle(t);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('iPhone: без согласия вопрос не уходит, с согласием — уходит, второй раз не спрашиваем', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    await t.pumpWidget(host(ChatScreen(api: fakeApi(bodies: bodies))));
    await settle(t);

    await ask(t, 'Что такое энтропия?');
    expect(find.text('Вопрос уйдёт сервису ИИ'), findsOneWidget);
    expect(find.textContaining('OpenRouter, Inc. и Google LLC'), findsOneWidget);
    await t.tap(find.text('Не сейчас'));
    await settle(t);
    expect(bodies.containsKey('POST /api/chat'), isFalse);

    await ask(t, 'Что такое энтропия?');
    await t.tap(find.text('Согласен'));
    await settle(t);
    expect(bodies.containsKey('POST /api/chat'), isTrue);
    expect((await SharedPreferences.getInstance()).getBool(aiConsentKey), isTrue);

    bodies.clear();
    await ask(t, 'А информация?');
    expect(find.text('Вопрос уйдёт сервису ИИ'), findsNothing);
    expect(bodies.containsKey('POST /api/chat'), isTrue);
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('Android: листа нет, вопрос уходит сразу', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    await t.pumpWidget(host(ChatScreen(api: fakeApi(bodies: bodies))));
    await settle(t);
    await ask(t, 'Что такое энтропия?');
    expect(find.text('Вопрос уйдёт сервису ИИ'), findsNothing);
    expect(bodies.containsKey('POST /api/chat'), isTrue);
  });
}

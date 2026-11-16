// Староста без своего входа ходит общей кукой из настроек бота (16.11):
// она протухла — экран «Вход в СДО» говорил «работает» и не давал подключить
// свой вход. Теперь статус честный, а свой вход можно подключить всегда.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/sdo_connect.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

void main() {
  testWidgets('общий вход протух — честно «устарел» и кнопка своего входа', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true});
    phone(t);
    final api = fakeApi(
      overrides: const {
        'GET /api/sdo/status': {'state': 'expired', 'checked_at': null, 'shared': true},
      },
    );
    await t.pumpWidget(host(SdoConnectScreen(api: api, webLogin: true)));
    await settle(t);
    expect(find.text('Вход старосты устарел'), findsOneWidget);
    expect(find.text('Подключено, работает'), findsNothing);
    expect(find.text('Свой вход'), findsOneWidget);
    expect(find.text('Войти в СДО'), findsOneWidget);
    expect(find.text('Убрать вход'), findsNothing); // общий вход отсюда не убрать
  });

  testWidgets('общий вход жив — «работает», и всё равно можно подключить свой', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true});
    phone(t);
    final api = fakeApi(
      overrides: const {
        'GET /api/sdo/status': {'state': 'ok', 'checked_at': null, 'shared': true},
      },
    );
    await t.pumpWidget(host(SdoConnectScreen(api: api, webLogin: true)));
    await settle(t);
    expect(find.text('Подключено, работает'), findsOneWidget);
    expect(find.text('Вход старосты из настроек бота'), findsOneWidget);
    await t.scrollUntilVisible(find.text('Войти в СДО'), 200);
    expect(find.text('Свой вход'), findsOneWidget);
    expect(find.text('Отключить СДО'), findsNothing);
  });

  testWidgets('свой вход работает — подключать заново не предлагаем', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true});
    phone(t);
    final api = fakeApi(
      overrides: const {
        'GET /api/sdo/status': {'state': 'ok', 'checked_at': null},
      },
    );
    await t.pumpWidget(host(SdoConnectScreen(api: api, webLogin: true)));
    await settle(t);
    expect(find.text('Подключено, работает'), findsOneWidget);
    expect(find.text('Войти в СДО'), findsNothing);
    expect(find.text('Отключить СДО'), findsOneWidget);
  });
}

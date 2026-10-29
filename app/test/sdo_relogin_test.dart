// Тихое обновление входа в СДО (5.102.0): вход устарел, а единый вход МИРЭА
// в окне приложения ещё помнит человека — новая сессия уходит на сервер без
// экрана. Только после входа страницей на этом телефоне и не чаще раза в 30 мин.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/sdo_connect.dart';
import 'package:uiboshki/screens/sdo_login.dart';
import 'package:uiboshki/screens/sdo_relogin.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

void main() {
  var opened = 0;
  String? next;
  setUp(() {
    opened = 0;
    next = 'sess-2';
    SdoRelogin.available = true;
    SdoRelogin.silent = (_) async {
      opened++;
      return next;
    };
  });
  tearDown(() {
    SdoRelogin.available = null;
    SdoRelogin.silent = null;
  });

  const expired = {
    'GET /api/sdo/status': {'state': 'expired', 'checked_at': null},
    'POST /api/sdo/connect': {'state': 'ok', 'checked_at': null},
  };

  testWidgets('вход устарел — обновляется сам, без пароля и без экрана', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true, sdoPageLoginKey: true});
    phone(t);
    final bodies = <String, Object?>{};
    final api = fakeApi(bodies: bodies, overrides: expired);
    await t.pumpWidget(host(SdoConnectScreen(api: api, webLogin: true)));
    await t.pump();
    await t.pump();
    expect(opened, 1);
    expect(bodies['POST /api/sdo/connect'], {'cookie': 'sess-2', 'via': 'silent'});
    await settle(t);
    expect(find.text('Вход в СДО обновлён'), findsOneWidget);
    await t.pump(const Duration(seconds: 5));
  });

  testWidgets('МИРЭА не помнит — обычная кнопка «Войти в СДО», и не чаще раза в 30 мин', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true, sdoPageLoginKey: true});
    phone(t);
    next = null;
    final bodies = <String, Object?>{};
    final api = fakeApi(bodies: bodies, overrides: expired);
    await t.pumpWidget(host(SdoConnectScreen(api: api, webLogin: true)));
    await settle(t);
    expect(opened, 1);
    expect(bodies, isEmpty);
    expect(find.text('Вход устарел'), findsOneWidget);
    expect(find.text('Войти в СДО'), findsOneWidget);

    await t.pumpWidget(const SizedBox());
    await t.pumpWidget(host(SdoConnectScreen(api: api, webLogin: true)));
    await settle(t);
    expect(opened, 1); // только что пробовали — второй раз не ждём 20 секунд
  });

  testWidgets('вставил куку вручную — молча не обновляем', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true});
    phone(t);
    await t.pumpWidget(host(SdoConnectScreen(api: fakeApi(overrides: expired), webLogin: true)));
    await settle(t);
    expect(opened, 0);
    expect(find.text('Вход устарел'), findsOneWidget);
  });

  testWidgets('оболочка спрашивает статус только у вошедших страницей', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true});
    final requests = <String>[];
    final api = fakeApi(requests: requests, overrides: expired);
    late BuildContext ctx;
    await t.pumpWidget(
      host(
        Builder(
          builder: (c) {
            ctx = c;
            return const SizedBox();
          },
        ),
      ),
    );
    expect(await SdoRelogin.refreshIfExpired(ctx, api), isFalse);
    expect(requests, isEmpty);

    await SdoRelogin.rememberPageLogin();
    expect(await SdoRelogin.refreshIfExpired(ctx, api), isTrue);
    expect(requests, ['GET /api/sdo/status', 'POST /api/sdo/connect']);

    await SdoRelogin.forget(); // отключил СДО или вышел из аккаунта
    expect((await SharedPreferences.getInstance()).getBool(sdoPageLoginKey), isNull);
  });

  test('ответ пробы страницы: Android в кавычках, iPhone как есть', () {
    expect(probeResult('"password"'), 'password');
    expect(probeResult('https://sso.mirea.ru/x'), 'https://sso.mirea.ru/x');
    expect(probeResult(null), '');
  });
}

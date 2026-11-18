// Пульс МИРЭА для всех (18.11): экран объясняет, что даёт Пульс, вход — только
// с галочкой согласия (152-ФЗ, как у СДО); подключён — сканер и «Отключить».
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/pulse.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

void main() {
  test('подпись в «Ещё» и ответы сервера словами', () {
    expect(pulseRowSub(null).text, 'посещения лекций и отметка по QR');
    expect(pulseRowSub({'state': 'ok'}).text, startsWith('подключён'));
    expect(pulseRowSub({'state': 'expired'}).warn, isTrue);
    expect(pulseConnectProblem({'state': 'ok'}), isNull);
    expect(pulseConnectProblem({'state': 'blocked'}), contains('QR работает'));
    expect(pulseConnectProblem({'state': 'empty'}), isNotNull);
  });

  test('Пульс открыт по /me → pulse (и прежнему lab), но только в приложении', () {
    // тесты идут не на телефоне — окна входа нет, значит и Пульса нет
    expect(pulseOpen({'pulse': true}), pulseAvailable);
    expect(pulseOpen({'pulse': false}), isFalse);
  });

  testWidgets('не подключён: что даст, кнопка входа — только с галочкой', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true});
    phone(t);
    final api = fakeApi(
      overrides: const {
        'GET /api/pulse/status': {'state': 'off'},
        'GET /api/consent': {'pd': true, 'sdo': false, 'pulse': false},
      },
    );
    await t.pumpWidget(host(PulseScreen(api: api)));
    await settle(t);
    expect(find.text('Не подключён'), findsOneWidget);
    expect(find.text('Что даст вход'), findsOneWidget);
    await t.scrollUntilVisible(find.byKey(const Key('pulse:login')), 200);
    final btn = find.descendant(of: find.byKey(const Key('pulse:login')), matching: find.byType(FilledButton));
    expect(t.widget<FilledButton>(btn).onPressed, isNull);
  });

  testWidgets('согласие уже есть — галочки нет, войти можно сразу', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true});
    phone(t);
    final api = fakeApi(
      overrides: const {
        'GET /api/pulse/status': {'state': 'expired'},
        'GET /api/consent': {'pd': true, 'sdo': true, 'pulse': true},
      },
    );
    await t.pumpWidget(host(PulseScreen(api: api)));
    await settle(t);
    expect(find.text('Вход устарел'), findsOneWidget);
    await t.scrollUntilVisible(find.text('Войти заново'), 200);
    final btn = find.descendant(of: find.byKey(const Key('pulse:login')), matching: find.byType(FilledButton));
    expect(t.widget<FilledButton>(btn).onPressed, isNotNull);
  });

  testWidgets('подключён: сканер и «Отключить Пульс», входа нет', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true});
    phone(t);
    final api = fakeApi(
      overrides: const {
        'GET /api/pulse/status': {'state': 'ok', 'checked_at': null},
      },
    );
    await t.pumpWidget(host(PulseScreen(api: api)));
    await settle(t);
    expect(find.text('Подключён, работает'), findsOneWidget);
    expect(find.byKey(const Key('pulse:scan')), findsOneWidget);
    expect(find.byKey(const Key('pulse:login')), findsNothing);
    await t.scrollUntilVisible(find.text('Отключить Пульс'), 200);
  });
}

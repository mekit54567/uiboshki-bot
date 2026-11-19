// Кружок QR на «Сегодня» (сканер Пульса): над меню справа, крупный, и
// последняя карточка списка, докрученного до конца, уходит выше него, а не
// садится под кружок (тред «Пульс для всех», 18.11).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/screens/pulse.dart';
import 'package:uiboshki/screens/pulse_scan.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';
import 'package:uiboshki/theme/tokens.dart';
import 'package:uiboshki/widgets/capsule_tabbar.dart';

import 'fake_api.dart';
import 'util.dart';

Map<String, Object> _answers({required bool pulse}) => {
  'GET /api/meta': {
    'api': 1,
    'server': '5.118.0',
    'min_client': {'web': '0.0.0', 'android': '0.0.0', 'ios': '0.0.0'},
    'login': ['telegram'],
    'features': {'groups': true, 'sessions': true, 'offline': true, 'design2': true, 'design3': 'new'},
    'links': {'bot': 'https://t.me/UiboshkiBot'},
  },
  'GET /api/me': {
    'id': 222,
    'first_name': 'Аня',
    'group': {'id': 4928, 'name': 'УИБО-03-24', 'own': true},
    'plan': 'own',
    'lab': pulse,
  },
};

Future<void> _open(
  WidgetTester t, {
  required bool pulse,
  required bool fresh,
  double bottomInset = 0,
  bool loggedHere = false,
}) async {
  phone(t);
  if (bottomInset > 0) {
    t.view.padding = FakeViewPadding(bottom: bottomInset * 3);
    t.view.viewPadding = FakeViewPadding(bottom: bottomInset * 3);
  }
  SharedPreferences.setMockInitialValues({
    'uib_toured': true,
    'uib_look_fresh': fresh,
    'uib_fresh_moved': true,
    // в Пульс уже входили с этого телефона (#392): кружок сразу открывает сканер
    if (loggedHere) pulseLoginKey: 1763500000,
  });
  await t.pumpWidget(
    UiboApp(
      key: UniqueKey(),
      api: fakeApi(overrides: _answers(pulse: pulse)),
      design2: true,
      theme: ThemeChoice.light,
      look: Look.classic.copyWith(fresh: fresh),
    ),
  );
  await settle(t);
}

/// Где кончается содержимое списка «Сегодня», докрученного до конца.
double _listEnd(WidgetTester t) {
  final list = find.byType(ListView).first;
  final pad = (t.widget<ListView>(list).padding! as EdgeInsets).bottom;
  return t.getRect(list).bottom - pad;
}

void main() {
  // кружок есть только там, где есть вход в Пульс, — в приложении на телефоне
  final ios = TargetPlatformVariant.only(TargetPlatform.iOS);

  for (final fresh in [true, false]) {
    for (final inset in [0.0, 34.0]) {
      testWidgets('кружок QR не накрывает конец списка (${fresh ? 'новый' : 'прежний'} вид, низ $inset)', (t) async {
        await _open(t, pulse: true, fresh: fresh, bottomInset: inset);
        final qr = find.byKey(const Key('today:qr'));
        expect(qr, findsOneWidget);
        final r = t.getRect(qr);
        // крупный: больше 44 pt для пальца
        expect(r.width - 2 * CapsuleAction.ring, greaterThanOrEqualTo(CapsuleAction.size));
        // правый край кружка — по краю капсулы меню
        expect(r.right - CapsuleAction.ring, moreOrLessEquals(t.view.physicalSize.width / 3 - Space.l));
        // докрученный до конца список кончается выше кружка
        expect(_listEnd(t), lessThanOrEqualTo(r.top));
      }, variant: ios);
    }
  }

  testWidgets('без Пульса нет кружка и лишнего места под списком', (t) async {
    await _open(t, pulse: false, fresh: true);
    expect(find.byKey(const Key('today:qr')), findsNothing);
    final list = find.byType(ListView).first;
    expect((t.widget<ListView>(list).padding! as EdgeInsets).bottom, 120);
  }, variant: ios);

  testWidgets('нажал на кружок — открылся сканер', (t) async {
    await _open(t, pulse: true, fresh: true, loggedHere: true);
    await t.tap(find.byKey(const Key('today:qr')));
    await t.pump();
    await t.pump(const Duration(milliseconds: 400));
    expect(find.byType(PulseScanScreen), findsOneWidget);
  }, variant: ios);

  testWidgets('нажал на кружок, а в Пульс с этого телефона не входили — сначала экран Пульса', (t) async {
    await _open(t, pulse: true, fresh: true);
    await t.tap(find.byKey(const Key('today:qr')));
    await t.pump();
    await t.pump(const Duration(milliseconds: 400));
    expect(find.byType(PulseScreen), findsOneWidget);
    expect(find.byType(PulseScanScreen), findsNothing);
  }, variant: ios);
}

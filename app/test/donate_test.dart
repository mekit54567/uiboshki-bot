// «Поддержать проект» (Никита 18.10): строка в «Ещё» (не плитка) и в экране
// «Капибара+», лист с пояснением «не подписка» и кнопкой на сайт; на iPhone —
// нет (сервер hidden, сборка не спрашивает). Данные выдуманные.
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/plus/donate.dart';
import 'package:uiboshki/plus/plus.dart';
import 'package:uiboshki/plus/plus_screen.dart';
import 'package:uiboshki/plus/roadmap.dart';
import 'package:uiboshki/screens/more.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

const _donate = {
  'hidden': false,
  'url': 'https://www.uiboshki.ru/donate?k=demo',
  'amounts': [100, 300, 500],
  'min': 50,
  'max': 15000,
  'note': 'Это не подписка — просто спасибо. В ответ откроется роадмап: что я делаю сейчас и что дальше.',
};

Widget _more(Api api) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(
    home: Scaffold(
      body: MoreScreen(api: api, onFont: (_) {}, onLogout: () {}),
    ),
  ),
);

Future<void> _down(WidgetTester t) async {
  await t.drag(find.byType(MoreScreen), const Offset(0, -2000));
  await settle(t);
}

void main() {
  final opened = <Uri>[];
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    PlusBonus.reset();
    opened.clear();
    PlusLinks.open = (u) async {
      opened.add(u);
      return true;
    };
  });

  testWidgets('«Ещё»: строка «Поддержать проект», лист — «не подписка» и кнопка на сайт', (t) async {
    phone(t);
    await t.pumpWidget(_more(fakeApi(overrides: {'GET /api/donate': _donate})));
    await settle(t);
    await _down(t);
    expect(find.byKey(const Key('more:donate')), findsOneWidget);
    expect(find.text('разово, сумма на выбор'), findsOneWidget);
    expect(find.text(donateNote), findsNothing); // «не подписка» — только на листе (Никита 18.10)
    await t.tap(find.byKey(const Key('more:donate')));
    await settle(t);
    expect(find.byType(DonateSheet), findsOneWidget);
    expect(find.text(donateNote), findsOneWidget);
    expect(find.textContaining('100 ₽ · 300 ₽ · 500 ₽ или своя, от 50 ₽'), findsOneWidget);
    expect(find.byKey(const Key('donate:soon')), findsNothing);
    await t.tap(find.byKey(const Key('donate:go')));
    await settle(t);
    expect(opened.single.toString(), 'https://www.uiboshki.ru/donate?k=demo');
    expect(find.byType(DonateSheet), findsNothing); // лист закрылся
  });

  testWidgets('касса не подключена — «совсем скоро», кнопки на сайт нет', (t) async {
    phone(t);
    await t.pumpWidget(
      _more(
        fakeApi(
          overrides: {
            'GET /api/donate': {..._donate, 'url': ''},
          },
        ),
      ),
    );
    await settle(t);
    await _down(t);
    await t.tap(find.byKey(const Key('more:donate')));
    await settle(t);
    expect(find.byKey(const Key('donate:soon')), findsOneWidget);
    expect(find.byKey(const Key('donate:go')), findsNothing);
  });

  testWidgets('hidden:true или старый сервер — строки нет', (t) async {
    phone(t);
    await t.pumpWidget(
      _more(
        fakeApi(
          overrides: {
            'GET /api/donate': {'hidden': true},
          },
        ),
      ),
    );
    await settle(t);
    await _down(t);
    expect(find.text('Позвать'), findsOneWidget);
    expect(find.byKey(const Key('more:donate')), findsNothing);

    await t.pumpWidget(_more(fakeApi()));
    await settle(t);
    await _down(t);
    expect(find.byKey(const Key('more:donate')), findsNothing);
  });

  testWidgets('«Роадмап» под донатом: до доната — замок и «Поддержать» ведёт на лист доната', (t) async {
    phone(t);
    await t.pumpWidget(
      _more(
        fakeApi(
          overrides: {
            'GET /api/donate': _donate,
            'GET /api/roadmap': {'hidden': false, 'locked': true, 'donate_url': 'https://x', 'min': 50},
          },
        ),
      ),
    );
    await settle(t);
    await _down(t);
    await t.tap(find.byKey(const Key('more:roadmap')));
    await settle(t);
    expect(find.byKey(const Key('roadmap:locked')), findsOneWidget);
    await t.tap(find.byKey(const Key('roadmap:donate')));
    await settle(t);
    expect(find.byType(RoadmapSheet), findsNothing);
    expect(find.byType(DonateSheet), findsOneWidget); // ведёт на тот же лист доната
  });

  testWidgets('«Роадмап» у поддержавшего: пункты по статусам, пустых разделов нет', (t) async {
    phone(t);
    const statuses = {'now': 'Делаю сейчас', 'next': 'Следующее', 'idea': 'Попробую', 'done': 'Недавно вышло'};
    await t.pumpWidget(
      _more(
        fakeApi(
          overrides: {
            'GET /api/donate': _donate,
            'GET /api/roadmap': {
              'hidden': false,
              'locked': false,
              'updated': '2026-10-19',
              'statuses': statuses,
              'items': [
                {'status': 'now', 'title': 'Комментарии под парой', 'about': 'обсудить пару'},
                {'status': 'done', 'title': 'Открытый канал', 'about': 'новости'},
              ],
            },
          },
        ),
      ),
    );
    await settle(t);
    await _down(t);
    await t.tap(find.byKey(const Key('more:roadmap')));
    await settle(t);
    expect(find.byKey(const Key('roadmap:locked')), findsNothing);
    expect(find.text('ДЕЛАЮ СЕЙЧАС'), findsOneWidget);
    expect(find.text('НЕДАВНО ВЫШЛО'), findsOneWidget);
    expect(find.text('СЛЕДУЮЩЕЕ'), findsNothing); // пустых разделов нет
    expect(find.text('Комментарии под парой'), findsOneWidget);
  });

  test('iPhone: ни строки, ни запроса', () async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    final asked = <String>[];
    expect(await donateShown(fakeApi(requests: asked, overrides: {'GET /api/donate': _donate})), isFalse);
    expect(asked, isEmpty);
  });

  testWidgets('экран «Капибара+»: «Поддержать проект» открывает тот же лист', (t) async {
    phone(t);
    final api = fakeApi(
      overrides: {
        'GET /api/plus': {
          'hidden': false,
          'active': false,
          'prices': [],
          'pay_url': '',
          'invite': {'came': 0, 'rewarded': 0, 'bonus_days': 7, 'friend_days': 3},
        },
        'GET /api/donate': _donate,
      },
    );
    await t.pumpWidget(
      AppStyle(
        p: Palette.depth,
        font: FontChoice.book,
        child: MaterialApp(home: PlusScreen(api: api)),
      ),
    );
    await settle(t);
    final list = find.descendant(of: find.byType(PlusScreen), matching: find.byType(Scrollable)).first;
    await t.scrollUntilVisible(find.byKey(const Key('plus:donate')), 200, scrollable: list);
    await settle(t);
    expect(find.text('Сказать спасибо рублём'), findsOneWidget);
    expect(find.text(donateNote), findsNothing);
    await t.tap(find.byKey(const Key('plus:donate')));
    await settle(t);
    expect(find.byType(DonateSheet), findsOneWidget);
    await t.tap(find.byKey(const Key('donate:go')));
    await settle(t);
    expect(opened.single.toString(), 'https://www.uiboshki.ru/donate?k=demo');
  });
}

// Карта корпусов (5.100.4): плитка «Карта» в «Ещё» — только когда сервер её
// включил; поиск аудитории, «отсюда → сюда», маршрут с переходом по этажам,
// нажатие на план, подпись источника. Данные — тестовый корпус
// (tests/data/map/test.json, тот же, что у сервера в тестах).
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/links.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/screens/map_screen.dart';

import 'fake_api.dart';
import 'util.dart';

final _campus = jsonDecode(File('../tests/data/map/test.json').readAsStringSync()) as Map<String, dynamic>;

Map<String, Object?> _meta(bool map) => {
  'api': 1,
  'server': '5.100.4',
  'min_client': {'web': '0.0.0', 'android': '0.0.0', 'ios': '0.0.0'},
  'login': ['telegram'],
  'features': {'groups': true, 'sessions': true, 'offline': true, 'design2': false, 'map': map},
  'links': {'bot': 'https://t.me/UiboshkiBot'},
};

String _q(Map<String, String> q) => Uri(queryParameters: q).query;

final _route = {
  'from': {'id': 'Т-101', 'name': 'Т-101', 'floor': 1},
  'to': {'id': 'Т-305', 'name': 'Т-305', 'floor': 3},
  'meters': 41,
  'minutes': 1,
  'legs': [
    {
      'floor': 1,
      'points': [
        [195, 210],
        [195, 250],
        [195, 290],
      ],
    },
    {
      'floor': 3,
      'points': [
        [195, 290],
        [195, 250],
        [855, 250],
        [855, 210],
      ],
    },
  ],
  'steps': [
    {'kind': 'stairs', 'from': 1, 'to': 3},
  ],
};

Map<String, Object?> _overrides({bool map = true}) => {
  'GET /api/meta': _meta(map),
  'GET /api/map': {
    'campuses': [
      {
        'id': 'test',
        'name': 'Тестовый корпус',
        'short': 'Т',
        'address': 'тестовые данные',
        'source': 'тестовые данные',
        'floors': [1, 2, 3],
      },
    ],
  },
  'GET /api/map/test': _campus,
  'GET /api/map/find?${_q({'q': 'т101'})}': {
    'rooms': [
      {'campus': 'test', 'short': 'Т', 'floor': 1, 'id': 'Т-101', 'name': 'Т-101', 'kind': 'room'},
    ],
  },
  'GET /api/map/find?${_q({'q': 'т305'})}': {
    'rooms': [
      {'campus': 'test', 'short': 'Т', 'floor': 3, 'id': 'Т-305', 'name': 'Т-305', 'kind': 'room'},
    ],
  },
  'GET /api/map/route?${_q({'campus': 'test', 'src': 'Т-101', 'dst': 'Т-305'})}': _route,
};

Future<void> _openMap(WidgetTester t, List<String> asked) async {
  await t.pumpWidget(
    UiboApp(
      api: fakeApi(requests: asked, overrides: _overrides()),
    ),
  );
  await settle(t);
  await t.tap(find.bySemanticsLabel('Ещё'));
  await settle(t);
  await t.scrollUntilVisible(find.byKey(const Key('more:map')), 300, scrollable: find.byType(Scrollable).first);
  await settle(t);
  await t.tap(find.byKey(const Key('more:map')));
  await settle(t);
  expect(find.byType(MapScreen), findsOneWidget);
}

Future<void> _pick(WidgetTester t, String q, String room, String how) async {
  await t.enterText(find.byKey(const Key('map:search')), q);
  await settle(t);
  await t.tap(find.byKey(Key('map:hit:$room')));
  await settle(t);
  expect(find.byKey(const Key('map:room')), findsOneWidget);
  await t.tap(find.text(how));
  await settle(t);
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({'uib_toured': true});
    forgetLinks();
  });

  testWidgets('карта выключена на сервере — плитки нет', (t) async {
    phone(t);
    await t.pumpWidget(UiboApp(api: fakeApi(overrides: _overrides(map: false))));
    await settle(t);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    expect(find.byKey(const Key('more:group'), skipOffstage: false), findsOneWidget);
    expect(find.byKey(const Key('more:map'), skipOffstage: false), findsNothing);
  });

  testWidgets('поиск → «Отсюда» и «Сюда» → маршрут через этажи, сброс', (t) async {
    phone(t);
    final asked = <String>[];
    await _openMap(t, asked);
    expect(find.text('Карта: тестовые данные'), findsOneWidget);
    for (final n in [1, 2, 3]) {
      expect(find.byKey(Key('map:floor:$n')), findsOneWidget);
    }
    expect(find.text('Нажми на аудиторию, чтобы построить маршрут'), findsOneWidget);
    // низкий корпус: рамка по высоте этажа, без пустоты сверху и снизу (5.100.12)
    final frame = t.getSize(find.byKey(const Key('map:plan')));
    expect(frame.height, lessThan(frame.width));
    final below =
        t.getTopLeft(find.byKey(const Key('map:source'))).dy - t.getBottomLeft(find.byKey(const Key('map:plan'))).dy;
    expect(below, lessThan(200)); // подсказка маршрута и подпись — сразу под планом

    await _pick(t, 'т101', 'Т-101', 'Отсюда');
    expect(find.text('Выбери, куда идёшь'), findsOneWidget);
    // приблизили пальцами — маршрут показывает этаж целиком и по центру (5.100.10)
    final view = t.widget<InteractiveViewer>(find.byType(InteractiveViewer)).transformationController!;
    view.value = Matrix4.diagonal3Values(2.5, 2.5, 1)..setTranslationRaw(-300, -40, 0);
    await _pick(t, 'т305', 'Т-305', 'Сюда');
    expect(view.value, Matrix4.identity());
    expect(asked.where((k) => k.startsWith('GET /api/map/route')), hasLength(1));
    expect(find.text('Т-101  →  Т-305'), findsOneWidget);
    expect(find.text('41 м · ~1 мин · по лестнице на 3 этаж'), findsOneWidget);

    await t.tap(find.byKey(const Key('map:route:clear')));
    await settle(t);
    expect(find.byKey(const Key('map:route')), findsNothing);
  });

  testWidgets('нажатие на план открывает аудиторию; этажи переключаются', (t) async {
    phone(t);
    await _openMap(t, []);
    await t.tap(find.byKey(const Key('map:floor:2')));
    await settle(t);
    // центр Т-203 на плане (x 450…600, y 60…210) → точка на экране, как в _Fit
    final box = t.getRect(find.byKey(const Key('map:plan')));
    const plan = Size(1200, 500);
    final k = [(box.width - 24) / plan.width, (box.height - 24) / plan.height].reduce((a, b) => a < b ? a : b);
    final shift = Offset((box.width - plan.width * k) / 2, (box.height - plan.height * k) / 2);
    await t.tapAt(box.topLeft + shift + const Offset(525, 135) * k);
    await settle(t);
    expect(find.byKey(const Key('map:room')), findsOneWidget);
    expect(find.text('Т-203'), findsWidgets);
    expect(find.text('2 этаж'), findsWidgets);
  });
}

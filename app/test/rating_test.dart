import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/screens/rating.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'util.dart';

Widget _wrap(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

Map<String, dynamic> _rating({bool show = false, int? place = 2, String nick = 'Анна И.'}) => {
  'me': {
    'brs': 35,
    'submit': 15,
    'early': 10,
    'ach': 0,
    'file': 2,
    'total': 62,
    'nick': nick,
    'custom_nick': false,
    'show': show,
  },
  'group': {
    'name': 'УИБО-03-24',
    'xp': 30,
    'institute': 'ИТУ',
    'place': place,
    'place_inst': place,
    'mine': true,
    'people': place == null ? 1 : 3,
    'need': place == null ? 2 : 0,
    'institute_name': 'Институт технологий управления',
    'groups_inst': 2,
    'groups_all': 5,
  },
  'institute_top': [
    {'name': 'УИБО-01-24', 'xp': 150, 'institute': 'ИТУ', 'place': 1, 'place_inst': 1, 'mine': false},
    {'name': 'УИБО-03-24', 'xp': 30, 'institute': 'ИТУ', 'place': 2, 'place_inst': 2, 'mine': true},
  ],
  'university_top': [
    {'name': 'УИБО-01-24', 'xp': 150, 'institute': 'ИТУ', 'place': 1, 'place_inst': 1, 'mine': false},
  ],
  'people': [
    {'nick': 'Тихий кот', 'xp': 80, 'me': false, 'hidden': false},
    {'nick': nick, 'xp': 62, 'me': true, 'hidden': !show},
  ],
  'rules': {'brs': 1, 'submit': 15, 'early': 10, 'ach': 5, 'file': 2, 'min_people': 3},
};

/// Api с одним ответом на /rating и ответом на PUT (код и тело) — что спрашивали, в [asked].
Api _api(List<String> asked, {Map<String, dynamic>? data, int putStatus = 200, Object? putBody}) {
  final client = MockClient((req) async {
    asked.add(
      '${req.method} ${req.url.path.replaceFirst('/api/v1/', '/api/')}${req.body.isEmpty ? '' : ' ${req.body}'}',
    );
    final body = req.method == 'PUT' ? (putBody ?? {'ok': true}) : (data ?? _rating());
    return http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      req.method == 'PUT' ? putStatus : 200,
      headers: {'content-type': 'application/json'},
    );
  });
  return Api(client: client)..token = 't';
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('место группы в институте и в вузе, топы, свой опыт по частям', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(RatingScreen(api: _api([]))));
    await settle(t);
    expect(find.text('Рейтинг'), findsOneWidget);
    expect(find.text('место в ИТУ'), findsOneWidget);
    expect(find.text('из 5 групп'), findsOneWidget);
    expect(find.text('Институт технологий управления'), findsOneWidget);
    expect(find.text('Весь университет'), findsOneWidget);
    expect(find.text('Тихий кот'), findsOneWidget);
    expect(find.textContaining('видишь только ты'), findsWidgets);
    await t.scrollUntilVisible(find.byKey(const Key('rating:mine')), 200);
    expect(find.text('Сданные работы'), findsOneWidget);
    expect(find.text('62'), findsWidgets);
    await t.scrollUntilVisible(find.textContaining('Галочка «сделал» опыта не даёт'), 200);
  });

  testWidgets('группа ещё не в рейтинге — сколько людей не хватает', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(RatingScreen(api: _api([], data: _rating(place: null)))));
    await settle(t);
    expect(find.byKey(const Key('rating:wait')), findsOneWidget);
    expect(find.textContaining('ещё у 2 человек'), findsOneWidget);
  });

  testWidgets('показывать меня — на сервер; плохой ник — причина от сервера', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(
      _wrap(
        RatingScreen(
          api: _api(asked, putStatus: 400, putBody: {'detail': 'такой ник не подойдёт — без мата и оскорблений'}),
        ),
      ),
    );
    await settle(t);
    await t.tap(find.byKey(const Key('rating:show')));
    await settle(t);
    expect(asked, contains('PUT /api/rating/me {"show":true}'));

    await t.tap(find.byKey(const Key('rating:nick')));
    await settle(t);
    await t.enterText(find.byType(TextField), 'плохой');
    await t.tap(find.text('Сохранить'));
    await settle(t);
    expect(asked, contains('PUT /api/rating/me {"nick":"плохой"}'));
    expect(find.textContaining('без мата и оскорблений'), findsOneWidget);
    await t.pump(const Duration(seconds: 5));
  });

  test('строка в «Ещё»', () {
    expect(RatingRow.line(_rating()), '2 место в ИТУ · 2 в вузе');
    expect(RatingRow.line(_rating(place: null)), 'места групп в институте и вузе');
    expect(RatingRow.line({'ok': true}), 'места групп в институте и вузе');
  });
}

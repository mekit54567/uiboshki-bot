import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/screens/rating.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/trend_chart.dart';

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
    'show_all': false,
    'public_nick': null,
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
    'id': 4928,
    'parts': {'brs': 20, 'submit': 0, 'early': 0, 'ach': 5, 'file': 5},
    'history': [
      for (var i = 0; i < 8; i++)
        {
          'week': '${10 + i}.08',
          'xp': i * 4,
          'place': i < 3 ? null : 6 - i ~/ 2,
          'place_inst': i < 3 ? null : 3 - i ~/ 4,
        },
    ],
  },
  'institute_top': [
    {'id': 501, 'name': 'УИБО-01-24', 'xp': 150, 'institute': 'ИТУ', 'place': 1, 'place_inst': 1, 'mine': false},
    {'id': 4928, 'name': 'УИБО-03-24', 'xp': 30, 'institute': 'ИТУ', 'place': 2, 'place_inst': 2, 'mine': true},
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

Map<String, dynamic> _group() => {
  ...(_rating()['group'] as Map<String, dynamic>),
  'id': 501,
  'name': 'УИБО-01-24',
  'mine': false,
  'member': false,
  'hidden': 4,
  'people_list': [
    {'nick': 'Отличник', 'xp': 120, 'me': false, 'hidden': false},
  ],
};

/// Api с одним ответом на /rating и ответом на PUT (код и тело) — что спрашивали, в [asked].
Api _api(List<String> asked, {Map<String, dynamic>? data, int putStatus = 200, Object? putBody}) {
  final client = MockClient((req) async {
    asked.add(
      '${req.method} ${req.url.path.replaceFirst('/api/v1/', '/api/')}${req.body.isEmpty ? '' : ' ${req.body}'}',
    );
    final body = req.method == 'PUT'
        ? (putBody ?? {'ok': true})
        : req.url.path.contains('/rating/group/')
        ? _group()
        : req.url.path.endsWith('/legal/rating_all')
        ? _ratingAllDoc
        : (data ?? _rating());
    return http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      req.method == 'PUT' ? putStatus : 200,
      headers: {'content-type': 'application/json'},
    );
  });
  return Api(client: client)..token = 't';
}

const _ratingAllDoc = {
  'name': 'rating_all',
  'title': 'Согласие на показ в рейтинге всем',
  'version': '1',
  'date': '18.10.2026',
  'lead': 'Ставя галочку, я даю согласие оператору — Никита, разработчик сервиса «Капибара» — на показ ника и опыта.',
  'lead_short': 'Отдельное согласие: твой ник и опыт увидят все пользователи «Капибары».',
  'sections': [
    {
      'title': 'Что показываем',
      'sheet': true,
      'blocks': [
        {
          'ul': ['мой ник', 'мой опыт'],
        },
      ],
    },
    {
      'title': 'Срок и как отключить',
      'blocks': [
        {'p': 'Пока включено «Показывать меня всем».'},
      ],
    },
  ],
};

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('место группы в институте и в вузе, топы, свой опыт по частям', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(RatingScreen(api: _api([]))));
    await settle(t);
    expect(find.text('Рейтинг'), findsOneWidget);
    expect(find.text('место в ИТУ'), findsOneWidget);
    expect(find.text('из 5 групп'), findsOneWidget);
    await t.scrollUntilVisible(find.text('Институт технологий управления'), 200);
    await t.scrollUntilVisible(find.text('Весь университет'), 200);
    await t.scrollUntilVisible(find.text('Тихий кот'), 200);
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
    await t.scrollUntilVisible(find.byKey(const Key('rating:nick')), 300);
    await settle(t);
    await t.tap(find.byKey(const Key('rating:show')));
    await settle(t);
    expect(asked, contains('PUT /api/rating/me {"show":true}'));

    await t.tap(find.byKey(const Key('rating:nick')));
    await settle(t);
    expect(find.textContaining('Нельзя: мат и оскорбления'), findsOneWidget); // как можно назваться, а как нет
    await t.enterText(find.byType(TextField), 'плохой');
    await t.tap(find.text('Сохранить'));
    await settle(t);
    expect(asked, contains('PUT /api/rating/me {"nick":"плохой"}'));
    expect(find.textContaining('без мата и оскорблений'), findsOneWidget);
    await t.pump(const Duration(seconds: 5));
  });

  testWidgets('графики: опыт по неделям и место, из чего опыт группы', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(RatingScreen(api: _api([]))));
    await settle(t);
    expect(find.byKey(const Key('rating:growth')), findsOneWidget);
    expect(find.textContaining('28 опыта', findRichText: true), findsOneWidget); // последняя неделя подписана сверху
    await t.tap(find.byKey(const Key('rating:growth:place')));
    await settle(t);
    expect(find.textContaining('2 место в ИТУ', findRichText: true), findsOneWidget);
    await t.tap(find.byKey(const Key('rating:growth:place_all'))); // среди всех групп вуза
    await settle(t);
    expect(find.textContaining('3 место в вузе', findRichText: true), findsOneWidget);
    await t.scrollUntilVisible(find.byKey(const Key('rating:parts')), 200);
    expect(find.text('67%  '), findsOneWidget); // 20 из 30 — баллы БРС
  });

  testWidgets('нажал на группу — её люди, кто разрешил, и сколько скрыто', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(_wrap(RatingScreen(api: _api(asked))));
    await settle(t);
    await t.scrollUntilVisible(find.byKey(const Key('rating:group:501:place_inst')), 300);
    await settle(t);
    await t.tap(find.byKey(const Key('rating:group:501:place_inst')));
    await settle(t);
    expect(asked, contains('GET /api/rating/group/501'));
    expect(find.byType(GroupRatingScreen), findsOneWidget);
    await t.scrollUntilVisible(find.byKey(const Key('rating:group:people')), 200);
    expect(find.text('Отличник'), findsOneWidget);
    expect(find.textContaining('Ещё 4 человека с опытом'), findsOneWidget);
  });

  testWidgets('«Показывать меня всем» — только через лист отдельного согласия с галочкой', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(_wrap(RatingScreen(api: _api(asked))));
    await settle(t);
    await t.scrollUntilVisible(find.byKey(const Key('rating:nick')), 300);
    await settle(t);
    await t.tap(find.byKey(const Key('rating:show_all')));
    await settle(t);
    expect(asked, contains('GET /api/legal/rating_all'));
    expect(find.byType(ShowAllSheet), findsOneWidget);
    expect(find.textContaining('Капибара №…', findRichText: true), findsWidgets);
    // на листе — коротко; оператор и срок — в полном тексте по ссылке
    expect(find.text('Что показываем'), findsOneWidget);
    expect(find.text('Срок и как отключить'), findsNothing);
    expect(find.textContaining('разработчик сервиса'), findsNothing);
    expect(find.byKey(const Key('rating:all:full')), findsOneWidget);
    final on = find.byKey(const Key('rating:all:on'));
    expect(t.widget<FilledButton>(on).onPressed, isNull); // без галочки — неактивна
    await t.tap(find.byKey(const Key('rating:all:agree')));
    await settle(t);
    await t.tap(on);
    await settle(t);
    expect(asked, contains('PUT /api/rating/me {"show_all":true,"consent":"1"}'));
  });

  test('ось места: 1 сверху, подписано каждое место или три', () {
    expect(trendScale([null, 6, 5, 4], true).ticks, [1, 2, 3, 4, 5, 6]);
    expect(trendScale([3, 2, 1], true).ticks, [1, 2, 3]);
    expect(trendScale([12, 9], true).ticks, [1, 7, 12]);
    expect(trendScale([1, 1], true).ticks, [1, 2]);
    final xp = trendScale([0, 10, 28], false);
    expect(xp.lo, 0);
    expect(xp.ticks, [0, 14, 28]);
  });

  test('строка в «Ещё»', () {
    expect(RatingRow.line(_rating()), '2 место в ИТУ · 2 в вузе');
    expect(RatingRow.line(_rating(place: null)), 'места групп в институте и вузе');
    expect(RatingRow.line({'ok': true}), 'места групп в институте и вузе');
  });
}

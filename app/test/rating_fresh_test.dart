// «Рейтинг» нового дизайна (шаг 7): открывается на «Я» — своё место в группе,
// институте и вузе; «Группы» — места групп; ник и видимость — в листе «Мой
// опыт». Только при «Новом» в «Оформлении»; в «Классике» экран прежний.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/screens/rating.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';

import 'util.dart';

Widget _wrap(Widget child, {bool fresh = true}) => AppStyle(
  p: fresh ? Palette.paper : Palette.notebook,
  font: FontChoice.book,
  design2: true,
  look: Look(fresh: fresh),
  child: MaterialApp(home: child),
);

Map<String, Object?> _row(int place, String nick, int xp, {String? group, bool me = false, bool? seen}) => {
  'place': place,
  'nick': nick,
  'xp': xp,
  'me': me,
  'group': ?group,
  'seen': ?seen,
};

Map<String, Object?> _hidden(int place) => {'place': place, 'hidden': true};

const _rules = {'brs': 1, 'submit': 15, 'early': 10, 'ach': 5, 'file': 2, 'min_people': 3, 'ach_min': 3, 'ach_max': 25};

Map<String, Object?> _group({String institute = 'ИКБ'}) => {
  'id': 4928,
  'name': 'УИБО-03-24',
  'xp': 5840,
  'institute': institute,
  'place': 17,
  'place_inst': institute.isEmpty ? null : 3,
  'mine': true,
  'people': 14,
  'need': 0,
  'up_inst': institute.isEmpty ? null : 311,
  'up_all': 46,
  'institute_name': '',
  'groups_inst': 41,
  'groups_all': 380,
  'parts': {'brs': 3300, 'submit': 1500, 'early': 600, 'ach': 320, 'file': 120},
  'history': const [],
};

Map<String, Object?> _rating({bool show = true, bool showAll = false, bool inst = true}) => {
  'me': {
    'brs': 234,
    'submit': 105,
    'early': 40,
    'ach': 25,
    'file': 8,
    'total': 412,
    'nick': 'Аня',
    'custom_nick': false,
    'show': show,
    'show_all': showAll,
    'public_nick': showAll ? 'Капибара №4821' : null,
    'week': 38,
  },
  'ranks': {
    'group': {
      'place': 4,
      'of': 14,
      'up': 26,
      'above': 71,
      'rows': [
        _row(1, 'Егор К.', 655),
        _row(2, 'Капибара на паре', 540),
        _hidden(3),
        _row(4, 'Аня', 412, me: true, seen: show),
        _row(5, 'Даша М.', 390),
        _hidden(6),
        _row(7, 'Лёва', 350),
        _hidden(8),
        _row(9, 'Миша Т.', 290),
        _hidden(10),
        _hidden(11),
        _row(12, 'Оля', 120),
        _hidden(13),
        _hidden(14),
      ],
    },
    'inst': inst
        ? {
            'place': 37,
            'of': 412,
            'up': 4,
            'above': 91,
            'rows': [
              _row(1, 'Капибара №4821', 1930, group: 'БСБО-07-23'),
              {'gap': 35},
              _row(37, 'Аня', 412, group: 'УИБО-03-24', me: true, seen: showAll),
              {'gap': 375},
            ],
          }
        : null,
    'all': {
      'place': 318,
      'of': 2940,
      'up': 2,
      'above': 89,
      'rows': [
        _row(1, 'Капибара №4821', 1930, group: 'БСБО-07-23'),
        _row(2, 'ночной_дедлайн', 1884, group: 'ИКБО-12-23'),
        _row(3, 'Капибара №117', 1790, group: 'УИБО-01-24'),
        {'gap': 313},
        _hidden(317),
        _row(318, 'Аня', 412, group: 'УИБО-03-24', me: true, seen: showAll),
        _row(319, 'Капибара №2204', 411, group: 'ИНБО-03-24'),
        {'gap': 2621},
      ],
    },
  },
  'group': _group(institute: inst ? 'ИКБ' : ''),
  'institute_top': [
    {'id': 500, 'name': 'УИБО-01-24', 'xp': 6720, 'institute': 'ИКБ', 'place': 2, 'place_inst': 1, 'mine': false},
    {'id': 4928, 'name': 'УИБО-03-24', 'xp': 5840, 'institute': 'ИКБ', 'place': 17, 'place_inst': 3, 'mine': true},
  ],
  'university_top': [
    for (var i = 1; i <= 10; i++)
      {'id': 600 + i, 'name': 'ИВБО-0$i-23', 'xp': 8000 - i * 100, 'institute': '', 'place': i, 'mine': false},
  ],
  'people': const [],
  'rules': _rules,
};

/// Api: /rating — [data] (после PUT — [after], если дан), группа, текст
/// согласия; что спрашивали — в [asked].
Api _api(List<String> asked, {Map<String, Object?>? data, Map<String, Object?>? after}) {
  var saved = false;
  final client = MockClient((req) async {
    final path = req.url.path.replaceFirst('/api/v1/', '/api/');
    asked.add('${req.method} $path${req.body.isEmpty ? '' : ' ${req.body}'}');
    if (req.method == 'PUT') saved = true;
    final Object body = req.method == 'PUT'
        ? {'ok': true}
        : path.contains('/rating/group/')
        ? {
            ..._group(),
            'id': 500,
            'name': 'УИБО-01-24',
            'place': 2,
            'place_inst': 1,
            'mine': false,
            'member': false,
            'hidden': 9,
            'people_list': [
              {'nick': 'тихий_отличник', 'xp': 980, 'me': false},
            ],
          }
        : path.endsWith('/legal/rating_all')
        ? {
            'title': 'Согласие на показ в рейтинге всем',
            'version': '2',
            'date': '18.11.2026',
            'lead_short': 'Отдельное согласие: твой ник и опыт увидят все пользователи «Капибары».',
            'sections': const [],
          }
        : (saved && after != null ? after : (data ?? _rating()));
    return http.Response.bytes(utf8.encode(jsonEncode(body)), 200, headers: {'content-type': 'application/json'});
  });
  return Api(client: client)..token = 't';
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('открывается на «Я»: место в группе, опыт за неделю и сколько до места выше', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(RatingScreen(api: _api([]))));
    await settle(t);
    expect(find.byKey(const ValueKey('rating:fresh')), findsOneWidget);
    expect(find.text('Ты в группе'), findsOneWidget);
    expect(find.text('место из 14'), findsOneWidget);
    expect(find.text('+38 за\u00A0неделю'), findsOneWidget);
    expect(find.text('До 3\u00A0места 26 опыта: это 2 работы, сданные заранее'), findsOneWidget);
    // своя строка — акцентом и «это ты», скрытые — одним местом
    expect(find.descendant(of: find.byKey(const Key('rating:row:me')), matching: find.text('это ты')), findsOneWidget);
    expect(find.text('3\u00A0место не показывает себя'), findsOneWidget);
    // хвост группы свёрнут: сколько ещё и сколько из них скрыты
    expect(find.text('ещё 9\u00A0человек, из них 6 скрыты'), findsOneWidget);
    expect(find.byKey(const Key('rating:row:12')), findsNothing);
    await t.tap(find.byKey(const Key('rating:more')));
    await settle(t);
    await t.scrollUntilVisible(find.byKey(const Key('rating:row:12')), 200);
    expect(find.text('Оля'), findsOneWidget);
  });

  testWidgets('вкладки «Институт» и «Вуз»: верх, пропуски, соседи и кто тебя видит', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(RatingScreen(api: _api([]))));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:scope:1')));
    await settle(t);
    expect(find.text('Ты в ИКБ'), findsOneWidget);
    expect(find.text('место из 412'), findsOneWidget);
    expect(find.text('До 36\u00A0места 4 опыта: это 4 балла БРС'), findsOneWidget);
    expect(find.text('дальше 35\u00A0человек'), findsOneWidget);
    expect(find.text('ещё 375\u00A0человек'), findsOneWidget);

    await t.tap(find.byKey(const Key('rating:scope:2')));
    await settle(t);
    expect(find.text('Ты в вузе'), findsOneWidget);
    expect(find.text('место из 2\u00A0940'), findsOneWidget);
    expect(find.text('выше 89%'), findsOneWidget); // в вузе — вместо «за неделю»
    expect(find.text('БСБО-07-23'), findsOneWidget); // чужие — с группой
    // «группе» включено, «всем» — нет: здесь тебя видят только свои
    expect(
      find.descendant(of: find.byKey(const Key('rating:row:me')), matching: find.text('это ты · видят только свои')),
      findsOneWidget,
    );
  });

  testWidgets('без института — вкладки «Группа» и «Вуз»', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(RatingScreen(api: _api([], data: _rating(inst: false)))));
    await settle(t);
    expect(find.byKey(const Key('rating:scope:2')), findsNothing);
    await t.tap(find.byKey(const Key('rating:scope:1')));
    await settle(t);
    expect(find.text('Ты в вузе'), findsOneWidget);
  });

  testWidgets('«Группы»: место группы, своя ниже верха — после пропуска, нажатие — экран группы', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(_wrap(RatingScreen(api: _api(asked))));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:view:1')));
    await settle(t);
    expect(find.text('УИБО-03-24 в ИКБ'), findsOneWidget);
    expect(find.text('место из 41'), findsOneWidget);
    expect(find.text('из 380'), findsOneWidget);
    expect(find.text('У группы 5\u00A0840 опыта · до 2\u00A0места 311 · твой вклад 7%'), findsOneWidget);
    expect(find.text('твоя группа'), findsOneWidget);

    await t.tap(find.byKey(const Key('rating:groups:scope:1')));
    await settle(t);
    await t.scrollUntilVisible(find.text('ещё 363\u00A0группы'), 200);
    expect(find.text('дальше 6\u00A0групп'), findsOneWidget);
    expect(find.byKey(const Key('rating:group:4928:place')), findsOneWidget);

    await t.tap(find.byKey(const Key('rating:groups:scope:0')));
    await settle(t);
    await t.scrollUntilVisible(find.byKey(const Key('rating:group:500:place_inst')), -200);
    await t.tap(find.byKey(const Key('rating:group:500:place_inst')));
    await settle(t);
    expect(asked, contains('GET /api/rating/group/500'));
    expect(find.byKey(const ValueKey('rating:group:fresh')), findsOneWidget);
    expect(find.text('1\u00A0место в ИКБ · 2\u00A0в\u00A0вузе'), findsOneWidget);
    await t.scrollUntilVisible(find.byKey(const Key('rating:group:hidden')), 200);
    expect(find.text('тихий_отличник'), findsOneWidget);
    expect(find.text('ещё 9\u00A0человек не показывают себя'), findsOneWidget);
  });

  testWidgets('лист «Мой опыт»: из чего опыт, «показывать группе» — сразу и на сервер', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(_wrap(RatingScreen(api: _api(asked, after: _rating(show: false)))));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:mine:open')));
    await settle(t);
    expect(find.byKey(const Key('rating:mine')), findsOneWidget);
    expect(find.text('видишь только ты'), findsOneWidget);
    expect(find.text('Сдано заранее'), findsOneWidget);
    expect(find.text('группа видит твой ник и опыт'), findsOneWidget);
    await t.tap(find.byKey(const Key('rating:show')));
    await settle(t);
    expect(asked, contains('PUT /api/rating/me {"show":false}'));
    expect(find.text('сейчас группа тебя не видит'), findsOneWidget);
    // правила — по нажатию, не абзацем на экране
    expect(find.byKey(const Key('rating:rules:text')), findsNothing);
    await t.tap(find.text('Как считается опыт'));
    await settle(t);
    expect(find.textContaining('Галочка «сделал» опыта не даёт'), findsOneWidget);
  });

  testWidgets('«Показывать меня всем» из листа — через отдельное согласие', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(_wrap(RatingScreen(api: _api(asked, after: _rating(showAll: true)))));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:mine:open')));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:show_all')));
    await settle(t);
    expect(asked, contains('GET /api/legal/rating_all'));
    expect(find.byType(ShowAllSheet), findsOneWidget);
    await t.tap(find.byKey(const Key('rating:all:agree')));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:all:on')));
    await settle(t);
    expect(asked, contains('PUT /api/rating/me {"show_all":true,"consent":"2"}'));
    expect(find.text('все видят тебя как «Капибара №4821»'), findsOneWidget);
  });

  testWidgets('в «Классике» — прежний экран', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(RatingScreen(api: _api([])), fresh: false));
    await settle(t);
    expect(find.byKey(const ValueKey('rating:fresh')), findsNothing);
    expect(find.text('место в ИКБ'), findsOneWidget);
  });

  test('сколько до места выше — понятными делами', () {
    String hint(int? place, int? up, {int of = 14}) => ratingUpHint({'place': place, 'up': up, 'of': of}, _rules);
    expect(hint(null, null), startsWith('Место появится с первым опытом'));
    expect(hint(1, null), 'Ты на первом месте.');
    expect(hint(1, null, of: 1), 'Пока опыт здесь только у тебя.');
    expect(hint(5, 1), 'До 4\u00A0места 1 опыта: это 1 балл БРС');
    expect(hint(5, 12), 'До 4\u00A0места 12 опыта: это одна сданная работа');
    expect(hint(5, 22), 'До 4\u00A0места 22 опыта: это одна работа, сданная заранее');
    expect(hint(5, 120), 'До 4\u00A0места 120 опыта: это 5 работ, сданных заранее');
    expect(hint(5, 1200), 'До 4\u00A0места 1\u00A0200 опыта');
  });
}

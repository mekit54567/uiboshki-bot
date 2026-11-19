// Предложение показаться в рейтинге (варианты А + В, 18.11): карточка на
// «Рейтинге», лист с двумя выключенными тумблерами, «Не сейчас» и «Больше не
// предлагать». Ничего не включается само.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/screens/rating.dart';
import 'package:uiboshki/screens/notify.dart' show AppSwitch;
import 'package:uiboshki/screens/rating_offer.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';

import 'util.dart';

Widget _wrap(Widget child) => AppStyle(
  p: Palette.paper,
  font: FontChoice.book,
  design2: true,
  look: const Look(fresh: true),
  child: MaterialApp(home: child),
);

Map<String, Object?> _rating({bool show = false, bool showAll = false}) => {
  'me': {
    'brs': 0,
    'submit': 0,
    'early': 0,
    'ach': 0,
    'file': 0,
    'total': 0,
    'nick': 'Аня',
    'custom_nick': false,
    'show': show,
    'show_all': showAll,
    'public_nick': null,
    'week': 0,
  },
  'ranks': {'group': null, 'inst': null, 'all': null},
  'group': {'id': 1, 'name': 'УИБО-03-24', 'xp': 0, 'institute': '', 'place': null, 'people': 1, 'need': 2},
  'institute_top': const [],
  'university_top': const [],
  'people': const [],
  'rules': {'brs': 1, 'submit': 15, 'early': 10, 'ach': 5, 'file': 2, 'min_people': 3, 'ach_min': 3, 'ach_max': 25},
};

/// Api: что спрашивали — в [asked]; [offer] — ответ GET /rating/offer.
Api _api(List<String> asked, {Map<String, Object?> offer = const {'card': true, 'sheet': false}, bool show = false}) {
  var saved = false;
  final client = MockClient((req) async {
    final path = req.url.path.replaceFirst('/api/v1/', '/api/');
    asked.add('${req.method} $path${req.body.isEmpty ? '' : ' ${req.body}'}');
    if (req.method == 'PUT') saved = true;
    final Object body = path.endsWith('/rating/offer')
        ? (req.method == 'GET' ? offer : {'card': false, 'sheet': false})
        : path.endsWith('/legal/rating_all')
        ? {
            'title': 'Согласие',
            'version': '2',
            'date': '18.11.2026',
            'lead_short': 'Отдельное согласие.',
            'sections': [],
          }
        : req.method == 'PUT'
        ? {'ok': true}
        : _rating(show: show || (saved && asked.any((a) => a.contains('"show":true'))));
    return http.Response.bytes(utf8.encode(jsonEncode(body)), 200, headers: {'content-type': 'application/json'});
  });
  return Api(client: client)..token = 't';
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    resetRatingOfferRun();
  });

  testWidgets('карточка на «Рейтинге», пока тебя не видно: две кнопки одного размера и «Больше не предлагать»', (
    t,
  ) async {
    phone(t);
    await t.pumpWidget(_wrap(RatingScreen(api: _api([]))));
    await settle(t);
    expect(find.text('Тебя не видно в рейтинге группы'), findsOneWidget);
    final show = t.getSize(find.byKey(const Key('rating:offer:show')));
    final later = t.getSize(find.byKey(const Key('rating:offer:later')));
    expect(show, later, reason: '«Не сейчас» не меньше «Показать»');
    expect(find.byKey(const Key('rating:offer:stop')), findsOneWidget);
  });

  testWidgets('карточки нет, если тебя уже видно, или сервер не просит', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(RatingScreen(api: _api([], show: true))));
    await settle(t);
    expect(find.byKey(const Key('rating:offer')), findsNothing);
    await t.pumpWidget(
      _wrap(
        RatingScreen(
          key: UniqueKey(),
          api: _api([], offer: const {'card': false, 'sheet': false}),
        ),
      ),
    );
    await settle(t);
    expect(find.byKey(const Key('rating:offer')), findsNothing);
  });

  testWidgets('«Не сейчас» прячет карточку и говорит серверу, «Больше не предлагать» — тоже', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(_wrap(RatingScreen(api: _api(asked))));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:offer:later')));
    await settle(t);
    expect(find.byKey(const Key('rating:offer')), findsNothing);
    expect(asked, contains('POST /api/rating/offer {"action":"later"}'));
    await t.pumpWidget(_wrap(RatingScreen(key: UniqueKey(), api: _api(asked))));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:offer:stop')));
    await settle(t);
    expect(find.byKey(const Key('rating:offer')), findsNothing);
    expect(asked, contains('POST /api/rating/offer {"action":"stop"}'));
  });

  testWidgets('«Показать» — лист: оба тумблера выключены, ничего не сохранено', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(_wrap(RatingScreen(api: _api(asked))));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:offer:show')));
    await settle(t);
    expect(find.byKey(const Key('rating:offer:sheet')), findsOneWidget);
    expect(t.widget<AppSwitch>(find.byKey(const Key('rating:offer:group'))).value, isFalse);
    expect(t.widget<AppSwitch>(find.byKey(const Key('rating:offer:all'))).value, isFalse);
    expect(find.text('Оставить скрытым'), findsOneWidget);
    expect(asked.where((a) => a.startsWith('PUT')), isEmpty);
  });

  testWidgets('тумблер «Группе» — отдельно, сразу на сервер; «Всем» без согласия не включается', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(_wrap(RatingScreen(api: _api(asked))));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:offer:show')));
    await settle(t);
    await t.tap(find.byKey(const Key('rating:offer:group')));
    await settle(t);
    expect(asked, contains('PUT /api/rating/me {"show":true}'));
    expect(asked.where((a) => a.contains('show_all')), isEmpty, reason: 'одна кнопка не включает обе');
    expect(asked, contains('POST /api/rating/offer {"action":"accepted","source":"card"}'));
    expect(find.text('Готово'), findsOneWidget);
    // «Всем» — через лист отдельного согласия; закрыли его — ничего не сохранено
    await t.tap(find.byKey(const Key('rating:offer:all')));
    await settle(t);
    expect(find.text('Согласие'), findsOneWidget);
    expect(asked.where((a) => a.contains('show_all')), isEmpty);
  });

  testWidgets('лист при входе: сервер сказал «пора» — показываем и считаем показ', (t) async {
    phone(t);
    final asked = <String>[];
    final api = _api(asked, offer: const {'card': true, 'sheet': true});
    late BuildContext ctx;
    await t.pumpWidget(
      _wrap(
        Builder(
          builder: (c) {
            ctx = c;
            return const Scaffold();
          },
        ),
      ),
    );
    unawaitedOffer(maybeOfferRating(ctx, api));
    await settle(t);
    expect(find.byKey(const Key('rating:offer:sheet')), findsOneWidget);
    expect(asked, contains('POST /api/rating/offer {"action":"shown"}'));
    // «Больше не предлагать» в листе
    await t.tap(find.byKey(const Key('rating:offer:sheet:stop')));
    await settle(t);
    expect(asked, contains('POST /api/rating/offer {"action":"stop"}'));
    expect(find.byKey(const Key('rating:offer:sheet')), findsNothing);
  });

  testWidgets('лист при входе: сервер не просит — тишина', (t) async {
    phone(t);
    final asked = <String>[];
    late BuildContext ctx;
    await t.pumpWidget(
      _wrap(
        Builder(
          builder: (c) {
            ctx = c;
            return const Scaffold();
          },
        ),
      ),
    );
    await maybeOfferRating(ctx, _api(asked));
    await settle(t);
    expect(find.byKey(const Key('rating:offer:sheet')), findsNothing);
    expect(asked.where((a) => a.startsWith('POST')), isEmpty);
  });
}

void unawaitedOffer(Future<void> f) {}

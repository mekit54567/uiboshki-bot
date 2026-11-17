// «Ещё» (23Б): шапка с именем и группой, баллы БРС одной цифрой и фразой —
// нажал, открылась «Учёба»; без своего входа в СДО — «Подключи СДО»;
// СДО не отвечает — остальной экран работает.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/screens/more.dart';
import 'package:uiboshki/screens/study.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

/// Api на ответах стенда, где у части путей — ошибка (код, текст).
Api failingApi(Map<String, (int, String)> errors) {
  final fx = demoFixtures();
  return Api(
    client: MockClient((req) async {
      final path = req.url.path.replaceFirst('/api/v1/', '/api/');
      final key = '${req.method} $path${req.url.query.isEmpty ? '' : '?${req.url.query}'}';
      final err = errors[key];
      final (code, body) = err != null ? (err.$1, {'detail': err.$2}) : (200, fx[key] ?? {'ok': true});
      return http.Response.bytes(utf8.encode(jsonEncode(body)), code, headers: {'content-type': 'application/json'});
    }),
  )..token = 't';
}

Widget host(Api api, {VoidCallback? onSdo}) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(
    home: Scaffold(
      body: MoreScreen(api: api, onFont: (_) {}, onLogout: () {}, onSdo: onSdo),
    ),
  ),
);

Course course(String title, num score, {bool credit = false}) => Course.fromJson({
  'id': title.hashCode,
  'title': title,
  'score': score,
  'marks': credit
      ? [
          {'at': 40, 'label': 'зачёт'},
        ]
      : [
          {'at': 40, 'label': '3'},
          {'at': 60, 'label': '4'},
          {'at': 80, 'label': '5'},
        ],
});

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  test('сводка по баллам стенда: среднее, на «3» или зачёт хватает, меньше всего', () {
    final courses = [for (final c in demoFixtures()['GET /api/sdo/grades']['courses'] as List) Course.fromJson(c)];
    final sum = PointsSummary.of(courses);
    // (34 + 48 + 28 + 64 + 13 + 44) / 6 = 38,5
    expect(sum.average, 39);
    expect(
      sum.sentence,
      'На «3» или зачёт хватает в 3\u00A0из\u00A06 предметов. Меньше всего\u00A0— Основы предпринимательской деятельности, 13.',
    );
  });

  test('сводка: только экзамены, ни одной «3», пусто, баллов ещё нет', () {
    expect(
      PointsSummary.of([course('Анализ данных', 22), course('Учёт', 61)]).sentence,
      'На «3» хватает в 1\u00A0из\u00A02 предметов. Меньше всего\u00A0— Анализ данных, 22.',
    );
    expect(
      PointsSummary.of([course('Анализ данных', 22), course('Право', 30, credit: true)]).sentence,
      'На «3» или зачёт пока не хватает ни в одном из 2 предметов. Меньше всего\u00A0— Анализ данных, 22.',
    );
    expect(
      PointsSummary.of([course('Право', 45.5, credit: true)]).sentence,
      'На зачёт хватает в 1\u00A0из\u00A01 предмета.',
    );
    expect(PointsSummary.of([]).sentence, 'Пока пусто — преподаватели ещё не завели журналы.');
    expect(
      PointsSummary.of([course('Анализ данных', 0), course('Учёт', 0)]).sentence,
      'Баллов пока нет — ни в одном из 2 предметов.',
    );
  });

  testWidgets('шапка: имя, группа, средний балл и фраза; нажал — открылась «Учёба»', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(UiboApp(api: fakeApi(requests: asked)));
    await settle(t);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    expect(asked, contains('GET /api/sdo/grades'));
    expect(find.text('Аня'), findsOneWidget);
    expect(find.text('А'), findsOneWidget); // кружок с первой буквой
    expect(find.text('УИБО-03-24'), findsOneWidget);
    expect(find.text('профиль и настройки'), findsNothing);
    expect(find.text('Баллы БРС, в среднем'), findsOneWidget);
    expect(find.text('39'), findsOneWidget);
    expect(
      find.text(
        'На «3» или зачёт хватает в 3\u00A0из\u00A06 предметов. Меньше всего\u00A0— Основы предпринимательской деятельности, 13.',
      ),
      findsOneWidget,
    );
    // настройки плитками — все на месте
    // список ленивый: докручиваем до каждой плитки, потом обратно наверх
    final list = find.descendant(of: find.byType(MoreScreen), matching: find.byType(Scrollable)).first;
    for (final title in ['Уведомления', 'Тема и шрифт', 'Безопасность', 'Календарь', 'Группа', 'Позвать', 'Выйти']) {
      await t.scrollUntilVisible(find.text(title), 200, scrollable: list);
      expect(find.text(title), findsOneWidget, reason: title);
    }
    await t.drag(find.byType(MoreScreen), const Offset(0, 4000));
    await settle(t);

    expect(find.byType(StudyScreen), findsNothing);
    await t.tap(find.byKey(const Key('more:points')));
    await settle(t);
    expect(find.byType(StudyScreen), findsOneWidget); // вкладка «Учёба»
    expect(find.byType(MoreScreen), findsNothing);
  });

  testWidgets('без своего входа в СДО — «Подключи СДО», ведёт на вход', (t) async {
    phone(t);
    final api = failingApi({'GET /api/sdo/grades': (403, 'подключи СДО, чтобы видеть свои баллы')});
    var sdo = 0;
    await t.pumpWidget(host(api, onSdo: () => sdo++));
    await settle(t);
    expect(find.text('Подключи СДО — тут будут баллы'), findsOneWidget);
    expect(find.text('Баллы БРС, в среднем'), findsNothing);
    expect(find.text('Уведомления'), findsOneWidget);
    await t.tap(find.byKey(const Key('more:sdo')));
    await settle(t);
    expect(find.text('Вход в СДО'), findsOneWidget);
    // вернулся со входа — оболочка перестроит «Учёбу», чтобы там не висело «Подключить СДО»
    Navigator.of(t.element(find.text('Вход в СДО'))).pop();
    await settle(t);
    expect(sdo, 1);
  });

  testWidgets('вход в СДО устарел — «подключи заново»', (t) async {
    phone(t);
    final api = failingApi({'GET /api/sdo/grades': (403, 'вход в СДО устарел — подключи заново: вкладка СДО → Вход')});
    await t.pumpWidget(host(api));
    await settle(t);
    expect(find.text('Вход в СДО устарел — подключи заново'), findsOneWidget);
  });

  testWidgets('СДО не отвечает — тихая строка, шапка и настройки работают', (t) async {
    phone(t);
    final api = failingApi({'GET /api/sdo/grades': (502, 'СДО сейчас не отвечает — попробуй позже')});
    await t.pumpWidget(host(api));
    await settle(t);
    expect(find.text('Баллы не видны: СДО сейчас не отвечает — попробуй позже'), findsOneWidget);
    expect(find.text('Аня'), findsOneWidget);
    expect(find.text('Безопасность'), findsOneWidget);
  });
}

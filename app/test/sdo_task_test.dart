import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/screens/legal.dart';
import 'package:uiboshki/screens/sdo_connect.dart';
import 'package:uiboshki/screens/sdo_login.dart';
import 'package:uiboshki/screens/study.dart';
import 'package:uiboshki/screens/task.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

/// Списки ленивые: сначала докрутить до строки, потом нажать.
Future<void> tapVisible(WidgetTester t, Finder f) async {
  await t.scrollUntilVisible(f, 200, scrollable: find.byType(Scrollable).first);
  await settle(t);
  await t.tap(f);
  await settle(t);
}

void main() {
  test('ссылки на файлы СДО и статусы Moodle по-человечески', () {
    expect(sdoLink('/sdl/tok/a.pdf').toString(), '${Api.base}/sdl/tok/a.pdf');
    expect(sdoLink('https://www.uiboshki.ru/sdl/t/b.pdf').toString(), 'https://www.uiboshki.ru/sdl/t/b.pdf');
    expect(humanStatus('Ответы на задание еще не представлены'), 'Ещё не сдано');
    expect(humanStatus('Отправлено для оценивания'), 'Сдано, ждёт оценки');
    expect(humanStatus('что-то своё'), 'что-то своё');
    expect(needsSdo('вход в СДО устарел — подключи заново: вкладка СДО → Вход'), isTrue);
    expect(needsSdo('СДО сейчас не отвечает — попробуй позже'), isFalse);
  });

  testWidgets('вход в СДО: кука уходит на сервер, делиться с группой, отключить', (t) async {
    phone(t);
    final asked = <String>[];
    final bodies = <String, Object?>{};
    const ok = {'state': 'ok', 'checked_at': null, 'share': false, 'can_share': true, 'group': 'УИБО-01-24'};
    final api = fakeApi(
      requests: asked,
      bodies: bodies,
      overrides: {
        'GET /api/sdo/status': {'state': 'off'},
        'POST /api/sdo/connect': ok,
        'POST /api/sdo/share': {...ok, 'share': true},
        'POST /api/sdo/disconnect': {'state': 'off'},
      },
    );
    await t.pumpWidget(host(SdoConnectScreen(api: api, webLogin: false)));
    await settle(t);
    expect(asked, contains('GET /api/sdo/status'));
    expect(find.text('Не подключено'), findsOneWidget);
    expect(find.text('Как подключить'), findsOneWidget);
    expect(find.textContaining('MoodleSession', findRichText: true), findsWidgets);

    await t.scrollUntilVisible(find.byType(TextField), 200, scrollable: find.byType(Scrollable).first);
    await t.enterText(find.byType(TextField), '  abc123  ');
    await tapVisible(t, find.text('Проверить и сохранить'));
    expect(asked, isNot(contains('POST /api/sdo/connect'))); // без галочки согласия — не отправляем
    await tapVisible(t, find.descendant(of: find.byType(ConsentCheck), matching: find.byType(AnimatedContainer)));
    await tapVisible(t, find.text('Проверить и сохранить'));
    expect(bodies['POST /api/sdo/connect'], {'cookie': 'abc123', 'agree': true});
    expect(find.text('Подключено, работает'), findsOneWidget);
    expect(find.textContaining('для всей УИБО-01-24'), findsOneWidget);

    await tapVisible(t, find.byType(Switch));
    expect(bodies['POST /api/sdo/share'], {'share': true});
    expect(find.textContaining('Задания группы появятся'), findsOneWidget);

    await tapVisible(t, find.text('Отключить СДО'));
    await t.tap(find.text('Отключить'));
    await settle(t);
    expect(asked, contains('POST /api/sdo/disconnect'));
    expect(find.text('Не подключено'), findsOneWidget);
  });

  testWidgets('вход страницей СДО: сессия из страницы входа уходит на сервер', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    var opened = 0;
    final api = fakeApi(
      bodies: bodies,
      overrides: {
        'GET /api/sdo/status': {'state': 'off'},
        'POST /api/sdo/connect': {'state': 'ok', 'checked_at': null},
      },
    );
    Future<String?> page(BuildContext _) async {
      opened++;
      return 'sess-1';
    }

    await t.pumpWidget(host(SdoConnectScreen(api: api, webLogin: true, sdoLogin: page)));
    await settle(t);
    expect(find.byType(TextField), findsNothing); // вставка куки — только по кнопке «вручную»
    await tapVisible(t, find.text('Войти в СДО'));
    expect(opened, 0); // без галочки согласия страница не открывается
    await tapVisible(t, find.descendant(of: find.byType(ConsentCheck), matching: find.byType(AnimatedContainer)));
    await tapVisible(t, find.text('Войти в СДО'));
    expect(opened, 1);
    expect(bodies['POST /api/sdo/connect'], {'cookie': 'sess-1', 'agree': true});
    expect(find.text('Подключено, работает'), findsOneWidget);
  });

  testWidgets('вход страницей СДО: можно вставить MoodleSession вручную', (t) async {
    phone(t);
    final api = fakeApi(
      overrides: {
        'GET /api/sdo/status': {'state': 'off'},
      },
    );
    await t.pumpWidget(host(SdoConnectScreen(api: api, webLogin: true, sdoLogin: (_) async => null)));
    await settle(t);
    await tapVisible(t, find.byKey(const Key('sdo-manual')));
    expect(find.byType(TextField), findsOneWidget);
    expect(find.text('Проверить и сохранить'), findsOneWidget);
  });

  test('вошёл в СДО — страница СДО, но не вход', () {
    expect(sdoLoggedIn(Uri.parse('https://online-edu.mirea.ru/my/')), isTrue);
    expect(sdoLoggedIn(Uri.parse('https://online-edu.mirea.ru/login/index.php')), isFalse);
    expect(sdoLoggedIn(Uri.parse('https://sso.mirea.ru/login')), isFalse);
    expect(sdoLoggedIn(null), isFalse);
  });

  testWidgets('учёба без входа в СДО: карточка «Подключить СДО» ведёт на вход', (t) async {
    phone(t);
    final asked = <String>[];
    final api = Api(
      client: MockClient((req) async {
        asked.add('${req.method} ${req.url.path}');
        final (code, body) = switch (req.url.path) {
          '/api/v1/sdo/grades' => (403, {'detail': 'подключи СДО, чтобы видеть свои баллы'}),
          '/api/v1/sdo/status' => (200, {'state': 'off'}),
          _ => (200, {'ok': true}),
        };
        return http.Response.bytes(utf8.encode(jsonEncode(body)), code, headers: {'content-type': 'application/json'});
      }),
    )..token = 't';
    await t.pumpWidget(host(Scaffold(body: StudyScreen(api: api))));
    await settle(t);
    expect(find.text('Подключи СДО, чтобы видеть свои баллы'), findsOneWidget);
    expect(find.bySemanticsLabel('СДО не подключено'), findsOneWidget);
    expect(find.textContaining('Сдача работ прямо отсюда'), findsOneWidget);

    await tapVisible(t, find.text('Подключить СДО'));
    expect(find.text('Вход в СДО'), findsOneWidget);
    expect(find.text('Не подключено'), findsOneWidget);
    asked.clear();
    await t.tap(find.byTooltip('Назад'));
    await settle(t);
    expect(asked, contains('GET /api/v1/sdo/grades')); // вернулся — баллы заново
  });

  testWidgets('экран задания по фикстуре: срок, статус, файлы, «Сдать работу»', (t) async {
    phone(t);
    final asked = <String>[];
    final opened = <Uri>[];
    final api = fakeApi(requests: asked);
    final work = {
      'name': 'Практическое задание 3. BPMN-модель',
      'module': 'assign',
      'cmid': 105,
      'status': 'wait',
      'grade': null,
      'max': 8,
      'pass_mark': 5,
    };
    await t.pumpWidget(
      host(TaskScreen(api: api, work: work, course: 'Бизнес-процессы', open: (u) async => opened.add(u))),
    );
    await settle(t);
    expect(asked, contains('GET /api/sdo/task/105'));
    final task = demoFixtures()['GET /api/sdo/task/105'] as Map;
    // в заголовке после дефиса — невидимый «не переносить» (U+2060)
    expect(find.text((task['title'] as String).replaceAll('-', '-\u2060')), findsOneWidget);
    expect(find.text('четверг, 8 октября 2026, 23:59'), findsOneWidget);
    expect(find.text('ждёт оценки'), findsOneWidget);
    expect(find.text('Сдано, ждёт оценки'), findsOneWidget);
    expect(find.text('Не оценено'), findsOneWidget);
    expect(find.text('до 8 баллов · зачёт от 5'), findsOneWidget);
    expect(find.textContaining('BPMN-модель основного'), findsOneWidget);

    await tapVisible(t, find.text('Нотация BPMN — памятка.pdf'));
    expect(opened, [sdoLink('#')]);

    await tapVisible(t, find.text('Сдать ещё / заменить · до 3 файлов'));
    expect(asked, contains('GET /api/sdo/submit-rules?cmid=105&deadline_id=0'));
    expect(find.text('Сдать файлом'), findsOneWidget);
  });

  testWidgets('предмет: нажал на задание — открылся его экран', (t) async {
    phone(t);
    final asked = <String>[];
    final api = fakeApi(requests: asked);
    final course = Course.fromJson(Map<String, dynamic>.from(demoFixtures()['GET /api/sdo/grades/18672']));
    await t.pumpWidget(host(CourseScreen(api: api, course: course)));
    await settle(t);
    final row = find.text('Практическое задание 3. BPMN-модель');
    await t.scrollUntilVisible(row, 300, scrollable: find.byType(Scrollable).first);
    await settle(t);
    await t.tap(row);
    await settle(t);
    expect(asked, contains('GET /api/sdo/task/105'));
    expect(find.byType(TaskScreen), findsOneWidget);
    await t.scrollUntilVisible(find.text('Нотация BPMN — памятка.pdf'), 200, scrollable: find.byType(Scrollable).first);
    await t.scrollUntilVisible(find.textContaining('Сдать ещё'), 200, scrollable: find.byType(Scrollable).first);
  });
}

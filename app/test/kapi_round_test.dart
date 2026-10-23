// Круг правок Kapi ИИ (Никита 21.10, скрины с iPhone): список «по какому
// предмету?» сворачивается после выбора, под ошибкой — «Повторить» (тот же
// вопрос, а не «?»), предмет по сокращению переключает шапку, текст слайда
// склеен в абзацы без номера страницы.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/screens/chat.dart';
import 'package:uiboshki/screens/files.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.notebook,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

/// /chat отвечает по очереди из [answers] (int — код ошибки с detail).
Api chatApi(List<Object> answers, List<Map> sent) {
  final client = MockClient((req) async {
    final path = req.url.path.replaceFirst('/api/v1/', '/api/');
    if (path == '/api/chat') {
      sent.add(jsonDecode(req.body) as Map);
      final a = answers.removeAt(0);
      if (a is int) {
        return http.Response.bytes(
          utf8.encode(jsonEncode({'detail': 'Не получилось ответить — ИИ сейчас перегружен.'})),
          a,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response.bytes(utf8.encode(jsonEncode(a)), 200, headers: {'content-type': 'application/json'});
    }
    final body = path == '/api/subjects' ? {'subjects': []} : {'ok': true};
    return http.Response.bytes(utf8.encode(jsonEncode(body)), 200, headers: {'content-type': 'application/json'});
  });
  return Api(client: client)..token = 't';
}

Future<void> ask(WidgetTester t, String q) async {
  await t.enterText(find.byType(TextField), q);
  await t.tap(find.byTooltip('Отправить'));
  await settle(t);
}

const subjects = [
  'Анализ данных',
  'Архитектура предприятия',
  'Моделирование бизнес-процессов',
  'Основы предпринимательской деятельности',
];

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('текст слайда: строки одной фразы склеены, номер страницы убран', () {
    const raw =
        'Методология IDEF0\nОсновой методологии IDEF0, используемой для моделирования\n'
        'бизнес -процессов, стали методология SADT и алгоритмические\nязыки.\n'
        'Появление методологии было предопределено\n(Mainframe) и подходами MRP.\n37';
    expect(
      tidyPageText(raw),
      'Методология IDEF0\nОсновой методологии IDEF0, используемой для моделирования бизнес-процессов, '
      'стали методология SADT и алгоритмические языки.\nПоявление методологии было предопределено '
      '(Mainframe) и подходами MRP.',
    );
  });

  testWidgets('выбрал предмет — список свернулся в одну строку', (t) async {
    phone(t);
    final sent = <Map>[];
    final api = chatApi([
      {'content': 'По какому предмету?', 'html': 'По какому предмету?', 'choose': subjects},
      {'content': 'На лекции — IDEF0.', 'html': 'На лекции — IDEF0.'},
    ], sent);
    await t.pumpWidget(host(ChatScreen(api: api)));
    await settle(t);
    await ask(t, 'что на лекции будет');
    expect(find.text('Архитектура предприятия'), findsOneWidget);
    await t.tap(find.text('Моделирование бизнес-процессов'));
    await settle(t);
    expect(find.text('Архитектура предприятия'), findsNothing); // список ушёл
    expect(find.byKey(const Key('chat:chosen')), findsOneWidget);
    expect(sent.last['subject'], 'Моделирование бизнес-процессов');
    expect(find.text('На лекции — IDEF0.'), findsOneWidget);
  });

  testWidgets('ошибка — «Повторить» задаёт тот же вопрос, ошибка уходит', (t) async {
    phone(t);
    final sent = <Map>[];
    final api = chatApi([
      502,
      {'content': 'Ответ.', 'html': 'Ответ.'},
    ], sent);
    await t.pumpWidget(host(ChatScreen(api: api)));
    await settle(t);
    await ask(t, 'что завтра на лекции?');
    expect(find.textContaining('Не получилось ответить'), findsOneWidget);
    expect(find.textContaining('Gemini'), findsNothing);
    await t.tap(find.byKey(const Key('chat:retry')));
    await settle(t);
    expect(find.textContaining('Не получилось ответить'), findsNothing);
    expect(find.text('Ответ.'), findsOneWidget);
    final history = sent.last['history'] as List;
    expect((history.last as Map)['content'], 'что завтра на лекции?');
  });

  testWidgets('сервер узнал предмет по сокращению — шапка переключилась', (t) async {
    phone(t);
    final sent = <Map>[];
    final api = chatApi([
      {'content': 'Ок.', 'html': 'Ок.', 'subject': 'Моделирование бизнес-процессов'},
      {'content': 'Ещё.', 'html': 'Ещё.'},
    ], sent);
    await t.pumpWidget(host(ChatScreen(api: api)));
    await settle(t);
    await ask(t, 'завтра МБП что будет');
    await ask(t, 'а подробнее?');
    expect(sent.last['subject'], 'Моделирование бизнес-процессов');
  });
}

// Kapi ИИ нового дизайна (шаг 8, макет «Kapi ИИ», Никита 11.11): «С чего
// начать» подставляет начало вопроса в поле, а не отправляет его; остаток
// вопросов и где лежит история — строкой над полем; источники — строками;
// «Скопировать» и «Подумать ещё · N» под ответом. В «Классике» всё прежнее.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/chat.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';

import 'fake_api.dart';
import 'util.dart';

Widget _wrap(Widget child, {bool fresh = true}) => AppStyle(
  p: fresh ? Palette.paper : Palette.notebook,
  font: FontChoice.book,
  design2: true,
  look: Look(fresh: fresh),
  child: MaterialApp(home: child),
);

Map<String, Object?> _fx() => {
  'GET /api/subjects': {
    ...demoFixtures()['GET /api/subjects'] as Map,
    'quota': {'left': 17, 'limit': 20},
    'think': {'label': 'Подумать ещё', 'left': 10, 'daily': 10},
  },
  'POST /api/chat': {
    'content': 'Метрика это любое измеримое число [1]. KPI это метрика с целью [2].',
    'html': '<b>Метрика</b> это любое измеримое число [1]. <b>KPI</b> это метрика с целью [2].',
    'sources': [
      {
        'n': 1,
        'id': 7,
        'title': '!Лекция 4. Метрики и KPI',
        'page': 3,
        'kind': 'слайд',
        'label': 'Лекция 4. Метрики и KPI · слайд 3',
      },
      {
        'n': 2,
        'id': 7,
        'title': '!Лекция 4. Метрики и KPI',
        'page': 5,
        'kind': 'слайд',
        'label': 'Лекция 4. Метрики и KPI · слайды 5–6',
      },
    ],
    'think': {'label': 'Подумать ещё', 'left': 9, 'daily': 10},
  },
};

void main() {
  setUpAll(loadFonts);
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('строка над полем: остаток из лимита и где хранится история', () {
    expect(freshQuotaLine(17, 20), 'Сегодня осталось 17 вопросов из 20. История чатов хранится на этом телефоне.');
    expect(freshQuotaLine(1, 20), startsWith('Сегодня остался 1 вопрос из 20.'));
    expect(freshQuotaLine(3, null), startsWith('Сегодня осталось 3 вопроса.'));
    expect(freshQuotaLine(0, 20), startsWith('На сегодня вопросы кончились'));
    expect(freshQuotaLine(null, null), 'История чатов хранится на этом телефоне.'); // староста без лимита
  });

  test('строка источника: название без «!», место — из подписи сервера', () {
    final src = {'title': '!_Лекция 4', 'page': 5, 'kind': 'слайд', 'label': 'Лекция 4 · слайды 5–6'};
    expect(freshSourceTitle(src), 'Лекция 4');
    expect(freshSourceWhere(src), 'слайды 5–6');
    expect(freshSourceWhere({'title': 'План', 'page': 18, 'kind': 'часть', 'label': 'План'}), isNull);
    expect(freshSourceWhere({'title': 'Лекция 1', 'page': 7}), 'стр. 7'); // старый ответ из истории
    expect(freshSourceWhere({'title': 'Лекция 1'}), isNull); // файл целиком
  });

  testWidgets('начало чата: «С чего начать», остаток над полем, без случайных примеров', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(ChatScreen(api: fakeApi(overrides: _fx()))));
    await settle(t);
    expect(find.text('отвечает по лекциям твоей\u00A0группы'), findsOneWidget);
    expect(find.text('С чего начать'), findsOneWidget);
    expect(find.text('Объяснить лекцию'), findsOneWidget);
    expect(find.text('Разобрать задачу'), findsOneWidget);
    expect(find.text('Что сдать на этой неделе'), findsOneWidget);
    expect(find.text('Чем метрика отличается от KPI?'), findsNothing);
    expect(find.text('Сегодня осталось 17 вопросов из 20. История чатов хранится на этом телефоне.'), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('chat:subject')), matching: find.text('Все предметы')), findsOne);
  });

  testWidgets('«Разобрать задачу» подставляет начало в поле и ничего не отправляет', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(
      _wrap(
        ChatScreen(
          api: fakeApi(requests: asked, overrides: _fx()),
        ),
      ),
    );
    await settle(t);
    await t.tap(find.byKey(const Key('chat:start:1')));
    await settle(t);
    expect(t.widget<TextField>(find.byType(TextField)).controller!.text, 'Разбери задачу: ');
    expect(asked, isNot(contains('POST /api/chat')));
    expect(find.byKey(const Key('chat:quota')), findsOneWidget); // пока не спросил — строка на месте
  });

  testWidgets('«Объяснить лекцию» без предмета — сначала выбрать предмет', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(ChatScreen(api: fakeApi(overrides: _fx()))));
    await settle(t);
    await t.tap(find.byKey(const Key('chat:start:0')));
    await settle(t);
    await t.tap(find.text('Анализ данных'));
    await settle(t);
    expect(t.widget<TextField>(find.byType(TextField)).controller!.text, 'Объясни лекцию ');
    expect(find.descendant(of: find.byKey(const Key('chat:subject')), matching: find.text('Анализ данных')), findsOne);
  });

  testWidgets('ответ: источники строками, «Скопировать» без «[1]», «Подумать ещё · 9»', (t) async {
    phone(t);
    String? copied;
    t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') copied = (call.arguments as Map)['text'] as String?;
      return null;
    });
    addTearDown(() => t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
    await t.pumpWidget(_wrap(ChatScreen(api: fakeApi(overrides: _fx()))));
    await settle(t);
    await t.enterText(find.byType(TextField), 'Чем метрика отличается от KPI?');
    await t.tap(find.byTooltip('Отправить'));
    await settle(t);

    expect(find.byKey(const Key('chat:quota')), findsNothing);
    expect(find.text('С чего начать'), findsNothing);
    final rows = find.byKey(const Key('chat:sources'));
    expect(find.descendant(of: rows, matching: find.text('Лекция 4. Метрики и KPI')), findsNWidgets(2));
    expect(find.descendant(of: rows, matching: find.text('слайд 3')), findsOneWidget);
    expect(find.descendant(of: rows, matching: find.text('слайды 5–6')), findsOneWidget);
    expect(find.text('Подумать ещё · 9'), findsOneWidget);

    await t.tap(find.byKey(const Key('chat:copy')));
    await settle(t);
    expect(copied, 'Метрика это любое измеримое число. KPI это метрика с целью.');
  });

  testWidgets('в «Классике» прежние примеры и счётчик, без «С чего начать»', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(ChatScreen(api: fakeApi(overrides: _fx())), fresh: false));
    await settle(t);
    expect(find.text('С чего начать'), findsNothing);
    expect(find.text('Чем метрика отличается от KPI?'), findsOneWidget);
    expect(find.text('Сегодня можно ещё 17 вопросов'), findsOneWidget);
    expect(find.byKey(const Key('chat:quota')), findsNothing);
  });
}

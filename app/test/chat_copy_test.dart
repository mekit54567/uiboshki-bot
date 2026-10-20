// Копирование в помощнике (Никита, 20.10: «не могу копировать своё сообщение,
// а ответ выделяется по слову и легко сбрасывается»): долгое нажатие — пузырь
// приподнимается, меню «Копировать» (целиком) и «Выбрать текст».
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/chat.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.notebook,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

void main() {
  String? copied;

  setUp(() {
    copied = null;
    SharedPreferences.setMockInitialValues({
      chatsStoreKey: jsonEncode({
        'current': 'c1',
        'chats': [
          {
            'id': 'c1',
            'title': 'Что такое NPV?',
            'updated': DateTime(2026, 10, 12, 10).millisecondsSinceEpoch,
            'subject': '',
            'log': [
              {'role': 'user', 'content': 'Что такое NPV?'},
              {
                'role': 'assistant',
                'content': 'NPV',
                'html': '<b>NPV</b> — чистая приведённая стоимость [1].<br>Считают &lt;по годам&gt;.',
                'sources': [
                  {'n': 1, 'id': 7, 'title': 'Лекция 3', 'page': 4, 'label': 'Лекция 3 · стр. 4'},
                ],
              },
            ],
          },
        ],
      }),
    });
  });

  Future<void> open(WidgetTester t) async {
    phone(t);
    t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') copied = (call.arguments as Map)['text'] as String?;
      return null;
    });
    addTearDown(() => t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
    await t.pumpWidget(host(ChatScreen(api: fakeApi())));
    await settle(t);
  }

  testWidgets('своё сообщение: зажал → «Копировать» копирует целиком', (t) async {
    await open(t);
    await t.longPress(find.text('Что такое NPV?').last);
    await settle(t);
    expect(find.text('Копировать'), findsOneWidget);
    expect(find.text('Выбрать текст'), findsOneWidget);
    await t.tap(find.text('Копировать'));
    await settle(t);
    expect(copied, 'Что такое NPV?');
    expect(find.text('Копировать'), findsNothing);
    expect(find.text('Скопировано'), findsOneWidget);
  });

  testWidgets('ответ помощника: копируется без разметки и без «[1]»', (t) async {
    await open(t);
    await t.longPress(find.textContaining('чистая приведённая').first);
    await settle(t);
    await t.tap(find.text('Копировать'));
    await settle(t);
    expect(copied, 'NPV — чистая приведённая стоимость.\nСчитают <по годам>.');
  });

  testWidgets('«Выбрать текст» — лист с выделяемым текстом, нажатие мимо меню закрывает', (t) async {
    await open(t);
    await t.longPress(find.text('Что такое NPV?').last);
    await settle(t);
    await t.tapAt(const Offset(8, 700));
    await settle(t);
    expect(find.text('Копировать'), findsNothing);

    await t.longPress(find.text('Что такое NPV?').last);
    await settle(t);
    await t.tap(find.text('Выбрать текст'));
    await settle(t);
    expect(find.widgetWithText(SelectableText, 'Что такое NPV?'), findsOneWidget);
  });
}

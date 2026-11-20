import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/chat.dart';
import 'package:uiboshki/screens/files.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/tg_html.dart';

import 'fake_api.dart';
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.notebook,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

String plain(InlineSpan s) => s.toPlainText();

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('разметка Telegram → текст со стилями', () {
    final span = tgHtml(
      '<b>Метрика</b> — число &lt;5&gt;<br>и <i>KPI</i> <a href="https://x.ru">ссылка</a>',
      const TextStyle(fontSize: 15),
    );
    expect(plain(span), 'Метрика — число <5>\nи KPI ссылка');
    final bold = (span.children!.first as TextSpan);
    expect(bold.text, 'Метрика');
    expect(bold.style!.fontWeight, FontWeight.w700);
    final link = span.children!.last as TextSpan;
    expect(link.recognizer, isNotNull);
    expect(plain(tgHtml('без тегов &amp; всё', const TextStyle())), 'без тегов & всё');
  });

  testWidgets('помощник: вопрос → ответ по лекциям и источники', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(host(ChatScreen(api: fakeApi(requests: asked))));
    await settle(t);
    await t.enterText(find.byType(TextField), 'Чем метрика отличается от KPI?');
    await t.tap(find.byTooltip('Отправить'));
    await settle(t);
    expect(asked, contains('POST /api/chat'));
    expect(find.textContaining('все KPI — метрики', findRichText: true), findsOneWidget);
    expect(find.text('Лекция 4. Метрики и KPI · стр. 3'), findsOneWidget);
  });

  testWidgets('файлы: предмет → файл → готовый конспект', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(host(FilesScreen(api: fakeApi(requests: asked))));
    await settle(t);
    await t.tap(find.text('Основы бизнес-анализа в ИТ-сфере'));
    await settle(t);
    expect(find.text('Лекции'), findsOneWidget); // подписи типов без эмодзи
    await t.tap(find.text('Требования и стейкхолдеры')); // тема — строкой под «Лекция 2»
    await settle(t);
    expect(asked, contains('GET /api/summary/2'));
    expect(find.textContaining('Кто такие стейкхолдеры', findRichText: true), findsOneWidget);
    expect(find.text('Скачать'), findsOneWidget);
    expect(find.text('Просмотр'), findsOneWidget); // в Safari — листать там (владелец, 09.10)
    expect(find.text('Прислать в Telegram'), findsOneWidget);
  });

  testWidgets('обе кнопки показывают ошибку, если сервер не прислал ссылку', (t) async {
    phone(t);
    await t.pumpWidget(host(FilesScreen(api: fakeApi())));
    await settle(t);
    await t.tap(find.text('Основы бизнес-анализа в ИТ-сфере'));
    await settle(t);
    await t.tap(find.text('Требования и стейкхолдеры'));
    await settle(t);
    for (final action in ['Скачать', 'Просмотр']) {
      await t.tap(find.text(action));
      await settle(t);
      expect(find.text('Сервер не прислал ссылку на файл.'), findsOneWidget);
      expect(t.takeException(), isNull);
    }
  });
}

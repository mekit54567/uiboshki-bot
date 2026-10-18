// Тема и шрифт, свои плашки и листы вместо системных окон, календарь
// (владелец, 09.10, 3.6, 3.7, 3.10).
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/screens/more.dart';
import 'package:uiboshki/screens/today.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'util.dart';

AppStyle styleOf(WidgetTester t) => AppStyle.of(t.element(find.byType(Scaffold).first));

Future<void> openThemeSheet(WidgetTester t) async {
  await t.tap(find.bySemanticsLabel('Ещё'));
  await settle(t);
  await t.tap(find.text('Тема и шрифт'));
  await settle(t);
}

/// Что копируется в буфер обмена.
List<String> watchClipboard(WidgetTester t) {
  final copied = <String>[];
  t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
    if (call.method == 'Clipboard.setData') copied.add((call.arguments as Map)['text'] as String);
    return null;
  });
  addTearDown(() => t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
  return copied;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  test('в приложении нет системных плашек и окон — только свои', () {
    for (final f in Directory('lib').listSync(recursive: true).whereType<File>()) {
      final code = f.readAsStringSync();
      for (final bad in ['SnackBar(', 'showSnackBar', 'AlertDialog(', 'showDialog<']) {
        expect(code.contains(bad), isFalse, reason: '${f.path}: $bad');
      }
    }
  });

  test('тема из настроек: по умолчанию — как в телефоне', () {
    expect(themeFromPrefs(null), ThemeChoice.system);
    expect(themeFromPrefs('dark'), ThemeChoice.dark);
    expect(themeFromPrefs('light'), ThemeChoice.light);
    expect(themeFromPrefs('мусор'), ThemeChoice.system);
  });

  testWidgets('тема: как в телефоне → тёмная → светлая, запоминается', (t) async {
    phone(t);
    await t.pumpWidget(UiboApp(api: fakeApi()));
    await settle(t);
    expect(styleOf(t).p.dark, isFalse); // телефон в тестах светлый
    await openThemeSheet(t);
    expect(find.text('Как в телефоне'), findsOneWidget);
    await t.tap(find.text('Тёмная'));
    await settle(t);
    expect(styleOf(t).p.dark, isTrue);
    expect(styleOf(t).theme, ThemeChoice.dark);
    expect((await SharedPreferences.getInstance()).getString('uib_theme'), 'dark');
    await t.tap(find.text('Светлая'));
    await settle(t);
    expect(styleOf(t).p.dark, isFalse);
    expect((await SharedPreferences.getInstance()).getString('uib_theme'), 'light');
  });

  testWidgets('сохранённая тёмная тема — сразу при запуске', (t) async {
    phone(t);
    await t.pumpWidget(UiboApp(api: fakeApi(), theme: ThemeChoice.dark));
    await settle(t);
    expect(styleOf(t).p.dark, isTrue);
  });

  // Баг: «Строгий» применялся везде, а «Книжный» обратно — только в «Ещё».
  testWidgets('шрифт туда и обратно — на всех пяти вкладках снова книжный', (t) async {
    phone(t);
    await t.pumpWidget(UiboApp(api: fakeApi()));
    await settle(t);
    final todayBefore = t.state(find.byType(TodayScreen, skipOffstage: false));
    await openThemeSheet(t);
    await t.tap(find.text('Строгий'));
    await settle(t);
    await t.tap(find.text('Книжный'));
    await settle(t);
    await t.tapAt(const Offset(20, 20)); // закрыть лист
    await settle(t);

    for (final tab in ['Сегодня', 'Неделя', 'Сдать', 'Учёба', 'Ещё']) {
      await t.tap(find.bySemanticsLabel(tab));
      await settle(t);
      final big = [
        for (final w in t.widgetList<Text>(find.byType(Text)))
          if ((w.style?.fontSize ?? 0) >= 28) w.style!.fontFamily,
      ];
      expect(big, isNotEmpty, reason: tab);
      expect(big.toSet(), {'SourceSerif'}, reason: tab);
    }
    // скрытая во время смены вкладка построена заново — без старой отрисовки
    expect(t.state(find.byType(TodayScreen, skipOffstage: false)), isNot(same(todayBefore)));
  });

  testWidgets('«Позвать» — своя плашка, не системная', (t) async {
    phone(t);
    final copied = watchClipboard(t);
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(
          overrides: {
            'GET /api/invite': {
              'link': 'https://t.me/UiboshkiBot?start=ref_demo1',
              'share_text': 'Капибара — расписание и дедлайны',
              'share_image': '',
              'tg_share': 'https://t.me/share/url?url=x',
            },
          },
        ),
      ),
    );
    await settle(t);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    // список «Ещё» — до конца: строка не под меню-капсулой
    await t.drag(find.byType(MoreScreen), const Offset(0, -2000));
    await settle(t);
    await t.tap(find.text('Позвать'));
    await settle(t);
    await t.tap(find.byKey(const Key('invite:copy')));
    await settle(t);
    // не голая ссылка — готовое сообщение
    expect(copied.single, 'Капибара — расписание и дедлайны\nhttps://t.me/UiboshkiBot?start=ref_demo1');
    expect(find.byType(SnackBar), findsNothing);
    expect(find.byType(AppToast), findsOneWidget);
    expect(find.text('Скопировано — вставь в чат другу'), findsOneWidget);
    // над меню-капсулой, а не поверх неё
    final toast = t.getRect(find.byKey(const ValueKey('toast')));
    final bar = t.getRect(find.bySemanticsLabel('Сегодня'));
    expect(toast.bottom, lessThan(bar.top));
    await t.pump(const Duration(seconds: 6));
    expect(find.byType(AppToast), findsNothing); // ушла сама
  });

  testWidgets('выйти — лист в дизайне приложения, не системное окно', (t) async {
    phone(t);
    await t.pumpWidget(UiboApp(api: fakeApi()));
    await settle(t);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    // список «Ещё» — до конца: строка не под меню-капсулой
    await t.drag(find.byType(MoreScreen), const Offset(0, -6000));
    await settle(t);
    await t.tap(find.text('Выйти'));
    await settle(t);
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.byType(SheetFrame), findsOneWidget);
    expect(find.text('Выйти?'), findsOneWidget);
    await t.tap(find.text('Остаться'));
    await settle(t);
    expect(find.byType(SheetFrame), findsNothing);
    await t.tap(find.text('Выйти'));
    await settle(t);
    await t.tap(find.text('Выйти').last);
    await settle(t);
    expect(find.text('Войти через Telegram'), findsOneWidget);
  });

  group('календарь', () {
    final calendar = {
      'GET /api/calendar/link': {'token': 'tok', 'ics_path': '/ics/tok'},
    };
    tearDown(() => MoreScreen.openUrl = (u) async => false);

    testWidgets('«Добавить» сразу открывает подписку webcal://', (t) async {
      phone(t);
      final copied = watchClipboard(t);
      final opened = <Uri>[];
      MoreScreen.openUrl = (u) async {
        opened.add(u);
        return true;
      };
      await t.pumpWidget(UiboApp(api: fakeApi(overrides: calendar)));
      await settle(t);
      await t.tap(find.bySemanticsLabel('Ещё'));
      await settle(t);
      await t.tap(find.text('Календарь'));
      await settle(t);
      await t.tap(find.text('Добавить в календарь'));
      await settle(t);
      expect(opened.single.toString(), 'webcal://www.uiboshki.ru/ics/tok');
      expect(copied, isEmpty);
      expect(find.byType(SnackBar), findsNothing);
    });

    testWidgets('не открылось — ссылка копируется, подсказка плашкой', (t) async {
      phone(t);
      final copied = watchClipboard(t);
      MoreScreen.openUrl = (u) async => false;
      await t.pumpWidget(UiboApp(api: fakeApi(overrides: calendar)));
      await settle(t);
      await t.tap(find.bySemanticsLabel('Ещё'));
      await settle(t);
      await t.tap(find.text('Календарь'));
      await settle(t);
      await t.tap(find.text('Добавить в календарь'));
      await settle(t);
      expect(copied.single, 'https://www.uiboshki.ru/ics/tok');
      expect(find.byType(AppToast), findsOneWidget);

      await t.tap(find.text('Календарь'));
      await settle(t);
      await t.tap(find.text('Скопировать ссылку'));
      await settle(t);
      expect(copied.last, 'https://www.uiboshki.ru/ics/tok');
      expect(find.textContaining('Ссылка скопирована'), findsOneWidget);
    });
  });
}

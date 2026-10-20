// Ачивки (Никита 14–15.10): ловятся по ответам API и по касаниям, хранятся
// на телефоне; экран «Ачивки», лист с полароидом, плашка «Новая ачивка»;
// сверхредкая фраза — капибара поворачивается к тебе.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/achievements/captions.dart';
import 'package:uiboshki/achievements/catalog.dart';
import 'package:uiboshki/achievements/store.dart';
import 'package:uiboshki/achievements/ui.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/capy.dart';

import 'flutter_test_config.dart' show NoLuck;
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(
    navigatorKey: appNavigator,
    home: Scaffold(body: child),
  ),
);

/// Случай, которому везёт один раз: первое nextInt — 0.
class OnceLucky implements math.Random {
  bool _used = false;
  @override
  int nextInt(int max) {
    if (_used) return max - 1;
    _used = true;
    return 0;
  }

  @override
  double nextDouble() => 0.5;
  @override
  bool nextBool() => false;
}

final at = DateTime(2026, 10, 15, 12);
Future<void> api(String method, String path, [Object? body, Object? result]) =>
    AchStore.onApi(method, path, body, result, at);

/// Долистать до плитки и показать её целиком (список строится лениво).
Future<void> show(WidgetTester t, String key) async {
  final f = find.byKey(Key(key));
  await t.scrollUntilVisible(f, 300, scrollable: find.byType(Scrollable).first);
  await t.ensureVisible(f);
  await settle(t);
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    AchStore.reset();
  });

  test('каталог: 25 ачивок, id не повторяются, у каждой подпись полароида', () {
    expect(achievements.length, 25);
    expect(achievements.map((a) => a.id).toSet().length, achievements.length);
    for (final a in achievements) {
      expect(polaroidCaptions[a.id], isNotNull, reason: a.id);
      if (a.rank == Rank.dawn) expect(a.place, isNotNull, reason: '${a.id}: у рассветных есть «Показать где»');
    }
    expect([for (final r in Rank.values) r.title], ['Рассвет', 'Полдень', 'Сумерки', 'Полночь']);
  });

  test('ответы API: вошёл в СДО, плюс балл, все работы зачтены', () async {
    Map course(num score, {int passed = 1}) => {'id': 7, 'score': score, 'works_total': 3, 'works_passed': passed};
    await api('GET', '/sdo/grades', null, {
      'courses': [course(30)],
    });
    expect(AchStore.has('sdo'), isTrue);
    expect(AchStore.has('plus'), isFalse); // первый раз — не с чем сравнить
    await api('GET', '/sdo/grades', null, {
      'courses': [course(30)],
    });
    expect(AchStore.has('plus'), isFalse);
    await api('GET', '/sdo/grades', null, {
      'courses': [course(34, passed: 3)],
    });
    expect(AchStore.has('plus'), isTrue);
    expect(AchStore.has('clean'), isTrue);
  });

  test('сдал из приложения: за три дня — «Заранее», три раза не в последний день — «Без паники»', () async {
    await api('GET', '/deadlines', null, {
      'items': [
        {'id': 1, 'due_date': '2026-10-18'},
        {'id': 2, 'due_date': '2026-10-15'},
        {'id': 3, 'due_date': '2026-10-16'},
      ],
    });
    await api('POST', '/sdo/submit', {'deadline_id': 3});
    expect(AchStore.has('submit'), isTrue);
    expect(AchStore.has('early'), isFalse); // за день — ещё не «заранее»
    await api('POST', '/sdo/submit', {'deadline_id': 3});
    await api('POST', '/sdo/submit', {'deadline_id': 2}); // в последний день — серия сначала
    await api('POST', '/sdo/submit', {'deadline_id': 3});
    await api('POST', '/sdo/submit', {'deadline_id': 3});
    expect(AchStore.has('calm'), isFalse);
    await api('POST', '/sdo/submit', {'deadline_id': 1});
    expect(AchStore.has('early'), isTrue);
    expect(AchStore.has('calm'), isTrue);
  });

  test('предмет: автомат набран, четыре лекции подряд, остальное по путям', () async {
    await api('GET', '/sdo/grades/7', null, {
      'goal': {'mode': 'exam', 'status': 'done'},
      'attendance': {
        'lectures': [
          {'status': 'ok'},
          {'status': 'ok'},
          {'status': 'miss'},
          {'status': 'ok'},
          {'status': 'ok'},
          {'status': 'wait'},
          {'status': 'ok'},
        ],
      },
    });
    expect(AchStore.has('auto'), isFalse);
    expect(AchStore.has('streak'), isFalse); // три подряд после пропуска
    await api('GET', '/sdo/grades/7', null, {
      'goal': {'mode': 'auto', 'status': 'done'},
      'attendance': {
        'lectures': [
          for (var i = 0; i < 4; i++) {'status': 'ok'},
        ],
      },
    });
    expect(AchStore.has('auto'), isTrue);
    expect(AchStore.has('streak'), isTrue);

    await api('GET', '/target/1/4928');
    expect(AchStore.has('teacher'), isFalse); // группа, не преподаватель
    await api('GET', '/target/2/77');
    await api('GET', '/files/5/page/12');
    await api('GET', '/summary/5', null, {'summary': null});
    expect(AchStore.has('summary'), isFalse); // конспекта ещё нет
    await api('POST', '/summary/5', null, {'summary': '<b>кратко</b>'});
    await api('POST', '/chat', {'question': 'что такое BPMN'});
    await api('POST', '/sdo/goal/7', {'mode': 'auto'});
    await api('POST', '/notify', {
      'prefs': {'evening': true},
    });
    expect(AchStore.has('remind'), isFalse);
    await api('POST', '/notify', {
      'prefs': {'remind_first': 30},
    });
    for (final id in ['teacher', 'found', 'summary', 'ai', 'goal', 'remind']) {
      expect(AchStore.has(id), isTrue, reason: id);
    }
  });

  test('заходы: неделя с понедельника по пятницу, пятница 13-е, месяц, 22:22', () async {
    for (var d = 12; d <= 15; d++) {
      await AchStore.visit(DateTime(2026, 10, d, 9));
    }
    expect(AchStore.has('week5'), isFalse);
    await AchStore.visit(DateTime(2026, 10, 16, 9)); // пятница
    expect(AchStore.has('week5'), isTrue);
    expect(AchStore.has('fri13'), isFalse);
    await AchStore.visit(DateTime(2026, 11, 13, 9)); // пятница, 13-е
    expect(AchStore.has('fri13'), isTrue);
    for (var d = 1; d <= 24; d++) {
      await AchStore.visit(DateTime(2026, 12, d, 9));
    }
    expect(AchStore.has('month'), isTrue); // 30 разных дней
    await AchStore.capyTouched(DateTime(2026, 10, 15, 22, 21));
    expect(AchStore.has('t2222'), isFalse);
    await AchStore.capyTouched(DateTime(2026, 10, 15, 22, 22));
    expect(AchStore.has('t2222'), isTrue);
  });

  test('открытые ачивки помнятся на телефоне', () async {
    await AchStore.unlock('lesson');
    AchStore.reset();
    await AchStore.load();
    expect(AchStore.has('lesson'), isTrue);
    expect(await AchStore.unlock('lesson'), isFalse); // второй раз — не новая
  });

  testWidgets('сверхредкая фраза: капибара поворачивается, ачивка «Один из нас»', (t) async {
    phone(t);
    capyRandom = OnceLucky();
    addTearDown(() => capyRandom = NoLuck());
    await t.pumpWidget(host(const Center(child: CapyBadge(hour: 14))));
    await t.tap(find.byType(CapyBadge));
    await t.pump(const Duration(milliseconds: 400));
    expect(find.byType(CapyTurn), findsOneWidget);
    await t.pump(const Duration(seconds: 6)); // повернулась и допечатала
    expect(t.widget<CapyOverlay>(find.byType(CapyOverlay)).text, oneOfUsLine);
    expect(AchStore.has('one_of_us'), isTrue);
    await t.tapAt(const Offset(30, 60));
    await settle(t);
  });

  testWidgets('экран: счёт, полночные не выдают секрет, лист открытой — полароид', (t) async {
    phone(t);
    await AchStore.unlock('t2222', at: DateTime(2026, 10, 14, 22, 22));
    achName = 'Аня';
    await t.pumpWidget(host(const AchievementsScreen()));
    await settle(t);
    expect(find.text('1 из 25'), findsOneWidget);

    await show(t, 'ach:secret');
    await settle(t);
    await t.tap(find.byKey(const Key('ach:secret')));
    await settle(t);
    expect(find.text('Секрет. Как получить — не скажу'), findsOneWidget);
    expect(find.byKey(const Key('ach:where')), findsNothing);
    await t.tapAt(const Offset(30, 60));
    await settle(t);

    await show(t, 'ach:t2222');
    await settle(t);
    await t.tap(find.byKey(const Key('ach:t2222')));
    await settle(t);
    expect(find.byType(Polaroid), findsOneWidget);
    expect(find.text(polaroidCaptions['t2222']!), findsOneWidget);
    expect(find.text("'26 10 14 22:22"), findsOneWidget);
    expect(find.text('Аня · 1 из 25'), findsOneWidget);
    expect(find.text('Поделиться'), findsOneWidget);
  });

  testWidgets('новая ачивка — плашка снизу, «Посмотреть» открывает лист; «Показать где» — вкладка', (t) async {
    phone(t);
    achBanners = true;
    addTearDown(() => achBanners = false);
    int? tab;
    AchStore.onUnlock = showUnlockBanner;
    AchStore.openTab = (i) => tab = i;
    await t.pumpWidget(host(const SizedBox()));
    await t.runAsync(() => AchStore.unlock('ai'));
    await t.pump(const Duration(milliseconds: 500));
    expect(find.text('Новая ачивка · Рассвет'), findsOneWidget);
    // снизу, над меню: сверху закрывала «назад» и стрелки недели (робот 16.10)
    final h = t.view.physicalSize.height / t.view.devicePixelRatio;
    expect(t.getRect(find.byKey(const Key('ach:banner'))).top, greaterThan(h / 2));
    await t.tap(find.byKey(const Key('ach:banner')));
    await settle(t);
    expect(find.byType(Polaroid), findsOneWidget);
    await t.tap(find.byKey(const Key('ach:where')));
    await settle(t);
    expect(tab, 3);
    expect(find.text('Нажми «Kapi ИИ»'), findsOneWidget); // подсказка плашкой снизу
    await t.pump(const Duration(seconds: 6));
  });

  test('адрес бота на полароиде — из /api/meta (BOT_USERNAME), без ответа — прежний', () {
    expect(achBot, '@UiboshkiBot');
    setAchBot(null);
    setAchBot('');
    expect(achBot, '@UiboshkiBot');
    setAchBot('https://t.me/KapibaraBot');
    expect(achBot, '@KapibaraBot');
    setAchBot('https://t.me/UiboshkiBot');
  });
}

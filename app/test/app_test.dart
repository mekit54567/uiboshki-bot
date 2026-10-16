import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/screens/login.dart';
import 'package:uiboshki/screens/shell.dart';
import 'package:uiboshki/screens/tour.dart';
import 'package:uiboshki/screens/week.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/capsule_tabbar.dart';
import 'package:uiboshki/widgets/capy.dart';

import 'fake_api.dart';
import 'util.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  testWidgets('вход через VK: окно провайдера → токен из адреса возврата', (t) async {
    phone(t);
    final api = fakeApi(token: null);
    String? opened;
    Future<String> webAuth(String url) async {
      opened = url;
      return 'ru.uiboshki.app://auth#token=tok-123';
    }

    await t.pumpWidget(
      AppStyle(
        p: Palette.depth,
        font: FontChoice.book,
        child: MaterialApp(
          home: LoginScreen(api: api, onDone: () {}, webAuth: webAuth),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Войти через Яндекс ID'), findsOneWidget);
    await t.tap(find.text('Войти через VK ID'));
    await settle(t);
    expect(opened, startsWith('https://id.vk.com/authorize'));
    expect(api.token, 'tok-123');
  });

  testWidgets('вход по коду для проверяющих: кнопка только когда сервер её даёт', (t) async {
    phone(t);
    Future<void> open(Api api) async {
      await t.pumpWidget(
        AppStyle(
          p: Palette.depth,
          font: FontChoice.book,
          child: MaterialApp(
            home: LoginScreen(key: UniqueKey(), api: api, onDone: () {}),
          ),
        ),
      );
      await settle(t);
    }

    await open(fakeApi(token: null));
    expect(find.byKey(const Key('login-code')), findsNothing);

    final bodies = <String, Object?>{};
    final api = fakeApi(
      token: null,
      bodies: bodies,
      overrides: {
        'GET /api/auth/providers': {'items': [], 'code': true},
      },
    );
    await open(api);
    await t.tap(find.byKey(const Key('login-code')));
    await settle(t);
    await t.enterText(find.byType(TextField), ' kapibara-review ');
    await t.tap(find.text('Войти'));
    await settle(t);
    expect(bodies['POST /api/auth/review'], {'code': 'kapibara-review'});
    expect(api.token, 'rv.demo');
  });

  testWidgets('вход через Apple: токен системы → сессия, отмена — без ошибки', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    final api = fakeApi(
      token: null,
      bodies: bodies,
      overrides: {
        'GET /api/auth/providers': {'items': [], 'apple': true},
      },
    );
    String? sentNonce;
    await t.pumpWidget(
      AppStyle(
        p: Palette.depth,
        font: FontChoice.book,
        child: MaterialApp(
          home: LoginScreen(
            api: api,
            onDone: () {},
            appleDevice: true,
            appleAuth: (nonce) async {
              sentNonce = nonce;
              return (idToken: 'jwt', code: 'c-1', name: 'Аня Петрова');
            },
          ),
        ),
      ),
    );
    await settle(t);
    await t.tap(find.byKey(const Key('login-apple')));
    await settle(t);
    final body = bodies['POST /api/auth/apple'] as Map;
    expect(body['id_token'], 'jwt');
    expect(body['nonce'], sentNonce);
    expect(sentNonce!.length, 32);
    expect(api.token, 'apple-tok');
  });

  testWidgets('кнопки Apple нет без ключей на сервере и не на iPhone', (t) async {
    phone(t);
    await t.pumpWidget(
      AppStyle(
        p: Palette.depth,
        font: FontChoice.book,
        child: MaterialApp(
          home: LoginScreen(
            api: fakeApi(
              token: null,
              overrides: {
                'GET /api/auth/providers': {'items': [], 'apple': true},
              },
            ),
            onDone: () {},
            appleDevice: false,
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.byKey(const Key('login-apple')), findsNothing);
  });

  test('вход через бота отдаёт число для проверки в Telegram (как у Google)', () async {
    final r = await fakeApi(token: null).startLogin();
    expect(r.code, 'abc');
    expect(r.pick, 47);
  });

  testWidgets('без токена — экран входа через бота', (t) async {
    await t.pumpWidget(UiboApp(api: fakeApi(token: null)));
    await settle(t);
    expect(find.text('Войти через Telegram'), findsOneWidget);
    expect(find.text('Капибара'), findsOneWidget);
  });

  testWidgets('с токеном — вкладки, капсула переключает экраны', (t) async {
    final asked = <String>[];
    phone(t);
    await t.pumpWidget(UiboApp(api: fakeApi(requests: asked)));
    await settle(t);
    expect(asked, contains('GET /api/today'));
    // выбранная вкладка подписана, остальные — значки
    expect(find.text('Сегодня'), findsWidgets);
    await t.tap(find.bySemanticsLabel('Сдать'));
    await settle(t);
    expect(asked, contains('GET /api/deadlines?include_done=true'));
    expect(find.text('Сдать'), findsWidgets);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    expect(find.text('Аня'), findsOneWidget); // имя из /api/me
    expect(find.text('УИБО-03-24'), findsOneWidget); // группа из профиля, не из настроек
  });

  testWidgets('шрифт переключается и запоминается', (t) async {
    await t.pumpWidget(UiboApp(api: fakeApi()));
    await settle(t);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    await t.tap(find.text('Тема и шрифт')); // шрифт — в листе «Тема и шрифт»
    await settle(t);
    await t.tap(find.text('Строгий'));
    await settle(t);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('uib_font'), 'strict');
  });

  testWidgets('первый запуск — тур по шагам, один раз; повтор — из «Ещё»', (t) async {
    SharedPreferences.setMockInitialValues({});
    phone(t);
    await t.pumpWidget(UiboApp(api: fakeApi()));
    await settle(t);
    expect(find.text('Что где'), findsOneWidget);
    for (final title in ['Листай недели', 'Сдал — смахни вправо', 'Нажми на пару', 'Цель по предмету']) {
      await t.tap(find.text('Дальше'));
      await settle(t);
      expect(find.text(title), findsOneWidget);
    }
    expect(find.text('Пропустить'), findsNothing); // последний шаг
    await t.tap(find.text('Понятно'));
    await settle(t);
    expect(find.byType(TourOverlay), findsNothing);
    expect((await SharedPreferences.getInstance()).getBool('uib_toured'), isTrue);

    // второй запуск — без тура
    await t.pumpWidget(const SizedBox());
    await t.pumpWidget(UiboApp(api: fakeApi()));
    await settle(t);
    expect(find.byType(TourOverlay), findsNothing);

    // «Ещё → Как пользоваться» — тур снова, «Пропустить» закрывает
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    await t.ensureVisible(find.text('Как пользоваться'));
    await t.tap(find.text('Как пользоваться'));
    await settle(t);
    expect(find.text('Что где'), findsOneWidget);
    await t.tap(find.text('Пропустить'));
    await settle(t);
    expect(find.byType(TourOverlay), findsNothing);
  });

  testWidgets('тур открывает вкладку своего шага', (t) async {
    SharedPreferences.setMockInitialValues({});
    phone(t);
    await t.pumpWidget(UiboApp(api: fakeApi()));
    await settle(t);
    int tab() => t.widget<CapsuleTabBar>(find.byType(CapsuleTabBar)).index;
    expect(tab(), 0);
    await t.tap(find.text('Дальше'));
    await settle(t);
    expect(tab(), 1); // свайп недели — на «Неделе»
    await t.tap(find.text('Дальше'));
    await settle(t);
    expect(tab(), 2);
  });

  test('вкладка из ссылки пуша', () {
    expect(tabByName('deadlines'), 2);
    expect(tabByName('sdo'), 3);
    expect(tabByName(null), 0);
  });

  test('капибара по времени суток', () {
    expect(poseAt(8), CapyPose.morning); // часы — как в WebApp
    expect(poseAt(14), CapyPose.day);
    expect(poseAt(20), CapyPose.evening);
    expect(poseAt(2), CapyPose.night);
  });

  test('сроки и числа по-русски', () {
    expect(leftText(const Duration(hours: 13, minutes: 2)), '13 ч 02 мин');
    expect(leftText(const Duration(days: 3)), '3 дня');
    expect(leftText(const Duration(minutes: -1)), 'срок прошёл');
    expect(plural(21, 'день', 'дня', 'дней'), 'день');
    expect(plural(12, 'день', 'дня', 'дней'), 'дней');
    expect(mondayOf(DateTime(2026, 10, 11)), DateTime(2026, 10, 5));
    expect(dayTitle(DateTime(2026, 10, 8)), 'Четверг, 8 октября');
  });

  test('цвет предмета один и тот же', () {
    expect(subjectColor('Анализ данных'), subjectColor('анализ данных'));
  });

  test('пара из ответа API', () {
    final l = Lesson.fromJson({
      'start': '09:00',
      'end': '10:30',
      'title': 'Анализ данных',
      'kind': 'лекция',
      'room': 'А-17 (В-78)',
      'start_iso': '2026-10-08T09:00:00+03:00',
    });
    expect(l.place, 'Лекция · А-17 (В-78)');
    expect(l.startAt, isNotNull);
  });

  testWidgets('неделя: тема телефона — тёмная «Глубина»', (t) async {
    t.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
    addTearDown(t.platformDispatcher.clearPlatformBrightnessTestValue);
    await t.pumpWidget(UiboApp(api: fakeApi()));
    await settle(t);
    final ctx = t.element(find.byType(Scaffold).first);
    expect(AppStyle.of(ctx).p.dark, isTrue);
    await t.tap(find.bySemanticsLabel('Неделя'));
    await settle(t);
    expect(find.text('Неделя'), findsWidgets);
  });
}

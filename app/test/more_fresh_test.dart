// «Ещё» нового дизайна (макет Е3, Никита 11.11): только при «Новом» в
// «Оформлении»; в «Классике» экран прежний (more_header_test.dart).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/api/links.dart';
import 'package:uiboshki/screens/more.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';

import 'fake_api.dart';
import 'util.dart';

Widget _host(Api api, {VoidCallback? onLogout, VoidCallback? onTour, bool fresh = true}) => AppStyle(
  p: fresh ? Palette.paper : Palette.notebook,
  font: FontChoice.book,
  design2: true,
  look: Look(fresh: fresh),
  child: MaterialApp(
    home: Scaffold(
      body: SafeArea(
        child: MoreScreen(api: api, onFont: (_) {}, onLogout: onLogout ?? () {}, onTour: onTour),
      ),
    ),
  ),
);

const _rating = {
  'group': {'id': 4928, 'name': 'УИБО-03-24', 'place': 12, 'place_inst': 3, 'institute': 'ИКБ'},
};

void main() {
  setUpAll(loadFonts);
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  test('курс — по году поступления в названии группы, с сентября', () {
    expect(courseOfGroup('УИБО-03-24', DateTime(2026, 10, 8)), '3 курс');
    expect(courseOfGroup('УИБО-03-24', DateTime(2026, 8, 20)), '2 курс'); // лето — ещё прошлый учебный год
    expect(courseOfGroup('ИКБО-01-25', DateTime(2025, 9, 1)), '1 курс');
    expect(courseOfGroup('ИКБО-01-12', DateTime(2026, 10, 8)), isNull); // 15-й курс — не год поступления
    expect(courseOfGroup('УИБО-03-27', DateTime(2026, 10, 8)), isNull); // ещё не поступили
    expect(courseOfGroup('Моя группа', DateTime(2026, 10, 8)), isNull);
  });

  test('уведомления одной строкой: что включено', () {
    final fx = Map<String, dynamic>.from(demoFixtures()['GET /api/notify'] as Map);
    // в записи стенда выключен только «вечер»
    expect(notifySummary(fx), 'утро, перед парой и ещё 4');
    expect(notifySummary({...fx, 'subscribed': false}), 'выключены');
    Map<String, dynamic> only(Set<String> on) => {
      'subscribed': true,
      'prefs': {
        for (final k in ['morning', 'lessons', 'deadlines', 'grades']) k: on.contains(k),
      },
    };
    expect(notifySummary(only({'morning', 'lessons', 'deadlines', 'grades'})), 'включены все');
    expect(notifySummary(only({'morning', 'deadlines'})), 'утро, дедлайны');
    expect(notifySummary(only({})), 'ничего не включено');
  });

  testWidgets('весь экран: шапка, ачивки и рейтинг наверху, три раздела строками, без баллов БРС', (t) async {
    phone(t);
    await t.pumpWidget(_host(fakeApi(overrides: {'GET /api/rating': _rating})));
    await settle(t);
    expect(find.byKey(const ValueKey('more:fresh')), findsOneWidget);
    expect(find.text('Аня'), findsOneWidget);
    expect(find.textContaining('УИБО-03-24 · '), findsOneWidget);
    expect(find.text('Баллы БРС, в среднем'), findsNothing); // баллы — на «Учёбе»
    expect(find.byKey(const Key('more:points')), findsNothing);

    expect(find.byKey(const Key('more:achievements')), findsOneWidget);
    expect(find.text('Ачивки'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.text('УИБО-03-24 на 3 месте в институте'), findsOneWidget);

    expect(find.text('Сменить мою группу'), findsOneWidget);
    expect(find.text('сейчас УИБО-03-24'), findsOneWidget);
    // своя группа бота — «Я староста» не нужен; предметов по выбору в записи нет — строки нет
    expect(find.text('Я староста этой группы'), findsNothing);
    expect(find.byKey(const Key('more:optional')), findsNothing);
    expect(find.text('Добавить в календарь телефона'), findsOneWidget);

    final list = find.byType(Scrollable).first;
    await t.scrollUntilVisible(find.byKey(const Key('more:logout')), 300, scrollable: list);
    expect(find.text('утро, перед парой и ещё 4'), findsOneWidget);
    expect(find.text('Тетрадь, книжный шрифт'), findsOneWidget);
    expect(find.text('Безопасность и мои данные'), findsOneWidget);
    expect(find.text('позвать друга, новости и связь'), findsOneWidget);
    // в записи стенда «Капибары+» и «Поддержать» нет — без слова «поддержка»
    expect(find.text('как пользоваться и другие устройства'), findsOneWidget);
    expect(find.text('Выйти'), findsOneWidget);
    // приписка для магазинов — в листе «О Капибаре»
    expect(find.text(unofficialNote), findsNothing);
  });

  testWidgets('рейтинг ещё не посчитан — значок и прежняя строка', (t) async {
    phone(t);
    await t.pumpWidget(
      _host(
        fakeApi(
          overrides: {
            'GET /api/rating': {
              'group': {'name': 'УИБО-03-24', 'place': null},
            },
          },
        ),
      ),
    );
    await settle(t);
    expect(find.text('места групп в институте и вузе'), findsOneWidget);
    expect(find.byIcon(Icons.leaderboard_outlined), findsOneWidget);
  });

  testWidgets('«Сообщество» и «О Капибаре» — листы с пунктами', (t) async {
    phone(t);
    var toured = 0;
    await t.pumpWidget(_host(fakeApi(), onTour: () => toured++));
    await settle(t);
    final list = find.byType(Scrollable).first;
    await t.scrollUntilVisible(find.byKey(const Key('more:about')), 300, scrollable: list);

    await t.tap(find.byKey(const Key('more:community')));
    await settle(t);
    expect(find.text('Позвать'), findsOneWidget);
    expect(find.text('Новости и связь'), findsOneWidget);
    expect(find.text('канал Капибары'), findsOneWidget); // «Написать нам» сервер не задал
    await t.tapAt(const Offset(200, 40)); // мимо листа — закрыть
    await settle(t);

    await t.tap(find.byKey(const Key('more:about')));
    await settle(t);
    expect(find.text('Как пользоваться'), findsOneWidget);
    expect(find.text('Капибара в других местах'), findsOneWidget);
    expect(find.text('Капибара+'), findsNothing);
    expect(find.text('Поддержать проект'), findsNothing);
    expect(find.text(unofficialNote), findsOneWidget);
    await t.tap(find.text('Как пользоваться'));
    await settle(t);
    expect(toured, 1);
    expect(find.text(unofficialNote), findsNothing); // лист закрылся
  });

  testWidgets('«О Капибаре»: «Капибара+», «Поддержать» и «Роадмап» — если сервер показывает', (t) async {
    phone(t);
    await t.pumpWidget(
      _host(
        fakeApi(
          overrides: {
            'GET /api/plus': {'hidden': false},
            'GET /api/donate': {'hidden': false},
          },
        ),
      ),
    );
    await settle(t);
    final list = find.byType(Scrollable).first;
    await t.scrollUntilVisible(find.byKey(const Key('more:about')), 300, scrollable: list);
    expect(find.text('как пользоваться, другие устройства, поддержка'), findsOneWidget);
    await t.tap(find.byKey(const Key('more:about')));
    await settle(t);
    expect(find.byKey(const Key('more:plus')), findsOneWidget);
    expect(find.byKey(const Key('more:donate')), findsOneWidget);
    expect(find.byKey(const Key('more:roadmap')), findsOneWidget);
  });

  testWidgets('предметы по выбору: строка с вопросом, лист с «Хожу» и «Не хожу»', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    await t.pumpWidget(
      _host(
        fakeApi(
          bodies: bodies,
          overrides: {
            'GET /api/optional': {
              'pending': ['Военная кафедра'],
              'answers': <String, bool>{},
            },
            'POST /api/optional': {'ok': true},
          },
        ),
      ),
    );
    await settle(t);
    expect(find.text('Военная кафедра: ходишь?'), findsOneWidget);
    await t.tap(find.byKey(const Key('more:optional')));
    await settle(t);
    expect(find.text('Предметы по выбору'), findsNWidgets(2)); // строка под листом и заголовок листа
    await t.tap(find.text('Не хожу'));
    await settle(t);
    expect(bodies['POST /api/optional'], {'subject': 'Военная кафедра', 'attend': false});
    expect(find.text('Не хожу — пары скрыты'), findsOneWidget);
  });

  testWidgets('«Выйти» — переспрашивает листом', (t) async {
    phone(t);
    var out = 0;
    await t.pumpWidget(_host(fakeApi(), onLogout: () => out++));
    await settle(t);
    final list = find.byType(Scrollable).first;
    await t.scrollUntilVisible(find.byKey(const Key('more:logout')), 300, scrollable: list);
    await t.tap(find.byKey(const Key('more:logout')));
    await settle(t);
    expect(find.text('Выйти?'), findsOneWidget);
    await t.tap(find.widgetWithText(FilledButton, 'Выйти'));
    await settle(t);
    expect(out, 1);
  });

  testWidgets('в «Классике» — прежний экран', (t) async {
    phone(t);
    await t.pumpWidget(_host(fakeApi(), fresh: false));
    await settle(t);
    expect(find.byKey(const ValueKey('more:fresh')), findsNothing);
    expect(find.byKey(const Key('more:notify')), findsOneWidget);
    expect(find.text('Баллы БРС, в среднем'), findsOneWidget);
  });
}

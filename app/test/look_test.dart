// «Оформление» (5.79, второй круг дизайна, Никита 12.10): настройки вида в
// одном экране, по умолчанию всё как было, сервер выключает новое одной
// переменной (features.design2).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/screens/look_screen.dart';
import 'package:uiboshki/screens/today.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';
import 'package:uiboshki/widgets/capy.dart';
import 'package:uiboshki/widgets/cheer.dart';

import 'fake_api.dart';
import 'util.dart';

/// Долистать «Оформление» до кнопки (список ленивый).
Future<void> reach(WidgetTester t, String key) async {
  final list = find.descendant(of: find.byType(LookScreen), matching: find.byType(Scrollable)).first;
  await t.scrollUntilVisible(find.byKey(Key(key)), 200, scrollable: list);
  await settle(t);
}

AppStyle styleOf(WidgetTester t) => AppStyle.of(t.element(find.byType(Scaffold).first));

Map<String, Object?> meta(bool on) => {
  'GET /api/meta': {
    'api': 1,
    'server': '5.79.0',
    'min_client': {'web': '0.0.0', 'android': '0.0.0', 'ios': '0.0.0'},
    'login': ['telegram'],
    'features': {'groups': true, 'sessions': true, 'offline': true, 'design2': on},
    'links': {'bot': 'https://t.me/UiboshkiBot'},
  },
};

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  test('по умолчанию — ровно прежний вид', () {
    expect(const Look(), Look.classic);
    expect(Look.classic.light, LightTheme.notebook);
    expect(Look.classic.dark, DarkTheme.depth);
    expect(Look.classic.paper, Paper.smooth);
    expect(Look.classic.card, CardStyle.tint);
    expect(Look.classic.day, DayView.cards);
    expect(Look.classic.cheer, Cheer.quiet);
  });

  test('настройки вида запоминаются, мусор — по умолчанию', () async {
    SharedPreferences.setMockInitialValues({'uib_look_paper': 'мусор'});
    final prefs = await SharedPreferences.getInstance();
    expect(Look.fromPrefs(prefs), Look.classic);
    const l = Look(light: LightTheme.campus, dark: DarkTheme.library, card: CardStyle.stripe, cheer: Cheer.capy);
    await l.save(prefs);
    expect(Look.fromPrefs(prefs), l);
    expect(fontFromPrefs('hand'), FontChoice.hand);
    expect(fontFromPrefs(null), FontChoice.book);
    expect(themeFromPrefs('sunset'), ThemeChoice.sunset);
  });

  test('закат в Москве: осенью около половины шестого, летом после девяти', () {
    int min(DateTime t) => t.hour * 60 + t.minute;
    final oct = moscowSun(DateTime(2026, 10, 12));
    expect(min(oct.rise), inInclusiveRange(6 * 60 + 40, 7 * 60 + 20));
    expect(min(oct.set), inInclusiveRange(17 * 60 + 20, 18 * 60));
    final june = moscowSun(DateTime(2026, 6, 22));
    expect(min(june.rise), inInclusiveRange(3 * 60 + 30, 4 * 60));
    expect(min(june.set), inInclusiveRange(21 * 60, 21 * 60 + 30));
    // днём светлая, после заката тёмная, за час до заката — темнеет понемногу
    expect(sunsetPhase(DateTime(2026, 10, 12, 12)).dark, isFalse);
    expect(sunsetPhase(DateTime(2026, 10, 12, 12)).dusk, 0);
    expect(sunsetPhase(DateTime(2026, 10, 12, 23)).dark, isTrue);
    expect(sunsetPhase(DateTime(2026, 10, 12, 5)).dark, isTrue);
    final before = sunsetPhase(oct.set.subtract(const Duration(minutes: 30)));
    expect(before.dark, isFalse);
    expect(before.dusk, closeTo(0.5, 0.02));
  });

  test('перед закатом темнеют фон и карточки, текст тот же', () {
    final d = Palette.notebook.dusk(1);
    expect(d.bg, isNot(Palette.notebook.bg));
    expect(d.text, Palette.notebook.text);
    expect(Palette.notebook.dusk(0), same(Palette.notebook));
    expect(Palette.depth.dusk(1), same(Palette.depth));
  });

  testWidgets('сервер выключил новый дизайн — всё как раньше, «Тема и шрифт»', (t) async {
    phone(t);
    SharedPreferences.setMockInitialValues({'uib_toured': true, 'uib_design2': true});
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: meta(false)),
        design2: true,
        font: FontChoice.hand,
        theme: ThemeChoice.sunset,
        look: const Look(light: LightTheme.campus, card: CardStyle.stripe),
      ),
    );
    await settle(t);
    final s = styleOf(t);
    expect(s.design2, isFalse);
    expect(s.look, Look.classic);
    expect(s.font, FontChoice.book);
    expect(s.theme, ThemeChoice.system);
    expect(s.p.bg, Palette.notebook.bg);
    expect((await SharedPreferences.getInstance()).getBool('uib_design2'), isFalse);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    expect(find.text('Тема и шрифт'), findsOneWidget);
    expect(find.text('Оформление'), findsNothing);
  });

  testWidgets('«Оформление»: тема, шрифт, бумага — сразу и запоминаются; «Вернуть как было»', (t) async {
    phone(t);
    await t.pumpWidget(UiboApp(api: fakeApi(overrides: meta(true)), design2: true));
    await settle(t);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    await t.tap(find.text('Оформление'));
    await settle(t);
    expect(find.byType(LookScreen), findsOneWidget);
    expect(find.text('Идёт первая пара'), findsOneWidget);
    expect(find.byKey(const Key('look:reset')), findsNothing); // ничего не менял

    await reach(t, 'look:light:campus'); // выше — строка «Новое / Классика» (11.11)
    await t.tap(find.byKey(const Key('look:light:campus')));
    await settle(t);
    expect(styleOf(t).p.bg, Palette.campus.bg);
    // бумага — только у «Тетради»
    expect(find.byKey(const Key('look:paper:cell')), findsNothing);
    await t.tap(find.byKey(const Key('look:light:notebook')));
    await settle(t);
    await reach(t, 'look:paper:cell');
    await t.tap(find.byKey(const Key('look:paper:cell')));
    await settle(t);
    await reach(t, 'look:font:hand');
    await t.tap(find.byKey(const Key('look:font:hand')));
    await settle(t);
    expect(styleOf(t).font, FontChoice.hand);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('uib_look_paper'), 'cell');
    expect(prefs.getString('uib_font'), 'hand');

    await reach(t, 'look:reset');
    await t.tap(find.byKey(const Key('look:reset')));
    await settle(t);
    expect(styleOf(t).look, Look.classic);
    expect(styleOf(t).font, FontChoice.book);
    expect(prefs.getString('uib_look_paper'), 'smooth');
  });

  testWidgets('«строками» — пары дня одной карточкой, «с полоской» — без заливки', (t) async {
    phone(t);
    Future<void> show(Look l) async {
      await t.pumpWidget(
        AppStyle(
          p: Palette.notebook,
          font: FontChoice.book,
          look: l,
          design2: true,
          child: MaterialApp(
            home: Scaffold(body: TodayScreen(api: fakeApi())),
          ),
        ),
      );
      await settle(t);
    }

    await show(const Look(day: DayView.rows));
    expect(find.byType(LessonList), findsOneWidget);
    expect(find.byType(LessonCard), findsNothing);
    await show(const Look(card: CardStyle.stripe));
    expect(find.byType(LessonCard), findsWidgets);
  });

  testWidgets('«сдано» с капибарой: она выпрыгивает и уходит; «тихо» — ничего', (t) async {
    phone(t);
    Future<void> run(Cheer c) async {
      await t.pumpWidget(
        AppStyle(
          p: Palette.notebook,
          font: FontChoice.book,
          look: Look(cheer: c),
          design2: true,
          child: MaterialApp(
            home: Scaffold(
              body: Builder(
                builder: (context) => TextButton(onPressed: () => cheer(context), child: const Text('сдал')),
              ),
            ),
          ),
        ),
      );
      await t.tap(find.text('сдал'));
      await t.pump(const Duration(milliseconds: 400));
    }

    await run(Cheer.capy);
    expect(find.byType(CapyImage), findsOneWidget);
    await t.pump(const Duration(seconds: 2));
    expect(find.byType(CapyImage), findsNothing);
    await run(Cheer.quiet);
    expect(find.byType(CapyImage), findsNothing);
  });
}

// Дизайн по брендбуку v1 (Никита 11.11): «Новое / Классика» в «Оформлении».
// «Новое» — «Тетрадь», «Ночная тетрадь» (запасная «Глубина») и «Книжный»;
// по умолчанию — «Классика»; сервер выключает или включает всем одной
// переменной (features.design3: off / opt / on).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';

import 'fake_api.dart';
import 'util.dart';

AppStyle styleOf(WidgetTester t) => AppStyle.of(t.element(find.byType(Scaffold).first));

Map<String, Object?> meta(String? d3) => {
  'GET /api/meta': {
    'api': 1,
    'server': '5.118.0',
    'min_client': {'web': '0.0.0', 'android': '0.0.0', 'ios': '0.0.0'},
    'login': ['telegram'],
    'features': {'groups': true, 'sessions': true, 'offline': true, 'design2': true, 'design3': ?d3},
    'links': {'bot': 'https://t.me/UiboshkiBot'},
  },
};

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  test('палитры — по брендбуку, выбор запоминается', () async {
    expect(Palette.paper.accent, const Color(0xFFA8452B));
    expect(Palette.paper.muted, const Color(0xFF5F5A50));
    expect(Palette.paper.edge, const Color(0xFF8F8777));
    expect(Palette.night.bg, const Color(0xFF1F1C18));
    expect(Palette.night.onAccent, Palette.night.bg);
    // у прежних тем «край» — та же линия: вид не меняется
    expect(Palette.notebook.edge, Palette.notebook.line);
    const fresh = Look(fresh: true);
    expect(Palette.of(fresh, dark: false), same(Palette.paper));
    expect(Palette.of(fresh, dark: true), same(Palette.night));
    expect(Palette.of(fresh.copyWith(freshDepth: true), dark: true), same(Palette.depth));
    expect(Palette.of(Look.classic, dark: false), same(Palette.notebook));
    final prefs = await SharedPreferences.getInstance();
    expect(Look.fromPrefs(prefs).fresh, isFalse);
    await fresh.copyWith(freshDepth: true).save(prefs);
    expect(Look.fromPrefs(prefs).fresh, isTrue);
    expect(Look.fromPrefs(prefs).freshDepth, isTrue);
  });

  testWidgets('по умолчанию «Классика»; «Новое» — «Тетрадь» и «Книжный», и обратно', (t) async {
    phone(t);
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: meta('opt')),
        design2: true,
        font: FontChoice.strict,
        theme: ThemeChoice.light,
      ),
    );
    await settle(t);
    expect(styleOf(t).fresh, isFalse);
    expect(styleOf(t).p.accent, Palette.notebook.accent);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    await t.tap(find.text('Оформление'));
    await settle(t);
    await t.tap(find.byKey(const Key('look:mode:fresh')));
    await settle(t);
    final s = styleOf(t);
    expect(s.fresh, isTrue);
    expect(s.p.accent, Palette.paper.accent);
    expect(s.font, FontChoice.book);
    expect(find.text('шрифт заголовков'), findsNothing);
    expect((await SharedPreferences.getInstance()).getBool('uib_look_fresh'), isTrue);
    await t.tap(find.byKey(const Key('look:mode:classic')));
    await settle(t);
    expect(styleOf(t).fresh, isFalse);
    expect(styleOf(t).font, FontChoice.strict); // свой шрифт «Классики» не потерян
  });

  testWidgets('сервер выключил (off) — у выбравшего «Новое» снова прежний вид, строки нет', (t) async {
    phone(t);
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: meta('off')),
        design2: true,
        theme: ThemeChoice.light,
        look: const Look(fresh: true),
      ),
    );
    await settle(t);
    expect(styleOf(t).fresh, isFalse);
    expect(styleOf(t).p.accent, Palette.notebook.accent);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    await t.tap(find.text('Оформление'));
    await settle(t);
    expect(find.byKey(const Key('look:mode:fresh')), findsNothing);
  });

  testWidgets('сервер включил всем (on) — новое у тех, кто сам не выбирал', (t) async {
    phone(t);
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: meta('on')),
        design2: true,
        theme: ThemeChoice.dark,
      ),
    );
    await settle(t);
    expect(styleOf(t).fresh, isTrue);
    expect(styleOf(t).p.bg, Palette.night.bg);
  });

  testWidgets('выбрал «Классику» — сервер «on» её не перебивает; старый сервер — как было', (t) async {
    phone(t);
    SharedPreferences.setMockInitialValues({'uib_toured': true, 'uib_look_fresh': false});
    await t.pumpWidget(UiboApp(api: fakeApi(overrides: meta('on')), design2: true));
    await settle(t);
    expect(styleOf(t).fresh, isFalse);
    SharedPreferences.setMockInitialValues({'uib_toured': true});
    await t.pumpWidget(
      UiboApp(
        key: UniqueKey(),
        api: fakeApi(overrides: meta(null)),
        design2: true,
      ),
    );
    await settle(t);
    expect(styleOf(t).fresh, isFalse);
    expect(styleOf(t).design3, 'opt');
  });
}

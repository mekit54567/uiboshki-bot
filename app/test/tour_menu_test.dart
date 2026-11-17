// Меню внизу «С подписями» (шаг 8, макет «Каким сделать меню», Никита 11.11):
// в «Новом» последний шаг тура предлагает «Коротко» или «С подписями» — меню
// внизу меняется сразу, выбор запоминается; поменять можно в «Оформлении».
// По умолчанию «Коротко»; в «Классике» тур и меню прежние.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/screens/look_screen.dart';
import 'package:uiboshki/screens/tour.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';
import 'package:uiboshki/widgets/capsule_tabbar.dart';

import 'fake_api.dart';
import 'util.dart';

/// Сервер с новым дизайном «по выбору» (как в fresh_look_test).
final _meta = {
  'GET /api/meta': {
    'api': 1,
    'server': '5.118.0',
    'min_client': {'web': '0.0.0', 'android': '0.0.0', 'ios': '0.0.0'},
    'login': ['telegram'],
    'features': {'groups': true, 'sessions': true, 'offline': true, 'design2': true, 'design3': 'opt'},
    'links': {'bot': 'https://t.me/UiboshkiBot'},
  },
};

AppStyle styleOf(WidgetTester t) => AppStyle.of(t.element(find.byType(Scaffold).first));

/// Подписи, которые видны в живом меню внизу.
int barLabels(WidgetTester t) => find
    .descendant(
      of: find.byType(CapsuleTabBar),
      matching: find.byWidgetPredicate(
        (w) => w is Text && const ['Сегодня', 'Неделя', 'Сдать', 'Учёба', 'Ещё'].contains(w.data),
      ),
    )
    .evaluate()
    .length;

Future<void> toLastStep(WidgetTester t) async {
  for (var i = 0; i < 5; i++) {
    await t.tap(find.text('Дальше'));
    await settle(t);
  }
}

void main() {
  setUpAll(loadFonts);

  test('подписи в меню запоминаются, по умолчанию — коротко', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    expect(Look.fromPrefs(prefs).tabLabels, isFalse);
    await const Look(fresh: true, tabLabels: true).save(prefs);
    expect(Look.fromPrefs(prefs).tabLabels, isTrue);
    expect(const Look(tabLabels: true) == const Look(), isFalse);
  });

  testWidgets('новый вид: последний шаг тура — «Каким сделать меню», меню меняется сразу', (t) async {
    SharedPreferences.setMockInitialValues({'uib_look_fresh': true});
    phone(t);
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: _meta),
        design2: true,
        look: const Look(fresh: true),
      ),
    );
    await settle(t);
    expect(styleOf(t).fresh, isTrue);
    expect(find.text('Что где'), findsOneWidget);
    expect(barLabels(t), 1); // «Коротко»: подписана только открытая вкладка
    await toLastStep(t);
    expect(find.text('Каким сделать меню'), findsOneWidget);
    expect(find.text('Готово'), findsOneWidget);
    expect(find.text('Поменять можно в любой момент: «Ещё», «Оформление».'), findsOneWidget);
    // два образца — настоящее меню, но нажать в них нечего
    for (final k in ['short', 'labels']) {
      final card = find.byKey(Key('tour:menu:$k'));
      expect(find.descendant(of: card, matching: find.byType(IgnorePointer)), findsWidgets);
    }
    expect(
      find.descendant(of: find.byKey(const Key('tour:menu:labels')), matching: find.text('Учёба')),
      findsOneWidget,
    );

    await t.tap(find.byKey(const Key('tour:menu:labels')));
    await settle(t);
    expect(styleOf(t).look.tabLabels, isTrue);
    expect(barLabels(t), 5);
    expect((await SharedPreferences.getInstance()).getBool('uib_look_tab_labels'), isTrue);

    await t.tap(find.text('Готово'));
    await settle(t);
    expect(find.byType(TourOverlay), findsNothing);
    expect(barLabels(t), 5);
    expect((await SharedPreferences.getInstance()).getBool('uib_toured'), isTrue);
  });

  testWidgets('«Оформление»: «меню внизу» — «С подписями» и обратно «Коротко»', (t) async {
    SharedPreferences.setMockInitialValues({'uib_toured': true, 'uib_look_fresh': true});
    phone(t);
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: _meta),
        design2: true,
        look: const Look(fresh: true),
      ),
    );
    await settle(t);
    await t.tap(find.bySemanticsLabel('Ещё'));
    await settle(t);
    await t.ensureVisible(find.text('Оформление'));
    await settle(t);
    await t.tap(find.text('Оформление'));
    await settle(t);
    final list = find.descendant(of: find.byType(LookScreen), matching: find.byType(Scrollable)).first;
    await t.scrollUntilVisible(find.byKey(const Key('look:tabs:labels')), 200, scrollable: list);
    await settle(t);
    expect(find.text('меню внизу'), findsOneWidget);
    await t.tap(find.byKey(const Key('look:tabs:labels')));
    await settle(t);
    expect(styleOf(t).look.tabLabels, isTrue);
    expect((await SharedPreferences.getInstance()).getBool('uib_look_tab_labels'), isTrue);
    await t.tap(find.byKey(const Key('look:tabs:short')));
    await settle(t);
    expect(styleOf(t).look.tabLabels, isFalse);
  });

  testWidgets('«Классика»: тур из пяти шагов, «меню внизу» нет, подписи не включаются', (t) async {
    SharedPreferences.setMockInitialValues({});
    phone(t);
    // подписи выбраны, пока был «Новый», — «Классика» их не показывает
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: _meta),
        design2: true,
        look: const Look(tabLabels: true),
      ),
    );
    await settle(t);
    expect(styleOf(t).fresh, isFalse);
    expect(barLabels(t), 1);
    for (var i = 0; i < 4; i++) {
      await t.tap(find.text('Дальше'));
      await settle(t);
    }
    expect(find.text('Цель по предмету'), findsOneWidget);
    expect(find.text('Понятно'), findsOneWidget);
    expect(find.text('Каким сделать меню'), findsNothing);
  });
}

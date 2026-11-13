// «Неделя» и поиск нового дизайна (макет «Неделя», Никита 11.11): поиск чужого
// расписания — подписанной кнопкой «Найти расписание», у закреплённой группы —
// «Сравнить с моей», сравнение названо прямо; «Классика» — как была.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/compare.dart';
import 'package:uiboshki/screens/search.dart';
import 'package:uiboshki/screens/week.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';

import 'fake_api.dart';
import 'search_test.dart' show targetFixture;
import 'util.dart';

Widget _wrap(Widget child, {bool fresh = true, bool scaffold = true}) => AppStyle(
  p: fresh ? Palette.paper : Palette.notebook,
  font: FontChoice.book,
  design2: true,
  look: Look(fresh: fresh),
  child: MaterialApp(
    home: scaffold ? Scaffold(body: SafeArea(child: child)) : child,
  ),
);

const _pins = {
  'GET /api/pins': {
    'items': [
      {'type': 1, 'id': 4927, 'title': 'УИБО-02-24'},
      {'type': 2, 'id': 77, 'title': 'Сиганьков А. А.'},
    ],
  },
};

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('подпись недели: сокращается слово и номер, даты — целиком', () {
    expect(WeekLabelText.forms('7 неделя · 12–18 окт'), ['7 неделя · 12–18 окт', '7 нед · 12–18 окт', '12–18 окт']);
    expect(WeekLabelText.forms('28 сен – 4 окт'), ['28 сен – 4 окт']);
  });

  testWidgets('переключатель вида: слово у выбранного; на узком экране даты недели видны целиком', (t) async {
    await loadFonts();
    t.view.physicalSize = const Size(360, 740);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.reset);
    await t.pumpWidget(_wrap(WeekScreen(api: fakeApi(overrides: _pins))));
    await settle(t);
    expect(find.text('Лента'), findsOneWidget);
    expect(find.text('Дни'), findsNothing);
    await t.tap(find.byTooltip('Следующая неделя'));
    await settle(t);
    // появился значок «к сегодня» — места меньше: подпись короче, но даты целиком и не сжаты
    final text = find.descendant(of: find.byType(WeekLabelText), matching: find.byType(Text)).last;
    expect(t.widget<Text>(text).data, matches(RegExp(r'\d (окт|ноя)$')));
    final fitted = find.ancestor(of: text, matching: find.byType(FittedBox)).first;
    expect(t.getSize(text).width, lessThanOrEqualTo(t.getSize(fitted).width + 0.5));
    expect(t.takeException(), isNull);
    await t.tap(find.byTooltip('По дням'));
    await settle(t);
    expect(find.text('Дни'), findsOneWidget);
    expect(find.text('Лента'), findsNothing);
    expect(t.takeException(), isNull);
  });

  testWidgets('неделя: кнопка «Найти расписание» открывает поиск, лупы нет', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(WeekScreen(api: fakeApi(overrides: _pins))));
    await settle(t);
    expect(find.byTooltip('Поиск расписания'), findsNothing);
    await t.tap(find.byKey(const ValueKey('week:find')));
    await settle(t);
    expect(find.byType(SearchScreen), findsOneWidget);
    expect(find.text('Найти расписание'), findsWidgets);
    expect(find.text('Когда мы оба свободны'), findsOneWidget);
  });

  testWidgets('поиск: «Сравнить с моей» у закреплённой группы открывает сравнение', (t) async {
    phone(t);
    final asked = <String>[];
    final api = fakeApi(requests: asked, overrides: {..._pins, 'GET /api/target/1/4927': targetFixture()});
    await t.pumpWidget(_wrap(SearchScreen(api: api), scaffold: false));
    await settle(t);
    expect(find.text('Сравнить с моей'), findsOneWidget); // у преподавателя сравнивать нечего
    await t.tap(find.byKey(const ValueKey('search:cmp:4927')));
    await settle(t);
    expect(asked, contains('GET /api/target/1/4927'));
    expect(find.byType(CompareScreen), findsOneWidget);
  });

  testWidgets('поиск: «Когда мы оба свободны» ставит фильтр «Группы» и курсор в поле', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(
      _wrap(
        SearchScreen(
          api: fakeApi(requests: asked, overrides: _pins),
        ),
        scaffold: false,
      ),
    );
    await settle(t);
    FocusManager.instance.primaryFocus?.unfocus();
    await t.pump();
    await t.tap(find.byKey(const ValueKey('search:both')));
    await t.pump();
    expect(FocusManager.instance.primaryFocus?.context?.findAncestorWidgetOfExactType<TextField>(), isNotNull);
    await t.enterText(find.byType(TextField), 'УИБО');
    await settle(t);
    expect(asked.any((k) => k.startsWith('GET /api/search') && k.endsWith('type=1')), isTrue);
  });

  testWidgets('«Классика»: лупа и прежний поиск', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(WeekScreen(api: fakeApi(overrides: _pins)), fresh: false));
    await settle(t);
    expect(find.byKey(const ValueKey('week:find')), findsNothing);
    await t.tap(find.byTooltip('Поиск расписания'));
    await settle(t);
    expect(find.text('Поиск'), findsOneWidget);
    expect(find.text('Сравнить с моей'), findsNothing);
    expect(find.text('Когда мы оба свободны'), findsNothing);
  });
}

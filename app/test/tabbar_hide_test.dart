// Меню при прокрутке (новый дизайн, Никита 12.10, вариант Г): капсула
// уезжает вниз только в длинном списке, пока листаешь дальше, и возвращается,
// когда листнул назад, сменил вкладку или список короткий. Без design2 —
// никогда не прячется.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/screens/week.dart';
import 'package:uiboshki/widgets/capsule_tabbar.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'util.dart';

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

String _d(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

/// Неделя стенда (5–11 октября) переезжает на текущую; [short] — без пар.
Map<String, Object?> week({bool short = false}) {
  final fx = demoFixtures();
  final monday = mondayOf(now());
  Object? move(Object? v) {
    var s = jsonEncode(v);
    for (var i = 0; i < 7; i++) {
      s = s.replaceAll(_d(DateTime(2026, 10, 5 + i)), _d(monday.add(Duration(days: i))));
    }
    return jsonDecode(s);
  }

  return {
    'GET /api/week?start=${_d(monday)}': short ? {'week': 6, 'days': []} : move(fx['GET /api/week?start=2026-10-05']),
    for (var i = 0; i < 7; i++)
      'GET /api/day?date=${_d(monday.add(Duration(days: i)))}': short
          ? {'lessons': []}
          : move(fx['GET /api/day?date=${_d(DateTime(2026, 10, 5 + i))}']),
  };
}

/// Верх капсулы на экране; за нижним краем — спрятана.
double barTop(WidgetTester t) =>
    t.getRect(find.descendant(of: find.byType(CapsuleTabBar), matching: find.byType(ClipRRect)).first).top;

bool hidden(WidgetTester t) => barTop(t) >= t.view.physicalSize.height / t.view.devicePixelRatio;

Finder weekList() => find.descendant(of: find.byType(WeekScreen), matching: find.byType(CustomScrollView));

Future<void> openWeek(WidgetTester t, {required bool design2, bool short = false}) async {
  phone(t);
  await t.pumpWidget(
    UiboApp(
      api: fakeApi(
        overrides: {
          ...meta(design2),
          ...week(short: short),
        },
      ),
      design2: design2,
    ),
  );
  await settle(t);
  await t.tap(find.bySemanticsLabel('Неделя'));
  await settle(t);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  testWidgets('длинная неделя: листаешь дальше — меню уезжает, назад — возвращается', (t) async {
    await openWeek(t, design2: true);
    final pos = t.state<ScrollableState>(find.descendant(of: weekList(), matching: find.byType(Scrollable))).position;
    expect(
      pos.maxScrollExtent - pos.minScrollExtent,
      greaterThan(1.5 * pos.viewportDimension),
      reason: 'неделя длинная',
    );
    // неделя открывается на сегодня, а в субботу до конца списка рукой подать
    // (17.10 тест упал в субботу) — листаем с понедельника
    pos.jumpTo(pos.minScrollExtent);
    await settle(t);
    expect(hidden(t), isFalse);

    await t.drag(weekList(), const Offset(0, -200));
    await settle(t);
    expect(hidden(t), isTrue);

    await t.drag(weekList(), const Offset(0, 60));
    await settle(t);
    expect(hidden(t), isFalse);

    // снова спрятали — у конца списка меню возвращается
    await t.drag(weekList(), const Offset(0, -200));
    await settle(t);
    expect(hidden(t), isTrue);
    await t.drag(weekList(), const Offset(0, -5000));
    await settle(t);
    expect(pos.pixels, closeTo(pos.maxScrollExtent, 1));
    expect(hidden(t), isFalse);
  });

  testWidgets('прыжок списка из кода меню не прячет', (t) async {
    await openWeek(t, design2: true);
    final pos = t.state<ScrollableState>(find.descendant(of: weekList(), matching: find.byType(Scrollable))).position;
    pos.jumpTo(pos.pixels + 300);
    await settle(t);
    expect(hidden(t), isFalse);
  });

  testWidgets('короткий экран: меню не прячется', (t) async {
    await openWeek(t, design2: true, short: true);
    await t.drag(weekList(), const Offset(0, -300));
    await settle(t);
    expect(hidden(t), isFalse);
  });

  testWidgets('без нового дизайна меню не прячется', (t) async {
    await openWeek(t, design2: false);
    await t.drag(weekList(), const Offset(0, -200));
    await settle(t);
    expect(hidden(t), isFalse);
  });
}

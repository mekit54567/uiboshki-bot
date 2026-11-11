// Дизайн по выбору владельца (09.10): кабинет плашкой (12А), без подписей над
// заголовком и итог «Безопасности» карточкой (14А), цветной формат файла
// (16А), капибара радуется, грустит и выглядывает (17Б, 17Г), названия без
// засечек (18Б), «Неделя» открывается на сегодня (19Б).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/files.dart';
import 'package:uiboshki/screens/security.dart';
import 'package:uiboshki/screens/today.dart';
import 'package:uiboshki/screens/week.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/capy.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'util.dart';

Widget _wrap(Widget child, {Palette p = Palette.depth}) => AppStyle(
  p: p,
  font: FontChoice.book,
  child: MaterialApp(home: Scaffold(body: child)),
);

const _lesson = Lesson(
  start: '14:20',
  end: '15:50',
  title: 'Объектно-ориентированный анализ и программирование',
  kind: 'практика',
  room: 'А-332 (МП-1)',
  teacher: 'Зорина Н. В.',
  status: '',
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('кабинет: корпус — в скобках (2.2), общий корпус один раз', () {
    expect(roomText('А-332 (МП-1)'), 'А-332 (МП-1)');
    expect(roomText('А-332(МП-1)'), 'А-332 (МП-1)');
    expect(roomText('А-332 (МП-1), Б-304 (МП-1)'), 'А-332, Б-304 (МП-1)');
    expect(roomText('А-332 (МП-1), Г-212 (В-78)'), 'А-332 (МП-1), Г-212 (В-78)');
    expect(roomText('СДО'), 'СДО');
  });

  testWidgets('пара: кабинет плашкой, тип серым рядом, название без засечек', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(LessonList(lessons: const [_lesson], at: DateTime(2026, 10, 9, 12))));
    expect(find.text('А-332 (МП-1)'), findsOneWidget);
    expect(find.text('практика'), findsOneWidget);
    expect(find.byType(RoomPill), findsOneWidget);
    final title = t.widget<Text>(find.text(_lesson.title));
    expect(title.style?.fontFamily, 'Onest'); // шрифт «Книжный», а название — без засечек
    expect(title.style?.fontWeight, FontWeight.w700);
  });

  testWidgets('заголовок экрана без подписи над ним; «Безопасность» — итог карточкой', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(const ScreenTitle(title: 'Уведомления')));
    expect(find.byType(Text), findsOneWidget);

    await t.pumpWidget(_wrap(SecurityScreen(api: fakeApi(), onLogout: () {})));
    await settle(t);
    expect(find.text('Как защищены твои данные'), findsOneWidget);
    expect(find.textContaining('что бот знает'), findsNothing);
  });

  testWidgets('файл: формат цветным значком, конспект — зелёным', (t) async {
    phone(t);
    final p = Palette.depth;
    expect(formatColor('PDF', p), p.danger);
    expect(formatColor('DOCX', p), isNot(formatColor('PPTX', p)));
    expect(formatColor('XLSX', p), p.ok);
    await t.pumpWidget(
      _wrap(
        const Row(
          children: [
            FormatBadge(ext: 'PDF'),
            FormatBadge(ext: '', category: 'lecture'),
          ],
        ),
      ),
    );
    expect(t.widget<Text>(find.text('PDF')).style?.color, p.danger);
    expect(find.byIcon(Icons.menu_book_outlined), findsOneWidget);
  });

  testWidgets('капибара: в пустом экране выглядывает, нажал — повернулась; ночью — «z»', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(const Notice(title: 'Пар нет', text: 'отдыхай', pose: CapyPose.joy)));
    await settle(t);
    expect(find.byType(CapyPeek), findsOneWidget);
    Matrix4 turn() => t
        .widget<Transform>(find.descendant(of: find.byType(CapyPeek), matching: find.byType(Transform)).last)
        .transform;
    expect(turn().storage[0], closeTo(1, 1e-6));
    await t.tap(find.byType(CapyPeek));
    await settle(t);
    expect(turn().storage[0], closeTo(-1, 1e-6)); // развернулась спиной

    await t.pumpWidget(_wrap(const CapyPeek(size: 84, hour: 2)));
    await t.pump(const Duration(milliseconds: 600));
    expect(find.text('z'), findsWidgets);
    await t.pumpWidget(_wrap(const CapyPeek(size: 84, hour: 13)));
    await t.pump(const Duration(milliseconds: 600));
    expect(find.text('z'), findsNothing);

    // не загрузилось — грустная капибара слева, не выглядывает
    await t.pumpWidget(_wrap(const Notice(title: 'Не загрузилось', text: '…', pose: CapyPose.sad)));
    expect(find.byType(CapyPeek), findsNothing);
  });

  testWidgets('капибара: «Сдано» — прыгает', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(const Center(child: CapyHop(size: 104))));
    double y() => t.getTopLeft(find.byType(CapyImage)).dy;
    final rest = y();
    await t.pump(const Duration(milliseconds: 320));
    expect(y(), lessThan(rest - 10)); // в прыжке
    await t.pump(const Duration(milliseconds: 900));
    expect(y(), closeTo(rest, 0.5)); // приземлилась
  });

  testWidgets('неделя открывается на сегодняшнем дне, прошедшие — выше', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(SafeArea(child: WeekScreen(api: fakeApi()))));
    await settle(t);
    final list = t.getRect(find.byType(CustomScrollView));
    final today = t.getTopLeft(find.textContaining('· сегодня'));
    expect(today.dy - list.top, lessThan(40));
    final monday = mondayOf(now());
    if (now().weekday > 1) {
      // понедельник построен, но выше экрана — до него долистать
      final mon = find.textContaining('${monday.day} ${monthsGen[monday.month - 1]}', skipOffstage: false);
      expect(mon, findsOneWidget);
      expect(t.getTopLeft(mon).dy, lessThan(list.top));
    }
  });
}

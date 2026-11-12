// «Сдать» нового дизайна (макет Д1, Никита 11.11): выбор «По срокам / По
// предметам», полки чипами, горящее с двумя кнопками; «Классика» — как была.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/deadlines.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';

final _at = DateTime(2026, 10, 8, 10, 7);

Deadline _d(int id, String subject, DateTime due, {String time = '23:59', bool done = false, bool submit = false}) =>
    Deadline(id: id, subject: subject, dueDate: iso(due), dueTime: time, done: done, canSubmit: submit);

final _items = [
  _d(1, 'Лабораторная работа 3 · ООАиП', DateTime(2026, 10, 8), submit: true),
  _d(2, 'Курсовая: глава 1 · Бизнес-анализ', DateTime(2026, 10, 14), time: ''),
  _d(3, 'Практика 2 · Анализ данных', DateTime(2026, 10, 2)),
  _d(4, 'Практика 1 · Анализ данных', DateTime(2026, 9, 25), done: true),
];

Widget _wrap({bool fresh = true, List<String>? log}) => AppStyle(
  p: fresh ? Palette.paper : Palette.notebook,
  font: FontChoice.book,
  design2: true,
  look: Look(fresh: fresh),
  child: MaterialApp(
    home: Scaffold(
      body: SafeArea(
        child: DeadlinesView(
          items: _items,
          extra: const {},
          api: Api(),
          at: _at,
          onToggle: (d, done) async => log?.add('toggle ${d.id} $done'),
          onSubmit: (d) => log?.add('submit ${d.id}'),
          onOpen: (d) => log?.add('open ${d.id}'),
          onAdd: () {},
        ),
      ),
    ),
  ),
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('по срокам: полки со счётчиками, горящее с «Сдать в СДО» и «Отметить»', (t) async {
    final log = <String>[];
    await t.pumpWidget(_wrap(log: log));
    await t.pump();
    expect(find.byKey(const ValueKey('due:fresh')), findsOneWidget);
    expect(find.text('Активные · 2'), findsOneWidget);
    expect(find.text('Просрочено · 1'), findsOneWidget);
    expect(find.text('Готово · 1'), findsOneWidget);
    expect(find.byKey(const ValueKey('due:hot:1')), findsOneWidget);
    expect(find.text('сегодня до 23:59'), findsOneWidget);
    expect(find.text('Дальше'), findsOneWidget);
    expect(find.text('Курсовая: глава 1'), findsOneWidget);
    expect(find.text('Практика 2'), findsNothing); // просроченное — на своей полке
    await t.tap(find.text('Сдать в СДО'));
    await t.tap(find.text('Отметить'));
    expect(log, ['submit 1', 'toggle 1 true']);

    await t.tap(find.byKey(const ValueKey('due:shelf:1')));
    await t.pump();
    expect(find.text('Практика 2'), findsOneWidget);
    expect(find.byKey(const ValueKey('due:hot:1')), findsNothing);
    await t.tap(find.byKey(const ValueKey('due:shelf:2')));
    await t.pump();
    expect(find.text('Практика 1'), findsOneWidget);
  });

  testWidgets('по предметам: статус у каждой работы, ближайший срок выше, вид запоминается', (t) async {
    final log = <String>[];
    await t.pumpWidget(_wrap(log: log));
    await t.pump();
    await t.tap(find.text('По предметам'));
    await t.pumpAndSettle();
    expect(find.text('Активные · 2'), findsNothing);
    expect(find.text('1 сегодня'), findsOneWidget);
    expect(find.text('до 23:59 · ещё не сдано'), findsOneWidget);
    expect(find.text('ср 14 октября · время не указано'), findsOneWidget);
    expect(find.text('1 просрочена'), findsOneWidget);
    expect(find.text('срок был 2 октября'), findsOneWidget);
    expect(find.text('сдано · 1'), findsOneWidget);
    final y = [
      for (final k in ['ООАиП', 'Бизнес-анализ', 'Анализ данных']) t.getTopLeft(find.byKey(ValueKey('due:subj:$k'))).dy,
    ];
    expect(y[0] < y[1] && y[1] < y[2], isTrue);
    await t.tap(find.widgetWithText(FilledButton, 'Сдать'));
    await t.tap(find.text('Практика 2'));
    expect(log, ['submit 1', 'open 3']);
    expect((await SharedPreferences.getInstance()).getString('uib_due_view'), 'subject');

    // открыли заново — тот же вид
    await t.pumpWidget(const SizedBox());
    await t.pumpWidget(_wrap());
    await t.pumpAndSettle();
    expect(find.text('1 сегодня'), findsOneWidget);
  });

  testWidgets('«Классика» — прежний экран: «Впереди / Сдано», без полок', (t) async {
    await t.pumpWidget(_wrap(fresh: false));
    await t.pump();
    expect(find.byKey(const ValueKey('due:fresh')), findsNothing);
    expect(find.text('Впереди · 2'), findsOneWidget);
    expect(find.text('По предметам'), findsNothing);
  });
}

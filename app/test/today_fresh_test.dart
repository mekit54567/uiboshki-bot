// «Сегодня» и экран пары нового дизайна (макеты С1 и П1, Никита 11.11):
// только при «Новом» в «Оформлении»; в «Классике» экран прежний.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/chat.dart';
import 'package:uiboshki/screens/lesson.dart';
import 'package:uiboshki/screens/today.dart';
import 'package:uiboshki/screens/week.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';
import 'package:uiboshki/widgets/common.dart';
import 'package:uiboshki/widgets/lesson_comments.dart';
import 'package:uiboshki/widgets/lesson_reactions.dart';

import 'fake_api.dart';
import 'util.dart';

String _hm(DateTime d) => '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

Map<String, Object?> _lesson(DateTime start, Object num, String title, String room, {String teacher = ''}) {
  final end = start.add(const Duration(minutes: 90));
  return {
    'num': num,
    'start': _hm(start),
    'end': _hm(end),
    'title': title,
    'kind': 'лекция',
    'room': room,
    'teacher': teacher,
    'groups': '',
    'status': '',
    'start_iso': start.toIso8601String(),
    'end_iso': end.toIso8601String(),
  };
}

Map<String, Object?> _answers(
  List<Map<String, Object?>> lessons, {
  List<Map<String, Object?>> soon = const [],
  List<Map<String, Object?>> tomorrow = const [],
}) => {
  'GET /api/today': {
    'lessons': lessons,
    'tomorrow_first': tomorrow.isEmpty ? null : tomorrow.first,
    'weather': '',
    'deadlines': {'active': soon.length, 'soon': soon},
  },
  'GET /api/me': {
    'id': 1,
    'first_name': 'Аня',
    'group': {'id': 4928, 'name': 'УИБО-03-24', 'own': true},
  },
  'GET /api/week?start=${iso(mondayOf(now()))}': {'week': 6, 'days': []},
  'GET /api/day?date=${iso(now().add(const Duration(days: 1)))}': {'lessons': tomorrow},
};

Widget _wrap(Widget child, {bool fresh = true}) => AppStyle(
  p: fresh ? Palette.paper : Palette.notebook,
  font: FontChoice.book,
  design2: true,
  look: Look(fresh: fresh),
  child: MaterialApp(
    home: Scaffold(body: SafeArea(child: child)),
  ),
);

Map<String, Object?> _due(int id, String subject, DateTime at, {bool submit = false}) => {
  'id': id,
  'subject': subject,
  'due_date': iso(at),
  'due_time': _hm(at),
  'days': 0,
  'can_submit': submit,
};

void main() {
  setUpAll(loadFonts);
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('идёт пара: карточка пары с «дальше», «Важно сегодня» с кнопкой, остальные строками', (t) async {
    phone(t);
    final n = now();
    final first = _lesson(
      n.subtract(const Duration(minutes: 60)),
      1,
      'Моделирование',
      'А-17 (В-78)',
      teacher: 'Сиганьков А. А.',
    );
    final second = _lesson(n.add(const Duration(minutes: 40)), 2, 'Анализ данных', 'А-17 (В-78)');
    final third = _lesson(n.add(const Duration(minutes: 140)), 3, 'Архитектура', 'А-223 (В-78)');
    var opened = 0;
    await t.pumpWidget(
      _wrap(
        TodayScreen(
          api: fakeApi(
            overrides: _answers(
              [first, second, third],
              soon: [
                _due(7, 'Лабораторная работа 3', n.add(const Duration(hours: 5)), submit: true),
                _due(8, 'Курсовая: глава 1', n.add(const Duration(days: 4))),
              ],
            ),
          ),
          onDeadlines: () => opened++,
        ),
      ),
    );
    await settle(t);
    expect(find.byKey(const ValueKey('today:fresh')), findsOneWidget);
    expect(find.text('Идёт первая пара'), findsOneWidget);
    expect(find.text('до конца'), findsOneWidget);
    final card = find.byKey(const Key('today:now'));
    expect(find.descendant(of: card, matching: find.text('Моделирование')), findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('лекция · Сиганьков А. А.')), findsOneWidget);
    expect(find.text('Дальше в ${second['start']} тот же кабинет, никуда не идти'), findsOneWidget);
    // срок ближайших суток — наверху, с кнопкой; дальний — тихим списком
    expect(find.text('важно сегодня'), findsOneWidget);
    expect(find.byKey(const Key('today:hot:7')), findsOneWidget);
    expect(find.byKey(const Key('today:hot:8')), findsNothing);
    expect(find.text('Курсовая: глава 1'), findsOneWidget);
    await t.tap(find.text('Сдать'));
    expect(opened, 1);
    // идущая пара в списке не повторяется
    expect(find.text('ещё сегодня · 2 пары'), findsOneWidget);
    expect(find.text('Моделирование'), findsOneWidget);
    expect(find.byKey(const Key('today:past')), findsNothing);
  });

  testWidgets('пары кончились: цифра до срока, завтра раскрыто, прошедшее свёрнуто', (t) async {
    phone(t);
    final n = now();
    final done = _lesson(n.subtract(const Duration(hours: 3)), 1, 'Моделирование', 'А-17');
    final tomorrow = _lesson(n.add(const Duration(hours: 20)), 1, 'Анализ данных', 'А-17');
    await t.pumpWidget(
      _wrap(
        TodayScreen(
          api: fakeApi(
            overrides: _answers(
              [done],
              soon: [_due(7, 'Лабораторная работа 3', n.add(const Duration(hours: 3)))],
              tomorrow: [tomorrow],
            ),
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Пары закончились'), findsOneWidget);
    expect(find.text('до срока'), findsOneWidget);
    expect(find.text('завтра · 1 пара'), findsOneWidget);
    expect(find.text('Анализ данных'), findsOneWidget);
    expect(find.text('Моделирование'), findsNothing);
    await t.scrollUntilVisible(find.byKey(const Key('today:past')), 200, scrollable: find.byType(Scrollable).first);
    await t.tap(find.byKey(const Key('today:past')));
    await settle(t);
    expect(find.text('Моделирование'), findsOneWidget);
  });

  testWidgets('«Классика» — прежний экран', (t) async {
    phone(t);
    final n = now();
    await t.pumpWidget(
      _wrap(
        TodayScreen(
          api: fakeApi(
            overrides: _answers([_lesson(n.subtract(const Duration(minutes: 30)), 1, 'Моделирование', 'А-17')]),
          ),
        ),
        fresh: false,
      ),
    );
    await settle(t);
    expect(find.byKey(const ValueKey('today:main')), findsOneWidget);
    expect(find.byKey(const Key('today:now')), findsNothing);
  });

  testWidgets('экран пары: статус справа, «По предмету» выше обсуждения, «Спросить Kapi» открывает чат', (t) async {
    phone(t);
    final n = now();
    final l = Lesson.fromJson(
      Map<String, dynamic>.from(
        _lesson(n.subtract(const Duration(minutes: 30)), 1, 'Анализ данных', 'А-17 (В-78)', teacher: 'Иванова А. С.'),
      ),
    );
    await t.pumpWidget(_wrap(LessonScreen(api: fakeApi(), lesson: l)));
    await settle(t);
    expect(find.byKey(const Key('lesson:status')), findsOneWidget);
    expect(find.textContaining('идёт · ещё'), findsOneWidget);
    expect(find.textContaining('лекция · '), findsOneWidget);
    final list = find.byType(Scrollable).first;
    await t.scrollUntilVisible(find.byKey(const Key('lesson:ask')), 200, scrollable: list);
    final ask = t.getTopLeft(find.byKey(const Key('lesson:ask'))).dy;
    // обсуждение и реакции — ниже материалов (если уже построены ленивым списком)
    for (final f in [find.byType(LessonComments), find.byType(LessonReactions)]) {
      if (f.evaluate().isNotEmpty) expect(t.getTopLeft(f).dy, greaterThan(ask));
    }
    await t.tap(find.byKey(const Key('lesson:ask')));
    await settle(t);
    expect(find.byType(ChatScreen), findsOneWidget);
    expect(t.widget<ChatScreen>(find.byType(ChatScreen)).subject, 'Анализ данных');
  });

  testWidgets('экран пары в «Классике»: без кнопки Kapi и плашки статуса', (t) async {
    phone(t);
    final n = now();
    final l = Lesson.fromJson(
      Map<String, dynamic>.from(_lesson(n.subtract(const Duration(minutes: 30)), 1, 'Анализ данных', 'А-17')),
    );
    await t.pumpWidget(_wrap(LessonScreen(api: fakeApi(), lesson: l), fresh: false));
    await settle(t);
    expect(find.byKey(const Key('lesson:status')), findsNothing);
    expect(find.byKey(const Key('lesson:ask')), findsNothing);
  });
}

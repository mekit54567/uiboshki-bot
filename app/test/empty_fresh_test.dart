// Пустые экраны и сбой нового вида (шаг 8, макет «Пустые экраны и сбои»,
// Никита 11.11): капибара крупно по центру и что дальше. Пар нет — когда
// ближайшая пара и «но кое-что ждёт»; сайт расписания молчит — плашка сверху
// и сохранённое расписание под ней; «Сдать» без активных — «Активных сроков
// нет», про просроченное и «Проверить обновления». «Классика» не меняется.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/deadlines.dart';
import 'package:uiboshki/screens/today.dart';
import 'package:uiboshki/screens/week.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';
import 'package:uiboshki/widgets/capy.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'util.dart';

Widget _wrap(Widget child, {bool fresh = true}) => AppStyle(
  p: fresh ? Palette.paper : Palette.notebook,
  font: FontChoice.book,
  design2: true,
  look: Look(fresh: fresh),
  child: MaterialApp(
    home: Scaffold(body: SafeArea(child: child)),
  ),
);

String _hm(DateTime d) => '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

const _in = ['в понедельник', 'во вторник', 'в среду', 'в четверг', 'в пятницу', 'в субботу', 'в воскресенье'];

/// Тексты с неразрывными пробелами — сравниваем с обычными.
String _plain(String s) => s.replaceAll('\u00A0', ' ');

Lesson _l(String start) =>
    Lesson.fromJson({'start': start, 'end': '12:10', 'title': 'Анализ данных', 'kind': 'лекция'});

/// Сегодня и завтра пар нет, ближайшие — через три дня в 10:40.
Map<String, Object?> _freeDay({List<Map<String, Object?>> soon = const [], Object? stale, bool ok = true}) {
  final later = now().add(const Duration(days: 3));
  return {
    'GET /api/today': {
      'lessons': [],
      'tomorrow_first': null,
      'weather': '',
      'schedule_ok': ok,
      'stale': stale,
      'deadlines': {'active': soon.length, 'soon': soon},
    },
    'GET /api/me': {
      'id': 1,
      'first_name': 'Аня',
      'group': {'id': 4928, 'name': 'УИБО-03-24', 'own': true},
    },
    'GET /api/week?start=${iso(mondayOf(now()))}': {
      'week': 6,
      'days': [
        {
          'date': iso(later),
          'dots': ['лекция'],
        },
      ],
    },
    'GET /api/day?date=${iso(now().add(const Duration(days: 1)))}': {'lessons': []},
    'GET /api/day?date=${iso(later)}': {
      'lessons': [
        {'start': '10:40', 'end': '12:10', 'title': 'Анализ данных', 'kind': 'лекция'},
      ],
    },
  };
}

Map<String, Object?> _soonDue(DateTime at) => {
  'id': 7,
  'subject': 'Курсовая: глава 1 · Бизнес-анализ',
  'due_date': iso(at),
  'due_time': _hm(at),
  'days': 0,
  'can_submit': true,
};

bool _capy(CapyPose pose) => find.byWidgetPredicate((w) => w is CapyImage && w.pose == pose).evaluate().isNotEmpty;

void main() {
  setUpAll(loadFonts);
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('свободный день: завтрашняя пара, ближайшая через несколько дней, дальше недели — датой', () {
    final at = DateTime(2026, 10, 9, 13, 5); // пятница
    expect(_plain(freeDayText(at, _l('10:40'), null)), 'Завтра первая пара в 10:40.');
    expect(freeDayText(at, null, null), 'Завтра тоже свободно.');
    expect(
      _plain(freeDayText(at, null, (day: DateTime(2026, 10, 13), start: '10:40'))),
      'Завтра тоже свободно. Ближайшая пара во вторник в 10:40.',
    );
    expect(
      _plain(freeDayText(at, null, (day: DateTime(2026, 10, 19), start: '09:00'))),
      'Завтра тоже свободно. Ближайшая пара 19 октября в 09:00.',
    );
  });

  test('плашка сбоя: метка сервера словами', () {
    expect(
      _plain(savedScheduleText('07:30')),
      'Показываю расписание, сохранённое сегодня в 07:30. Попробую снова через минуту.',
    );
    expect(_plain(savedScheduleText('1 окт, 14:20')), startsWith('Показываю расписание, сохранённое 1 окт в 14:20.'));
  });

  test('«Активных сроков нет»: просроченное на соседней полке и когда смотрели СДО', () {
    final at = DateTime(2026, 10, 9, 13, 5);
    expect(
      freshNoDueText(1, null, at),
      'Одна работа просрочена, загляни на соседнюю полку. Новые задания из СДО проверяем несколько раз в день.',
    );
    expect(freshNoDueText(3, null, at), startsWith('3 работы просрочены, загляни на соседнюю полку.'));
    expect(
      freshNoDueText(0, DateTime.parse('2026-10-09T12:40:00+03:00'), at),
      'Новые задания из СДО проверяем несколько раз в день, последний раз в 12:40.',
    );
    expect(
      freshNoDueText(0, DateTime.parse('2026-10-08T21:10:00+03:00'), at),
      endsWith('последний раз вчера в 21:10.'),
    );
  });

  testWidgets('пар нет: капибара крупно, ближайшая пара и «но кое-что ждёт»', (t) async {
    phone(t);
    final later = now().add(const Duration(days: 3));
    final due = now().add(const Duration(hours: 3));
    await t.pumpWidget(
      _wrap(
        TodayScreen(
          api: fakeApi(overrides: _freeDay(soon: [_soonDue(due)])),
        ),
      ),
    );
    await settle(t);
    expect(find.byKey(const Key('today:free')), findsOneWidget);
    expect(find.text('Сегодня пар нет'), findsOneWidget);
    final free = find.byWidgetPredicate(
      (w) =>
          w is Text &&
          _plain(w.data ?? '') == 'Завтра тоже свободно. Ближайшая пара ${_in[later.weekday - 1]} в 10:40.',
    );
    expect(free, findsOneWidget);
    expect(find.text('но кое-что ждёт'), findsOneWidget);
    expect(find.byKey(const Key('today:hot:7')), findsOneWidget);
    expect(_capy(CapyPose.joy), isTrue);
    expect(find.byKey(const Key('today:down')), findsNothing);
  });

  testWidgets('сайт молчит, есть сохранённое: плашка сверху, капибара одна — в плашке', (t) async {
    phone(t);
    await t.pumpWidget(
      _wrap(
        TodayScreen(
          api: fakeApi(overrides: _freeDay(stale: '07:30')),
        ),
      ),
    );
    await settle(t);
    expect(find.text('МИРЭА не отвечает'), findsOneWidget);
    final saved = find.byWidgetPredicate(
      (w) =>
          w is Text &&
          _plain(w.data ?? '') == 'Показываю расписание, сохранённое сегодня в 07:30. Попробую снова через минуту.',
    );
    expect(saved, findsOneWidget);
    expect(find.text('Сегодня пар нет'), findsOneWidget);
    expect(find.byType(CapyImage), findsOneWidget);
    expect(_capy(CapyPose.sad), isTrue);
  });

  testWidgets('сайт молчит и сохранённого нет: не «пар нет», а «Расписания пока нет»', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(TodayScreen(api: fakeApi(overrides: _freeDay(ok: false)))));
    await settle(t);
    expect(find.text('Расписания пока нет'), findsOneWidget);
    expect(find.text('Сегодня пар нет'), findsNothing);
    expect(find.textContaining('Расписание сейчас не загрузить'), findsOneWidget);
    expect(find.byType(CapyBadge), findsNothing);
  });

  testWidgets('в «Классике» свободный день прежний', (t) async {
    phone(t);
    await t.pumpWidget(
      _wrap(
        TodayScreen(
          api: fakeApi(overrides: _freeDay(stale: '07:30')),
        ),
        fresh: false,
      ),
    );
    await settle(t);
    expect(find.byKey(const Key('today:free')), findsNothing);
    expect(find.text('МИРЭА не отвечает'), findsNothing);
  });

  testWidgets('«Сдать» без активных: про просроченное и «Проверить обновления»', (t) async {
    t.view.physicalSize = const Size(360 * 3, 780 * 3);
    t.view.devicePixelRatio = 3;
    addTearDown(t.view.reset);
    final asked = <String>[];
    final api = fakeApi(
      requests: asked,
      overrides: {
        'GET /api/deadlines?include_done=true': {
          'items': [
            {'id': 3, 'subject': 'Практика 2 · Анализ данных', 'due_date': '2020-10-02', 'due_time': '18:00'},
          ],
          'stats': {},
          'sdo': {'ok': true, 'checked_at': null, 'last_ok': null},
        },
      },
    );
    await t.pumpWidget(_wrap(DeadlinesScreen(api: api)));
    await settle(t);
    expect(find.text('Активных сроков нет'), findsOneWidget);
    expect(find.textContaining('Одна работа просрочена, загляни на соседнюю полку.'), findsOneWidget);
    expect(_capy(CapyPose.evening), isTrue); // не радуется, пока есть просроченное
    // полки в одну строку и на 360: «Активные · 0» больше не переносится
    for (var i = 0; i < 3; i++) {
      expect(t.getSize(find.byKey(ValueKey('due:shelf:$i'))).height, lessThan(48));
    }
    asked.clear();
    await t.tap(find.text('Проверить обновления'));
    await settle(t);
    expect(asked, ['POST /api/sdo/recheck', 'GET /api/deadlines?include_done=true']);
    await t.pump(const Duration(seconds: 5));
  });

  testWidgets('не загрузилось в новом виде: капибара по центру и «Ещё раз»', (t) async {
    phone(t);
    var calls = 0;
    await t.pumpWidget(
      _wrap(
        Loader<int>(
          load: () async {
            calls++;
            throw ApiError('Сервер не ответил');
          },
          builder: (_, _, _) => const SizedBox(),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Не загрузилось'), findsOneWidget);
    expect(find.byType(FreshEmpty), findsOneWidget);
    await t.tap(find.text('Ещё раз'));
    await settle(t);
    expect(calls, greaterThan(1));
  });
}

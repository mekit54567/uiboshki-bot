// «Сегодня» по выбору владельца (09.10): главный вид 21А — группа с неделей и
// погода одной строкой, приветствие с именем; во время пары 21В — «до конца»
// и где следующая; пары карточками с номером пары. Второй вид 22А — дни
// недели плитками — на вкладке «Неделя»: переключатель там, выбор
// запоминается, свайп листает недели, а не дни.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/lesson.dart';
import 'package:uiboshki/screens/today.dart';
import 'package:uiboshki/screens/week.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/capy.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'util.dart';

String _hm(DateTime d) => '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

Map<String, Object?> _lesson(DateTime start, Object num, String title, String room) {
  final end = start.add(const Duration(minutes: 90));
  return {
    'num': num,
    'start': _hm(start),
    'end': _hm(end),
    'title': title,
    'kind': 'практика',
    'room': room,
    'teacher': 'Зорина Н. В.',
    'groups': '',
    'status': '',
    'start_iso': start.toIso8601String(),
    'end_iso': end.toIso8601String(),
  };
}

const _weather = '🌤 +4°, переменная облачность, ощущается +2° · 🧣 куртка не помешает';

/// Ответы: «Сегодня» с данными парами, имя и группа, 6 неделя.
Map<String, Object?> _answers(List<Map<String, Object?>> lessons, {Map<String, Object?> days = const {}}) => {
  'GET /api/today': {
    'lessons': lessons,
    'tomorrow_first': null,
    'weather': _weather,
    'deadlines': {'active': 0, 'soon': []},
  },
  'GET /api/me': {
    'id': 1,
    'first_name': 'Никита',
    'group': {'id': 4928, 'name': 'УИБО-03-24', 'own': true},
  },
  'GET /api/week?start=${iso(mondayOf(now()))}': {'week': 6, 'days': []},
  ...days,
};

Widget _wrap(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(
    home: Scaffold(body: SafeArea(child: child)),
  ),
);

void main() {
  setUpAll(loadFonts); // ширина шапки — настоящими шрифтами, как на телефоне
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('погода коротко и без эмодзи; номер пары из API', () {
    final w = weatherBrief(_weather)!;
    expect(w.temp, '+4°');
    expect(w.sky, 'облачно');
    expect(w.full, '+4°, переменная облачность, ощущается +2° · куртка не помешает');
    expect(weatherBrief('🌧 -3°, лёгкий дождь, ощущается -7° · 🧤 перчатки')!.sky, 'дождь');
    expect(weatherBrief(''), isNull);
    expect(Lesson.fromJson({'num': 4}).number, '4');
    expect(Lesson.fromJson({'num': '1–5'}).number, '1–5');
    expect(Lesson.fromJson({}).number, '');
    expect(spanText(134), '2 ч 14 мин');
    expect(spanText(45), '45 мин');
    expect(splitRoom('А-332 (МП-1), Б-304 (МП-1)'), (code: 'А-332, Б-304', campus: 'МП-1'));
  });

  testWidgets('до пар: группа с неделей и погода в одной строке, ниже — приветствие с именем', (t) async {
    phone(t);
    final start = now().add(const Duration(hours: 2, minutes: 5));
    final api = fakeApi(
      overrides: _answers([_lesson(start, 4, 'Объектно-ориентированный анализ и программирование', 'А-332 (МП-1)')]),
    );
    await t.pumpWidget(_wrap(TodayScreen(api: api)));
    await settle(t);
    final group = find.text('УИБО-03-24 · 6 неделя');
    final weather = find.text('+4° облачно');
    expect(group, findsOneWidget);
    expect(weather, findsOneWidget);
    expect((t.getCenter(group).dy - t.getCenter(weather).dy).abs(), lessThan(1)); // одна строка
    final hello = find.text('${greeting(now().hour)},\nНикита');
    expect(hello, findsOneWidget);
    expect(t.getTopLeft(hello).dy, greaterThan(t.getBottomLeft(group).dy));
    expect(find.text('первая пара в'), findsOneWidget);
    expect(find.text('А-332'), findsOneWidget); // плашка кабинета
    expect(find.text('корпус МП-1'), findsOneWidget);
    expect(find.text('2 ч 05 мин'), findsOneWidget);
    expect(find.textContaining('🌤'), findsNothing);

    // погода целиком — чип раскрывается карточкой на месте (П5), тоже без
    // эмодзи и без серой системной плашки снизу; нажал ещё раз — свернулась
    await t.tap(weather);
    await settle(t);
    expect(find.byType(SnackBar), findsNothing);
    expect(find.text('Переменная облачность'), findsOneWidget);
    expect(find.text('ощущается +2°'), findsOneWidget);
    expect(find.text('куртка не помешает'), findsOneWidget);
    expect(t.getTopLeft(hello).dy, greaterThan(t.getBottomLeft(find.text('куртка не помешает')).dy));
    await t.tap(find.text('Переменная облачность'));
    await settle(t);
    expect(find.text('Переменная облачность'), findsNothing);
  });

  test('погода по частям для карточки; дождь — для капибары', () {
    expect(weatherDetails(_weather), (
      temp: '+4°',
      desc: 'Переменная облачность',
      feels: 'ощущается +2°',
      advice: 'куртка не помешает',
    ));
    expect(weatherDetails('+5°')!.advice, '');
    expect(rainy('🌧 -3°, лёгкий дождь, ощущается -7° · 🧤 перчатки'), isTrue);
    expect(rainy(_weather), isFalse);
  });

  testWidgets('капибара: по центру поверх размытого экрана, подпись печатается; случай первым', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(TodayScreen(api: fakeApi(overrides: _answers([])))));
    await settle(t);
    final pose = poseAt(now().hour);
    Future<String> open({bool long = false}) async {
      final capy = find.byType(CapyBadge);
      long ? await t.longPress(capy) : await t.tap(capy);
      await t.pump(const Duration(milliseconds: 400));
      expect(find.byType(BackdropFilter), findsOneWidget);
      // без Material у текста в диалоге — жёлтое подчёркивание
      expect(find.ancestor(of: find.byType(CapyOverlay), matching: find.byType(Material)), findsWidgets);
      await t.pump(const Duration(seconds: 3)); // допечаталась
      final shown = t.widget<CapyOverlay>(find.byType(CapyOverlay)).text;
      await t.tapAt(const Offset(30, 60)); // нажатие в любом месте закрывает
      await settle(t);
      expect(find.byType(CapyOverlay), findsNothing);
      return shown;
    }

    expect(find.byType(SnackBar), findsNothing);
    expect(await open(), momentLines[CapyMoment.dayOff]); // пар нет — сначала «выходной»
    expect(capyLines[pose], contains(await open(long: true)));
    final third = await open();
    expect(capyLines[pose], contains(third));
    expect(await open(), isNot(third)); // по кругу, не повторяется подряд
    expect(await open(), tickleLine); // пятое нажатие подряд
  });

  testWidgets('после последней пары недели — своя подпись, иначе «на сегодня всё»', (t) async {
    if (poseAt(now().hour) == CapyPose.night) return; // ночью капибара спит, без случаев
    phone(t);
    final ended = _lesson(now().subtract(const Duration(hours: 2)), 1, 'Основы бизнес-анализа', 'А-18 (В-78)');
    Future<String> first(List<Map<String, Object?>> days) async {
      final api = fakeApi(
        overrides: {
          ..._answers([ended]),
          'GET /api/week?start=${iso(mondayOf(now()))}': {'week': 6, 'days': days},
        },
      );
      await t.pumpWidget(_wrap(TodayScreen(key: UniqueKey(), api: api)));
      await settle(t);
      await t.tap(find.byType(CapyBadge));
      await t.pump(const Duration(milliseconds: 400));
      final text = t.widget<CapyOverlay>(find.byType(CapyOverlay)).text;
      await t.tapAt(const Offset(30, 60));
      await settle(t);
      return text;
    }

    final today = iso(now());
    final later = iso(now().add(const Duration(days: 1)));
    expect(
      await first([
        {
          'date': today,
          'dots': ['#fff'],
        },
      ]),
      momentLines[CapyMoment.weekOver],
    );
    expect(
      await first([
        {
          'date': today,
          'dots': ['#fff'],
        },
        {
          'date': later,
          'dots': ['#fff'],
        },
      ]),
      momentLines[CapyMoment.dayOver],
    );
  });

  testWidgets('во время пары: «до конца», полоска и где следующая', (t) async {
    phone(t);
    final at = now();
    final next = _lesson(at.add(const Duration(minutes: 97)), 5, 'Моделирование бизнес-процессов', 'Б-304 (МП-1)');
    Future<void> show(String nextRoom) async {
      final api = fakeApi(
        overrides: _answers([
          _lesson(at.subtract(const Duration(minutes: 23)), 4, 'Объектно-ориентированный анализ', 'А-332 (МП-1)'),
          {...next, 'room': nextRoom},
        ]),
      );
      await t.pumpWidget(_wrap(TodayScreen(key: UniqueKey(), api: api)));
      await settle(t);
    }

    await show('Б-304 (МП-1)');
    expect(find.text('Идёт первая пара'), findsOneWidget);
    expect(t.widget<Text>(find.text('Идёт первая пара')).maxLines, 1); // на узком экране — мельче, не в две строки (2.17)
    expect(find.text('до конца'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsWidgets);
    expect(find.text('дальше в ${next['start']}'), findsOneWidget);
    expect(find.text('Б-304'), findsOneWidget);
    expect(find.text('тот же корпус'), findsOneWidget);
    // карточка идущей пары: «идёт · ещё…», номер залит
    expect(find.text('идёт · ещё 1 ч 07 мин'), findsOneWidget);
    expect(t.widget<PairBadge>(find.widgetWithText(PairBadge, '4')).live, isTrue);
    expect(t.widget<PairBadge>(find.widgetWithText(PairBadge, '5')).live, isFalse);

    await show('Б-304 (В-78)');
    expect(find.text('другой корпус, В-78'), findsOneWidget);

    // следующая — в том же кабинете (2.2)
    await show('А-332 (МП-1)');
    expect(find.text('тот же кабинет, никуда не идти'), findsOneWidget);
    expect(find.text('тот же корпус'), findsNothing);
  });

  testWidgets('пары — отдельными карточками с номером пары справа', (t) async {
    phone(t);
    final at = now();
    final api = fakeApi(
      overrides: _answers([
        _lesson(at.add(const Duration(hours: 1)), 4, 'Анализ данных', 'ИВЦ-126 (В-78)'),
        _lesson(at.add(const Duration(hours: 3)), '5–6', 'Архитектура предприятия', 'А-223 (В-78)'),
      ]),
    );
    await t.pumpWidget(_wrap(TodayScreen(api: api)));
    await settle(t);
    expect(find.text('сегодня · 2 пары'), findsOneWidget);
    expect(find.byType(LessonCard), findsNWidgets(2));
    expect(find.descendant(of: find.byType(LessonCard), matching: find.text('4')), findsOneWidget);
    expect(find.descendant(of: find.byType(LessonCard), matching: find.text('5–6')), findsOneWidget);
    expect(find.descendant(of: find.byType(LessonCard), matching: find.text('ИВЦ-126 (В-78)')), findsOneWidget);
    await t.tap(find.byType(LessonCard).first); // нажал карточку — экран пары
    await settle(t);
    expect(find.byType(LessonScreen), findsOneWidget);
  });

  testWidgets('на «Сегодня» переключателя нет — только сводка дня', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(TodayScreen(api: fakeApi(overrides: _answers([])))));
    await settle(t);
    expect(find.byType(ViewToggle), findsNothing);
    expect(find.byKey(const ValueKey('today:main')), findsOneWidget);
  });

  testWidgets('«Неделя»: переключатель видов, запоминается; свайп по дням — соседняя неделя', (t) async {
    phone(t);
    final monday = mondayOf(now());
    final next = monday.add(const Duration(days: 7));
    final ti = now().weekday - 1;
    Map<String, Object?> day(DateTime d, String who) => _lesson(
      d.add(const Duration(hours: 10)),
      d.weekday,
      'Предмет: $who ${weekdays[d.weekday - 1]}',
      'А-100 (МП-1)',
    );
    final asked = <String>[];
    final api = fakeApi(
      requests: asked,
      overrides: {
        'GET /api/week?start=${iso(monday)}': {'week': 6, 'days': []},
        'GET /api/week?start=${iso(next)}': {'week': 7, 'days': []},
        for (var i = 0; i < 7; i++) ...{
          'GET /api/day?date=${iso(monday.add(Duration(days: i)))}': {
            'lessons': [day(monday.add(Duration(days: i)), 'эта')],
          },
          'GET /api/day?date=${iso(next.add(Duration(days: i)))}': {
            'lessons': [day(next.add(Duration(days: i)), 'след')],
          },
        },
      },
    );
    await t.pumpWidget(_wrap(WeekScreen(api: api)));
    await settle(t);
    final where = t.getRect(find.byTooltip('По дням'));
    await t.tap(find.byTooltip('По дням'));
    await settle(t);
    expect(t.getRect(find.byTooltip('По дням')), where); // переключатель не сдвинулся
    expect((await SharedPreferences.getInstance()).getString(WeekScreen.viewKey), 'days');
    // сверху — та же полоса дней, что и в ленте, все семь дней (владелец, 10.10)
    expect(find.byType(DayCell), findsNWidgets(7));
    // открыт сегодняшний день, у пары — номер
    expect(find.text('${dayHead(now(), today: true)} · 1 пара'), findsOneWidget); // как в ленте (2.13)
    final today = find.text('Предмет: эта ${weekdays[ti]}');
    expect(today, findsOneWidget);
    expect(find.descendant(of: find.byType(LessonCard), matching: find.text('${ti + 1}')), findsOneWidget);

    // нажал плитку — её день
    await t.tap(find.byKey(ValueKey('day:${iso(monday)}')));
    await settle(t);
    expect(find.text('Предмет: эта ${weekdays[0]}'), findsOneWidget);

    // свайп вбок — следующая неделя, а не соседний день; открыта на первом дне с парами
    await t.fling(find.text('Предмет: эта ${weekdays[0]}'), const Offset(-400, 0), 1500);
    await settle(t);
    expect(asked, contains('GET /api/week?start=${iso(next)}'));
    expect(find.textContaining('7 неделя'), findsOneWidget);
    expect(find.text('Предмет: след ${weekdays[0]}'), findsOneWidget);
    expect(find.byKey(ValueKey('day:${iso(next)}')), findsOneWidget);
    // стрелка — обратно
    await t.tap(find.byTooltip('Прошлая неделя'));
    await settle(t);
    expect(find.textContaining('6 неделя'), findsOneWidget);

    // заново открытый экран — сразу по дням; обратно — лента
    await t.pumpWidget(_wrap(WeekScreen(key: UniqueKey(), api: api)));
    await settle(t);
    expect(find.byKey(ValueKey('day:${iso(monday)}')), findsOneWidget);
    await t.tap(find.byTooltip('Лентой'));
    await settle(t);
    expect(find.byKey(ValueKey('day:${iso(monday)}')), findsNothing);
    expect((await SharedPreferences.getInstance()).getString(WeekScreen.viewKey), 'list');
    expect(find.byType(DayCell), findsNWidgets(7));
  });

  testWidgets('выбор «дни недели» со старой «Сегодня» переносится на «Неделю»', (t) async {
    phone(t);
    SharedPreferences.setMockInitialValues({WeekScreen.oldViewKey: 'days'});
    await t.pumpWidget(_wrap(WeekScreen(api: fakeApi())));
    await settle(t);
    expect(find.byKey(ValueKey('day:${iso(mondayOf(now()))}')), findsOneWidget);
  });

  testWidgets('«Неделя»: ушёл на другие недели — «Сегодня» возвращает на эту неделю и сегодняшний день', (t) async {
    phone(t);
    SharedPreferences.setMockInitialValues({WeekScreen.viewKey: 'days'});
    final asked = <String>[];
    await t.pumpWidget(_wrap(WeekScreen(api: fakeApi(requests: asked))));
    await settle(t);
    final today = ValueKey('day:${iso(now())}');
    expect(find.text('Сегодня'), findsNothing); // на своей неделе кнопки нет
    for (var i = 0; i < 3; i++) {
      await t.tap(find.byTooltip('Следующая неделя'));
      await settle(t);
    }
    expect(find.byKey(today), findsNothing);
    await t.tap(find.text('Сегодня'));
    await settle(t);
    expect(find.text('Сегодня'), findsNothing);
    expect(t.widget<DayCell>(find.byKey(today)).selected, isTrue);
    expect(asked.last, isNot(contains('start=${iso(mondayOf(now()).add(const Duration(days: 21)))}')));
  });
}

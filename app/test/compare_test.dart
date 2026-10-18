// «Сравнить неделю» (5.100.2, Никита 18.10): своя неделя рядом с другой
// группой — по времени, общая пара одной карточкой, «обе свободны с …».
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/compare.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

Lesson _l(String start, String end, String title, String room) =>
    Lesson(start: start, end: end, title: title, kind: 'лекция', room: room, teacher: '', status: '');

Map<String, Object?> _j(String start, String end, String title, String room) => {
  'start': start,
  'end': end,
  'title': title,
  'kind': 'лекция',
  'room': room,
};

void main() {
  test('пары двух групп по времени, общая — одной строкой', () {
    final mine = [_l('09:00', '10:30', 'Анализ данных', 'А-17 (В-78)'), _l('10:40', '12:10', 'Матан', 'А-223 (В-78)')];
    final theirs = [_l('09:00', '10:30', 'анализ  данных', 'А-17 (В-78)'), _l('12:40', '14:10', 'Право', 'Б-404')];
    final rows = compareDay(mine, theirs);
    expect([for (final r in rows) r.start], ['09:00', '10:40', '12:40']);
    expect(rows[0].together, isTrue);
    expect(rows[1].theirs, isNull);
    expect(rows[2].mine, isNull);
    expect(bothFreeFrom(mine, theirs), '14:10');
    expect(bothFreeFrom(const [], const []), '');
  });

  test('название в узкой колонке — по словам, до двух строк, дальше «…»', () {
    const style = TextStyle(fontSize: 13);
    // в тестах шрифт квадратный: буква = 13 px
    expect(wordLines('Право', style, 200), 'Право');
    expect(wordLines('Моделирование бизнес-процессов', style, 13 * 14), 'Моделирование\nбизнес-процес…');
    final two = wordLines('Основы предпринимательской деятельности и права', style, 13 * 14);
    expect(two.split('\n'), hasLength(2));
    expect(two.endsWith('…'), isTrue);
    for (final line in two.split('\n')) {
      expect(line.length <= 14, isTrue, reason: line);
    }
    // слово длиннее строки не рвётся посередине — обрезается с «…»
    expect(wordLines('Программирование', style, 13 * 8), 'Програм…');
  });

  testWidgets('экран: две колонки, «вместе», свободны с', (t) async {
    phone(t);
    final weeks = [
      {
        'monday': '2026-10-05',
        'week': 6,
        'days': [
          {'date': '2026-10-05', 'lessons': []},
          {'date': '2026-10-06', 'lessons': []},
          {'date': '2026-10-07', 'lessons': []},
          {
            'date': '2026-10-08',
            'lessons': [
              _j('09:00', '10:30', 'Моделирование бизнес-процессов', 'А-17 (В-78)'),
              _j('18:00', '19:30', 'Физкультура', 'Спортзал'),
            ],
          },
          {'date': '2026-10-09', 'lessons': []},
          {'date': '2026-10-10', 'lessons': []},
          {'date': '2026-10-11', 'lessons': []},
        ],
      },
    ];
    await t.pumpWidget(
      AppStyle(
        p: Palette.depth,
        font: FontChoice.strict,
        child: MaterialApp(
          home: CompareScreen(api: fakeApi(), title: 'УИБО-01-24', weeks: weeks),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Сравнить неделю'), findsOneWidget);
    expect(find.text('УИБО-03-24'), findsOneWidget); // своя — из /me
    expect(find.text('УИБО-01-24'), findsWidgets);
    expect(find.textContaining('вместе'), findsOneWidget); // общая лекция в А-17
    // строки названия — каждая своим Text с «…» от Flutter: замер до загрузки
    // шрифта в вебе не срежет многоточие до «..» (5.100.9)
    final title = t.widgetList<Text>(find.byType(Text)).where((w) => (w.data ?? '').startsWith('Моделирование'));
    expect(title, isNotEmpty);
    for (final w in title) {
      expect((w.maxLines, w.overflow, w.data!.contains('\n')), (1, TextOverflow.ellipsis, false));
    }
    await t.scrollUntilVisible(find.text('Обе свободны с 19:30'), 200);
    expect(find.text('Обе свободны с 19:30'), findsOneWidget);
    expect(find.text('Пар нет у обеих'), findsWidgets); // вторник
  });
}

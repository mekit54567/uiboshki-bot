// «Неделя», второй вид (владелец, 09.10, 22А; переехал сюда с «Сегодня»):
// сверху та же полоса дней, что и в ленте (владелец, 10.10), ниже — пары
// выбранного дня карточками с номером пары. Открывается на сегодня (в другой
// неделе — на первом дне с парами); свайп вбок листает недели, как и в ленте.
import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/common.dart';
import 'today.dart' show LessonCard;
import 'week.dart' show DayCell, WeekData, dayHead, noLessonsText, noLessonsTitle;

class WeekDays extends StatefulWidget {
  final WeekData data;
  final ValueChanged<Lesson> onLesson;
  const WeekDays({super.key, required this.data, required this.onLesson});

  @override
  State<WeekDays> createState() => _WeekDaysState();
}

class _WeekDaysState extends State<WeekDays> {
  late final String _today = iso(now());
  late int _selected = _start();
  int _dir = 1; // куда уехал день: 1 — вперёд, -1 — назад

  DateTime _date(int i) => widget.data.monday.add(Duration(days: i));
  List<Lesson> _lessons(int i) => widget.data.days[iso(_date(i))] ?? const [];

  int _start() {
    for (var i = 0; i < 7; i++) {
      if (iso(_date(i)) == _today) return i;
    }
    for (var i = 0; i < 7; i++) {
      if (_lessons(i).isNotEmpty) return i;
    }
    return 0;
  }

  static String _count(int n) => ', ${n == 0 ? 'пар нет' : '$n ${plural(n, 'пара', 'пары', 'пар')}'}';

  void _go(int i) {
    if (i == _selected) return;
    tick();
    setState(() {
      _dir = i > _selected ? 1 : -1;
      _selected = i;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = now();
    final date = _date(_selected);
    final key = iso(date);
    final lessons = _lessons(_selected);
    final n = lessons.length;
    final day = dayHead(date, today: key == _today);
    final p = AppStyle.of(context).p;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.m),
          child: Row(
            children: [
              for (var i = 0; i < 7; i++)
                Expanded(
                  child: DayCell(
                    key: ValueKey('day:${iso(_date(i))}'),
                    date: _date(i),
                    dots: _lessons(i).length,
                    hint: _count(_lessons(i).length),
                    selected: i == _selected,
                    today: iso(_date(i)) == _today,
                    onTap: () => _go(i),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: Space.s),
        Divider(height: 1, color: p.line),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.only(bottom: 120),
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              Section(n == 0 ? day : '$day · $n ${plural(n, 'пара', 'пары', 'пар')}'),
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 260),
                switchInCurve: Curves.easeOutCubic,
                switchOutCurve: Curves.easeInCubic,
                layoutBuilder: (current, previous) =>
                    Stack(alignment: Alignment.topCenter, children: [...previous, ?current]),
                transitionBuilder: (child, anim) {
                  final incoming = child.key == ValueKey(key);
                  final from = Offset((incoming ? 0.15 : -0.15) * _dir, 0);
                  return FadeTransition(
                    opacity: anim,
                    child: SlideTransition(
                      position: Tween(begin: from, end: Offset.zero).animate(anim),
                      child: child,
                    ),
                  );
                },
                child: KeyedSubtree(
                  key: ValueKey(key),
                  child: lessons.isEmpty
                      ? const Notice(title: noLessonsTitle, text: noLessonsText, pose: CapyPose.joy)
                      : Column(
                          children: [
                            for (final l in lessons)
                              Padding(
                                padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
                                child: LessonCard(lesson: l, at: t, onTap: () => widget.onLesson(l)),
                              ),
                          ],
                        ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

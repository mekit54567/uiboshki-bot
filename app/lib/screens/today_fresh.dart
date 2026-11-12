// «Сегодня» нового дизайна (брендбук v1, макет С1, Никита 11.11) — только при
// «Новом» в «Оформлении» ([AppStyle.fresh]); прежний экран — [_MainView].
// Сверху ответ «что сейчас и куда идти»: заголовок, одна большая цифра и
// карточка пары; под ней «Важно сегодня» — сроки ближайших суток с кнопкой
// «Сдать»; дальше остальные пары строками. Пары кончились — цифра считает
// время до ближайшего срока, завтра раскрыто, прошедшее свёрнуто в строку.
part of 'today.dart';

class _FreshView extends StatelessWidget {
  final TodayData data;
  final Api api;
  final Widget top;

  /// Открыть вкладку «Сдать» (кнопка у срока в «Важно сегодня»).
  final VoidCallback? onDeadlines;
  const _FreshView({super.key, required this.data, required this.api, required this.top, this.onDeadlines});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final t = now();
    final lessons = data.lessons;
    Lesson? current, next;
    for (final l in lessons) {
      if (l.startAt == null || l.endAt == null) continue;
      if (!t.isBefore(l.startAt!) && t.isBefore(l.endAt!)) current = l;
      if (next == null && t.isBefore(l.startAt!)) next = l;
    }
    void open(Lesson l) => openLesson(context, api, l);
    final free = lessons.isEmpty || (current == null && next == null);
    // «важно» — сроки ближайших суток; остальные ближайшие — тихим списком ниже
    final hot = [
      for (final d in data.soon)
        if (d.due.difference(t).inHours < 24) d,
    ];
    final later = [
      for (final d in data.soon)
        if (!hot.contains(d)) d,
    ];
    final focusLesson = current ?? next;

    final String title;
    final List<Widget> hero;
    if (current != null) {
      title = 'Идёт ${ordinal(lessons.indexOf(current))} пара';
      final live = current.liveAt(t);
      final from = live?.start ?? current.startAt!, till = live?.end ?? current.endAt!;
      final total = till.difference(from).inSeconds;
      final passed = t.difference(from).inSeconds.clamp(0, total);
      hero = [
        _FreshLabel(
          live == null || live.of == 1
              ? 'до конца'
              : live.pause
              ? 'перемена · до ${live.index}-й пары из ${live.of}'
              : 'до конца пары · ${live.index} из ${live.of}',
        ),
        _Countdown(minutes: minutesTo(t, till), color: p.text),
        const SizedBox(height: Space.m),
        ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: total == 0 ? 0 : passed / total,
            minHeight: 6,
            color: p.ok,
            backgroundColor: p.line,
          ),
        ),
      ];
    } else if (next != null) {
      final i = lessons.indexOf(next);
      title = i == 0 ? (data.name.isEmpty ? greeting(t.hour) : '${greeting(t.hour)},\n${data.name}') : 'Перемена';
      hero = [_FreshLabel('${ordinal(i)} пара через'), _Countdown(minutes: minutesTo(t, next.startAt!), color: p.text)];
    } else {
      title = lessons.isEmpty ? 'Сегодня пар нет' : 'Пары закончились';
      final tf = data.tomorrowFirst;
      if (hot.isNotEmpty) {
        hero = [const _FreshLabel('до срока'), _Countdown(minutes: minutesTo(t, hot.first.due), color: p.accent)];
      } else if (tf != null) {
        hero = [const _FreshLabel('завтра первая пара в'), Text(tf.start, style: s.number(52))];
      } else {
        hero = [Text('Завтра тоже свободно.', style: s.body(15, color: p.muted))];
      }
    }

    // остальные пары дня: без той, что в карточке сверху; отменённые — на своих местах
    final ahead = [
      for (final l in lessons)
        if (l != focusLesson && l.endAt != null && t.isBefore(l.endAt!)) l,
      for (final l in data.cancelled)
        if (l.endAt == null || t.isBefore(l.endAt!)) l,
    ]..sort((a, b) => a.start.compareTo(b.start));
    final past = [
      for (final l in lessons)
        if (l.endAt != null && !t.isBefore(l.endAt!)) l,
    ];
    final nAhead = ahead.where((l) => !l.cancelled).length;
    final rest = free ? data.tomorrow : const <Lesson>[];

    Widget pad(Widget child) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: child,
    );
    return ListView(
      padding: const EdgeInsets.only(bottom: 120),
      children: [
        top,
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.m, 0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    title.contains('\n') ? FitWords(title, style: s.title(30)) : _fitLine(title, s.title(30)),
                    const SizedBox(height: Space.m),
                    ...hero,
                  ],
                ),
              ),
              const SizedBox(width: Space.s),
              CapyBadge(hour: t.hour, size: 62, moments: _MainView.momentsOf(data, t, current, next)),
            ],
          ),
        ),
        if (focusLesson != null) ...[
          const SizedBox(height: Space.m),
          pad(
            _NowCard(
              lesson: focusLesson,
              live: current != null,
              after: current == null ? _beforeLine(lessons, focusLesson) : _afterLine(focusLesson, next),
              onTap: () => open(focusLesson),
            ),
          ),
        ],
        if (hot.isNotEmpty) ...[
          const Section('важно сегодня'),
          for (final d in hot)
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
              child: _HotCard(d, at: t, onTap: onDeadlines),
            ),
        ],
        if (ahead.isNotEmpty) ...[
          Section(
            focusLesson == null
                ? 'сегодня · $nAhead ${plural(nAhead, 'пара', 'пары', 'пар')}'
                : 'ещё сегодня · $nAhead ${plural(nAhead, 'пара', 'пары', 'пар')}',
          ),
          pad(LessonList(lessons: ahead, at: t, onTap: open)),
        ],
        if (rest.isNotEmpty) ...[
          Section('завтра · ${rest.length} ${plural(rest.length, 'пара', 'пары', 'пар')}'),
          pad(LessonList(lessons: rest, at: t, onTap: open)),
        ],
        if (later.isNotEmpty) ...[
          const Section('сдать'),
          pad(_SoonList(later, at: t)),
        ] else if (free && hot.isEmpty) ...[
          const Section('сдать'),
          pad(
            Tile(
              child: Row(
                children: [
                  Icon(Icons.task_alt_rounded, size: 17, color: p.ok),
                  const SizedBox(width: Space.s),
                  Expanded(
                    child: Text('Открытых сроков нет', style: s.body(14, color: p.muted)),
                  ),
                ],
              ),
            ),
          ),
        ],
        if (past.isNotEmpty) ...[const SizedBox(height: Space.xl), pad(_PastToday(lessons: past, at: t, onTap: open))],
      ],
    );
  }

  /// Под идущей парой: что дальше и надо ли куда-то идти.
  static ({String text, bool warn}) _afterLine(Lesson lesson, Lesson? n) {
    if (n == null) return (text: 'Последняя на сегодня, конец в ${lesson.end}', warn: false);
    final from = campusOf(lesson.room), to = campusOf(n.room);
    final known = from.isNotEmpty && to.isNotEmpty;
    final room = splitRoom(n.room).code;
    if (room.isNotEmpty && room == splitRoom(lesson.room).code) {
      return (text: 'Дальше в ${n.start} тот же кабинет, никуда не идти', warn: false);
    }
    if (known && from != to) return (text: 'Дальше в ${n.start} другой корпус: $to', warn: true);
    final where = room.isEmpty ? n.title : room;
    return (text: 'Дальше в ${n.start}: $where${known ? ', тот же корпус' : ''}', warn: false);
  }

  /// Под следующей парой на перемене: переход в другой корпус.
  static ({String text, bool warn}) _beforeLine(List<Lesson> lessons, Lesson next) {
    final i = lessons.indexOf(next);
    if (i <= 0) return (text: '', warn: false);
    final prev = lessons[i - 1];
    final from = campusOf(prev.room), to = campusOf(next.room);
    if (from.isEmpty || to.isEmpty || from == to) return (text: '', warn: false);
    final gap = prev.endAt != null && next.startAt != null ? next.startAt!.difference(prev.endAt!).inMinutes : 0;
    return (text: 'Другой корпус: $to, на переход $gap мин', warn: true);
  }
}

/// Тихая подпись над большой цифрой.
class _FreshLabel extends StatelessWidget {
  final String text;
  const _FreshLabel(this.text);

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Text(text, style: s.body(13, color: s.p.muted)),
    );
  }
}

/// Пара, о которой сейчас речь: время, название, тип и преподаватель,
/// кабинет плашкой; ниже строка «что дальше». Идущая — в зелёной рамке.
class _NowCard extends StatelessWidget {
  final Lesson lesson;
  final bool live;
  final ({String text, bool warn}) after;
  final VoidCallback onTap;
  const _NowCard({required this.lesson, required this.live, required this.after, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final sub = [if (lesson.kind.isNotEmpty) lesson.kind.toLowerCase(), if (lesson.teacher.isNotEmpty) lesson.teacher];
    return Tile(
      key: const Key('today:now'),
      radius: Radii.card,
      border: live ? p.ok : p.edge,
      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, Space.m),
      onTap: () {
        tick();
        onTap();
      },
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: MediaQuery.textScalerOf(context).scale(52),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(lesson.start, style: s.body(16, weight: FontWeight.w700)),
                    Text(lesson.end, style: s.body(12, color: p.muted)),
                  ],
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(lesson.title, style: s.name(16)),
                    if (sub.isNotEmpty) ...[
                      const SizedBox(height: 3),
                      Text(sub.join(' · '), style: s.body(13, color: p.muted)),
                    ],
                  ],
                ),
              ),
              if (lesson.roomWas.isNotEmpty) ...[
                const SizedBox(width: Space.s),
                RoomWas(lesson),
              ] else if (lesson.room.isNotEmpty) ...[
                const SizedBox(width: Space.s),
                RoomPill(lesson.room, color: s.ink(lesson.title), size: 15, inked: true),
              ],
            ],
          ),
          if (after.text.isNotEmpty) ...[
            const SizedBox(height: Space.s),
            Text(
              after.text,
              style: s.body(
                13,
                weight: after.warn ? FontWeight.w700 : FontWeight.w400,
                color: after.warn ? p.warn : p.muted,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Срок ближайших суток: название, сколько осталось, кнопка «Сдать» (ведёт
/// на вкладку «Сдать», где и сдача файлом, и «Уже сдал»).
class _HotCard extends StatelessWidget {
  final Deadline d;
  final DateTime at;
  final VoidCallback? onTap;
  const _HotCard(this.d, {required this.at, this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final today = d.dueDate == iso(at);
    final time = d.dueTime.isEmpty ? '23:59' : d.dueTime;
    return Tile(
      key: Key('today:hot:${d.id}'),
      border: p.danger.withValues(alpha: 0.55),
      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
      onTap: onTap == null
          ? null
          : () {
              tick();
              onTap!();
            },
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(d.subject, style: s.name(15), maxLines: 2, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 3),
                Text(
                  '${today ? 'сдать до $time' : 'сдать завтра до $time'} · ${leftText(d.due.difference(at))}',
                  style: s.body(13, weight: FontWeight.w600, color: p.danger),
                ),
              ],
            ),
          ),
          if (onTap != null) ...[
            const SizedBox(width: Space.s),
            Container(
              height: 36,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              alignment: Alignment.center,
              decoration: BoxDecoration(color: p.accent, borderRadius: BorderRadius.circular(18)),
              child: Text(
                d.canSubmit ? 'Сдать' : 'Открыть',
                style: s.body(14, weight: FontWeight.w700, color: p.onAccent),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// «Сегодня было · 5 пар» — свёрнуто в строку, нажал — список прошедших.
class _PastToday extends StatefulWidget {
  final List<Lesson> lessons;
  final DateTime at;
  final ValueChanged<Lesson> onTap;
  const _PastToday({required this.lessons, required this.at, required this.onTap});

  @override
  State<_PastToday> createState() => _PastTodayState();
}

class _PastTodayState extends State<_PastToday> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final n = widget.lessons.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          button: true,
          expanded: _open,
          child: Tile(
            key: const Key('today:past'),
            padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
            onTap: () {
              tick();
              setState(() => _open = !_open);
            },
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    'Сегодня было · $n ${plural(n, 'пара', 'пары', 'пар')}',
                    style: s.body(14, weight: FontWeight.w600, color: p.muted),
                  ),
                ),
                Icon(_open ? Icons.expand_less_rounded : Icons.expand_more_rounded, size: 20, color: p.muted),
              ],
            ),
          ),
        ),
        if (_open) ...[
          const SizedBox(height: Space.s),
          LessonList(lessons: widget.lessons, at: widget.at, onTap: widget.onTap),
        ],
      ],
    );
  }
}

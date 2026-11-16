// «Сдать» нового дизайна (брендбук v1, макет Д1, Никита 11.11) — только при
// «Новом» в «Оформлении» ([AppStyle.fresh]); прежний экран не меняется.
// Сверху выбор «По срокам / По предметам» (приложение помнит). По срокам —
// три полки чипами со счётчиками: «Активные», «Просрочено», «Готово»; горящее —
// карточкой с отсчётом и кнопками «Сдать в СДО» и «Отметить». По предметам —
// карточка на предмет, статус написан у каждой работы; предмет с ближайшим
// сроком — выше. Входы в «ДЗ группы» и «Заметки» — списком внизу.
part of 'deadlines.dart';

const _viewKey = 'uib_due_view';

class _FreshDue extends StatelessWidget {
  final DeadlinesView w;
  final DateTime at;
  final bool bySubject;
  final int shelf;
  final ValueChanged<bool> onView;
  final ValueChanged<int> onShelf;
  final Widget Function(List<Deadline>, {bool late}) card;
  const _FreshDue({
    required this.w,
    required this.at,
    required this.bySubject,
    required this.shelf,
    required this.onView,
    required this.onShelf,
    required this.card,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final t = at;
    final sdo = w.sdo;
    final sdoDown = sdo != null && !sdo.ok;
    final open = w.items.where((d) => !d.done && d.due.isAfter(t)).toList()..sort((a, b) => a.due.compareTo(b.due));
    final late = w.items.where((d) => !d.done && !d.due.isAfter(t)).toList()..sort((a, b) => b.due.compareTo(a.due));
    final done = w.items.where((d) => d.done).toList()..sort((a, b) => b.due.compareTo(a.due));
    void push(Widget screen) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));

    List<Widget> byTime() {
      final hot = open.isNotEmpty && isBurning(open.first, t) ? open.first : null;
      final weeks = <DateTime, List<Deadline>>{};
      for (final d in open) {
        if (d != hot) (weeks[_monday(d.due)] ??= []).add(d);
      }
      return [
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
          child: Row(
            children: [
              for (final (i, label) in [
                'Активные · ${open.length}',
                'Просрочено · ${late.length}',
                'Готово · ${done.length}',
              ].indexed) ...[
                if (i > 0) const SizedBox(width: 6),
                Expanded(
                  flex: label.length,
                  child: _ShelfChip(
                    key: ValueKey('due:shelf:$i'),
                    label: label,
                    on: shelf == i,
                    onTap: () => onShelf(i),
                  ),
                ),
              ],
            ],
          ),
        ),
        if (shelf == 0) ...[
          if (sdoDown && open.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
              child: _SdoDown(text: sdoShownText(sdo.lastOk, t), onRetry: w.onRetry),
            ),
          if (hot != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.l),
              child: _FreshHot(
                d: hot,
                x: w.extra[hot.id],
                at: t,
                onDone: () => w.onToggle(hot, true),
                onSubmit: () => w.onSubmit(hot),
                onOpen: () => w.onOpen(hot),
              ),
            ),
          if (open.isEmpty && sdoDown)
            Notice(
              title: 'СДО не ответил',
              text: sdoShownText(sdo.lastOk, t),
              pose: CapyPose.sad,
              onRetry: w.onRetry,
              retryLabel: 'Проверить СДО',
            )
          else if (open.isEmpty && late.isNotEmpty)
            Notice(
              title: 'Впереди сроков нет',
              text: 'Но на полке «Просрочено» работ: ${late.length}. Сдал — отметь, не нужна — убери.',
              pose: CapyPose.day,
            )
          else if (open.isEmpty)
            Notice(
              title: 'Ближайших сроков нет',
              text: sdo?.checkedAt != null
                  ? sdoCheckedText(sdo!.checkedAt!, t)
                  : 'Новые задания из СДО появятся здесь сами. Свой срок — кнопкой +.',
              pose: CapyPose.joy,
            ),
          for (final (i, e) in weeks.entries.indexed) ...[
            Section(i == 0 && hot != null ? 'Дальше' : weekLabel(e.key, t)),
            card(e.value),
          ],
        ] else if (shelf == 1) ...[
          if (late.isEmpty)
            const Notice(
              title: 'Просроченного нет',
              text: 'Работы с прошедшим сроком появятся здесь.',
              pose: CapyPose.joy,
            )
          else
            card(late, late: true),
        ] else ...[
          if (done.isEmpty)
            const Notice(title: 'Пока ничего', text: 'Сданное появится здесь — свайп вправо по сроку или «Отметить».')
          else
            card(done),
        ],
      ];
    }

    List<Widget> bySubj() {
      final groups = <String, List<Deadline>>{};
      for (final d in w.items) {
        (groups[splitTitle(d.subject).course] ??= []).add(d);
      }
      // у кого ближайший открытый срок — выше; потом просроченные; сданные целиком — в конце
      int rank(List<Deadline> g) => g.any((d) => !d.done && d.due.isAfter(t))
          ? 0
          : g.any((d) => !d.done)
          ? 1
          : 2;
      DateTime first(List<Deadline> g) => g
          .where((d) => !d.done && d.due.isAfter(t))
          .fold<DateTime>(DateTime(9999), (m, d) => d.due.isBefore(m) ? d.due : m);
      final keys = groups.keys.toList()
        ..sort((a, b) {
          final ra = rank(groups[a]!), rb = rank(groups[b]!);
          if (ra != rb) return ra.compareTo(rb);
          final c = first(groups[a]!).compareTo(first(groups[b]!));
          return c != 0 ? c : a.compareTo(b);
        });
      if (keys.isEmpty) {
        return [
          const Notice(
            title: 'Ближайших сроков нет',
            text: 'Новые задания из СДО появятся здесь сами. Свой срок — кнопкой +.',
            pose: CapyPose.joy,
          ),
        ];
      }
      return [
        for (final k in keys)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
            child: _SubjectCard(
              key: ValueKey('due:subj:$k'),
              course: k,
              items: groups[k]!,
              at: t,
              onOpen: w.onOpen,
              onSubmit: w.onSubmit,
            ),
          ),
      ];
    }

    return ListView(
      key: const ValueKey('due:fresh'),
      padding: const EdgeInsets.only(bottom: 120),
      children: [
        ScreenTitle(
          title: 'Сдать',
          trailing: IconButton.filled(
            tooltip: 'Свой срок',
            style: IconButton.styleFrom(backgroundColor: p.accent, foregroundColor: p.onAccent),
            onPressed: w.onAdd,
            icon: const Icon(Icons.add_rounded),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
          child: _Segments(
            labels: const ['По срокам', 'По предметам'],
            on: bySubject ? 1 : 0,
            onPick: (i) => onView(i == 1),
          ),
        ),
        ...(bySubject ? bySubj() : byTime()),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
          child: Tile(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                _Link(
                  icon: Icons.assignment_outlined,
                  title: 'ДЗ группы',
                  sub: 'что задали на парах',
                  onTap: () => push(HomeworkScreen(api: w.api)),
                ),
                Divider(height: 1, color: p.line),
                _Link(
                  icon: Icons.push_pin_outlined,
                  title: 'Заметки',
                  sub: 'видит вся группа',
                  onTap: () => push(NotesScreen(api: w.api)),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Полка: «Активные · 2» — чип; выбранный залит цветом текста.
class _ShelfChip extends StatelessWidget {
  final String label;
  final bool on;
  final VoidCallback onTap;
  const _ShelfChip({super.key, required this.label, required this.on, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Semantics(
      button: true,
      selected: on,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          if (on) return;
          tick();
          onTap();
        },
        child: Container(
          constraints: const BoxConstraints(minHeight: 40),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 9),
          decoration: BoxDecoration(
            color: on ? p.text : p.card,
            borderRadius: BorderRadius.circular(Radii.pill),
            border: Border.all(color: on ? p.text : p.edge),
          ),
          child: Text(
            label,
            style: s.body(14, weight: FontWeight.w600, color: on ? p.bg : p.text),
          ),
        ),
      ),
    );
  }
}

/// Строка-вход внизу экрана: «ДЗ группы», «Заметки».
class _Link extends StatelessWidget {
  final IconData icon;
  final String title, sub;
  final VoidCallback onTap;
  const _Link({required this.icon, required this.title, required this.sub, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return InkWell(
      onTap: () {
        tick();
        onTap();
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.m, vertical: Space.m),
        child: Row(
          children: [
            Icon(icon, size: 22, color: s.p.muted),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: s.body(15, weight: FontWeight.w600)),
                  Text(sub, style: s.body(13, color: s.p.muted)),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded, size: 20, color: s.p.muted),
          ],
        ),
      ),
    );
  }
}

/// Горит (меньше суток): срок словами, работа, отсчёт акцентом и две кнопки.
class _FreshHot extends StatelessWidget {
  final Deadline d;
  final DlExtra? x;
  final DateTime at;
  final VoidCallback onDone, onSubmit, onOpen;
  const _FreshHot({
    required this.d,
    required this.x,
    required this.at,
    required this.onDone,
    required this.onSubmit,
    required this.onOpen,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final left = d.due.difference(at);
    final h = left.inHours, m = left.inMinutes % 60;
    final when = _daysBetween(at, d.due) == 0 ? 'сегодня ${_time(d, pre: true)}' : 'завтра ${_time(d, pre: true)}';
    final name = splitTitle(d.subject);
    Widget unit(String u) => Padding(
      padding: const EdgeInsets.only(bottom: 6, left: 3, right: 8),
      child: Text(
        u,
        style: s.body(15, weight: FontWeight.w600, color: p.muted),
      ),
    );
    final pill = const StadiumBorder();
    Widget act(String text, VoidCallback on) => FilledButton(
      style: FilledButton.styleFrom(
        backgroundColor: p.accent,
        foregroundColor: p.onAccent,
        shape: pill,
        minimumSize: const Size(0, 46),
      ),
      onPressed: () {
        tick();
        on();
      },
      child: Text(text),
    );
    return Tile(
      key: ValueKey('due:hot:${d.id}'),
      onTap: onOpen,
      radius: Radii.card,
      border: Color.alphaBlend(p.accent.withValues(alpha: 0.55), p.card),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            when,
            style: s.body(13, weight: FontWeight.w700, color: p.accent),
          ),
          const SizedBox(height: 4),
          Text(name.task, style: s.name(19)),
          if (name.course.isNotEmpty) ...[
            const SizedBox(height: 4),
            _SubjectLine(course: name.course, rest: d.canSubmit ? 'задание из СДО' : '', size: 14),
          ],
          if (_hasChips(context, d, x)) ...[const SizedBox(height: Space.s), DlChips(x: x!)],
          const SizedBox(height: Space.s),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.bottomLeft,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (h > 0) ...[Text('$h', style: s.number(44, color: p.accent)), unit('ч')],
                Text(h > 0 ? m.toString().padLeft(2, '0') : '$m', style: s.number(44, color: p.accent)),
                unit('мин'),
              ],
            ),
          ),
          const SizedBox(height: Space.m),
          Row(
            children: [
              Expanded(child: d.canSubmit ? act('Сдать в СДО', onSubmit) : act('Отметить сданным', onDone)),
              if (d.canSubmit) ...[
                const SizedBox(width: Space.s),
                OutlinedButton(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: p.text,
                    side: BorderSide(color: p.edge),
                    shape: pill,
                    minimumSize: const Size(0, 46),
                  ),
                  onPressed: () {
                    tick();
                    onDone();
                  },
                  child: const Text('Отметить'),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

/// Карточка предмета: точка, название, итог справа («1 сегодня», «1 просрочена»,
/// «2 впереди», «всё сдано»); ниже работы — у каждой написан статус.
class _SubjectCard extends StatelessWidget {
  final String course;
  final List<Deadline> items;
  final DateTime at;
  final ValueChanged<Deadline> onOpen, onSubmit;
  const _SubjectCard({
    super.key,
    required this.course,
    required this.items,
    required this.at,
    required this.onOpen,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final open = items.where((d) => !d.done && d.due.isAfter(at)).toList()..sort((a, b) => a.due.compareTo(b.due));
    final late = items.where((d) => !d.done && !d.due.isAfter(at)).toList()..sort((a, b) => b.due.compareTo(a.due));
    final done = items.where((d) => d.done).length;
    final today = open.where((d) => isBurning(d, at)).length;
    final (String sum, Color color, bool bold) = today > 0
        ? ('$today сегодня', p.accent, true)
        : late.isNotEmpty
        ? ('${late.length} ${plural(late.length, 'просрочена', 'просрочены', 'просрочено')}', p.danger, true)
        : open.isNotEmpty
        ? ('${open.length} впереди', p.muted, false)
        : ('всё сдано', p.ok, true);
    String day(Deadline d) =>
        '${weekdaysShort[d.due.weekday - 1].toLowerCase()} ${d.due.day} ${monthsGen[d.due.month - 1]}';
    Widget row(Deadline d, String sub, {bool button = false}) => InkWell(
      onTap: () {
        tick();
        onOpen(d);
      },
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.m, Space.s),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(splitTitle(d.subject).task, style: s.body(15)),
                  Text(sub, style: s.body(13, color: p.muted)),
                ],
              ),
            ),
            const SizedBox(width: Space.s),
            if (button)
              FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: p.accent,
                  foregroundColor: p.onAccent,
                  shape: const StadiumBorder(),
                  minimumSize: const Size(0, 40),
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                ),
                onPressed: () {
                  tick();
                  onSubmit(d);
                },
                child: const Text('Сдать'),
              )
            else
              Icon(Icons.chevron_right_rounded, size: 20, color: p.muted),
          ],
        ),
      ),
    );
    return Tile(
      padding: const EdgeInsets.only(bottom: Space.s),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, Space.xs),
            child: Row(
              children: [
                Container(
                  width: 9,
                  height: 9,
                  decoration: BoxDecoration(color: course.isEmpty ? p.muted : s.ink(course), shape: BoxShape.circle),
                ),
                const SizedBox(width: Space.s),
                Expanded(
                  child: Text(course.isEmpty ? 'Без предмета' : course, style: s.body(16, weight: FontWeight.w700)),
                ),
                const SizedBox(width: Space.s),
                Text(
                  sum,
                  style: s.body(13, weight: bold ? FontWeight.w700 : FontWeight.w400, color: color),
                ),
              ],
            ),
          ),
          for (final d in open)
            isBurning(d, at)
                ? row(
                    d,
                    '${_daysBetween(at, d.due) == 0 ? '' : 'завтра '}${_time(d, pre: true)} · ещё не сдано',
                    button: d.canSubmit,
                  )
                : row(d, '${day(d)} · ${d.dueTime.isEmpty ? 'время не указано' : 'до ${d.dueTime}'}'),
          for (final d in late) row(d, 'срок был ${d.due.day} ${monthsGen[d.due.month - 1]}'),
          if (done > 0)
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.l, Space.xs, Space.l, Space.xs),
              child: Text(
                'сдано · $done',
                style: s.body(13, weight: FontWeight.w600, color: p.ok),
              ),
            ),
        ],
      ),
    );
  }
}

// «Сдать» (24А, владелец 09.10): переключатель «Впереди · N | Сдано · N»
// вместо строки с цифрами над заголовком. Во «Впереди» — горящее (меньше
// суток) большой карточкой с обратным отсчётом и кнопкой «Сдать», ниже —
// остальное по неделям с датой слева (сегодня — красным, завтра — жёлтым),
// в конце — «Срок прошёл». «Сдано» — сданное, свежее сверху. Свайп вправо —
// «сдал» (у сданного — «вернуть»), нажатие — действия (изменить, напомнить,
// убрать…), «+» — свой срок. Сверху — входы в «ДЗ группы» и «Заметки».
// Новый дизайн (5.80, «Пусто и ошибка»): пусто и сбой выглядят по-разному —
// «Ближайших сроков нет · СДО проверено в 12:40» с радостной капибарой и
// «СДО не ответил · показываю сроки от 09:41» с грустной (над списком —
// строкой); «Попробовать ещё раз» только перечитывает экран, синк не зовёт.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widget_data.dart';
import '../widgets/capy.dart';
import '../widgets/cheer.dart';
import '../widgets/common.dart';
import '../widgets/report.dart' show openReportMenu;
import 'deadline_edit.dart';
import 'homework.dart';
import 'submit.dart';

typedef _Items = ({List<Deadline> list, Map<int, DlExtra> extra, SdoCheck? sdo});

/// Последняя проверка СДО группы (/api/deadlines → sdo): получилось ли,
/// когда проверяли и когда получилось в последний раз.
class SdoCheck {
  final bool ok;
  final DateTime? checkedAt, lastOk;
  const SdoCheck({required this.ok, this.checkedAt, this.lastOk});

  /// null — группу не проверяли (нет СДО) или ответ старого сервера.
  static SdoCheck? fromJson(Object? j) {
    if (j is! Map || j['ok'] is! bool) return null;
    DateTime? at(Object? v) => v is String ? DateTime.tryParse(v) : null;
    return SdoCheck(ok: j['ok'] as bool, checkedAt: at(j['checked_at']), lastOk: at(j['last_ok']));
  }
}

/// Время сервера — по Москве (сроки и пары тоже московские), без пояса.
DateTime _msk(DateTime t) {
  final u = t.toUtc().add(const Duration(hours: 3));
  return DateTime(u.year, u.month, u.day, u.hour, u.minute);
}

String _hm(DateTime t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

/// «СДО проверено в 12:40» / «вчера в 12:40» / «10 октября в 12:40».
String sdoCheckedText(DateTime checked, DateTime at) {
  final t = _msk(checked);
  final n = _daysBetween(t, at);
  final day = n <= 0 ? '' : (n == 1 ? 'вчера ' : '${t.day} ${monthsGen[t.month - 1]} ');
  return 'СДО проверено $dayв ${_hm(t)}';
}

/// «Показываю сроки от 09:41» / «от вчера, 09:41» / «от 10 октября, 09:41».
String sdoShownText(DateTime? lastOk, DateTime at) {
  if (lastOk == null) return 'Новые сроки пока не подтянулись';
  final t = _msk(lastOk);
  final n = _daysBetween(t, at);
  final day = n <= 0 ? '' : (n == 1 ? 'вчера, ' : '${t.day} ${monthsGen[t.month - 1]}, ');
  return 'Показываю сроки от $day${_hm(t)}';
}

class DeadlinesScreen extends StatefulWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const DeadlinesScreen({super.key, required this.api, this.onUnauthorized});

  @override
  State<DeadlinesScreen> createState() => _DeadlinesScreenState();
}

class _DeadlinesScreenState extends State<DeadlinesScreen> {
  Future<_Items> _load() async {
    final j = await widget.api.get('/deadlines?include_done=true');
    final raw = [for (final x in j['items'] as List) Map<String, dynamic>.from(x)];
    final sdo = _sdo = SdoCheck.fromJson(j['sdo']);
    final list = [for (final x in raw) Deadline.fromJson(x)];
    if (!Api.cacheOnly) unawaited(HomeWidgets.fromDeadlines(list)); // горящий срок на виджете
    return (list: list, extra: {for (final x in raw) x['id'] as int: DlExtra.fromJson(x)}, sdo: sdo);
  }

  SdoCheck? _sdo;

  /// «Попробовать ещё раз»: только перечитать экран — синк СДО идёт по
  /// расписанию на сервере; всё ещё молчит — так и скажем.
  Future<void> _retry(Future<void> Function() reload) async {
    tick();
    await reload();
    if (mounted && _sdo?.ok == false) {
      snack(context, 'СДО пока молчит — бот проверит его сам', kind: ToastKind.info);
    }
  }

  /// Запрос с ошибкой внизу экрана; true — прошёл.
  Future<bool> _run(Future<void> Function() call) async {
    try {
      await call();
      return true;
    } on ApiError catch (e) {
      if (mounted) snack(context, e.message, kind: ToastKind.error);
    } catch (e) {
      if (mounted) snack(context, errorText(e), kind: ToastKind.error);
    }
    return false;
  }

  Future<void> _toggle(Deadline d, bool done) async {
    final ok = await _run(() => widget.api.post('/deadlines/${d.id}/toggle', {'done': done}));
    if (ok && done && mounted) cheer(context);
  }

  Future<void> _submit(Deadline d, Future<void> Function() reload) async {
    final ok = await showSubmitSheet(context, widget.api, title: d.subject, deadlineId: d.id);
    if (ok == true) await reload();
  }

  Future<void> _actions(Deadline d, DlExtra x, Future<void> Function() reload) async {
    final api = widget.api;
    final due = _dueLabel(d);
    final a = await showDeadlineActions(context, d, x, due: due);
    if (a == null || !mounted) return;
    switch (a) {
      case DlAction.submit:
        await _submit(d, reload);
      case DlAction.task:
        await launchUrl(Uri.parse(x.description), mode: LaunchMode.externalApplication);
      case DlAction.remind:
        await showRemindSheet(context, api, d, x, due: due);
        await reload();
      case DlAction.done || DlAction.undone:
        await _toggle(d, a == DlAction.done);
        await reload();
      case DlAction.edit:
        final saved = await showDeadlineEdit(context, api, d: d, x: x);
        if (saved == true) {
          final text = x.editScope == 'me' && !x.personal ? 'Сохранено у тебя' : 'Сохранено';
          if (mounted) snack(context, text, kind: ToastKind.done);
          await reload();
        }
      case DlAction.delete:
        if (!await confirmDelete(context, x)) return;
        if (await _run(() => api.delete('/deadlines/${d.id}'))) await reload();
      case DlAction.resetMine:
        if (await _run(() => api.delete('/deadlines/${d.id}/mine'))) {
          if (mounted) snack(context, 'Снова как у всей группы', kind: ToastKind.done);
          await reload();
        }
      case DlAction.report:
        await openReportMenu(context, api, kind: 'deadline', id: d.id, onChanged: reload);
    }
  }

  Future<void> _add(Future<void> Function() reload) async {
    tick();
    final saved = await showDeadlineEdit(context, widget.api);
    if (saved == true) {
      if (mounted) snack(context, 'Срок добавлен — видишь только ты', kind: ToastKind.done);
      await reload();
    }
  }

  @override
  Widget build(BuildContext context) => Loader<_Items>(
    load: _load,
    onUnauthorized: widget.onUnauthorized,
    builder: (context, items, reload) => DeadlinesView(
      items: items.list,
      extra: items.extra,
      api: widget.api,
      sdo: items.sdo,
      onRetry: () => _retry(reload),
      onAdd: () => _add(reload),
      onOpen: (d) => _actions(d, items.extra[d.id] ?? DlExtra.fromJson(const {}), reload),
      onSubmit: (d) => _submit(d, reload),
      onToggle: (d, done) async {
        await _toggle(d, done);
        await reload();
      },
    ),
  );
}

/// Название срока с сервера — «Практика 5-6 · Анализ данных (Экз)»
/// (deadline_names.pretty): работа крупно, предмет — строкой под ней.
/// Вид контроля в скобках в строке не нужен — он есть в листе по нажатию.
({String task, String course}) splitTitle(String subject) {
  final i = subject.lastIndexOf(' · ');
  if (i <= 0) return (task: subject.trim(), course: '');
  final course = subject.substring(i + 3).replaceFirst(RegExp(r'\s*\((Экз|Зач)\)\s*$'), '').trim();
  return (task: subject.substring(0, i).trim(), course: course);
}

/// Горит — меньше суток до срока (сегодняшние всегда сюда же).
bool isBurning(Deadline d, DateTime at) => !d.done && d.due.isAfter(at) && d.due.difference(at).inHours < 24;

DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);

/// Дней от at до d по календарю (переход на летнее время не сбивает).
int _daysBetween(DateTime at, DateTime d) => (_day(d).difference(_day(at)).inHours / 24).round();

DateTime _monday(DateTime d) => _day(d).subtract(Duration(days: d.weekday - 1));

/// Подпись недели: «Эта неделя», «Следующая», дальше — даты недели.
String weekLabel(DateTime monday, DateTime at) {
  final n = _daysBetween(_monday(at), monday) ~/ 7;
  if (n <= 0) return 'Эта неделя';
  if (n == 1) return 'Следующая';
  final sun = monday.add(const Duration(days: 6));
  return monday.month == sun.month
      ? '${monday.day}–${sun.day} ${monthsGen[sun.month - 1]}'
      : '${monday.day} ${monthsGen[monday.month - 1]} – ${sun.day} ${monthsGen[sun.month - 1]}';
}

/// Вкладка «Сдать» по готовому списку; [at] — «сейчас» для тестов
/// (без него — часы, отсчёт и группы обновляются сами раз в полминуты).
class DeadlinesView extends StatefulWidget {
  final List<Deadline> items;
  final Map<int, DlExtra> extra;
  final Api api;
  final Future<void> Function(Deadline, bool) onToggle;
  final ValueChanged<Deadline> onSubmit, onOpen;
  final VoidCallback onAdd;
  final DateTime? at;

  /// Последняя проверка СДО (новый дизайн): «проверено в …» или «не ответил».
  final SdoCheck? sdo;
  final VoidCallback? onRetry;
  const DeadlinesView({
    super.key,
    required this.items,
    required this.extra,
    required this.api,
    required this.onToggle,
    required this.onSubmit,
    required this.onOpen,
    required this.onAdd,
    this.at,
    this.sdo,
    this.onRetry,
  });

  @override
  State<DeadlinesView> createState() => _DeadlinesViewState();
}

class _DeadlinesViewState extends State<DeadlinesView> {
  bool _done = false;
  Timer? _clock;

  @override
  void initState() {
    super.initState();
    if (widget.at == null) {
      _clock = Timer.periodic(const Duration(seconds: 30), (_) {
        if (mounted) setState(() {});
      });
    }
  }

  @override
  void dispose() {
    _clock?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final style = AppStyle.of(context);
    final p = style.p;
    final t = widget.at ?? now();
    final items = widget.items;
    final sdo = style.design2 ? widget.sdo : null;
    final sdoDown = sdo != null && !sdo.ok;
    final open = items.where((d) => !d.done && d.due.isAfter(t)).toList()..sort((a, b) => a.due.compareTo(b.due));
    final late = items.where((d) => !d.done && !d.due.isAfter(t)).toList()..sort((a, b) => b.due.compareTo(a.due));
    final done = items.where((d) => d.done).toList()..sort((a, b) => b.due.compareTo(a.due));
    // горит — крупно сверху, в неделях его не повторяем
    final hot = open.isNotEmpty && isBurning(open.first, t) ? open.first : null;
    final weeks = <DateTime, List<Deadline>>{};
    for (final d in open) {
      if (d != hot) (weeks[_monday(d.due)] ??= []).add(d);
    }

    Widget card(List<Deadline> list, {bool late = false}) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: Tile(
        padding: EdgeInsets.zero,
        child: Column(
          children: [
            for (var i = 0; i < list.length; i++) ...[
              if (i > 0) Divider(height: 1, color: p.line),
              _Row(
                d: list[i],
                x: widget.extra[list[i].id],
                at: t,
                late: late,
                onToggle: widget.onToggle,
                onOpen: widget.onOpen,
              ),
            ],
          ],
        ),
      ),
    );

    void push(Widget screen) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));

    return ListView(
      padding: const EdgeInsets.only(bottom: 120),
      children: [
        ScreenTitle(
          title: 'Сдать',
          trailing: IconButton.filled(
            tooltip: 'Свой срок',
            style: IconButton.styleFrom(backgroundColor: p.accent, foregroundColor: p.onAccent),
            onPressed: widget.onAdd,
            icon: const Icon(Icons.add_rounded),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
          child: Row(
            children: [
              Expanded(
                child: _Entry(
                  icon: Icons.assignment_outlined,
                  text: 'ДЗ группы',
                  onTap: () => push(HomeworkScreen(api: widget.api)),
                ),
              ),
              const SizedBox(width: Space.s),
              Expanded(
                child: _Entry(
                  icon: Icons.push_pin_outlined,
                  text: 'Заметки',
                  onTap: () => push(NotesScreen(api: widget.api)),
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
          child: _Segments(
            labels: ['Впереди · ${open.length}', 'Сдано · ${done.length}'],
            on: _done ? 1 : 0,
            onPick: (i) => setState(() => _done = i == 1),
          ),
        ),
        if (!_done) ...[
          if (sdoDown && open.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
              child: _SdoDown(text: sdoShownText(sdo.lastOk, t), onRetry: widget.onRetry),
            ),
          if (hot != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.l),
              child: _Hot(
                d: hot,
                x: widget.extra[hot.id],
                at: t,
                onDone: () => widget.onToggle(hot, true),
                onSubmit: () => widget.onSubmit(hot),
                onOpen: () => widget.onOpen(hot),
              ),
            ),
          if (open.isEmpty && sdoDown)
            Notice(
              title: 'СДО не ответил',
              text: sdoShownText(sdo.lastOk, t),
              pose: CapyPose.sad,
              onRetry: widget.onRetry,
              retryLabel: 'Попробовать ещё раз',
            )
          else if (open.isEmpty && style.design2)
            Notice(
              title: 'Ближайших сроков нет',
              text: sdo?.checkedAt != null
                  ? sdoCheckedText(sdo!.checkedAt!, t)
                  : 'Новые задания из СДО появятся здесь сами. Свой срок — кнопкой +.',
              pose: CapyPose.joy,
            )
          else if (open.isEmpty)
            Notice(
              title: late.isEmpty ? 'Всё сдано' : 'Новых сроков нет',
              text: 'Новые задания из СДО появятся здесь сами. Свой срок — кнопкой +.',
              pose: CapyPose.joy,
            ),
          for (final w in weeks.entries) ...[Section(weekLabel(w.key, t)), card(w.value)],
          if (late.isNotEmpty) ...[Section('Срок прошёл · ${late.length}'), card(late, late: true)],
        ] else if (done.isEmpty)
          const Notice(title: 'Пока ничего', text: 'Сданное появится здесь — свайп вправо по сроку или «Уже сдал».')
        else
          card(done),
      ],
    );
  }
}

/// «СДО не ответил» строкой над списком: сроки есть, но могли устареть.
class _SdoDown extends StatelessWidget {
  final String text;
  final VoidCallback? onRetry;
  const _SdoDown({required this.text, this.onRetry});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Tile(
      padding: const EdgeInsets.fromLTRB(Space.m, Space.m, Space.m, Space.s),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CapyImage(pose: CapyPose.sad, size: 44, color: p.muted),
          const SizedBox(width: Space.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('СДО не ответил', style: s.body(15, weight: FontWeight.w600)),
                const SizedBox(height: 2),
                Text(text, style: s.body(13, color: p.muted)),
                if (onRetry != null)
                  TextButton(
                    style: TextButton.styleFrom(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size(0, 36),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                    onPressed: onRetry,
                    child: Text('Попробовать ещё раз', style: s.body(14, color: p.accent)),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Переключатель «Впереди · 28 | Сдано · 4» — капсула с двумя половинами.
class _Segments extends StatelessWidget {
  final List<String> labels;
  final int on;
  final ValueChanged<int> onPick;
  const _Segments({required this.labels, required this.on, required this.onPick});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: p.line, borderRadius: BorderRadius.circular(Radii.pill)),
      child: Row(
        children: [
          for (var i = 0; i < labels.length; i++)
            Expanded(
              child: Semantics(
                button: true,
                selected: i == on,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () {
                    if (i == on) return;
                    tick();
                    onPick(i);
                  },
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    curve: Curves.easeOutCubic,
                    alignment: Alignment.center,
                    padding: const EdgeInsets.symmetric(horizontal: Space.s, vertical: 9),
                    decoration: BoxDecoration(
                      color: i == on ? p.accent : p.accent.withValues(alpha: 0),
                      borderRadius: BorderRadius.circular(Radii.pill),
                    ),
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text(
                        labels[i],
                        maxLines: 1,
                        style: s.body(14, weight: FontWeight.w600, color: i == on ? p.onAccent : p.muted),
                      ),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Плитка-вход: «ДЗ группы», «Заметки».
class _Entry extends StatelessWidget {
  final IconData icon;
  final String text;
  final VoidCallback onTap;
  const _Entry({required this.icon, required this.text, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Tile(
      onTap: onTap,
      padding: const EdgeInsets.symmetric(horizontal: Space.m, vertical: Space.m),
      child: Row(
        children: [
          Icon(icon, size: 20, color: s.p.accent),
          const SizedBox(width: Space.s),
          // одной строкой: на узком экране с крупным шрифтом — мельче (2.17)
          Expanded(
            child: FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(text, style: s.body(15, weight: FontWeight.w600), maxLines: 1, softWrap: false),
            ),
          ),
          Icon(Icons.chevron_right_rounded, size: 20, color: s.p.muted),
        ],
      ),
    );
  }
}

/// Пометки на карточке — только если есть что показать (время теста — в
/// новом дизайне и у несданного).
bool _hasChips(BuildContext context, Deadline d, DlExtra? x) =>
    x != null && x.hasChips(time: AppStyle.of(context).design2 && !d.done);

String _time(Deadline d) => d.dueTime.isEmpty ? '23:59' : d.dueTime;

String _dueLabel(Deadline d) {
  final due = d.due;
  return '${weekdaysShort[due.weekday - 1].toLowerCase()}, ${due.day} ${monthsGen[due.month - 1]} · ${_time(d)}';
}

/// Строка «● Анализ данных · 18:00»: точка цвета предмета, предмет и время.
class _SubjectLine extends StatelessWidget {
  final String course, rest;
  final double size;
  const _SubjectLine({required this.course, required this.rest, this.size = 13});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final text = [if (course.isNotEmpty) course, if (rest.isNotEmpty) rest].join(' · ');
    return Text.rich(
      TextSpan(
        children: [
          if (course.isNotEmpty) ...[
            WidgetSpan(
              alignment: PlaceholderAlignment.middle,
              child: Container(
                width: 7,
                height: 7,
                margin: const EdgeInsets.only(right: 6),
                decoration: BoxDecoration(color: s.ink(course), shape: BoxShape.circle),
              ),
            ),
          ],
          TextSpan(text: text),
        ],
      ),
      style: s.body(size, color: s.p.muted),
    );
  }
}

/// Горит: до срока меньше суток — крупно, с отсчётом и кнопкой «Сдать».
class _Hot extends StatelessWidget {
  final Deadline d;
  final DlExtra? x;
  final DateTime at;
  final VoidCallback onDone, onSubmit, onOpen;
  const _Hot({
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
    final c = p.danger;
    final left = d.due.difference(at);
    final h = left.inHours, m = left.inMinutes % 60;
    final when = _daysBetween(at, d.due) == 0 ? 'до ${_time(d)}' : 'завтра до ${_time(d)}';
    final name = splitTitle(d.subject);
    Widget unit(String u) => Padding(
      padding: const EdgeInsets.only(bottom: 5, left: 3, right: 8),
      child: Text(u, style: s.body(14, color: p.muted)),
    );
    final button = FilledButton.icon(
      style: FilledButton.styleFrom(
        backgroundColor: c,
        foregroundColor: p.dark ? p.bg : Colors.white,
        shape: const StadiumBorder(),
      ),
      onPressed: () {
        tick();
        if (d.canSubmit) {
          onSubmit();
        } else {
          onDone();
        }
      },
      icon: Icon(d.canSubmit ? Icons.upload_rounded : Icons.check_rounded, size: 18),
      label: Text(d.canSubmit ? 'Сдать' : 'Уже сдал'),
    );
    return Tile(
      onTap: onOpen,
      radius: Radii.card,
      gradient: LinearGradient(
        begin: Alignment.topRight,
        end: Alignment.bottomLeft,
        colors: [
          c.withValues(alpha: p.dark ? 0.34 : 0.2),
          p.cardSolid.withValues(alpha: p.dark ? 0.6 : 1),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(color: c, shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text('горит · $when', style: s.eyebrow(color: c)),
              ),
            ],
          ),
          const SizedBox(height: Space.s),
          Text(name.task, style: s.name(19)),
          if (name.course.isNotEmpty) ...[
            const SizedBox(height: 4),
            _SubjectLine(course: name.course, rest: '', size: 14),
          ],
          if (_hasChips(context, d, x)) ...[const SizedBox(height: Space.s), DlChips(x: x!)],
          const SizedBox(height: Space.m),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.bottomLeft,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      if (h > 0) ...[Text('$h', style: s.number(44, color: c)), unit('ч')],
                      Text(h > 0 ? m.toString().padLeft(2, '0') : '$m', style: s.number(44, color: c)),
                      unit('мин'),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: Space.m),
              button,
            ],
          ),
        ],
      ),
    );
  }
}

const _months = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

/// Дата слева: день недели (у прошедшего — месяц) и число; сегодня — красным,
/// завтра — жёлтым.
class _DateCol extends StatelessWidget {
  final DateTime day;
  final DateTime at;
  final bool past;
  const _DateCol({required this.day, required this.at, required this.past});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final n = _daysBetween(at, day);
    final color = past
        ? p.muted
        : n == 0
        ? p.danger
        : n == 1
        ? p.warn
        : p.text;
    return SizedBox(
      width: 40,
      child: Column(
        children: [
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              past ? _months[day.month - 1] : weekdaysShort[day.weekday - 1].toLowerCase(),
              style: s.body(12, color: p.muted),
            ),
          ),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text('${day.day}', style: s.number(22, color: color)),
          ),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final Deadline d;
  final DlExtra? x;
  final DateTime at;
  final bool late;
  final Future<void> Function(Deadline, bool) onToggle;
  final ValueChanged<Deadline> onOpen;
  const _Row({
    required this.d,
    required this.x,
    required this.at,
    required this.late,
    required this.onToggle,
    required this.onOpen,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final name = splitTitle(d.subject);
    final row = InkWell(
      onTap: () {
        tick();
        onOpen(d);
      },
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: Space.m, vertical: d.done ? Space.s + 2 : Space.m),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _DateCol(day: d.due, at: at, past: d.done || late),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name.task, style: s.name(15, color: d.done ? p.muted : null)),
                  if (name.course.isNotEmpty || !d.done) ...[
                    const SizedBox(height: 2),
                    _SubjectLine(course: name.course, rest: d.done ? '' : _time(d)),
                  ],
                  if (_hasChips(context, d, x)) ...[const SizedBox(height: 6), DlChips(x: x!, time: !d.done)],
                ],
              ),
            ),
            if (d.done) ...[const SizedBox(width: Space.s), Icon(Icons.check_rounded, color: p.ok, size: 20)],
          ],
        ),
      ),
    );
    return Dismissible(
      key: ValueKey('dl-${d.id}-${d.done}'),
      direction: DismissDirection.startToEnd,
      confirmDismiss: (_) async {
        tick();
        await onToggle(d, !d.done);
        return false;
      },
      background: Container(
        alignment: Alignment.centerLeft,
        padding: const EdgeInsets.only(left: Space.xl),
        color: d.done ? p.muted : p.ok,
        child: Text(
          d.done ? 'Вернуть' : 'Сдано',
          style: s.body(15, weight: FontWeight.w700, color: Colors.white),
        ),
      ),
      child: row,
    );
  }
}

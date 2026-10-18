// Свой срок и действия со сроком — как в WebApp (js/deadlines.js):
// лист «Новый срок / Изменить», лист действий по нажатию и «Напомнить».
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';

/// Поля срока, которых нет в модели Deadline, — прямо из ответа /api/deadlines.
class DlExtra {
  final String description;
  final bool personal, mineChanged, canEdit;

  /// Общий срок, который завёл человек (староста группы), — можно пожаловаться (5.99).
  final bool reportable;

  /// all — правка у всей группы, me — только у себя.
  final String editScope;
  final List<({String at, String label})> reminders;

  /// Тест СДО с ограничением по времени — минуты (quiz_time.py), иначе null.
  final int? timeLimit;

  DlExtra.fromJson(Map<String, dynamic> j)
    : description = (j['description'] as String? ?? '').trim(),
      personal = j['personal'] == true,
      mineChanged = j['mine_changed'] == true,
      canEdit = j['can_edit'] == true,
      reportable = j['reportable'] == true,
      editScope = j['edit_scope'] as String? ?? 'me',
      reminders = [for (final r in (j['reminders'] as List? ?? [])) (at: '${r['at']}', label: '${r['label']}')],
      timeLimit = (j['time_limit'] as num?)?.toInt();

  /// Описание-ссылка — это задание в СДО.
  bool get isLink => description.startsWith('http://') || description.startsWith('https://');

  /// Пометки есть — с [time] считается и время теста (только в новом дизайне).
  bool hasChips({bool time = false}) =>
      personal || mineChanged || reminders.isNotEmpty || (time && quizTimeText(timeLimit) != null);
}

/// Время теста из СДО: «15 мин», «1 ч», «1 ч 30 мин»; без ограничения — null.
String? quizTimeText(int? minutes) {
  if (minutes == null || minutes <= 0) return null;
  final h = minutes ~/ 60, m = minutes % 60;
  if (h == 0) return '$m мин';
  return m == 0 ? '$h ч' : '$h ч $m мин';
}

const _monthsShort = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

/// Быстрые даты: Сегодня, Завтра, ближайший понедельник (или пятница, если
/// понедельник совпал с «Завтра» или «Через неделю») и Через неделю.
List<({String label, DateTime date})> quickDates(DateTime t) {
  DateTime at(int n) => DateTime(t.year, t.month, t.day + n);
  int ahead(int dow) {
    final n = (dow - t.weekday + 7) % 7;
    return n == 0 ? 7 : n;
  }

  var mon = ahead(DateTime.monday);
  if (mon == 1 || mon == 7) mon = ahead(DateTime.friday);
  final m = at(mon);
  return [
    (label: 'Сегодня', date: at(0)),
    (label: 'Завтра', date: at(1)),
    (label: '${weekdaysShort[m.weekday - 1]}, ${m.day} ${_monthsShort[m.month - 1]}', date: m),
    (label: 'Через неделю', date: at(7)),
  ];
}

String _hm(TimeOfDay t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

/// Короткое сообщение — своей плашкой (widgets/common.dart, showToast).
void snack(BuildContext context, String text, {ToastKind kind = ToastKind.info}) =>
    showToast(context, text, kind: kind);

Future<T?> _sheet<T>(BuildContext context, Widget child) => showModalBottomSheet<T>(
  context: context,
  backgroundColor: AppStyle.of(context).p.cardSolid,
  showDragHandle: true,
  isScrollControlled: true,
  builder: (_) => child,
);

// ── Новый срок / изменить ──────────────────────────────────────────────

/// Лист срока: без [d] — новый личный, с ним — правка. true — сохранено.
Future<bool?> showDeadlineEdit(BuildContext context, Api api, {Deadline? d, DlExtra? x}) =>
    _sheet<bool>(context, DeadlineEditSheet(api: api, d: d, x: x));

class DeadlineEditSheet extends StatefulWidget {
  final Api api;
  final Deadline? d;
  final DlExtra? x;
  const DeadlineEditSheet({super.key, required this.api, this.d, this.x});

  @override
  State<DeadlineEditSheet> createState() => _DeadlineEditSheetState();
}

class _DeadlineEditSheetState extends State<DeadlineEditSheet> {
  late final _subject = TextEditingController(text: widget.d?.subject ?? '');
  late final _desc = TextEditingController(text: widget.x?.description ?? '');
  late DateTime _date;
  TimeOfDay? _time;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    final d = widget.d;
    final t = now();
    _date = d == null ? DateTime(t.year, t.month, t.day + 7) : (DateTime.tryParse(d.dueDate) ?? t);
    final hm = (d?.dueTime ?? '23:59').split(':');
    _time = hm.length == 2 ? TimeOfDay(hour: int.tryParse(hm[0]) ?? 23, minute: int.tryParse(hm[1]) ?? 59) : null;
  }

  @override
  void dispose() {
    _subject.dispose();
    _desc.dispose();
    super.dispose();
  }

  String get _hint {
    final x = widget.x;
    if (widget.d == null) return 'Личный — видишь только ты. Общие сроки группы добавляет староста.';
    if (x?.personal ?? false) return 'Личный — видишь только ты.';
    if (x?.editScope == 'all') return 'Общий срок — изменится у всей группы. Синк СДО его больше не перезапишет.';
    return 'Изменится только у тебя — у группы останется как было.';
  }

  Future<void> _pickDate() async {
    tick();
    final t = now();
    final got = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(t.year - 1),
      lastDate: DateTime(t.year + 2),
    );
    if (got != null) setState(() => _date = got);
  }

  Future<void> _pickTime() async {
    tick();
    final got = await showTimePicker(context: context, initialTime: _time ?? const TimeOfDay(hour: 23, minute: 59));
    if (got != null) setState(() => _time = got);
  }

  Future<void> _save() async {
    final subject = _subject.text.trim();
    if (subject.isEmpty) {
      setState(() => _error = 'Напиши, что сдать');
      return;
    }
    tick();
    setState(() {
      _busy = true;
      _error = null;
    });
    final body = {
      'subject': subject,
      'due_date': iso(_date),
      'due_time': _time == null ? '' : _hm(_time!),
      'description': _desc.text.trim(),
    };
    try {
      final d = widget.d;
      if (d == null) {
        await widget.api.post('/deadlines', body);
      } else {
        await widget.api.patch('/deadlines/${d.id}', body);
      }
      if (mounted) Navigator.pop(context, true);
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = isOffline(e) ? 'Нет интернета — не сохранилось.' : errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  InputDecoration _field(AppStyle s, String hint) => InputDecoration(
    hintText: hint,
    hintStyle: s.body(15, color: s.p.muted),
    filled: true,
    fillColor: s.p.card,
    contentPadding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(Radii.chip),
      borderSide: BorderSide(color: s.p.line),
    ),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(Radii.chip),
      borderSide: BorderSide(color: s.p.line),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final editing = widget.d != null;
    final picked = iso(_date);
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.xl + MediaQuery.viewInsetsOf(context).bottom),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(editing ? 'Изменить срок' : 'Новый срок', style: s.title(24)),
            const SizedBox(height: Space.s),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  widget.x?.editScope == 'all' && !(widget.x?.personal ?? false)
                      ? Icons.groups_outlined
                      : Icons.person_outline_rounded,
                  size: 18,
                  color: p.muted,
                ),
                const SizedBox(width: Space.s),
                Expanded(
                  child: Text(_hint, style: s.body(13, color: p.muted)),
                ),
              ],
            ),
            const SizedBox(height: Space.l),
            TextField(
              controller: _subject,
              autofocus: !editing,
              textCapitalization: TextCapitalization.sentences,
              style: s.body(16, weight: FontWeight.w600),
              decoration: _field(s, 'Что сдать'),
            ),
            const SizedBox(height: Space.l),
            Text('Когда', style: s.eyebrow()),
            const SizedBox(height: Space.s),
            Wrap(
              spacing: Space.s,
              runSpacing: Space.s,
              children: [
                for (final q in quickDates(now()))
                  ChoiceChip(
                    label: Text(q.label),
                    selected: iso(q.date) == picked,
                    showCheckmark: false,
                    selectedColor: p.accent,
                    labelStyle: s.body(14, weight: FontWeight.w600, color: iso(q.date) == picked ? p.onAccent : p.text),
                    backgroundColor: p.card,
                    side: BorderSide(color: p.line),
                    shape: const StadiumBorder(),
                    onSelected: (_) {
                      tick();
                      setState(() => _date = q.date);
                    },
                  ),
              ],
            ),
            const SizedBox(height: Space.m),
            Row(
              children: [
                Expanded(
                  child: _PickTile(
                    icon: Icons.calendar_today_outlined,
                    text: '${weekdaysShort[_date.weekday - 1]}, ${_date.day} ${monthsGen[_date.month - 1]}',
                    onTap: _pickDate,
                  ),
                ),
                const SizedBox(width: Space.s),
                Expanded(
                  child: _PickTile(
                    icon: Icons.schedule_rounded,
                    text: _time == null ? 'без времени' : _hm(_time!),
                    onTap: _pickTime,
                  ),
                ),
              ],
            ),
            const SizedBox(height: Space.l),
            TextField(
              controller: _desc,
              minLines: 2,
              maxLines: 5,
              textCapitalization: TextCapitalization.sentences,
              style: s.body(15),
              decoration: _field(s, 'Подробности — по желанию'),
            ),
            if (_error != null) ...[const SizedBox(height: Space.m), Text(_error!, style: s.body(14, color: p.danger))],
            const SizedBox(height: Space.l),
            SizedBox(
              width: double.infinity,
              height: 50,
              child: FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: p.accent,
                  foregroundColor: p.onAccent,
                  shape: const StadiumBorder(),
                ),
                onPressed: _busy ? null : _save,
                child: Text(editing ? 'Сохранить' : 'Добавить'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PickTile extends StatelessWidget {
  final IconData icon;
  final String text;
  final VoidCallback onTap;
  const _PickTile({required this.icon, required this.text, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Tile(
      onTap: onTap,
      radius: Radii.chip,
      padding: const EdgeInsets.symmetric(horizontal: Space.m, vertical: Space.m),
      child: Row(
        children: [
          Icon(icon, size: 18, color: s.p.accent),
          const SizedBox(width: Space.s),
          Expanded(
            child: Text(text, style: s.body(15, weight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}

// ── Действия со сроком ──────────────────────────────────────────────────

enum DlAction { submit, task, remind, done, undone, edit, delete, resetMine, report }

/// Лист по нажатию на срок; возвращает выбранное действие.
Future<DlAction?> showDeadlineActions(BuildContext context, Deadline d, DlExtra x, {required String due}) =>
    _sheet<DlAction>(context, _ActionsSheet(d: d, x: x, due: due));

class _ActionsSheet extends StatelessWidget {
  final Deadline d;
  final DlExtra x;
  final String due;
  const _ActionsSheet({required this.d, required this.x, required this.due});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    Widget act(DlAction a, IconData icon, String text, {Color? color}) => ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(icon, color: color ?? p.accent),
      title: Text(
        text,
        style: s.body(16, weight: FontWeight.w600, color: color),
      ),
      onTap: () {
        tick();
        Navigator.pop(context, a);
      },
    );
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(d.done ? 'сдано' : 'до $due', style: s.eyebrow()),
            const SizedBox(height: 4),
            Text(d.subject, style: s.name(20)),
            if (x.description.isNotEmpty && !x.isLink) ...[
              const SizedBox(height: Space.s),
              Text(x.description, style: s.body(14, color: p.muted)),
            ],
            if (x.hasChips(time: s.design2 && !d.done)) ...[
              const SizedBox(height: Space.m),
              DlChips(x: x, time: !d.done),
            ],
            const SizedBox(height: Space.s),
            if (d.canSubmit && !d.done) act(DlAction.submit, Icons.upload_rounded, 'Сдать файлом'),
            if (x.isLink) act(DlAction.task, Icons.open_in_new_rounded, 'Задание в СДО'),
            if (!d.done) act(DlAction.remind, Icons.notifications_none_rounded, 'Напомнить'),
            if (d.done)
              act(DlAction.undone, Icons.undo_rounded, 'Вернуть в активные')
            else
              act(DlAction.done, Icons.check_rounded, 'Уже сдал'),
            if (x.canEdit) act(DlAction.edit, Icons.edit_outlined, 'Изменить'),
            if (x.mineChanged) act(DlAction.resetMine, Icons.restart_alt_rounded, 'Как у всех'),
            if (x.canEdit)
              act(
                DlAction.delete,
                Icons.delete_outline_rounded,
                x.editScope == 'me' ? 'Убрать у себя' : 'Удалить',
                color: p.danger,
              ),
            if (x.reportable) act(DlAction.report, Icons.flag_outlined, 'Пожаловаться или скрыть', color: p.muted),
          ],
        ),
      ),
    );
  }
}

/// Пометки срока: время теста (новый дизайн), личный, изменён у тебя, напоминания.
class DlChips extends StatelessWidget {
  final DlExtra x;

  /// Показать время теста — у сданного не нужно.
  final bool time;
  const DlChips({super.key, required this.x, this.time = true});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    Widget chip(IconData icon, String text, Color c) => Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.s, vertical: 3),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(Radii.pill)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: c),
          const SizedBox(width: 4),
          Text(
            text,
            style: s.body(12, weight: FontWeight.w600, color: c),
          ),
        ],
      ),
    );
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        if (time && s.design2 && quizTimeText(x.timeLimit) != null)
          KeyedSubtree(
            key: const ValueKey('quiz-time'),
            child: chip(Icons.timer_outlined, quizTimeText(x.timeLimit)!, p.muted),
          ),
        if (x.personal) chip(Icons.person_outline_rounded, 'личный', p.muted),
        if (x.mineChanged) chip(Icons.edit_outlined, 'изменён у тебя', p.accent),
        for (final r in x.reminders) chip(Icons.notifications_none_rounded, r.label, p.warn),
      ],
    );
  }
}

/// Спросить «точно?» перед удалением.
Future<bool> confirmDelete(BuildContext context, DlExtra x) => confirmSheet(
  context,
  title: x.editScope == 'me' ? 'Убрать у себя?' : 'Удалить срок?',
  text: x.editScope == 'me' ? 'У группы этот срок останется.' : 'Вернуть его не получится.',
  action: 'Убрать',
  cancel: 'Оставить',
  danger: true,
);

// ── Напомнить ────────────────────────────────────────────────────────────

/// Свои напоминания о сроке (deadline_reminders.py): за день, за 3 часа,
/// за час или своё время по Москве. После листа список сроков обновить.
Future<void> showRemindSheet(BuildContext context, Api api, Deadline d, DlExtra x, {required String due}) =>
    _sheet<void>(context, RemindSheet(api: api, d: d, reminders: x.reminders, due: due));

class RemindSheet extends StatefulWidget {
  final Api api;
  final Deadline d;
  final List<({String at, String label})> reminders;
  final String due;
  const RemindSheet({super.key, required this.api, required this.d, required this.reminders, required this.due});

  @override
  State<RemindSheet> createState() => _RemindSheetState();
}

class _RemindSheetState extends State<RemindSheet> {
  late final _list = [...widget.reminders];
  String? _error;

  Future<void> _add(Map<String, String> body) async {
    tick();
    setState(() => _error = null);
    try {
      final r = await widget.api.post('/deadlines/${widget.d.id}/remind', body);
      setState(() {
        _list
          ..add((at: '${r['at']}', label: '${r['label']}'))
          ..sort((a, b) => a.at.compareTo(b.at));
      });
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = errorText(e));
    }
  }

  Future<void> _remove(String at) async {
    tick();
    try {
      await widget.api.delete('/deadlines/${widget.d.id}/remind?at=${Uri.encodeQueryComponent(at)}');
      setState(() => _list.removeWhere((r) => r.at == at));
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = errorText(e));
    }
  }

  Future<void> _custom() async {
    tick();
    final t = now();
    final due = widget.d.due;
    final day = await showDatePicker(
      context: context,
      initialDate: due.isAfter(t) ? DateTime(due.year, due.month, due.day) : t,
      firstDate: DateTime(t.year, t.month, t.day),
      lastDate: DateTime(due.year, due.month, due.day + 1),
    );
    if (day == null || !mounted) return;
    final time = await showTimePicker(context: context, initialTime: const TimeOfDay(hour: 9, minute: 0));
    if (time == null) return;
    await _add({'at': '${iso(day)}T${_hm(time)}'});
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    Widget preset(String label, String code) => ActionChip(
      label: Text(label),
      labelStyle: s.body(14, weight: FontWeight.w600),
      backgroundColor: p.card,
      side: BorderSide(color: p.line),
      shape: const StadiumBorder(),
      onPressed: () => _add({'preset': code}),
    );
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Напомнить', style: s.title(24)),
            const SizedBox(height: 4),
            Text('${widget.d.subject} — до ${widget.due}', style: s.body(14, color: p.muted)),
            const SizedBox(height: Space.l),
            for (final r in _list)
              Padding(
                padding: const EdgeInsets.only(bottom: Space.s),
                child: Tile(
                  padding: const EdgeInsets.only(left: Space.l),
                  child: Row(
                    children: [
                      Icon(Icons.notifications_active_outlined, size: 18, color: p.warn),
                      const SizedBox(width: Space.s),
                      Expanded(
                        child: Text(r.label, style: s.body(15, weight: FontWeight.w600)),
                      ),
                      IconButton(
                        tooltip: 'Убрать напоминание',
                        onPressed: () => _remove(r.at),
                        icon: Icon(Icons.close_rounded, size: 18, color: p.muted),
                      ),
                    ],
                  ),
                ),
              ),
            Wrap(
              spacing: Space.s,
              runSpacing: Space.s,
              children: [
                preset('за день', '1d'),
                preset('за 3 часа', '3h'),
                preset('за час', '1h'),
                ActionChip(
                  avatar: Icon(Icons.edit_calendar_outlined, size: 16, color: p.accent),
                  label: const Text('своё время'),
                  labelStyle: s.body(14, weight: FontWeight.w600),
                  backgroundColor: p.card,
                  side: BorderSide(color: p.line),
                  shape: const StadiumBorder(),
                  onPressed: _custom,
                ),
              ],
            ),
            const SizedBox(height: Space.s),
            Text('Своё время — по Москве.', style: s.body(12, color: p.muted)),
            if (_error != null) ...[const SizedBox(height: Space.m), Text(_error!, style: s.body(14, color: p.danger))],
            const SizedBox(height: Space.l),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                style: OutlinedButton.styleFrom(
                  foregroundColor: p.text,
                  side: BorderSide(color: p.line),
                  shape: const StadiumBorder(),
                ),
                onPressed: () => Navigator.pop(context),
                child: const Text('Готово'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

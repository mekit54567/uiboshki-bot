// ДЗ группы (доска старосты, /addhw в боте) и заметки к парам на сегодня
// и завтра (/note в боте, «+» — здесь же) — входы плитками на вкладке «Сдать».
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/common.dart';
import '../widgets/report.dart';
import 'deadline_edit.dart' show snack;
import 'files.dart' show BackRow;
import 'legal.dart' show LegalLink, openLegal;

class Homework {
  final int id;
  final String subject, content, lessonDate;
  final bool hasFile;

  /// Своё — без «Пожаловаться» (сервер: mine).
  final bool mine;

  Homework.fromJson(Map<String, dynamic> j)
    : id = j['id'] as int,
      subject = j['subject'] as String? ?? '',
      content = j['content'] as String? ?? '',
      lessonDate = j['lesson_date'] as String? ?? '',
      hasFile = j['has_file'] == true,
      mine = j['mine'] == true;
}

/// «пт, 9 окт» — везде на доске ДЗ и в заметках один формат (владелец, 2.14).
String shortDay(String isoDate) {
  final d = DateTime.tryParse(isoDate);
  if (d == null) return isoDate;
  return '${weekdaysShort[d.weekday - 1].toLowerCase()}, ${d.day} ${monthsShort[d.month - 1]}';
}

/// Задание к прошедшей паре (срок раньше сегодня) — вниз, под «Прошло».
bool homeworkPast(Homework h, DateTime today) {
  final d = DateTime.tryParse(h.lessonDate);
  return d != null && d.isBefore(DateTime(today.year, today.month, today.day));
}

/// Экран поверх вкладок: фон, «назад», загрузка.
class _Page<T> extends StatelessWidget {
  final Future<T> Function() load;
  final Widget Function(BuildContext, T) builder;
  const _Page({super.key, required this.load, required this.builder});

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Backdrop(
      child: SafeArea(
        child: Loader<T>(load: load, builder: (context, data, _) => builder(context, data)),
      ),
    ),
  );
}

class HomeworkScreen extends StatefulWidget {
  final Api api;
  const HomeworkScreen({super.key, required this.api});

  @override
  State<HomeworkScreen> createState() => _HomeworkScreenState();
}

class _HomeworkScreenState extends State<HomeworkScreen> {
  int _epoch = 0; // скрыл автора — список заново

  Api get api => widget.api;

  Future<void> _send(BuildContext context, Homework h) async {
    tick();
    try {
      await api.post('/homework/${h.id}/send');
      if (context.mounted) snack(context, 'Отправил в Telegram — файл в чате с ботом.', kind: ToastKind.done);
    } on ApiError catch (e) {
      // Аккаунт без Telegram: сервер объяснит, почему не вышло.
      if (context.mounted) snack(context, e.message, kind: ToastKind.error);
    } catch (e) {
      if (context.mounted) snack(context, errorText(e), kind: ToastKind.error);
    }
  }

  @override
  Widget build(BuildContext context) => _Page<List<Homework>>(
    key: ValueKey(_epoch),
    load: () async => [for (final h in (await api.get('/homework'))['items'] as List) Homework.fromJson(h)],
    builder: (context, items) {
      final t = now();
      final past = [
        for (final h in items)
          if (homeworkPast(h, t)) h,
      ];
      final ahead = [
        for (final h in items)
          if (!homeworkPast(h, t)) h,
      ];
      Widget card(Homework h, {bool past = false}) => Padding(
        padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
        child: Opacity(
          opacity: past ? 0.55 : 1,
          child: _HomeworkCard(
            h: h,
            past: past,
            onSend: () => _send(context, h),
            report: h.mine
                ? null
                : ReportButton(api: api, kind: 'hw', id: h.id, onChanged: () => setState(() => _epoch++)),
          ),
        ),
      );
      return ListView(
        padding: const EdgeInsets.only(bottom: Space.xxl),
        children: [
          const BackRow(),
          const ScreenTitle(title: 'ДЗ группы'),
          if (items.isEmpty)
            const Notice(
              title: 'Доска ДЗ пока пустая',
              text: 'Староста добавит задания — они появятся тут.',
              pose: CapyPose.joy,
            ),
          for (final h in ahead) card(h),
          if (past.isNotEmpty) ...[const Section('Прошло'), for (final h in past) card(h, past: true)],
        ],
      );
    },
  );
}

class _HomeworkCard extends StatelessWidget {
  final Homework h;
  final VoidCallback onSend;

  /// Пара уже была — дата без «горящего» цвета.
  final bool past;

  /// «⋯» — пожаловаться или скрыть автора (чужое ДЗ).
  final Widget? report;
  const _HomeworkCard({required this.h, required this.onSend, this.past = false, this.report});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Tile(
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              width: 3,
              margin: const EdgeInsets.only(right: Space.m),
              decoration: BoxDecoration(color: s.ink(h.subject), borderRadius: BorderRadius.circular(2)),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(h.subject, style: s.body(15, weight: FontWeight.w600)),
                  if (h.content.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(h.content, style: s.body(14, color: p.muted)),
                  ],
                  if (h.lessonDate.isNotEmpty) ...[
                    const SizedBox(height: Space.s),
                    Row(
                      children: [
                        Icon(Icons.event_outlined, size: 14, color: past ? p.muted : p.warn),
                        const SizedBox(width: 4),
                        Text(
                          'к паре · ${shortDay(h.lessonDate)}',
                          style: s.body(12, weight: FontWeight.w600, color: past ? p.muted : p.warn),
                        ),
                      ],
                    ),
                  ],
                  if (h.hasFile) ...[
                    const SizedBox(height: Space.s),
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: p.text,
                        side: BorderSide(color: p.line),
                        shape: const StadiumBorder(),
                        visualDensity: VisualDensity.compact,
                      ),
                      onPressed: onSend,
                      icon: const Icon(Icons.attach_file_rounded, size: 16),
                      label: const Text('Прислать файл'),
                    ),
                  ],
                ],
              ),
            ),
            if (report != null) Align(alignment: Alignment.topRight, child: report),
          ],
        ),
      ),
    );
  }
}

class Note {
  final int id;
  final String subject, text;

  /// Своя заметка — её можно убрать отсюда (сервер: mine).
  final bool mine;
  Note.fromJson(Map<String, dynamic> j)
    : id = (j['id'] as num?)?.toInt() ?? 0,
      subject = j['subject'] as String? ?? '',
      text = j['text'] as String? ?? '',
      mine = j['mine'] == true;
}

/// Заметки к парам: сегодня и завтра — как /note в боте; «+» — своя заметка
/// к паре или дню прямо отсюда (владелец, 09.10, 2.9), её видит вся группа.
class NotesScreen extends StatefulWidget {
  final Api api;
  const NotesScreen({super.key, required this.api});

  @override
  State<NotesScreen> createState() => _NotesScreenState();
}

class _NotesScreenState extends State<NotesScreen> {
  int _epoch = 0; // добавили или убрали — список заново

  Api get api => widget.api;

  Future<List<Note>> _day(DateTime d) async {
    final j = await api.get('/notes?date=${iso(d)}');
    return [for (final n in (j['items'] as List? ?? [])) Note.fromJson(n)];
  }

  Future<void> _add() async {
    tick();
    final saved = await appSheet<String>(context, (_) => NoteSheet(api: api));
    if (saved == null || !mounted) return;
    showToast(context, saved, kind: ToastKind.done);
    setState(() => _epoch++);
  }

  Future<void> _delete(Note n) async {
    final ok = await confirmSheet(
      context,
      title: 'Убрать заметку?',
      text: 'Она пропадёт у всей группы.',
      action: 'Убрать',
      danger: true,
    );
    if (!ok || !mounted) return;
    try {
      await api.delete('/notes/${n.id}');
    } on ApiError catch (e) {
      if (mounted) showToast(context, e.message, kind: ToastKind.error);
      return;
    } catch (e) {
      if (mounted) showToast(context, errorText(e), kind: ToastKind.error);
      return;
    }
    if (mounted) setState(() => _epoch++);
  }

  @override
  Widget build(BuildContext context) {
    final t = now();
    final today = DateTime(t.year, t.month, t.day);
    final tomorrow = DateTime(t.year, t.month, t.day + 1);
    final p = AppStyle.of(context).p;
    return _Page<List<List<Note>>>(
      key: ValueKey(_epoch),
      load: () => Future.wait([_day(today), _day(tomorrow)]),
      builder: (context, days) {
        final s = AppStyle.of(context);
        final total = days[0].length + days[1].length;
        return ListView(
          padding: const EdgeInsets.only(bottom: Space.xxl),
          children: [
            const BackRow(),
            ScreenTitle(
              title: 'Заметки',
              trailing: IconButton.filled(
                key: const Key('notes:add'),
                tooltip: 'Новая заметка',
                style: IconButton.styleFrom(backgroundColor: p.accent, foregroundColor: p.onAccent),
                onPressed: _add,
                icon: const Icon(Icons.add_rounded),
              ),
            ),
            if (total == 0)
              const Notice(
                title: 'Заметок нет',
                text: 'Пометку к паре или дню добавь кнопкой «+» — её увидит вся группа под расписанием.',
                pose: CapyPose.joy,
              ),
            for (final (i, notes) in days.indexed)
              if (notes.isNotEmpty) ...[
                Section(i == 0 ? 'Сегодня · ${shortDay(iso(today))}' : 'Завтра · ${shortDay(iso(tomorrow))}'),
                for (final n in notes)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
                    child: Tile(
                      padding: EdgeInsets.fromLTRB(Space.l, Space.l, n.id > 0 ? Space.xs : Space.l, Space.l),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(Icons.push_pin_outlined, size: 18, color: s.p.accent),
                          const SizedBox(width: Space.m),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (n.subject.isNotEmpty) Text(n.subject, style: s.body(15, weight: FontWeight.w600)),
                                Text(n.text, style: s.body(15)),
                              ],
                            ),
                          ),
                          if (n.mine && n.id > 0)
                            IconButton(
                              tooltip: 'Убрать заметку',
                              visualDensity: VisualDensity.compact,
                              onPressed: () => _delete(n),
                              icon: Icon(Icons.delete_outline_rounded, size: 20, color: s.p.muted),
                            )
                          else if (n.id > 0)
                            ReportButton(api: api, kind: 'note', id: n.id, onChanged: () => setState(() => _epoch++)),
                        ],
                      ),
                    ),
                  ),
              ],
          ],
        );
      },
    );
  }
}

/// Лист «Новая заметка»: день (сегодня, завтра или другой), пара этого дня
/// (по желанию) и текст. Сохранил — лист закрывается с подписью для плашки.
class NoteSheet extends StatefulWidget {
  final Api api;
  const NoteSheet({super.key, required this.api});

  @override
  State<NoteSheet> createState() => _NoteSheetState();
}

class _NoteSheetState extends State<NoteSheet> {
  final _text = TextEditingController();
  late DateTime _date;
  String _subject = '';
  List<String> _subjects = [];
  int _asked = 0; // ответ о парах прошлого выбранного дня не подменит нынешний
  String? _error;
  bool _busy = false;

  static const maxLen = 500; // как NOTE_MAX в боте

  @override
  void initState() {
    super.initState();
    final t = now();
    _date = DateTime(t.year, t.month, t.day + 1);
    _loadSubjects();
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  /// Пары выбранного дня — чипами: заметка «к паре» одним нажатием.
  Future<void> _loadSubjects() async {
    final asked = ++_asked;
    List<String> got = [];
    try {
      final j = await widget.api.get('/day?date=${iso(_date)}');
      for (final l in (j['lessons'] as List? ?? [])) {
        final t = '${l['title'] ?? ''}'.trim();
        if (t.isNotEmpty && !got.contains(t)) got.add(t);
      }
    } catch (_) {
      got = [];
    }
    if (!mounted || asked != _asked) return;
    setState(() {
      _subjects = got;
      if (!got.contains(_subject)) _subject = '';
    });
  }

  void _setDate(DateTime d) {
    tick();
    setState(() => _date = d);
    _loadSubjects();
  }

  Future<void> _pickDate() async {
    tick();
    final t = now();
    final got = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(t.year, t.month, t.day),
      lastDate: DateTime(t.year, t.month + 6, t.day),
    );
    if (got != null) _setDate(got);
  }

  Future<void> _save() async {
    final text = _text.text.trim();
    if (text.isEmpty) {
      setState(() => _error = 'Напиши, что запомнить');
      return;
    }
    tick();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.post('/notes', {'date': iso(_date), 'subject': _subject, 'text': text});
      if (mounted) Navigator.pop(context, 'Заметка на ${shortDay(iso(_date))} — видна всей группе');
    } on ApiError catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _chip(String label, bool selected, VoidCallback onTap) {
    final s = AppStyle.of(context);
    final p = s.p;
    return ChoiceChip(
      label: Text(label, softWrap: true, maxLines: 2),
      selected: selected,
      showCheckmark: false,
      selectedColor: p.accent,
      labelStyle: s.body(14, weight: FontWeight.w600, color: selected ? p.onAccent : p.text),
      backgroundColor: p.card,
      side: BorderSide(color: p.line),
      shape: const StadiumBorder(),
      onSelected: (_) => onTap(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final t = now();
    final today = DateTime(t.year, t.month, t.day);
    final tomorrow = DateTime(t.year, t.month, t.day + 1);
    final other = iso(_date) != iso(today) && iso(_date) != iso(tomorrow);
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.xl + MediaQuery.viewInsetsOf(context).bottom),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Новая заметка', style: s.title(24)),
            const SizedBox(height: Space.s),
            Text('Увидит вся группа — под расписанием этого дня.', style: s.body(13, color: p.muted)),
            // правило Apple 1.2: согласие с правилами — у кнопки, которой публикуют
            GestureDetector(
              key: const Key('note:rules'),
              onTap: () => openLegal(context, widget.api, 'rules'),
              child: Text.rich(
                TextSpan(
                  text: 'Добавляя, соглашаешься с ',
                  style: s.body(13, color: p.muted),
                  children: [
                    TextSpan(
                      text: 'Правилами Капибары',
                      style: TextStyle(color: p.link),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: Space.l),
            Text('Когда', style: s.eyebrow()),
            const SizedBox(height: Space.s),
            Wrap(
              spacing: Space.s,
              runSpacing: Space.s,
              children: [
                _chip('Сегодня', iso(_date) == iso(today), () => _setDate(today)),
                _chip('Завтра', iso(_date) == iso(tomorrow), () => _setDate(tomorrow)),
                _chip(other ? shortDay(iso(_date)) : 'Другой день', other, _pickDate),
              ],
            ),
            if (_subjects.isNotEmpty) ...[
              const SizedBox(height: Space.l),
              Text('К паре', style: s.eyebrow()),
              const SizedBox(height: Space.s),
              Wrap(
                spacing: Space.s,
                runSpacing: Space.s,
                children: [
                  _chip('Ко всему дню', _subject.isEmpty, () {
                    tick();
                    setState(() => _subject = '');
                  }),
                  for (final subj in _subjects)
                    _chip(subj, _subject == subj, () {
                      tick();
                      setState(() => _subject = subj);
                    }),
                ],
              ),
            ],
            const SizedBox(height: Space.l),
            TextField(
              key: const Key('note:text'),
              controller: _text,
              autofocus: true,
              minLines: 2,
              maxLines: 5,
              maxLength: maxLen,
              textCapitalization: TextCapitalization.sentences,
              style: s.body(16),
              cursorColor: p.accent,
              decoration: fieldDecoration(s, 'Контрольная, принести ноутбук…'),
            ),
            if (_error != null) ...[const SizedBox(height: Space.s), Text(_error!, style: s.body(14, color: p.danger))],
            const SizedBox(height: Space.m),
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
                child: const Text('Сохранить'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

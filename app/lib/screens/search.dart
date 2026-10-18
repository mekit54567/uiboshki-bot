// Поиск расписания любой группы, преподавателя или аудитории МИРЭА (как
// вкладка поиска в WebApp, search.js): справочник на сервере, у однофамильцев
// подсказка. Закреплённые — на сервере (видны с любого устройства), недавние —
// на этом телефоне. Нажал — расписание на 8 недель, недели листаются.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api.dart';
import '../api/guest.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/capy_refresh.dart';
import '../widgets/common.dart';
import 'files.dart' show BackRow;
import 'lesson.dart' show openLesson;
import 'today.dart' show LessonList;

/// Чьё расписание: тип (1 — группа, 2 — преподаватель, 3 — аудитория), id, название.
class Target {
  final int type, id;
  final String title, hint;
  const Target(this.type, this.id, this.title, [this.hint = '']);

  factory Target.fromJson(Map j) =>
      Target((j['type'] as num).toInt(), (j['id'] as num).toInt(), '${j['title']}', '${j['hint'] ?? ''}');

  Map<String, Object> toJson() => {'type': type, 'id': id, 'title': title};

  bool same(Target o) => o.type == type && o.id == id;
}

const _kinds = {
  1: ('Группа', Icons.groups_outlined),
  2: ('Преподаватель', Icons.person_outline_rounded),
  3: ('Аудитория', Icons.meeting_room_outlined),
};

void openSearch(BuildContext context, Api api) =>
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => SearchScreen(api: api)));

// Недавние — с приставкой запаса ответов API: «выйти» стирает их вместе с ним.
const _recentKey = 'uib_cache:recent_targets';

Future<List<Target>> _recent() async {
  try {
    final raw = (await SharedPreferences.getInstance()).getString(_recentKey);
    if (raw == null) return [];
    return [for (final j in jsonDecode(raw) as List) Target.fromJson(j as Map)];
  } catch (_) {
    return [];
  }
}

Future<void> rememberTarget(Target t) async {
  try {
    final list = [t, ...(await _recent()).where((x) => !x.same(t))].take(6);
    await (await SharedPreferences.getInstance()).setString(_recentKey, jsonEncode([for (final x in list) x.toJson()]));
  } catch (_) {}
}

/// Открыть расписание и запомнить в недавних.
Future<void> openTargetScreen(BuildContext context, Api api, Target t) async {
  tick();
  unawaited(rememberTarget(t));
  await Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => TargetScreen(api: api, type: t.type, id: t.id, title: t.title),
    ),
  );
}

class SearchScreen extends StatefulWidget {
  final Api api;
  const SearchScreen({super.key, required this.api});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _q = TextEditingController();
  Timer? _debounce;
  int _seq = 0;
  int _type = 0; // 0 — все типы

  List<Target>? _items; // null — ещё не искали (короткий запрос)
  bool _ready = true, _busy = false, _failed = false;
  String _failedText = '';
  List<Target> _pins = [], _recents = [];

  @override
  void initState() {
    super.initState();
    _loadSaved();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _q.dispose();
    super.dispose();
  }

  Future<void> _loadSaved() async {
    var pins = _pins;
    try {
      pins = [for (final j in (await widget.api.get('/pins'))['items'] as List) Target.fromJson(j as Map)];
    } catch (_) {}
    final recents = await _recent();
    if (mounted) {
      setState(() {
        _pins = pins;
        _recents = recents;
      });
    }
  }

  void _changed(String _) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 250), _search);
    setState(() {}); // крестик «очистить»
  }

  Future<void> _search() async {
    _debounce?.cancel();
    final my = ++_seq; // ответ на старый запрос не перетирает новый
    final q = _q.text.trim();
    if (q.length < 2) {
      setState(() {
        _items = null;
        _busy = _failed = false;
      });
      return;
    }
    setState(() {
      _busy = true;
      _failed = false;
    });
    try {
      final r = await widget.api.get('/search?q=${Uri.encodeQueryComponent(q)}&type=$_type');
      if (my != _seq || !mounted) return;
      setState(() {
        _items = [for (final j in r['items'] as List) Target.fromJson(j as Map)];
        _ready = r['ready'] != false;
        _busy = false;
      });
    } catch (e) {
      if (my != _seq || !mounted) return;
      setState(() {
        _busy = false;
        _failed = true;
        _failedText = errorText(e);
      });
    }
  }

  Future<void> _open(Target t) async {
    await openTargetScreen(context, widget.api, t);
    _loadSaved(); // там могли закрепить или открепить
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final searching = _q.text.trim().length >= 2;
    return Scaffold(
      body: Backdrop(
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.only(bottom: Space.xxl),
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            children: [
              const BackRow(),
              const ScreenTitle(title: 'Поиск'),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: Space.l),
                child: TextField(
                  controller: _q,
                  autofocus: true, // сразу с курсором в поле (2.6)
                  onChanged: _changed,
                  onSubmitted: (_) => _search(),
                  textInputAction: TextInputAction.search,
                  style: s.body(17, weight: FontWeight.w600),
                  decoration: InputDecoration(
                    hintText: 'Фамилия, группа или аудитория',
                    hintStyle: s.body(17, color: p.muted),
                    prefixIcon: Icon(Icons.search_rounded, color: p.muted),
                    suffixIcon: _q.text.isEmpty
                        ? null
                        : IconButton(
                            tooltip: 'Очистить',
                            icon: Icon(Icons.close_rounded, color: p.muted),
                            onPressed: () {
                              _q.clear();
                              _search();
                            },
                          ),
                    filled: true,
                    fillColor: p.card,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(Radii.tile),
                      borderSide: BorderSide(color: p.line),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(Radii.tile),
                      borderSide: BorderSide(color: p.line),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: Space.m),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: Space.l),
                child: Row(
                  children: [
                    for (final (type, label) in const [
                      (0, 'Все'),
                      (1, 'Группы'),
                      (2, 'Преподаватели'),
                      (3, 'Аудитории'),
                    ])
                      _TypeChip(
                        label: label,
                        selected: _type == type,
                        onTap: () {
                          tick();
                          setState(() => _type = type);
                          _search();
                        },
                      ),
                  ],
                ),
              ),
              const SizedBox(height: Space.s),
              if (searching) ..._results(context) else ..._saved(context),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _results(BuildContext context) {
    final items = _items;
    if (_failed) {
      return [Notice(title: 'Не получилось', text: _failedText, onRetry: _search, pose: CapyPose.sad)];
    }
    if (_busy || items == null) {
      return [
        Padding(
          padding: const EdgeInsets.all(Space.xl),
          child: Center(child: CircularProgressIndicator(color: AppStyle.of(context).p.accent, strokeWidth: 2.5)),
        ),
      ];
    }
    if (items.isEmpty) {
      return [
        _ready
            ? const Notice(
                title: 'Ничего не нашлось',
                text: 'Проверь, как написано, или попробуй часть фамилии.',
                pose: CapyPose.sad,
              )
            : const Notice(
                title: 'Справочник ещё собирается',
                text: 'Первый запуск занимает около получаса — попробуй чуть позже.',
              ),
      ];
    }
    return [for (final t in items) _TargetRow(target: t, pinned: _pins.any(t.same), onTap: () => _open(t))];
  }

  List<Widget> _saved(BuildContext context) {
    final recents = _recents.where((t) => !_pins.any(t.same)).toList();
    if (_pins.isEmpty && recents.isEmpty) {
      return const [
        Notice(
          title: 'Чьё расписание ищем?',
          text:
              'Начни вводить фамилию преподавателя, номер группы или аудитории — например «Морозов» или «УИБО-03». '
              'Нужное можно закрепить.',
        ),
      ];
    }
    return [
      if (_pins.isNotEmpty) ...[
        const Section('Закреплённые'),
        for (final t in _pins) _TargetRow(target: t, pinned: true, onTap: () => _open(t)),
      ],
      if (recents.isNotEmpty) ...[
        const Section('Недавние'),
        for (final t in recents) _TargetRow(target: t, onTap: () => _open(t)),
      ],
    ];
  }
}

class _TypeChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _TypeChip({required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Padding(
      padding: const EdgeInsets.only(right: Space.s),
      child: Semantics(
        button: true,
        selected: selected,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.symmetric(horizontal: Space.m, vertical: Space.s),
            decoration: BoxDecoration(
              color: selected ? p.text : p.card,
              borderRadius: BorderRadius.circular(Radii.pill),
              border: Border.all(color: selected ? p.text : p.line),
            ),
            child: Text(
              label,
              style: s.body(14, weight: FontWeight.w600, color: selected ? p.bg : p.text),
            ),
          ),
        ),
      ),
    );
  }
}

class _TargetRow extends StatelessWidget {
  final Target target;
  final bool pinned;
  final VoidCallback onTap;
  const _TargetRow({required this.target, required this.onTap, this.pinned = false});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final (kind, icon) = _kinds[target.type] ?? ('', Icons.calendar_today_outlined);
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
      child: Tile(
        onTap: onTap,
        padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
        child: Row(
          children: [
            Icon(icon, color: p.accent),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(target.title, style: s.body(16, weight: FontWeight.w600)),
                  Text([kind, if (target.hint.isNotEmpty) target.hint].join(' · '), style: s.body(13, color: p.muted)),
                ],
              ),
            ),
            if (pinned) Icon(Icons.push_pin_rounded, size: 16, color: p.muted),
            Icon(Icons.chevron_right_rounded, color: p.muted),
          ],
        ),
      ),
    );
  }
}

/// Расписание группы, преподавателя или аудитории: сервер отдаёт сразу
/// 8 недель, листать — без запросов. Открывается на ближайшем дне с парами
/// (в субботу вечером «когда он в универе» — это уже следующая неделя).
class TargetScreen extends StatefulWidget {
  final Api api;
  final int type, id;

  /// Название из поиска — для «Закрепить», пока ответ не пришёл.
  final String title;
  const TargetScreen({super.key, required this.api, required this.type, required this.id, this.title = ''});

  @override
  State<TargetScreen> createState() => _TargetScreenState();
}

class _TargetScreenState extends State<TargetScreen> {
  Map<String, dynamic>? _data;
  bool _failed = false, _pinned = false, _pinBusy = false;
  int _week = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  List get _weeks => _data?['weeks'] as List? ?? const [];

  String get _today => '${_data?['today'] ?? iso(now())}';

  Future<void> _load() async {
    setState(() => _failed = false);
    try {
      final d = Map<String, dynamic>.from(await widget.api.get('/target/${widget.type}/${widget.id}'));
      if (!mounted) return;
      setState(() {
        _data = d;
        _pinned = d['pinned'] == true;
        _week = _firstWeek();
      });
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
  }

  /// Неделя ближайшего дня с парами начиная с сегодня; пар впереди нет — эта.
  int _firstWeek() {
    for (var w = 0; w < _weeks.length; w++) {
      for (final day in _weeks[w]['days'] as List) {
        if ('${day['date']}'.compareTo(_today) >= 0 && (day['lessons'] as List).isNotEmpty) return w;
      }
    }
    return 0;
  }

  String get _title {
    final t = '${_data?['title'] ?? ''}';
    return t.isEmpty || t == '${widget.id}' ? (widget.title.isEmpty ? t : widget.title) : t;
  }

  Future<void> _togglePin() async {
    final on = _pinned;
    final toast = Overlay.of(context, rootOverlay: true); // плашка — и после ухода с экрана
    setState(() => _pinBusy = true);
    try {
      final path = '/pins/${widget.type}/${widget.id}';
      if (on) {
        await widget.api.delete(path);
      } else {
        await widget.api.put(path, {'title': _title});
      }
      tick();
      if (mounted) setState(() => _pinned = !on);
      toastOn(toast, on ? 'Откреплено' : 'Закреплено — будет сверху в поиске', kind: ToastKind.done);
    } on ApiError catch (e) {
      toastOn(toast, 'Не получилось: ${e.message}', kind: ToastKind.error);
    } catch (e) {
      toastOn(toast, errorText(e), kind: ToastKind.error);
    } finally {
      if (mounted) setState(() => _pinBusy = false);
    }
  }

  void _shift(int k) {
    final next = (_week + k).clamp(0, _weeks.length - 1);
    if (next == _week) return;
    tick();
    setState(() => _week = next);
  }

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    return Scaffold(
      body: Backdrop(
        child: SafeArea(
          child: Column(
            children: [
              Row(
                children: [
                  const Expanded(child: BackRow()),
                  if (_data != null && widget.api is! GuestApi) // без входа закреплять некуда
                    Padding(
                      padding: const EdgeInsets.only(right: Space.s),
                      child: IconButton(
                        tooltip: _pinned ? 'Открепить' : 'Закрепить',
                        onPressed: _pinBusy ? null : _togglePin,
                        icon: Icon(
                          _pinned ? Icons.push_pin_rounded : Icons.push_pin_outlined,
                          color: _pinned ? p.accent : p.muted,
                        ),
                      ),
                    ),
                ],
              ),
              Expanded(child: _body(context)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _body(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    if (_failed) {
      return ListView(
        children: [
          const SizedBox(height: Space.xxl),
          Notice(
            title: 'Сайт МИРЭА сейчас не отвечает',
            text: 'Расписание появится, как только он оживёт. Обычно это минуты.',
            onRetry: _load,
            pose: CapyPose.sad,
          ),
        ],
      );
    }
    final d = _data;
    if (d == null) return const CapyLoading();
    final week = _weeks.isEmpty ? null : _weeks[_week] as Map;
    final days = week == null ? const [] : week['days'] as List;
    final t = now();
    return CapyRefresh(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.only(bottom: Space.xxl),
        children: [
          ScreenTitle(title: _title),
          if (d['stale'] != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.s),
              child: Row(
                children: [
                  Icon(Icons.warning_amber_rounded, size: 16, color: p.warn),
                  const SizedBox(width: Space.s),
                  Expanded(
                    child: Text('МИРЭА не отвечает · данные от ${d['stale']}', style: s.body(13, color: p.warn)),
                  ),
                ],
              ),
            ),
          if (week == null)
            const Notice(title: 'Пар нет', text: 'В расписании пусто.')
          else ...[
            _WeekSwitch(
              label: _weekLabel(week),
              number: week['week'] as int?,
              onPrev: _week > 0 ? () => _shift(-1) : null,
              onNext: _week < _weeks.length - 1 ? () => _shift(1) : null,
            ),
            for (final run in emptyRuns(days, _today))
              if (run.empty)
                _EmptyDays(from: run.from, to: run.to)
              else
                _TargetDay(
                  date: run.from,
                  today: iso(run.from) == _today,
                  lessons: [
                    for (final l in days[run.index]['lessons'] as List) Lesson.fromJson(Map<String, dynamic>.from(l)),
                  ],
                  at: t,
                  showGroups: widget.type != 1,
                  onLesson: (l) {
                    if (widget.api is! GuestApi) openLesson(context, widget.api, l);
                  },
                ),
          ],
        ],
      ),
    );
  }

  /// «Эта неделя», «Следующая неделя» или «13–18 октября».
  String _weekLabel(Map week) {
    final monday = DateTime.parse('${week['monday'] ?? (week['days'] as List).first['date']}');
    final today = DateTime.parse(_today);
    final thisMonday = DateTime(today.year, today.month, today.day).subtract(Duration(days: today.weekday - 1));
    final offset = (monday.difference(thisMonday).inHours / (24 * 7)).round();
    if (offset == 0) return 'Эта неделя';
    if (offset == 1) return 'Следующая неделя';
    if (offset == -1) return 'Прошлая неделя';
    final sat = monday.add(const Duration(days: 5));
    return monday.month == sat.month
        ? '${monday.day}–${sat.day} ${monthsGen[sat.month - 1]}'
        : '${monday.day} ${monthsGen[monday.month - 1]} – ${sat.day} ${monthsGen[sat.month - 1]}';
  }
}

class _WeekSwitch extends StatelessWidget {
  final String label;
  final int? number;
  final VoidCallback? onPrev, onNext;
  const _WeekSwitch({required this.label, required this.number, required this.onPrev, required this.onNext});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: Tile(
        padding: const EdgeInsets.symmetric(horizontal: Space.xs, vertical: Space.xs),
        child: Row(
          children: [
            IconButton(
              tooltip: 'Неделя раньше',
              onPressed: onPrev,
              icon: Icon(Icons.chevron_left_rounded, color: onPrev == null ? p.line : p.text),
            ),
            Expanded(
              child: Column(
                children: [
                  Text(label, style: s.body(16, weight: FontWeight.w700)),
                  if (number != null) Text('$number неделя', style: s.body(13, color: p.muted)),
                ],
              ),
            ),
            IconButton(
              tooltip: 'Неделя позже',
              onPressed: onNext,
              icon: Icon(Icons.chevron_right_rounded, color: onNext == null ? p.line : p.text),
            ),
          ],
        ),
      ),
    );
  }
}

/// Дни недели подряд: день с парами — сам по себе, пустые подряд — одной
/// строкой «Пн–Ср — пар нет» (владелец, 2.5). Сегодня — всегда отдельно,
/// воскресенье — только если в него есть пары.
List<({bool empty, int index, DateTime from, DateTime to})> emptyRuns(List days, String today) {
  final out = <({bool empty, int index, DateTime from, DateTime to})>[];
  for (var i = 0; i < days.length; i++) {
    final date = DateTime.parse('${days[i]['date']}');
    final none = (days[i]['lessons'] as List).isEmpty;
    if (i >= 6 && none) continue;
    final alone = !none || days[i]['date'] == today;
    final last = out.isEmpty ? null : out.last;
    if (!alone && last != null && last.empty && last.to.add(const Duration(days: 1)) == date) {
      out[out.length - 1] = (empty: true, index: last.index, from: last.from, to: date);
    } else {
      out.add((empty: !alone, index: i, from: date, to: date));
    }
  }
  return out;
}

/// «Вт — пар нет», «Пн–Ср — пар нет».
String emptyDaysText(DateTime from, DateTime to) {
  final a = weekdaysShort[from.weekday - 1], b = weekdaysShort[to.weekday - 1];
  return '${from == to ? a : '$a–$b'} — пар нет';
}

class _EmptyDays extends StatelessWidget {
  final DateTime from, to;
  const _EmptyDays({required this.from, required this.to});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
      child: Tile(
        padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
        child: Text(emptyDaysText(from, to), style: s.body(15, color: s.p.muted)),
      ),
    );
  }
}

class _TargetDay extends StatelessWidget {
  final DateTime date;
  final bool today, showGroups;
  final List<Lesson> lessons;
  final DateTime at;
  final ValueChanged<Lesson> onLesson;
  const _TargetDay({
    required this.date,
    required this.today,
    required this.lessons,
    required this.at,
    required this.showGroups,
    required this.onLesson,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: Space.s, bottom: Space.s),
            child: Text(
              today ? '${dayTitle(date)} · сегодня' : dayTitle(date),
              style: s.eyebrow(color: today ? p.text : p.muted),
            ),
          ),
          if (lessons.isEmpty)
            Tile(
              padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
              child: Text('Пар нет', style: s.body(15, color: p.muted)),
            )
          else
            LessonList(lessons: lessons, at: at, showGroups: showGroups, onTap: onLesson),
        ],
      ),
    );
  }
}

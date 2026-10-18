// «Неделя» — два вида пар, переключатель значками справа сверху, выбор
// запоминается (владелец, 09.10: переехал сюда с «Сегодня»).
// Лента: вся неделя одной лентой, сверху полоса дней с точками пар. Нажал
// день — лента плавно едет к нему; открывается сразу на сегодняшнем дне,
// прошедшие — выше, до них можно долистать (19Б). По дням — плитки дней и
// пары выбранного (week_days.dart). В обоих видах соседняя неделя — свайпом
// вбок или стрелками у дат недели; при этом шапка «Неделя», поиск и
// переключатель стоят на месте — едут только номер и даты недели, полоса
// дней и пары (владелец, 3.4). Пока грузится новая неделя, видна прошлая,
// бледнее, — без мигания всей страницы.
// Сроки сдачи тут не показываем — для них вкладка «Сдать» (владелец, 09.10).
// Итоги дня (5.79, А+Г): на прошедших днях после пар — что сдал и сколько
// баллов прибавилось; пустой день — без карточки. Только в новом дизайне.
// Карточка — одной строкой, подробности — листом по нажатию (Никита 12.10).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollCacheExtent;
import 'package:shared_preferences/shared_preferences.dart';

import '../achievements/store.dart';
import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/capy_refresh.dart';
import '../widgets/common.dart';
import 'lesson.dart';
import 'search.dart';
import 'today.dart' show LessonList;
import 'week_days.dart';

class WeekData {
  final int? number;
  final DateTime monday;
  final Map<String, List<Lesson>> days;

  /// Итоги прошедших дней по дате (поле `summary` в /day); пустых нет.
  final Map<String, DaySummary> summaries;
  WeekData(this.number, this.monday, this.days, {this.summaries = const {}});

  /// Итог дня, если его пора показать: прошедший день или сегодняшний, когда
  /// пары кончились (или их не было). Старый дизайн — никогда.
  DaySummary? summaryFor(BuildContext context, DateTime date, DateTime at) {
    if (!AppStyle.of(context).design2) return null;
    final sum = summaries[iso(date)];
    if (sum == null) return null;
    final today = DateTime(at.year, at.month, at.day);
    final day = DateTime(date.year, date.month, date.day);
    if (day.isAfter(today)) return null;
    if (day == today) {
      for (final l in days[iso(date)] ?? const <Lesson>[]) {
        final end = l.endAt ?? DateTime.tryParse('${iso(date)}T${l.end}:00');
        if (end == null || at.isBefore(end)) return null;
      }
    }
    return sum;
  }
}

/// Пустой день — одинаково в обоих видах недели (владелец, 2.13).
const noLessonsTitle = 'Пар нет', noLessonsText = 'Свободный день';

/// Подпись дня в обоих видах: «Вторник, 6 октября · сегодня».
String dayHead(DateTime date, {bool today = false}) => today ? '${dayTitle(date)} · сегодня' : dayTitle(date);

DateTime mondayOf(DateTime d) => DateTime(d.year, d.month, d.day).subtract(Duration(days: d.weekday - 1));

class WeekScreen extends StatefulWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const WeekScreen({super.key, required this.api, this.onUnauthorized});

  /// Какой вид открыт: 'list' — лента, 'days' — по дням.
  static const viewKey = 'uib_week_view';

  /// Где выбор лежал, пока переключатель был на «Сегодня»: 'days' — по дням.
  static const oldViewKey = 'uib_today_view';

  @override
  State<WeekScreen> createState() => _WeekScreenState();
}

class _WeekScreenState extends State<WeekScreen> {
  int _shift = 0;
  int _dir = 1; // куда уехала неделя: 1 — вперёд, -1 — назад

  /// Вид по дням; null — выбор ещё читается из памяти телефона.
  bool? _days;

  /// Показанная неделя и её сдвиг; пока грузится следующая — видна эта.
  WeekData? _data;
  int? _dataShift;
  Object? _error;
  int _seq = 0;

  /// Номера уже виденных недель — подпись в шапке меняется сразу при листании.
  final _numbers = <int, int?>{};

  @override
  void initState() {
    super.initState();
    _readView();
    _fetch();
  }

  Future<void> _readView() async {
    var days = false;
    try {
      final prefs = await SharedPreferences.getInstance();
      final v = prefs.getString(WeekScreen.viewKey) ?? prefs.getString(WeekScreen.oldViewKey);
      days = v == 'days';
    } catch (_) {}
    if (mounted) setState(() => _days = days);
  }

  Future<void> _setView(bool days) async {
    if (days == _days) return;
    tick();
    setState(() => _days = days);
    try {
      await (await SharedPreferences.getInstance()).setString(WeekScreen.viewKey, days ? 'days' : 'list');
    } catch (_) {}
  }

  void _shiftBy(int k) {
    tick();
    if (k > 0) AchStore.unlock('week_next');
    setState(() {
      _dir = k.sign;
      _shift += k;
      _error = null;
    });
    _fetch();
  }

  /// Назад на свою неделю: она открывается на сегодняшнем дне (владелец, 10.10).
  void _toToday() {
    if (_shift == 0) return;
    _shiftBy(-_shift);
  }

  DateTime _monday(int shift) => mondayOf(now()).add(Duration(days: 7 * shift));

  Future<WeekData> _load(int shift) async {
    final monday = _monday(shift);
    final dates = [for (var i = 0; i < 7; i++) monday.add(Duration(days: i))];
    final res = await Future.wait([
      widget.api.get('/week?start=${iso(monday)}'),
      for (final d in dates) widget.api.get('/day?date=${iso(d)}'),
    ]);
    final days = <String, List<Lesson>>{};
    final summaries = <String, DaySummary>{};
    for (var i = 0; i < 7; i++) {
      final day = res[i + 1];
      days[iso(dates[i])] = [for (final l in (day['lessons'] as List? ?? [])) Lesson.fromJson(l)];
      final sum = day['summary'];
      if (sum is Map<String, dynamic>) {
        final ds = DaySummary.fromJson(sum);
        if (!ds.isEmpty) summaries[iso(dates[i])] = ds;
      }
    }
    return WeekData(res[0]['week'] as int?, monday, days, summaries: summaries);
  }

  /// Неделя пришла: из запаса телефона сразу, из сети — следом (как Loader).
  void _show(int my, int shift, WeekData d) {
    if (my != _seq || !mounted) return;
    setState(() {
      _numbers[shift] = d.number;
      _data = d;
      _dataShift = shift;
      _error = null;
    });
  }

  Future<void> _fetch() async {
    final my = ++_seq, shift = _shift; // ответ на старую неделю не перетирает новую
    final cached = await Api.fromCache(() => _load(shift));
    if (cached != null && _dataShift != shift && my == _seq && mounted) _show(my, shift, cached);
    try {
      _show(my, shift, await _load(shift));
    } catch (e) {
      if (e is Unauthorized) {
        widget.onUnauthorized?.call();
        return;
      }
      if (my == _seq && mounted && _dataShift != shift) setState(() => _error = e);
    }
  }

  /// «6 неделя · 5–11 окт»: даты — сразу, номер — виденный или от соседней.
  String _label() {
    final monday = _monday(_shift);
    final n = _numbers.containsKey(_shift)
        ? _numbers[_shift]
        : (_numbers[_shift - _dir] == null ? null : _numbers[_shift - _dir]! + _dir);
    final range = weekRange(monday);
    return n != null && n > 0 ? '$n неделя · $range' : range;
  }

  /// Сдвиг вбок с проявлением — у подписи недели и у содержимого одинаковый.
  Widget _slide(Widget child, Animation<double> anim, Key current) {
    final incoming = child.key == current;
    final from = Offset((incoming ? 0.18 : -0.18) * _dir, 0);
    return FadeTransition(
      opacity: anim,
      child: SlideTransition(
        position: Tween(begin: from, end: Offset.zero).animate(anim),
        child: child,
      ),
    );
  }

  Widget _content(bool days) {
    final d = _data;
    if (d == null || (_error != null && _dataShift != _shift)) {
      if (_error == null) return const CapyLoading(key: ValueKey('week:loading'));
      return ListView(
        key: ValueKey('week:error:$_shift'),
        children: [
          const SizedBox(height: 120),
          Notice(title: 'Не загрузилось', text: errorText(_error!), onRetry: _fetch, pose: CapyPose.sad),
        ],
      );
    }
    final view = CapyRefresh(
      onRefresh: _fetch,
      child: _WeekView(
        key: ValueKey('week:${iso(d.monday)}'),
        onLesson: (l) => openLesson(context, widget.api, l),
        data: d,
        days: days,
      ),
    );
    // новая неделя ещё грузится — прошлая видна бледнее и не нажимается
    final waiting = _dataShift != _shift;
    return KeyedSubtree(
      key: ValueKey('week:$_dataShift'),
      child: AnimatedOpacity(
        opacity: waiting ? 0.45 : 1,
        duration: const Duration(milliseconds: 200),
        child: IgnorePointer(ignoring: waiting, child: view),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final days = _days;
    if (days == null) return const SizedBox.shrink();
    final p = AppStyle.of(context).p;
    final content = _content(days);
    final labelKey = ValueKey('label:$_shift');
    const duration = Duration(milliseconds: 280);
    return GestureDetector(
      // свайп вбок — соседняя неделя в обоих видах; вертикальную прокрутку не трогает
      behavior: HitTestBehavior.translucent,
      onHorizontalDragEnd: (e) {
        final v = e.primaryVelocity ?? 0;
        if (v.abs() >= 250) _shiftBy(v < 0 ? 1 : -1);
      },
      child: Column(
        children: [
          ScreenTitle(
            title: 'Неделя',
            lead: _WeekLabel(
              onShift: _shiftBy,
              onToday: _shift == 0 ? null : _toToday,
              child: AnimatedSwitcher(
                duration: duration,
                switchInCurve: Curves.easeOutCubic,
                switchOutCurve: Curves.easeInCubic,
                layoutBuilder: (current, previous) =>
                    Stack(alignment: Alignment.centerLeft, children: [...previous, ?current]),
                transitionBuilder: (child, anim) => _slide(child, anim, labelKey),
                child: WeekLabelText(_label(), key: labelKey),
              ),
            ),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  tooltip: 'Поиск расписания',
                  onPressed: () {
                    tick();
                    openSearch(context, widget.api);
                  },
                  icon: Icon(Icons.search_rounded, color: p.muted),
                ),
                const SizedBox(width: 2),
                ViewToggle(days: days, onChanged: _setView),
              ],
            ),
          ),
          Expanded(
            child: AnimatedSwitcher(
              duration: duration,
              switchInCurve: Curves.easeOutCubic,
              switchOutCurve: Curves.easeInCubic,
              layoutBuilder: (current, previous) => Stack(fit: StackFit.expand, children: [...previous, ?current]),
              transitionBuilder: (child, anim) => _slide(child, anim, content.key!),
              child: content,
            ),
          ),
        ],
      ),
    );
  }
}

/// «5–11 окт», через месяц — «28 сен – 4 окт»: коротко, чтобы подпись недели
/// влезала целиком и на узком экране (владелец, Б5).
String weekRange(DateTime monday) {
  final sunday = monday.add(const Duration(days: 6));
  return monday.month == sunday.month
      ? '${monday.day}–${sunday.day} ${monthsShort[sunday.month - 1]}'
      : '${monday.day} ${monthsShort[monday.month - 1]} – ${sunday.day} ${monthsShort[sunday.month - 1]}';
}

/// Содержимое недели под шапкой: полоса дней и лента пар или вид по дням.
class _WeekView extends StatefulWidget {
  final WeekData data;
  final ValueChanged<Lesson> onLesson;

  /// Вид по дням вместо ленты.
  final bool days;
  const _WeekView({super.key, required this.data, required this.onLesson, required this.days});

  @override
  State<_WeekView> createState() => _WeekViewState();
}

class _WeekViewState extends State<_WeekView> {
  final _keys = List.generate(7, (_) => GlobalKey());
  final _scroll = ScrollController();

  // День, с которого лента начинается (сегодня): дни до него лежат выше
  // нулевой точки прокрутки — экран открывается прямо на нём, даже если ниже
  // почти пусто (прыжок после первого кадра упирался в конец ленты).
  final _center = const ValueKey('week:center');
  late final int _anchor;
  late int _selected;

  @override
  void initState() {
    super.initState();
    final today = now();
    final i = DateTime(today.year, today.month, today.day).difference(widget.data.monday).inDays;
    _selected = _anchor = i >= 0 && i < 7 ? i : 0;
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _go(int i, {bool animate = true}) {
    setState(() => _selected = i);
    final ctx = _keys[i].currentContext;
    if (ctx == null) return;
    Scrollable.ensureVisible(
      ctx,
      duration: animate ? const Duration(milliseconds: 420) : Duration.zero,
      curve: Curves.easeOutCubic,
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final d = widget.data;
    final t = now();
    final todayIso = iso(t);
    return Column(
      children: [
        if (widget.days)
          Expanded(
            child: WeekDays(data: d, onLesson: widget.onLesson),
          )
        else ...[
          // Полоса дней
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.m),
            child: Row(
              children: [
                for (var i = 0; i < 7; i++)
                  Expanded(
                    child: DayCell(
                      date: d.monday.add(Duration(days: i)),
                      dots: d.days[iso(d.monday.add(Duration(days: i)))]?.length ?? 0,
                      selected: i == _selected,
                      today: iso(d.monday.add(Duration(days: i))) == todayIso,
                      onTap: () {
                        tick();
                        _go(i);
                      },
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: Space.s),
          Divider(height: 1, color: p.line),
          Expanded(
            child: CustomScrollView(
              controller: _scroll,
              center: _center,
              // все семь дней строятся сразу — нажатие на день доезжает и до понедельника
              scrollCacheExtent: const ScrollCacheExtent.pixels(5000),
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                for (var i = 0; i < 7; i++)
                  SliverToBoxAdapter(
                    key: i == _anchor ? _center : null,
                    child: _DayBlock(
                      key: _keys[i],
                      date: d.monday.add(Duration(days: i)),
                      lessons: d.days[iso(d.monday.add(Duration(days: i)))] ?? const [],
                      today: iso(d.monday.add(Duration(days: i))) == todayIso,
                      at: t,
                      summary: d.summaryFor(context, d.monday.add(Duration(days: i)), t),
                      onLesson: widget.onLesson,
                    ),
                  ),
                const SliverToBoxAdapter(child: SizedBox(height: 160)),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

/// Номер и даты недели, по бокам стрелки на соседние недели; стрелки стоят,
/// подпись между ними едет ([child]).
///
/// Ушёл со своей недели — подпись нажимается, а справа появляется «Сегодня»:
/// оба ведут обратно на эту неделю и сегодняшний день ([onToday]).
class _WeekLabel extends StatelessWidget {
  final Widget child;
  final ValueChanged<int> onShift;
  final VoidCallback? onToday;
  const _WeekLabel({required this.child, required this.onShift, this.onToday});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    Widget arrow(IconData icon, String tip, int k) => Tooltip(
      message: tip,
      child: Semantics(
        button: true,
        label: tip,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => onShift(k),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
            child: Icon(icon, size: 20, color: s.p.muted),
          ),
        ),
      ),
    );
    return Transform.translate(
      offset: const Offset(-4, 0), // стрелка — по краю заголовка
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          arrow(Icons.chevron_left_rounded, 'Прошлая неделя', -1),
          Flexible(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onToday,
              child: ClipRect(child: child),
            ),
          ),
          arrow(Icons.chevron_right_rounded, 'Следующая неделя', 1),
          AnimatedSize(
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
            child: onToday == null
                ? const SizedBox(height: 0)
                : Semantics(
                    button: true,
                    label: 'К сегодня',
                    excludeSemantics: true,
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: onToday,
                      child: Container(
                        margin: const EdgeInsets.only(left: 4),
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(Radii.pill),
                          border: Border.all(color: s.p.accent.withValues(alpha: 0.6)),
                        ),
                        child: Text(
                          'Сегодня',
                          style: s.body(12, weight: FontWeight.w600, color: s.p.accent),
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

/// Подпись недели целиком, без многоточия: если и короткая не влезает
/// (очень крупный системный шрифт) — мельче.
class WeekLabelText extends StatelessWidget {
  final String text;
  const WeekLabelText(this.text, {super.key});

  @override
  Widget build(BuildContext context) => FittedBox(
    fit: BoxFit.scaleDown,
    alignment: Alignment.centerLeft,
    child: Text(text, style: AppStyle.of(context).eyebrow(), maxLines: 1, softWrap: false),
  );
}

/// Переключатель двух видов недели — значками, без подписей (владелец, 09.10):
/// лента и по дням.
class ViewToggle extends StatelessWidget {
  final bool days;
  final ValueChanged<bool> onChanged;
  const ViewToggle({super.key, required this.days, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    Widget seg(IconData icon, String tip, bool on, bool value) => Tooltip(
      message: tip,
      child: Semantics(
        button: true,
        selected: on,
        label: tip,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => onChanged(value),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 240),
            curve: Curves.easeOutCubic,
            width: 36,
            height: 30,
            decoration: BoxDecoration(
              color: on ? p.accent : p.accent.withValues(alpha: 0),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, size: 18, color: on ? p.onAccent : p.muted),
          ),
        ),
      ),
    );
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: p.line, borderRadius: BorderRadius.circular(13)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          seg(Icons.view_agenda_outlined, 'Лентой', !days, false),
          const SizedBox(width: 2),
          seg(Icons.calendar_view_week_rounded, 'По дням', days, true),
        ],
      ),
    );
  }
}

/// День в полосе дней: день недели, число и точки по числу пар; выбранный
/// залит, сегодняшний — цветом акцента. Одна и та же полоса в обоих видах
/// «Недели» (владелец, 10.10: плитки по дням «как в Телеграме» — некрасиво).
class DayCell extends StatelessWidget {
  final DateTime date;
  final int dots;
  final bool selected, today;
  final VoidCallback onTap;

  /// Добавка к подписи для экранного диктора («, 5 пар»).
  final String hint;
  const DayCell({
    super.key,
    required this.date,
    required this.dots,
    required this.selected,
    required this.today,
    required this.onTap,
    this.hint = '',
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final fg = selected ? p.bg : (today ? p.accent : p.text);
    return Semantics(
      button: true,
      selected: selected,
      label: '${dayTitle(date)}$hint',
      excludeSemantics: hint.isNotEmpty,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOutCubic,
          margin: const EdgeInsets.symmetric(horizontal: 3),
          padding: const EdgeInsets.symmetric(vertical: 9),
          decoration: BoxDecoration(
            color: selected ? p.text : Colors.transparent,
            borderRadius: BorderRadius.circular(Radii.chip),
          ),
          child: Column(
            children: [
              Text(weekdaysShort[date.weekday - 1], style: s.body(12, color: selected ? p.bg : p.muted)),
              const SizedBox(height: 2),
              Text('${date.day}', style: s.number(21, color: fg)),
              const SizedBox(height: 5),
              SizedBox(
                height: 5,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    for (var k = 0; k < dots.clamp(0, 5); k++)
                      Container(
                        width: 4,
                        height: 4,
                        margin: const EdgeInsets.symmetric(horizontal: 1),
                        decoration: BoxDecoration(
                          color: (selected ? p.bg : p.muted).withValues(alpha: 0.8),
                          shape: BoxShape.circle,
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DayBlock extends StatelessWidget {
  final DateTime date;
  final List<Lesson> lessons;
  final bool today;
  final DateTime at;
  final ValueChanged<Lesson>? onLesson;

  /// Итог дня после пар (только в новом дизайне, см. [WeekData.summaryFor]).
  final DaySummary? summary;
  const _DayBlock({
    super.key,
    required this.date,
    required this.lessons,
    required this.today,
    required this.at,
    this.onLesson,
    this.summary,
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
              dayHead(date, today: today),
              style: s.eyebrow(color: today ? p.text : p.muted),
            ),
          ),
          if (lessons.isEmpty)
            Tile(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(noLessonsTitle, style: s.body(17, weight: FontWeight.w600)),
                  const SizedBox(height: 3),
                  Text(noLessonsText, style: s.body(13, color: p.muted)),
                ],
              ),
            )
          else
            LessonList(lessons: lessons, at: at, onTap: onLesson),
          if (summary case final sum?)
            Padding(
              padding: const EdgeInsets.only(top: Space.s),
              child: DaySummaryCard(summary: sum, lessons: lessons, date: date),
            ),
        ],
      ),
    );
  }
}

/// «Сводка за день» — одна строка итога (пары · сдано · баллы), одинаково в
/// ленте и по дням. Рамка и фон приглушённые: это итог, не пара. Подробности —
/// что сдал и баллы по предметам — по нажатию в листе (Никита 12.10: в неделе
/// карточка должна быть компактной).
class DaySummaryCard extends StatelessWidget {
  final DaySummary summary;
  final List<Lesson> lessons;
  final DateTime date;
  const DaySummaryCard({super.key, required this.summary, required this.lessons, required this.date});

  /// «6», «4,5», «−2» — без лишнего нуля, минус типографский.
  static String num1(double v) {
    final a = v.abs(), t = a == a.roundToDouble() ? '${a.round()}' : a.toStringAsFixed(1).replaceAll('.', ',');
    return v < 0 ? '−$t' : t;
  }

  static String signed(double v) => v < 0 ? num1(v) : '+${num1(v)}';

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Semantics(
      container: true,
      button: true,
      child: Tile(
        color: p.card.withValues(alpha: p.card.a * 0.5),
        border: p.line,
        padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
        onTap: () => showDaySummarySheet(context, summary: summary, lessons: lessons, date: date),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Сводка за день', style: s.body(13, color: p.muted)),
                  const SizedBox(height: 2),
                  _SummaryLine(summary: summary, lessons: lessons, size: 17),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded, color: p.muted),
          ],
        ),
      ),
    );
  }
}

/// Строка итога: «3 пары · 2 сдано · +14,5 балла» — числа крупно, слова тише.
class _SummaryLine extends StatelessWidget {
  final DaySummary summary;
  final List<Lesson> lessons;
  final double size;
  const _SummaryLine({required this.summary, required this.lessons, required this.size});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final pairs = lessons.fold<int>(0, (n, l) => n + l.pairs);
    final points = summary.points;
    final whole = points == points.roundToDouble();
    final parts = <(String, String)>[
      ('$pairs', plural(pairs, 'пара', 'пары', 'пар')),
      if (summary.done.isNotEmpty) ('${summary.done.length}', 'сдано'),
      if (summary.grades.isNotEmpty && points.abs() >= 0.05)
        (DaySummaryCard.signed(points), whole ? plural(points.abs().round(), 'балл', 'балла', 'баллов') : 'балла'),
    ];
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.end,
      spacing: 6,
      runSpacing: 2,
      children: [
        for (var i = 0; i < parts.length; i++) ...[
          if (i > 0) Text('·', style: s.body(15, color: p.muted)),
          Text.rich(
            TextSpan(
              children: [
                TextSpan(text: parts[i].$1, style: s.number(size)),
                TextSpan(
                  text: ' ${parts[i].$2}',
                  style: s.body(13, color: p.muted),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

/// Лист «Сводка за день»: итог строкой, что сдал (работа и предмет) и баллы
/// по предметам — как другие подробности в приложении (лист снизу).
Future<void> showDaySummarySheet(
  BuildContext context, {
  required DaySummary summary,
  required List<Lesson> lessons,
  required DateTime date,
}) {
  final s = AppStyle.of(context);
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: s.p.cardSolid,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (_) => DaySummarySheet(summary: summary, lessons: lessons, date: date),
  );
}

class DaySummarySheet extends StatelessWidget {
  final DaySummary summary;
  final List<Lesson> lessons;
  final DateTime date;
  const DaySummarySheet({super.key, required this.summary, required this.lessons, required this.date});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    Widget head(String text) => Padding(
      padding: const EdgeInsets.only(top: Space.xl, bottom: Space.xs),
      child: Text(text, style: s.eyebrow()),
    );
    Widget row({required IconData icon, required Color color, required String title, String sub = '', Widget? end}) =>
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Icon(icon, size: 18, color: color),
              ),
              const SizedBox(width: Space.m),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: s.body(15, weight: FontWeight.w600)),
                    if (sub.isNotEmpty) Text(sub, style: s.body(13, color: p.muted)),
                  ],
                ),
              ),
              if (end != null) ...[const SizedBox(width: Space.m), end],
            ],
          ),
        );
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.85),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Сводка за день', style: s.eyebrow()),
              const SizedBox(height: 4),
              Text(dayTitle(date), style: s.name(20)),
              const SizedBox(height: Space.m),
              _SummaryLine(summary: summary, lessons: lessons, size: 22),
              if (summary.done.isNotEmpty) ...[
                head('Сдано'),
                for (final (task, course) in summary.done)
                  row(icon: Icons.check_circle_rounded, color: p.ok, title: task, sub: course),
              ],
              if (summary.grades.isNotEmpty) ...[
                head('Баллы СДО'),
                for (final (name, delta) in summary.grades)
                  row(
                    icon: Icons.auto_awesome_rounded,
                    color: delta < 0 ? p.danger : p.accent,
                    title: name,
                    end: Text(DaySummaryCard.signed(delta), style: s.number(17, color: delta < 0 ? p.danger : p.text)),
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

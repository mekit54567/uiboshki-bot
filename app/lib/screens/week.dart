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
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollCacheExtent;
import 'package:shared_preferences/shared_preferences.dart';

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
  WeekData(this.number, this.monday, this.days);
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
    for (var i = 0; i < 7; i++) {
      days[iso(dates[i])] = [for (final l in (res[i + 1]['lessons'] as List? ?? [])) Lesson.fromJson(l)];
    }
    return WeekData(res[0]['week'] as int?, monday, days);
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
    if (cached != null && _dataShift != shift) _show(my, shift, cached);
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
          Notice(
            title: 'Не загрузилось',
            text: errorText(_error!),
            onRetry: _fetch,
            pose: CapyPose.sad,
          ),
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
                        child: Text('Сегодня', style: s.body(12, weight: FontWeight.w600, color: s.p.accent)),
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
  const _DayBlock({
    super.key,
    required this.date,
    required this.lessons,
    required this.today,
    required this.at,
    this.onLesson,
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
        ],
      ),
    );
  }
}

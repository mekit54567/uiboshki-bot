// «Сегодня» (владелец, 09.10, 21А/21В): группа с неделей и погода одной строкой, капибара, приветствие по
// времени суток; ближайшая пара крупно — время, название, кабинет плашкой
// цвета предмета и «через»; во время пары — сколько до конца, полоска и где
// следующая. Ниже пары дня карточками с номером пары и что горит по срокам.
// Второй вид пар (дни недели плитками) живёт на вкладке «Неделя» (владелец, 09.10).
// Время тикает раз в 30 секунд.
import 'dart:async';

import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/look.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widget_data.dart';
import '../widgets/common.dart';
import 'lesson.dart';
import 'week.dart' show mondayOf;

class TodayData {
  final List<Lesson> lessons;
  final Lesson? tomorrowFirst;
  final List<Deadline> soon;
  final String weather;

  /// Все пары завтра — когда сегодня пар нет или они кончились, экран
  /// показывает их ниже (владелец, 11.10: «пустовато»). Не пришли — пусто.
  final List<Lesson> tomorrow;

  /// Имя, группа и номер учебной недели — для шапки. Без сети и запаса их
  /// может не быть: экран всё равно показывается, просто без них.
  final String name, group;
  final int? week;

  /// Будут ли ещё пары на этой неделе после сегодня (null — не знаем):
  /// после последней пары недели у капибары своя подпись.
  final bool? moreThisWeek;

  /// Отменённые сегодня пары (5.79): в счёт пар и «идёт сейчас» не входят,
  /// в списке — серыми и зачёркнутыми.
  final List<Lesson> cancelled;
  TodayData(
    this.lessons,
    this.tomorrowFirst,
    this.soon,
    this.weather, {
    this.name = '',
    this.group = '',
    this.week,
    this.moreThisWeek,
    this.cancelled = const [],
    this.tomorrow = const [],
  });
}

const _ordinal = ['первая', 'вторая', 'третья', 'четвёртая', 'пятая', 'шестая', 'седьмая', 'восьмая'];

/// «первая», «вторая»… по месту пары в дне (не по звонку).
String ordinal(int i) => i < _ordinal.length ? _ordinal[i] : '${i + 1}-я';

/// Приветствие по времени суток — часы те же, что у позы капибары.
String greeting(int hour) => switch (poseAt(hour)) {
  CapyPose.morning => 'Доброе утро',
  CapyPose.day => 'Добрый день',
  CapyPose.evening => 'Добрый вечер',
  _ => 'Доброй ночи',
};

/// «25 мин», от часа — «2 ч 05 мин»: «134 минуты» не читается (владелец, 09.10).
String spanText(int minutes) =>
    minutes >= 60 ? '${minutes ~/ 60} ч ${(minutes % 60).toString().padLeft(2, '0')} мин' : '$minutes мин';

/// Минут до момента с округлением вверх: за 30 секунд до начала — «1 мин», а не «0».
int minutesTo(DateTime from, DateTime to) {
  final s = to.difference(from).inSeconds;
  return s <= 0 ? 0 : (s + 59) ~/ 60;
}

/// Погода из /api/today («🌤 +4°, переменная облачность, ощущается +2° ·
/// 🧣 куртка не помешает») для шапки: температура и коротко небо («облачно»),
/// а целиком — без эмодзи (их в интерфейсе нет). null — погоды нет.
({String temp, String sky, String full})? weatherBrief(String raw) {
  final full = raw
      .replaceAll(RegExp(r'[^\p{L}\p{N}\s°+\-−.,:·]', unicode: true), '')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
  if (full.isEmpty) return null;
  final parts = [
    for (final x in full.split(' · ').first.split(','))
      if (x.trim().isNotEmpty) x.trim(),
  ];
  if (parts.isEmpty) return null;
  return (temp: parts.first, sky: parts.length > 1 ? shortSky(parts[1]) : '', full: full);
}

/// Погода по частям для карточки под чипом: «Переменная облачность»,
/// «ощущается +2°» и совет «куртка не помешает» (пустые — если их нет).
({String temp, String desc, String feels, String advice})? weatherDetails(String raw) {
  final w = weatherBrief(raw);
  if (w == null) return null;
  final halves = w.full.split(' · ');
  var desc = '', feels = '';
  for (final x in halves.first.split(',').skip(1)) {
    final v = x.trim();
    if (v.startsWith('ощущается')) {
      feels = v;
    } else if (desc.isEmpty && v.isNotEmpty) {
      desc = v[0].toUpperCase() + v.substring(1);
    }
  }
  return (temp: w.temp, desc: desc, feels: feels, advice: halves.skip(1).join(' · ').trim());
}

/// Дождь по погоде — капибара напомнит про зонт.
bool rainy(String raw) => const {'дождь', 'ливень', 'морось', 'гроза'}.contains(weatherBrief(raw)?.sky);

/// «Переменная облачность» → «облачно», «Лёгкий дождь» → «дождь».
String shortSky(String desc) {
  final x = desc.toLowerCase().trim();
  for (final (key, short) in const [
    ('гроза', 'гроза'),
    ('ливень', 'ливень'),
    ('снег', 'снег'),
    ('дожд', 'дождь'),
    ('морось', 'морось'),
    ('туман', 'туман'),
    ('пасмурно', 'пасмурно'),
    ('облачн', 'облачно'),
    ('ясно', 'ясно'),
  ]) {
    if (x.contains(key)) return short;
  }
  return x.split(' ').last;
}

/// Корпус из «А-332 (МП-1)» — «МП-1»; без скобок — пусто.
String campusOf(String room) => RegExp(r'\(([^)]+)\)').firstMatch(room)?.group(1)?.trim() ?? '';

/// «А-332 (МП-1), Б-304 (МП-1)» → кабинеты «А-332, Б-304» и корпус «МП-1».
({String code, String campus}) splitRoom(String room) {
  final codes = <String>[], campuses = <String>[];
  for (final r in room.split(RegExp(r',\s*'))) {
    final code = r.replaceAll(RegExp(r'\s*\([^)]*\)'), '').trim();
    final c = campusOf(r);
    if (code.isNotEmpty) codes.add(code);
    if (c.isNotEmpty && !campuses.contains(c)) campuses.add(c);
  }
  return (code: codes.join(', '), campus: campuses.join(', '));
}

class TodayScreen extends StatefulWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const TodayScreen({super.key, required this.api, this.onUnauthorized});

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<TodayData> _load() async {
    final api = widget.api;
    // имя, группа и неделя — только для шапки: не пришли — экран всё равно есть
    Future<dynamic> extra(String path) => api.get(path).then<dynamic>((v) => v, onError: (_) => null);
    final res = await Future.wait([
      api.get('/today'),
      extra('/me'),
      extra('/week?start=${iso(mondayOf(now()))}'),
      extra('/day?date=${iso(now().add(const Duration(days: 1)))}'),
    ]);
    final j = res[0];
    final today = iso(now());
    var lessonsJson = j['lessons'] as List;
    var cancelledJson = j['cancelled'] as List? ?? const [];
    var tf = j['tomorrow_first'];
    var weather = '${j['weather'] ?? ''}';
    var tomorrowJson = res[3] is Map && res[3]['lessons'] is List ? res[3]['lessons'] as List : const [];
    var stale = false;
    // Б1: утром из памяти телефона приходит вчерашний «Сегодня». Из запаса —
    // не показываем (экран ждёт сеть); без сети — пары на сегодня из
    // сохранённого дня (вкладка «Неделя»), а нет его — честно говорим.
    if ('${j['date'] ?? today}' != today && (Api.cacheOnly || api.offlineSince.value != null)) {
      if (Api.cacheOnly) throw StateError('в запасе не сегодняшний день');
      final day = await Api.fromCache(() => api.get('/day?date=$today'));
      if (day is! Map || day['lessons'] is! List) {
        throw ApiError('Расписание на сегодня ещё не загружено — нужен интернет.');
      }
      final next = await Api.fromCache(() => api.get('/day?date=${iso(now().add(const Duration(days: 1)))}'));
      lessonsJson = day['lessons'] as List;
      cancelledJson = day['cancelled'] as List? ?? const [];
      tomorrowJson = next is Map && next['lessons'] is List ? next['lessons'] as List : const [];
      tf = tomorrowJson.isNotEmpty ? tomorrowJson.first : null;
      weather = ''; // вчерашняя погода не нужна
      stale = true;
    }
    final lessons = [for (final l in lessonsJson) Lesson.fromJson(l)];
    final soon = [
      for (final d in (j['deadlines']?['soon'] as List? ?? []))
        if (stale ? '${d['due_date'] ?? today}'.compareTo(today) >= 0 : (d['days'] ?? 0) >= 0) Deadline.fromJson(d),
    ];
    final me = res[1] is Map ? res[1] as Map : const {};
    final group = me['group'] is Map ? '${me['group']['name'] ?? ''}' : '';
    final week = res[2] is Map ? res[2]['week'] : null;
    final days = res[2] is Map && res[2]['days'] is List ? res[2]['days'] as List : null;
    final data = TodayData(
      lessons,
      tf == null ? null : Lesson.fromJson(tf),
      soon,
      weather,
      name: '${me['first_name'] ?? ''}'.trim(),
      group: group,
      week: week is int ? week : null,
      cancelled: [for (final l in cancelledJson) Lesson.fromJson(Map<String, dynamic>.from(l))],
      moreThisWeek: days == null || days.isEmpty
          ? null
          : days.any((d) => d is Map && '${d['date']}'.compareTo(today) > 0 && (d['dots'] as List? ?? []).isNotEmpty),
      tomorrow: [for (final l in tomorrowJson) Lesson.fromJson(l)],
    );
    // виджеты рабочего стола — свежим днём, не запасом (запас догонит сеть)
    if (!Api.cacheOnly) unawaited(HomeWidgets.fromToday(api, stale ? today : '${j['date'] ?? today}', data));
    return data;
  }

  @override
  Widget build(BuildContext context) => Loader<TodayData>(
    load: _load,
    onUnauthorized: widget.onUnauthorized,
    builder: (context, d, _) => _MainView(
      key: const ValueKey('today:main'),
      data: d,
      api: widget.api,
      top: TodayTop(data: d),
    ),
  );
}

/// Шапка: группа с неделей и погода одной строкой (не влезает — погода
/// только температурой, совсем узко — второй строкой). Нажал на погоду —
/// чип раскрывается карточкой на месте и сдвигает экран вниз (П5, 09.10).
class TodayTop extends StatefulWidget {
  final TodayData data;
  const TodayTop({super.key, required this.data});

  // на 320 pt «УИБО-03-24 · 6 неделя» и «+12° пасмурно» влезают в строку
  static const _gap = 5.0, _pad = 8.0, _padV = 4.5;

  @override
  State<TodayTop> createState() => _TodayTopState();
}

class _TodayTopState extends State<TodayTop> {
  static const _gap = TodayTop._gap, _pad = TodayTop._pad;
  bool _open = false;

  void _toggle() => setState(() => _open = !_open);

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final data = widget.data;
    final wx = weatherBrief(data.weather);
    final details = weatherDetails(data.weather);
    final head = [if (data.group.isNotEmpty) data.group, if (data.week != null) '${data.week} неделя'].join(' · ');
    // меряем тем же стилем, каким рисует Text (с межбуквенным из темы); подписи
    // в шапке растут с системным шрифтом не больше чем на 15 % — иначе на
    // 320 pt группа с неделей не влезает в строку
    final style = DefaultTextStyle.of(context).style
        .merge(s.body(12, weight: FontWeight.w600))
        .copyWith(letterSpacing: 0);
    final scaler = MediaQuery.textScalerOf(context).clamp(maxScaleFactor: 1.15);
    return Padding(
      key: const ValueKey('today:top'),
      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, 0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: LayoutBuilder(
              builder: (context, box) {
                double width(String text) {
                  final tp = TextPainter(
                    text: TextSpan(text: text, style: style),
                    textScaler: scaler,
                    textDirection: Directionality.of(context),
                    maxLines: 1,
                  )..layout();
                  final w = tp.width + 2 * _pad;
                  tp.dispose();
                  return w;
                }

                String? sky;
                if (wx != null) {
                  final full = wx.sky.isEmpty ? wx.temp : '${wx.temp} ${wx.sky}';
                  final used = head.isEmpty ? 0.0 : width(head) + _gap;
                  // всё в строку; не влезает — одна температура; и она не влезает — перенос
                  final room = box.maxWidth - 1; // запас на округление
                  sky = used + width(full) <= room || used + width(wx.temp) > room ? full : wx.temp;
                }
                return Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Wrap(
                        spacing: _gap,
                        runSpacing: _gap,
                        children: [
                          if (head.isNotEmpty) _Chip(head, style: style, scaler: scaler),
                          if (sky != null)
                            _Chip(
                              sky,
                              style: style,
                              scaler: scaler,
                              label: _open ? 'Свернуть погоду' : 'Погода: ${wx!.full}',
                              onTap: _toggle,
                            ),
                        ],
                      ),
                      AnimatedSize(
                        duration: const Duration(milliseconds: 320),
                        curve: Curves.easeOutCubic,
                        alignment: Alignment.topCenter,
                        child: _open && details != null
                            ? _WeatherCard(details, onTap: _toggle)
                            : const SizedBox(width: double.infinity),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// Погода целиком карточкой под чипом: температура крупно, небо, «ощущается»
/// и совет плашкой. Нажал — свернулась.
class _WeatherCard extends StatelessWidget {
  final ({String temp, String desc, String feels, String advice}) w;
  final VoidCallback onTap;
  const _WeatherCard(this.w, {required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Semantics(
      button: true,
      label: 'Свернуть погоду',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          tick();
          onTap();
        },
        child: TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: 1),
          duration: const Duration(milliseconds: 260),
          builder: (context, v, child) => Opacity(opacity: v, child: child),
          child: Container(
            key: const ValueKey('today:weather'),
            margin: const EdgeInsets.only(top: Space.s),
            padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, Space.m),
            decoration: BoxDecoration(
              color: p.card,
              borderRadius: BorderRadius.circular(Radii.tile),
              border: Border.all(color: p.line),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(w.temp, style: s.number(40)),
                    const SizedBox(width: Space.m),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (w.desc.isNotEmpty) Text(w.desc, style: s.body(15, weight: FontWeight.w600)),
                          if (w.feels.isNotEmpty) Text(w.feels, style: s.body(13, color: p.muted)),
                        ],
                      ),
                    ),
                  ],
                ),
                if (w.advice.isNotEmpty) ...[
                  const SizedBox(height: Space.s),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: p.accent.withValues(alpha: 0.14),
                      borderRadius: BorderRadius.circular(Radii.chip),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.checkroom_rounded, size: 15, color: p.accent),
                        const SizedBox(width: 6),
                        Flexible(
                          child: Text(
                            w.advice,
                            style: s.body(13, weight: FontWeight.w600, color: p.accent),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final String text;
  final TextStyle style;
  final TextScaler scaler;
  final String? label;
  final VoidCallback? onTap;
  const _Chip(this.text, {required this.style, required this.scaler, this.label, this.onTap});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    final chip = Container(
      padding: const EdgeInsets.symmetric(horizontal: TodayTop._pad, vertical: TodayTop._padV),
      decoration: BoxDecoration(color: p.line, borderRadius: BorderRadius.circular(Radii.pill)),
      child: Text(text, style: style, textScaler: scaler, maxLines: 1, overflow: TextOverflow.ellipsis),
    );
    if (onTap == null) return chip;
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: label != null,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          tick();
          onTap!();
        },
        child: chip,
      ),
    );
  }
}

/// Главный вид (21А): приветствие и ближайшая пара крупно; во время пары
/// (21В) — «Идёт первая пара», сколько до конца и где следующая.
class _MainView extends StatelessWidget {
  final TodayData data;
  final Api api;
  final Widget top;
  const _MainView({super.key, required this.data, required this.api, required this.top});

  /// Случай для подписи капибары: выходной, пары кончились (последняя пара
  /// недели — своя подпись), дождь. Ночью капибара спит — только выходной.
  List<CapyMoment> _moments(DateTime t, Lesson? current, Lesson? next) {
    final awake = poseAt(t.hour) != CapyPose.night;
    return [
      if (data.lessons.isEmpty)
        CapyMoment.dayOff
      else if (awake && current == null && next == null)
        data.moreThisWeek == false ? CapyMoment.weekOver : CapyMoment.dayOver,
      if (awake && rainy(data.weather)) CapyMoment.rain,
    ];
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final t = now();
    final lessons = data.lessons;
    Lesson? current, next;
    for (final l in lessons) {
      if (l.startAt == null || l.endAt == null) continue;
      if (!t.isBefore(l.startAt!) && t.isBefore(l.endAt!)) current = l;
      if (next == null && t.isBefore(l.startAt!)) next = l;
    }
    void open(Lesson l) => openLesson(context, api, l);
    // отменённые пары (5.79) — на своих местах в списке дня, только в новом дизайне
    final shown = s.design2 && data.cancelled.isNotEmpty
        ? ([...lessons, ...data.cancelled]..sort((a, b) => a.start.compareTo(b.start)))
        : lessons;
    final hello = data.name.isEmpty ? greeting(t.hour) : '${greeting(t.hour)},\n${data.name}';
    final String title;
    Widget? focus, notice;
    if (lessons.isEmpty) {
      title = hello;
      final tf = data.tomorrowFirst;
      notice = Notice(
        title: 'Сегодня пар нет',
        text: tf == null
            ? 'Завтра тоже свободно.'
            : data.tomorrow.isEmpty
            ? 'Завтра первая — ${tf.start}, ${tf.title}.'
            : 'Завтра первая — в ${tf.start}.',
        pose: CapyPose.joy,
      );
    } else if (current != null) {
      title = 'Идёт ${ordinal(lessons.indexOf(current))} пара';
      focus = _LiveFocus(lesson: current, next: next, at: t, onOpen: open);
    } else if (next != null) {
      final i = lessons.indexOf(next);
      title = i == 0 ? hello : 'Перемена';
      focus = _NextFocus(
        label: '${ordinal(i)} пара в',
        lesson: next,
        prev: i > 0 ? lessons[i - 1] : null,
        at: t,
        onOpen: open,
      );
    } else {
      // пары кончились — что завтра; завтра свободно — капибара радуется
      title = hello;
      final tf = data.tomorrowFirst;
      if (tf != null) {
        focus = _NextFocus(label: 'завтра первая пара в', lesson: tf, at: t, onOpen: open);
      } else {
        notice = const Notice(title: 'Пары закончились', text: 'Завтра свободно.', pose: CapyPose.joy);
      }
    }

    // сегодня пар нет или они кончились — ниже пары на завтра; первая из них
    // уже крупно в фокусе, если пары сегодня были
    final free = lessons.isEmpty || (current == null && next == null);
    final rest = lessons.isEmpty
        ? data.tomorrow
        : current == null && next == null && data.tomorrow.length > 1
        ? data.tomorrow.sublist(1)
        : const <Lesson>[];
    final n = rest.length;
    return ListView(
      padding: const EdgeInsets.only(bottom: 120),
      children: [
        top,
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.m, 0),
          child: Row(
            children: [
              // «Идёт первая пара», «Перемена» — одной строкой, на узком экране
              // мельче (2.17); приветствие с именем — в две строки, как было
              Expanded(
                child: title.contains('\n') ? FitWords(title, style: s.title(30)) : _fitLine(title, s.title(30)),
              ),
              const SizedBox(width: Space.s),
              CapyBadge(hour: t.hour, size: 62, moments: _moments(t, current, next)),
            ],
          ),
        ),
        if (focus != null) Padding(padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, 0), child: focus),
        if (notice != null) ...[const SizedBox(height: Space.m), notice],
        if (lessons.isNotEmpty) ...[
          Section('сегодня · ${lessons.length} ${plural(lessons.length, 'пара', 'пары', 'пар')}'),
          // «строками» (5.79, «Оформление»): весь день одной карточкой, как в «Неделе»
          if (s.look.day == DayView.rows)
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
              child: LessonList(lessons: shown, at: t, onTap: open),
            )
          else
            for (final l in shown)
              Padding(
                padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
                child: LessonCard(lesson: l, at: t, onTap: l.cancelled ? null : () => open(l)),
              ),
        ],
        if (rest.isNotEmpty) ...[
          Section('завтра · ${lessons.isEmpty ? '' : 'ещё '}$n ${plural(n, 'пара', 'пары', 'пар')}'),
          for (final l in rest)
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
              child: LessonCard(lesson: l, at: t, onTap: () => open(l)),
            ),
        ],
        // ближайшие три срока; «горит» — только если есть срок в ближайшие
        // три дня, иначе просто «сдать» (владелец, 11.10: «Завтра и сроки»)
        if (data.soon.isNotEmpty) ...[
          Section(data.soon.any((d) => d.due.difference(t).inDays < 3) ? 'горит' : 'сдать'),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: _SoonList(data.soon, at: t),
          ),
        ] else if (free) ...[
          const Section('сдать'),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: Tile(
              child: Row(
                children: [
                  Icon(Icons.task_alt_rounded, size: 17, color: s.p.ok),
                  const SizedBox(width: Space.s),
                  Expanded(child: Text('Открытых сроков нет', style: s.body(14, color: s.p.muted))),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

/// До пары: «первая пара в» и время крупно, название, кабинет плашкой цвета
/// предмета и «через» с преподавателем. Следующая в другом корпусе —
/// подсказка про переход.
class _NextFocus extends StatelessWidget {
  final String label;
  final Lesson lesson;
  final Lesson? prev;
  final DateTime at;
  final ValueChanged<Lesson> onOpen;
  const _NextFocus({required this.label, required this.lesson, this.prev, required this.at, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final from = prev == null ? '' : campusOf(prev!.room);
    final to = campusOf(lesson.room);
    final moving = from.isNotEmpty && to.isNotEmpty && from != to;
    final gap = prev?.endAt != null && lesson.startAt != null ? lesson.startAt!.difference(prev!.endAt!).inMinutes : 0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: s.body(13, color: p.muted)),
        const SizedBox(height: 4),
        Text(lesson.start, style: s.number(52)),
        const SizedBox(height: Space.s),
        _Name(lesson, onOpen: onOpen),
        const SizedBox(height: Space.m),
        _Tiles([
          if (lesson.room.isNotEmpty) RoomTile(lesson, onTap: () => onOpen(lesson)),
          if (lesson.startAt != null)
            _InfoTile(
              label: 'через',
              value: spanText(minutesTo(at, lesson.startAt!)),
              sub: lesson.teacher,
              onTap: () => onOpen(lesson),
            )
          else if (lesson.teacher.isNotEmpty)
            _InfoTile(label: 'ведёт', value: lesson.teacher, fit: false, onTap: () => onOpen(lesson)),
        ]),
        if (moving) ...[
          const SizedBox(height: Space.s),
          Row(
            children: [
              Icon(Icons.directions_walk_rounded, size: 16, color: p.warn),
              const SizedBox(width: 4),
              Expanded(
                child: Text(
                  'Другой корпус — $to, на переход $gap мин',
                  style: s.body(13, weight: FontWeight.w600, color: p.warn),
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }
}

/// Во время пары (21В): «до конца» крупно цветом предмета, полоска, название,
/// кабинет и куда дальше — тот же корпус или другой.
class _LiveFocus extends StatelessWidget {
  final Lesson lesson;
  final Lesson? next;
  final DateTime at;
  final ValueChanged<Lesson> onOpen;
  const _LiveFocus({required this.lesson, this.next, required this.at, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final c = s.ink(lesson.title);
    // в блоке (5 пар военки) — до конца текущей пары или перемены, не всего блока
    final live = lesson.liveAt(at);
    final from = live?.start ?? lesson.startAt!, till = live?.end ?? lesson.endAt!;
    final total = till.difference(from).inSeconds;
    final passed = at.difference(from).inSeconds.clamp(0, total);
    final label = live == null || live.of == 1
        ? 'до конца'
        : live.pause
        ? 'перемена · до ${live.index}-й пары из ${live.of}'
        : 'до конца пары · ${live.index} из ${live.of}';
    final n = next;
    final Widget after;
    if (n != null) {
      final from = campusOf(lesson.room), to = campusOf(n.room);
      final known = from.isNotEmpty && to.isNotEmpty;
      final moving = known && from != to;
      final room = splitRoom(n.room).code;
      final stay = room.isNotEmpty && room == splitRoom(lesson.room).code;
      after = _InfoTile(
        label: 'дальше в ${n.start}',
        value: room.isNotEmpty ? room : n.title,
        fit: room.isNotEmpty,
        sub: stay
            ? 'тот же кабинет, никуда не идти'
            : moving
            ? 'другой корпус, $to'
            : known
            ? 'тот же корпус'
            : room.isNotEmpty
            ? n.title
            : n.kind,
        subColor: moving ? p.warn : null,
        onTap: () => onOpen(n),
      );
    } else {
      after = _InfoTile(label: 'конец в', value: lesson.end, sub: 'последняя на сегодня', onTap: () => onOpen(lesson));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: s.body(13, color: p.muted)),
        const SizedBox(height: 4),
        _Countdown(minutes: minutesTo(at, till), color: c),
        const SizedBox(height: Space.m),
        ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: total == 0 ? 0 : passed / total,
            minHeight: 6,
            color: c,
            backgroundColor: p.line,
          ),
        ),
        const SizedBox(height: Space.m),
        _Name(lesson, onOpen: onOpen),
        const SizedBox(height: Space.m),
        _Tiles([if (lesson.room.isNotEmpty) RoomTile(lesson, onTap: () => onOpen(lesson)), after]),
      ],
    );
  }
}

/// «1 ч 07 мин» — цифры крупно, единицы мельче.
class _Countdown extends StatelessWidget {
  final int minutes;
  final Color color;
  const _Countdown({required this.minutes, required this.color});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final big = s.number(52, color: color);
    final unit = s.body(18, weight: FontWeight.w600, color: s.p.muted);
    return Semantics(
      label: 'до конца ${spanText(minutes)}',
      excludeSemantics: true,
      child: FittedBox(
        fit: BoxFit.scaleDown,
        alignment: Alignment.centerLeft,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            if (minutes >= 60) ...[
              Text('${minutes ~/ 60}', style: big),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: Text('ч', style: unit),
              ),
              Text((minutes % 60).toString().padLeft(2, '0'), style: big),
            ] else
              Text('$minutes', style: big),
            Padding(
              padding: const EdgeInsets.only(left: 7),
              child: Text('мин', style: unit),
            ),
          ],
        ),
      ),
    );
  }
}

/// Название пары крупно, без засечек; нажал — экран пары.
class _Name extends StatelessWidget {
  final Lesson lesson;
  final ValueChanged<Lesson> onOpen;
  const _Name(this.lesson, {required this.onOpen});

  @override
  Widget build(BuildContext context) => GestureDetector(
    behavior: HitTestBehavior.opaque,
    onTap: () {
      tick();
      onOpen(lesson);
    },
    child: Text(lesson.title, style: AppStyle.of(context).name(18)),
  );
}

/// Две плашки рядом одной высоты.
class _Tiles extends StatelessWidget {
  final List<Widget> children;
  const _Tiles(this.children);

  @override
  Widget build(BuildContext context) => IntrinsicHeight(
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < children.length; i++) ...[
          if (i > 0) const SizedBox(width: Space.s),
          Expanded(child: children[i]),
        ],
      ],
    ),
  );
}

class _TileBox extends StatelessWidget {
  final Color? color;
  final VoidCallback? onTap;
  final List<Widget> children;
  const _TileBox({this.color, this.onTap, required this.children});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    return Semantics(
      button: onTap != null,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap == null
            ? null
            : () {
                tick();
                onTap!();
              },
        child: Container(
          padding: const EdgeInsets.fromLTRB(Space.m, 10, Space.m, 11),
          decoration: BoxDecoration(
            color: color ?? p.card,
            borderRadius: BorderRadius.circular(16),
            border: color == null ? Border.all(color: p.line) : null,
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
        ),
      ),
    );
  }
}

/// Значение плашки в одну строку: не влезает — чуть мельче, а не обрезано.
Widget _fitLine(String text, TextStyle style) => FittedBox(
  fit: BoxFit.scaleDown,
  alignment: Alignment.centerLeft,
  child: Text(text, style: style, maxLines: 1, softWrap: false),
);

/// Кабинет плашкой, залитой цветом предмета: «кабинет / А-332 / корпус МП-1».
class RoomTile extends StatelessWidget {
  final Lesson lesson;
  final VoidCallback? onTap;
  const RoomTile(this.lesson, {super.key, this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final c = s.ink(lesson.title);
    final on = s.darkInk ? Colors.white : Color.lerp(c, Colors.black, 0.82)!;
    final r = splitRoom(lesson.room);
    return _TileBox(
      color: c,
      onTap: onTap,
      children: [
        Text(r.code.contains(',') ? 'кабинеты' : 'кабинет', style: s.body(12, color: on.withValues(alpha: 0.75))),
        const SizedBox(height: 2),
        _fitLine(r.code.isEmpty ? lesson.room : r.code, s.body(21, weight: FontWeight.w800, color: on)),
        if (r.campus.isNotEmpty) ...[
          const SizedBox(height: 2),
          Text(
            'корпус ${r.campus}',
            style: s.body(12, weight: FontWeight.w600, color: on),
          ),
        ],
      ],
    );
  }
}

/// Вторая плашка: «через / 2 ч 05 мин / преподаватель», «дальше в 16:20 / Б-304».
class _InfoTile extends StatelessWidget {
  final String label, value, sub;
  final Color? subColor;

  /// Короткое значение (время, кабинет) — мельче, если не влезает; длинное
  /// (название) — с многоточием.
  final bool fit;
  final VoidCallback? onTap;
  const _InfoTile({
    required this.label,
    required this.value,
    this.sub = '',
    this.subColor,
    this.fit = true,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final style = s.body(fit ? 21 : 16, weight: FontWeight.w800);
    return _TileBox(
      onTap: onTap,
      children: [
        Text(label, style: s.body(12, color: p.muted)),
        const SizedBox(height: 2),
        fit ? _fitLine(value, style) : Text(value, style: style, maxLines: 2, overflow: TextOverflow.ellipsis),
        if (sub.isNotEmpty) ...[
          const SizedBox(height: 2),
          Text(
            sub,
            style: s.body(12, weight: subColor == null ? FontWeight.w400 : FontWeight.w700, color: subColor ?? p.muted),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ],
    );
  }
}

/// «идёт · ещё 23 мин»; в блоке — до конца текущей пары: «идёт 2-я из 5 ·
/// ещё 23 мин», на перемене — «перемена · ещё 8 мин».
String _liveLine(Lesson l, DateTime at) {
  final live = l.liveAt(at);
  if (live == null) return 'идёт';
  final left = spanText(minutesTo(at, live.end));
  if (live.of == 1) return 'идёт · ещё $left';
  return live.pause ? 'перемена · ещё $left' : 'идёт ${live.index}-я из ${live.of} · ещё $left';
}

/// Пара карточкой (владелец, 09.10, 22А): слева время начала и конца,
/// название без засечек, точка цвета предмета и тип, кабинет плашкой,
/// преподаватель; справа номер пары по звонку. Карточка чуть подкрашена
/// цветом предмета; идущая — в зелёной рамке, с «идёт · ещё 1 ч 07 мин» и
/// тонкой полоской внизу, номер залит; прошедшие — бледнее.
class LessonCard extends StatelessWidget {
  final Lesson lesson;
  final DateTime at;
  final VoidCallback? onTap;
  const LessonCard({super.key, required this.lesson, required this.at, this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final l = lesson;
    final base = subjectColor(l.title); // подсветка карточки
    final c = s.ink(l.title); // точка, полоска, кабинет
    final past = l.endAt != null && !at.isBefore(l.endAt!);
    final live = l.startAt != null && l.endAt != null && !past && !at.isBefore(l.startAt!);
    final total = live ? l.endAt!.difference(l.startAt!).inSeconds : 0;
    final passed = live ? at.difference(l.startAt!).inSeconds.clamp(0, total) : 0;
    // «с полоской» (5.79, «Оформление»): карточка без заливки, цвет предмета —
    // полоской слева
    final stripe = s.look.card == CardStyle.stripe;
    final tint = p.dark
        ? base.withValues(alpha: live ? 0.2 : 0.13)
        : Color.alphaBlend(base.withValues(alpha: live ? 0.16 : 0.1), p.card);
    Widget dotLine(Color dot, String text, TextStyle style) => Row(
      children: [
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Flexible(child: Text(text, style: style)),
      ],
    );
    // изменения в расписании (5.79): кабинет сменили — рамка; пару отменили — серая
    final moved = s.design2 && l.roomWas.isNotEmpty && !l.cancelled;
    final gone = s.design2 && l.cancelled;
    final card = Tile(
      onTap: onTap,
      radius: 18,
      padding: EdgeInsets.zero,
      border: live ? p.ok.withValues(alpha: 0.6) : (moved ? p.warn : null),
      gradient: stripe || gone ? null : LinearGradient(colors: [tint, p.card], stops: const [0, 0.6]),
      child: _withStripe(
        stripe ? c : null,
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(14, Space.m, Space.m, Space.m),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    // «09:00» не рвётся на «09:0/0» при крупном системном шрифте
                    width: MediaQuery.textScalerOf(context).scale(50),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(l.start, style: s.body(15, weight: FontWeight.w700)),
                        const SizedBox(height: 1),
                        Text(l.end, style: s.body(12, color: p.muted)),
                      ],
                    ),
                  ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          l.title,
                          style: gone
                              ? s.name(15).copyWith(decoration: TextDecoration.lineThrough, color: p.muted)
                              : s.name(15),
                        ),
                        if (l.kind.isNotEmpty) ...[
                          const SizedBox(height: 5),
                          dotLine(gone ? p.muted : c, l.kind.toLowerCase(), s.body(13, color: p.muted)),
                        ],
                        if (gone) ...[
                          const SizedBox(height: 7),
                          Text(
                            'пары не будет',
                            style: s.body(13, weight: FontWeight.w700, color: p.muted),
                          ),
                        ] else if (l.room.isNotEmpty) ...[
                          const SizedBox(height: 7),
                          if (moved) RoomWas(l, size: 13) else RoomPill(l.room, color: c, size: 13, inked: true),
                        ],
                        if (l.teacher.isNotEmpty && !gone) ...[
                          const SizedBox(height: 5),
                          Text(l.teacher, style: s.body(13, color: p.muted)),
                        ],
                        if (live) ...[
                          const SizedBox(height: 7),
                          dotLine(p.ok, _liveLine(l, at), s.body(13, weight: FontWeight.w700, color: p.ok)),
                        ],
                      ],
                    ),
                  ),
                  if (l.number.isNotEmpty) ...[const SizedBox(width: Space.s), PairBadge(l.number, live: live)],
                ],
              ),
            ),
            if (live)
              LinearProgressIndicator(
                value: total == 0 ? 0 : passed / total,
                minHeight: 3,
                color: p.ok,
                backgroundColor: p.ok.withValues(alpha: 0.12),
              ),
          ],
        ),
      ),
    );
    return Faded(opacity: past || gone ? 0.5 : 1, radius: 18, child: card);
  }

  static Widget _withStripe(Color? c, Widget child) => c == null
      ? child
      : Stack(
          children: [
            child,
            Positioned(left: 0, top: 0, bottom: 0, child: Container(width: 4, color: c)),
          ],
        );
}

/// Номер пары по звонку — квадратик справа («4», у сдвоенной «1–5»);
/// у идущей залит акцентом.
class PairBadge extends StatelessWidget {
  final String number;
  final bool live;
  const PairBadge(this.number, {super.key, this.live = false});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final side = MediaQuery.textScalerOf(context).scale(24);
    return Semantics(
      label: '$number пара',
      excludeSemantics: true,
      child: Container(
        constraints: BoxConstraints(minWidth: side, minHeight: side),
        padding: const EdgeInsets.symmetric(horizontal: 6),
        alignment: Alignment.center,
        decoration: BoxDecoration(color: live ? p.accent : p.line, borderRadius: BorderRadius.circular(8)),
        child: Text(
          number,
          style: s.body(12.5, weight: FontWeight.w700, color: live ? p.onAccent : p.muted),
        ),
      ),
    );
  }
}

/// Пары списком: время, полоска цвета предмета, название и место.
/// Прошедшие — бледнее, идущая — подписана.
class LessonList extends StatelessWidget {
  final List<Lesson> lessons;
  final DateTime at;

  /// Нажал пару — её экран («Пара»); null — список только для чтения.
  final ValueChanged<Lesson>? onTap;

  /// Расписание преподавателя или аудитории: под парой — чьи это пары.
  final bool showGroups;
  const LessonList({super.key, required this.lessons, required this.at, this.onTap, this.showGroups = false});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Tile(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          for (var i = 0; i < lessons.length; i++) ...[
            if (i > 0) Divider(height: 1, thickness: 1, color: p.line),
            Builder(
              builder: (context) {
                final l = lessons[i];
                final past = l.endAt != null && !at.isBefore(l.endAt!);
                final live = l.startAt != null && !past && !at.isBefore(l.startAt!);
                final gone = s.design2 && l.cancelled; // отменили (5.79) — серой и зачёркнутой
                final row = Faded(
                  opacity: past || gone ? 0.45 : 1,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                    child: IntrinsicHeight(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          SizedBox(
                            // «09:00» не рвётся на «09:0/0» при крупном системном шрифте
                            width: MediaQuery.textScalerOf(context).scale(50),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(l.start, style: s.body(15, weight: FontWeight.w600)),
                                Text(l.end, style: s.body(12, color: p.muted)),
                              ],
                            ),
                          ),
                          Container(
                            width: 3,
                            margin: const EdgeInsets.only(right: Space.m),
                            decoration: BoxDecoration(color: s.ink(l.title), borderRadius: BorderRadius.circular(2)),
                          ),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  l.title,
                                  style: gone
                                      ? s.name(15).copyWith(decoration: TextDecoration.lineThrough)
                                      : s.name(15),
                                ),
                                const SizedBox(height: 5),
                                RoomLine(l, extra: [if (showGroups && l.groups.isNotEmpty) l.groups], live: live),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
                if (onTap == null || gone) return row;
                return InkWell(
                  onTap: () {
                    tick();
                    onTap!(l);
                  },
                  child: row,
                );
              },
            ),
          ],
        ],
      ),
    );
  }
}

/// Кабинет с корпусом в скобках (владелец, 2.2): «А-332 (МП-1)»; у
/// нескольких кабинетов в одном корпусе он один раз: «А-332, Б-304 (МП-1)».
String roomText(String room) {
  final parts = room.trim().split(RegExp(r',\s*')).where((r) => r.isNotEmpty).toList();
  String one(String r) {
    final code = r.replaceAll(RegExp(r'\s*\([^)]*\)'), '').trim();
    final c = campusOf(r);
    return c.isEmpty ? code : '$code ($c)';
  }

  final r = splitRoom(room);
  final shared = parts.length > 1 && !r.campus.contains(',') && parts.every((x) => campusOf(x) == r.campus);
  return shared && r.campus.isNotEmpty ? '${r.code} (${r.campus})' : parts.map(one).join(', ');
}

/// Кабинет плашкой цвета предмета — крупнее и ярче преподавателя, видно с
/// одного взгляда (владелец, 09.10, 12А).
class RoomPill extends StatelessWidget {
  final String room;
  final Color color;
  final double size;

  /// [color] — уже тёмный оттенок предмета ([AppStyle.ink]): текст им же.
  final bool inked;
  const RoomPill(this.room, {super.key, required this.color, this.size = 14, this.inked = false});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final fg = inked && s.darkInk
        ? color
        : Color.lerp(color, p.dark ? Colors.white : Colors.black, p.dark ? 0.55 : 0.35)!;
    return Container(
      padding: EdgeInsets.symmetric(horizontal: size * 0.65, vertical: size * 0.25),
      decoration: BoxDecoration(
        color: color.withValues(alpha: p.dark ? 0.22 : 0.16),
        borderRadius: BorderRadius.circular(size * 0.65),
      ),
      child: Text(
        roomText(room),
        style: s.body(size, weight: FontWeight.w700, color: fg),
      ),
    );
  }
}

/// Кабинет сменили (5.79, Никита 12.10, «изменения» Б): прежний зачёркнут,
/// новый — плашкой, ниже — когда заметили.
class RoomWas extends StatelessWidget {
  final Lesson lesson;
  final double size;
  const RoomWas(this.lesson, {super.key, this.size = 14});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: Space.s,
          runSpacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(
              roomText(lesson.roomWas),
              style: s.body(size, color: p.muted).copyWith(decoration: TextDecoration.lineThrough),
            ),
            RoomPill(lesson.room, color: p.warn, size: size),
          ],
        ),
        const SizedBox(height: 3),
        Text(
          lesson.changedAt.isEmpty ? 'кабинет изменён' : 'кабинет изменён в ${lesson.changedAt}',
          style: s.body(12, weight: FontWeight.w600, color: p.warn),
        ),
      ],
    );
  }
}

/// Строка под названием пары: кабинет плашкой, рядом серым тип пары
/// (и чьи пары — в расписании преподавателя), у идущей — «идёт».
class RoomLine extends StatelessWidget {
  final Lesson lesson;
  final List<String> extra;
  final bool live;
  const RoomLine(this.lesson, {super.key, this.extra = const [], this.live = false});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final c = s.ink(lesson.title);
    final rest = [if (lesson.kind.isNotEmpty) lesson.kind.toLowerCase(), ...extra].join(' · ');
    return Wrap(
      spacing: Space.s,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        if (s.design2 && lesson.cancelled)
          Text(
            'пары не будет',
            style: s.body(13, weight: FontWeight.w700, color: s.p.muted),
          )
        else if (s.design2 && lesson.roomWas.isNotEmpty)
          RoomWas(lesson)
        else if (lesson.room.isNotEmpty)
          RoomPill(lesson.room, color: c, inked: true),
        if (rest.isNotEmpty) Text(rest, style: s.body(13, color: s.p.muted)),
        if (live)
          Text(
            'идёт',
            style: s.body(13, weight: FontWeight.w700, color: c),
          ),
      ],
    );
  }
}

/// «Горит» — сроки ближе всего, одной компактной карточкой.
class _SoonList extends StatelessWidget {
  final List<Deadline> items;
  final DateTime at;
  const _SoonList(this.items, {required this.at});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Tile(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          for (var i = 0; i < items.length; i++) ...[
            if (i > 0) Divider(height: 1, thickness: 1, color: p.line),
            Builder(
              builder: (context) {
                final d = items[i];
                final left = d.due.difference(at);
                final hot = left.inHours < 24;
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: 11),
                  child: Row(
                    children: [
                      Icon(Icons.local_fire_department_outlined, size: 17, color: hot ? p.danger : p.warn),
                      const SizedBox(width: Space.s),
                      Expanded(
                        child: Text(d.subject, style: s.body(14, weight: FontWeight.w600)),
                      ),
                      const SizedBox(width: Space.s),
                      Text(
                        leftText(left),
                        style: s.body(12.5, weight: FontWeight.w600, color: hot ? p.danger : p.muted),
                      ),
                    ],
                  ),
                );
              },
            ),
          ],
        ],
      ),
    );
  }
}

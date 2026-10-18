// «Сравнить неделю» (5.100.2, Никита 18.10): своя неделя рядом с любой
// группой — открыл группу в поиске, нажал «Сравнить». По дням две колонки:
// пары по времени, общая пара (то же время, предмет и аудитория) — одной
// карточкой «вместе», внизу дня — с какого времени свободны обе.
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/capy_refresh.dart' show CapyLoading;
import '../widgets/common.dart';
import 'files.dart' show BackRow;
import 'search.dart' show WeekSwitch;
import 'week.dart' show weekRange;

/// Строка дня: время и что у каждой группы (null — свободна).
typedef CompareRow = ({String start, String end, Lesson? mine, Lesson? theirs, bool together});

String _norm(String s) => s.toLowerCase().replaceAll('ё', 'е').replaceAll(RegExp(r'\s+'), ' ').trim();

/// Пары двух групп одного дня — по времени начала, общие — одной строкой.
List<CompareRow> compareDay(List<Lesson> mine, List<Lesson> theirs) {
  final starts = {
    for (final l in [...mine, ...theirs]) l.start,
  }.toList()..sort();
  return [
    for (final t in starts)
      () {
        final a = mine.where((l) => l.start == t).firstOrNull;
        final b = theirs.where((l) => l.start == t).firstOrNull;
        final together = a != null && b != null && _norm(a.title) == _norm(b.title) && _norm(a.room) == _norm(b.room);
        return (start: t, end: (a ?? b)!.end, mine: a, theirs: b, together: together);
      }(),
  ];
}

/// Название в узкую колонку: переносы только между словами, не больше
/// [maxLines] строк; не влезло — «…» (робот 18.10: «Программиров/ание»).
/// Слово длиннее строки обрезается с «…», а не рвётся посередине.
String wordLines(String text, TextStyle style, double width, {int maxLines = 2, TextScaler? scaler}) {
  final words = text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
  double measure(String t) {
    final tp = TextPainter(
      text: TextSpan(text: t, style: style),
      textScaler: scaler ?? TextScaler.noScaling,
      textDirection: TextDirection.ltr,
      maxLines: 1,
    )..layout();
    final w = tp.width;
    tp.dispose();
    return w;
  }

  String cut(String line) {
    if (measure('$line…') <= width) return '$line…';
    var t = line;
    while (t.isNotEmpty && measure('${t.trimRight()}…') > width) {
      t = t.substring(0, t.length - 1);
    }
    return '${t.trimRight()}…';
  }

  final lines = <String>[];
  var cur = '';
  for (final w in words) {
    final next = cur.isEmpty ? w : '$cur $w';
    if (measure(next) <= width) {
      cur = next;
      continue;
    }
    if (cur.isNotEmpty) {
      lines.add(cur);
      if (lines.length == maxLines) {
        lines[maxLines - 1] = cut(lines.last);
        return lines.join('\n');
      }
    }
    if (measure(w) <= width) {
      cur = w;
      continue;
    }
    // слово шире строки — обрезаем его, дальше с новой строки
    lines.add(cut(w));
    cur = '';
    if (lines.length == maxLines) return lines.join('\n');
  }
  if (cur.isNotEmpty) lines.add(cur);
  return lines.join('\n');
}

/// Размер шрифта, при котором самое длинное слово влезает в строку, — но не
/// мельче [floor] от исходного (дальше слово обрежет «…» в [wordLines]).
double fitWordSize(String text, TextStyle style, double width, {double floor = 0.82, TextScaler? scaler}) {
  final base = style.fontSize ?? 14;
  var widest = 0.0;
  for (final w in text.split(RegExp(r'\s+'))) {
    final tp = TextPainter(
      text: TextSpan(text: w, style: style),
      textScaler: scaler ?? TextScaler.noScaling,
      textDirection: TextDirection.ltr,
    )..layout();
    if (tp.width > widest) widest = tp.width;
    tp.dispose();
  }
  if (widest <= width) return base;
  return (base * width / widest * 0.98).clamp(base * floor, base);
}

/// С какого времени свободны обе: конец самой поздней пары дня; пар нет — ''.
String bothFreeFrom(List<Lesson> mine, List<Lesson> theirs) {
  final ends = [
    for (final l in [...mine, ...theirs]) l.end,
  ]..sort();
  return ends.isEmpty ? '' : ends.last;
}

class CompareScreen extends StatefulWidget {
  final Api api;

  /// Другая группа: название и недели из /target (те же, что на её экране).
  final String title;
  final List weeks;
  final int week;
  const CompareScreen({super.key, required this.api, required this.title, required this.weeks, this.week = 0});

  @override
  State<CompareScreen> createState() => _CompareScreenState();
}

class _CompareScreenState extends State<CompareScreen> {
  late int _week = widget.week;
  String _me = 'Моя группа';

  /// Своя неделя по понедельнику: день → пары.
  final _own = <String, Future<Map<String, List<Lesson>>>>{};

  @override
  void initState() {
    super.initState();
    _myName();
  }

  Future<void> _myName() async {
    try {
      final j = await widget.api.get('/me');
      final n = '${(j['group'] as Map?)?['name'] ?? ''}';
      if (n.isNotEmpty && mounted) setState(() => _me = n);
    } catch (_) {}
  }

  Map get _w => widget.weeks[_week] as Map;

  Future<Map<String, List<Lesson>>> _loadOwn(List days) async {
    final res = await Future.wait([for (final d in days) widget.api.get('/day?date=${d['date']}')]);
    return {
      for (var i = 0; i < days.length; i++)
        '${days[i]['date']}': [for (final l in (res[i]['lessons'] as List? ?? [])) Lesson.fromJson(l)],
    };
  }

  Future<Map<String, List<Lesson>>> _ownWeek() {
    final w = _w;
    return _own.putIfAbsent(
      '${w['monday']}',
      () => _loadOwn(w['days'] as List)
        ..catchError((_) {
          _own.remove('${w['monday']}'); // «Ещё раз» спросит заново
          return <String, List<Lesson>>{};
        }),
    );
  }

  void _shift(int k) {
    final next = (_week + k).clamp(0, widget.weeks.length - 1);
    if (next == _week) return;
    tick();
    setState(() => _week = next);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final w = _w;
    return Scaffold(
      body: Backdrop(
        child: SafeArea(
          child: Column(
            children: [
              const BackRow(),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.only(bottom: Space.xxl),
                  children: [
                    const ScreenTitle(title: 'Сравнить неделю'),
                    WeekSwitch(
                      label: weekRange(DateTime.parse('${w['monday']}')),
                      number: w['week'] as int?,
                      onPrev: _week > 0 ? () => _shift(-1) : null,
                      onNext: _week < widget.weeks.length - 1 ? () => _shift(1) : null,
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(Space.l + 52, Space.l, Space.l, 0),
                      child: Row(
                        children: [
                          Expanded(child: _Head(_me, color: p.accent)),
                          const SizedBox(width: Space.s),
                          Expanded(child: _Head(widget.title, color: p.text)),
                        ],
                      ),
                    ),
                    FutureBuilder<Map<String, List<Lesson>>>(
                      key: ValueKey(w['monday']),
                      future: _ownWeek(),
                      builder: (context, snap) {
                        if (snap.connectionState != ConnectionState.done) {
                          return const Padding(
                            padding: EdgeInsets.only(top: Space.xxl),
                            child: CapyLoading(),
                          );
                        }
                        final own = snap.data ?? const {};
                        if (own.isEmpty) {
                          return Notice(
                            title: 'Не загрузилось',
                            text: 'Свою неделю не получилось загрузить',
                            onRetry: () => setState(() {}),
                            pose: CapyPose.sad,
                          );
                        }
                        return Column(
                          children: [
                            for (final (i, d) in (w['days'] as List).indexed)
                              if (i < 6 || (d['lessons'] as List).isNotEmpty || (own['${d['date']}'] ?? []).isNotEmpty)
                                _Day(
                                  date: DateTime.parse('${d['date']}'),
                                  mine: own['${d['date']}'] ?? const [],
                                  theirs: [
                                    for (final l in d['lessons'] as List) Lesson.fromJson(Map<String, dynamic>.from(l)),
                                  ],
                                  other: widget.title,
                                ),
                          ],
                        );
                      },
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

class _Head extends StatelessWidget {
  final String text;
  final Color color;
  const _Head(this.text, {required this.color});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Text(
      text,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      textAlign: TextAlign.center,
      style: s.body(13, weight: FontWeight.w700, color: color),
    );
  }
}

class _Day extends StatelessWidget {
  final DateTime date;
  final List<Lesson> mine, theirs;
  final String other;
  const _Day({required this.date, required this.mine, required this.theirs, required this.other});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final rows = compareDay(mine, theirs);
    final free = bothFreeFrom(mine, theirs);
    final String foot;
    if (rows.isEmpty) {
      foot = 'Пар нет у обеих';
    } else if (mine.isEmpty) {
      foot = 'У тебя пар нет · у $other до $free';
    } else if (theirs.isEmpty) {
      foot = 'У $other пар нет · у тебя до $free';
    } else {
      foot = 'Обе свободны с $free';
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: Space.s, bottom: Space.s),
            child: Text(dayTitle(date), style: s.eyebrow(color: p.muted)),
          ),
          Tile(
            padding: const EdgeInsets.all(Space.s),
            child: LayoutBuilder(
              builder: (context, box) {
                // ширина текста в ячейке: внутри IntrinsicHeight LayoutBuilder нельзя
                final cell = (box.maxWidth - 44 - Space.xs) / 2 - Space.s * 2;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (final r in rows)
                      Padding(
                        padding: const EdgeInsets.only(bottom: Space.xs),
                        child: IntrinsicHeight(
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              SizedBox(
                                width: 44,
                                child: Padding(
                                  padding: const EdgeInsets.only(top: Space.s),
                                  child: Text(r.start, style: s.body(13, weight: FontWeight.w700)),
                                ),
                              ),
                              if (r.together)
                                Expanded(
                                  child: _Cell(
                                    lesson: r.mine,
                                    together: true,
                                    width: cell * 2 + Space.xs + Space.s * 2,
                                  ),
                                )
                              else ...[
                                Expanded(
                                  child: _Cell(lesson: r.mine, width: cell),
                                ),
                                const SizedBox(width: Space.xs),
                                Expanded(
                                  child: _Cell(lesson: r.theirs, width: cell),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(Space.s, Space.xs, Space.s, Space.xs),
                      child: Text(foot, style: s.body(13, color: p.muted)),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _Cell extends StatelessWidget {
  final Lesson? lesson;
  final bool together;
  final double width;
  const _Cell({required this.lesson, required this.width, this.together = false});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final l = lesson;
    if (l == null) {
      return Container(
        alignment: Alignment.center,
        padding: const EdgeInsets.all(Space.s),
        decoration: BoxDecoration(
          border: Border.all(color: p.line),
          borderRadius: BorderRadius.circular(Radii.tile - 6),
        ),
        child: Text('свободно', style: s.body(12, color: p.muted)),
      );
    }
    final c = s.ink(l.title);
    final room = l.room.replaceAll(RegExp(r'\s*\([^)]*\)'), '').trim();
    return Container(
      padding: const EdgeInsets.all(Space.s),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(Radii.tile - 6)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Builder(
            builder: (context) {
              final scaler = MediaQuery.textScalerOf(context);
              final style = s.body(
                fitWordSize(l.title, s.body(13, weight: FontWeight.w600), width - 1, scaler: scaler),
                weight: FontWeight.w600,
              );
              return Text(
                wordLines(l.title, style, width - 1, scaler: scaler),
                maxLines: 2,
                softWrap: false,
                style: style,
              );
            },
          ),
          Text(
            [if (together) 'вместе', if (l.kind.isNotEmpty) l.kind, if (room.isNotEmpty) room].join(' · '),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: s.body(12, color: together ? c : p.muted),
          ),
        ],
      ),
    );
  }
}

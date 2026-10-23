// «Пара» (концепт, экран 3): что за пара и сколько идёт, где (аудитория и
// корпус), кто ведёт (все его пары), какой поток; по предмету — баллы и
// посещения, лекции с конспектами. Открывается нажатием на пару где угодно.
import 'package:flutter/material.dart';

import '../achievements/store.dart';
import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';
import '../widgets/lesson_comments.dart';
import '../widgets/lesson_reactions.dart';
import '../widgets/teacher_rating.dart';
import 'files.dart';
import 'search.dart';
import 'study.dart';

/// [own] — пара своей группы: у неё реакции (5.100). В чужом расписании
/// (поиск) — нет: счёт там был бы не той группы.
void openLesson(BuildContext context, Api api, Lesson l, {bool own = true}) {
  AchStore.unlock('lesson');
  Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => LessonScreen(api: api, lesson: l, own: own),
    ),
  );
}

/// Тот же предмет в журнале СДО и в файлах: без регистра и «ё».
bool sameSubject(String a, String b) {
  String n(String x) => x.toLowerCase().replaceAll('ё', 'е').trim();
  return n(a) == n(b) || (n(a).length > 12 && n(b).startsWith(n(a))) || (n(b).length > 12 && n(a).startsWith(n(b)));
}

/// Этаж по номеру аудитории (5.100.1, Никита 18.10): первая цифра
/// трёхзначного номера, как на табличках — «А-223» → 2, «426» → 4, «А-046» →
/// цоколь. Двузначные («А-17») и без номера — не знаем, строки нет. Правило
/// сверено с планами этажей корпусов В-78, В-86, С-20, МП-1.
String roomFloor(String room) {
  final m = RegExp(r'^(?:[А-ЯЁA-Z]{1,4}-?)?(\d)\d\d(?!\d)').firstMatch(room.trim());
  if (m == null) return '';
  return m.group(1) == '0' ? 'цокольный этаж' : '${m.group(1)} этаж';
}

/// Одна лекция в PDF и PPTX — одной строкой (как в «Файлах»).
Iterable<FileItem> _uniqueLectures(Iterable<FileItem> files) {
  final seen = <String>{};
  return files.where((f) => seen.add('${f.head}|${f.topic}'.toLowerCase()));
}

class LessonExtras {
  final Course? course;
  final List<FileItem> lectures;
  LessonExtras(this.course, this.lectures);
}

class LessonScreen extends StatefulWidget {
  final Api api;
  final Lesson lesson;
  final bool own;
  const LessonScreen({super.key, required this.api, required this.lesson, this.own = true});

  @override
  State<LessonScreen> createState() => _LessonScreenState();
}

class _LessonScreenState extends State<LessonScreen> {
  Api get api => widget.api;
  Lesson get lesson => widget.lesson;

  /// Один запрос на экран (2.18): FutureBuilder в build спрашивал баллы и
  /// файлы при каждой перерисовке — по три раза за открытие.
  late final Future<LessonExtras> _extras = _loadExtras();

  /// С кем эта пара (Никита 12.10): группы, у которых в это время пара в
  /// той же аудитории, — на лекциях весь поток. В календаре своей группы
  /// других групп нет, их знает календарь аудитории (`/api/lesson/groups`).
  late final Future<List<String>> _together = _loadTogether();

  Future<List<String>> _loadTogether() async {
    final at = lesson.startAt;
    if (at == null || lesson.groups.contains(',') || (lesson.room.isEmpty && lesson.teacher.isEmpty)) return const [];
    try {
      final q = {'start': at.toIso8601String(), 'room': lesson.room, 'teacher': lesson.teacher};
      final j = await api.get('/lesson/groups?${Uri(queryParameters: q).query}');
      return [for (final g in (j['groups'] as List? ?? const [])) '$g'];
    } catch (_) {
      return const [];
    }
  }

  /// Баллы и лекции по предмету — что найдётся; нет СДО — просто без них.
  Future<LessonExtras> _loadExtras() async {
    Course? course;
    var lectures = <FileItem>[];
    try {
      final g = await api.get('/sdo/grades');
      for (final c in g['courses'] as List) {
        if (sameSubject('${c['title']}', lesson.title)) course = Course.fromJson(Map<String, dynamic>.from(c));
      }
    } catch (_) {}
    try {
      final f = await api.get('/files');
      lectures = [
        for (final x in f['items'] as List)
          if (sameSubject('${x['subject']}', lesson.title) && x['category'] == 'lecture') FileItem.fromJson(x),
      ];
    } catch (_) {}
    return LessonExtras(course, lectures);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final c = s.ink(lesson.title); // точка, «идёт», полоса, кольцо баллов
    final t = now();
    final live =
        lesson.startAt != null && lesson.endAt != null && !t.isBefore(lesson.startAt!) && t.isBefore(lesson.endAt!);
    final campus = RegExp(r'\(([^)]+)\)').firstMatch(lesson.room)?.group(1) ?? '';
    final room = lesson.room.replaceAll(RegExp(r'\s*\([^)]*\)'), '').trim();
    final floor = roomFloor(room);
    final groups = lesson.groups.split(RegExp(r',\s*')).where((g) => g.isNotEmpty).toList();
    return Scaffold(
      body: Backdrop(
        tint: subjectColor(lesson.title),
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.only(bottom: Space.xxl),
            children: [
              const BackRow(),
              Padding(
                padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // длинное название — мельче, до трёх строк (2.3); вид пары —
                    // строкой под ним обычным шрифтом, не курсивом сверху (2.4)
                    FitWords(lesson.title, style: s.title(titleSize(lesson.title, 30)), maxLines: 3),
                    if (lesson.kind.isNotEmpty || live) ...[
                      const SizedBox(height: Space.xs),
                      Row(
                        children: [
                          Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(color: c, shape: BoxShape.circle),
                          ),
                          const SizedBox(width: 6),
                          Flexible(
                            child: Text.rich(
                              TextSpan(
                                children: [
                                  if (lesson.kind.isNotEmpty)
                                    TextSpan(text: lesson.kind[0].toUpperCase() + lesson.kind.substring(1)),
                                  if (lesson.kind.isNotEmpty && live) const TextSpan(text: ' · '),
                                  if (live)
                                    TextSpan(
                                      text: 'идёт',
                                      style: TextStyle(color: c, fontWeight: FontWeight.w700),
                                    ),
                                ],
                              ),
                              style: s.body(15, color: p.muted),
                            ),
                          ),
                        ],
                      ),
                    ],
                    const SizedBox(height: Space.l),
                    Row(
                      children: [
                        Text(lesson.start, style: s.body(14, weight: FontWeight.w700)),
                        const SizedBox(width: Space.m),
                        Expanded(
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(3),
                            child: LinearProgressIndicator(
                              value: !live
                                  ? (lesson.endAt != null && !t.isBefore(lesson.endAt!) ? 1 : 0)
                                  : t.difference(lesson.startAt!).inSeconds /
                                        lesson.endAt!.difference(lesson.startAt!).inSeconds,
                              minHeight: 5,
                              color: c,
                              backgroundColor: p.line,
                            ),
                          ),
                        ),
                        const SizedBox(width: Space.m),
                        Text(lesson.end, style: s.body(14, weight: FontWeight.w700)),
                      ],
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: Space.l),
                child: Tile(
                  padding: EdgeInsets.zero,
                  child: Column(
                    children: [
                      if (room.isNotEmpty)
                        _InfoRow(
                          icon: Icons.place_outlined,
                          title: room,
                          text: [
                            if (floor.isNotEmpty) floor,
                            if (campus.isNotEmpty) 'корпус $campus',
                            campus.isEmpty && floor.isEmpty ? 'аудитория · её расписание' : 'расписание аудитории',
                          ].join(' · '),
                          onTap: () => openTarget(context, api, room, 3),
                        ),
                      if (lesson.teacher.isNotEmpty) ...[
                        Divider(height: 1, color: p.line),
                        _InfoRow(
                          icon: Icons.person_outline_rounded,
                          title: lesson.teacher,
                          text: 'все пары преподавателя',
                          // оценка в капибарах (вариант А, 19.10) — своей группе
                          extra: widget.own ? TeacherRatingLine(api: api, name: lesson.teacher) : null,
                          onTap: () => openTarget(context, api, lesson.teacher, 2, subject: lesson.title),
                        ),
                      ],
                      if (groups.length <= 1)
                        FutureBuilder<List<String>>(
                          future: _together,
                          builder: (context, snap) {
                            final g = snap.data ?? const <String>[];
                            if (g.isEmpty) return const SizedBox.shrink();
                            final n = g.length;
                            return Column(
                              children: [
                                Divider(height: 1, color: p.line),
                                _InfoRow(
                                  icon: Icons.groups_outlined,
                                  title: n == 1
                                      ? 'Вместе с ${g.first}'
                                      : 'Общая пара · ещё $n ${plural(n, 'группа', 'группы', 'групп')}',
                                  text: n == 1
                                      ? 'общая пара · расписание группы'
                                      : n > 10
                                      ? '${g.take(9).join(', ')} и ещё ${n - 9}'
                                      : g.join(', '),
                                  onTap: n == 1 ? () => openTarget(context, api, g.first, 1) : null,
                                ),
                              ],
                            );
                          },
                        ),
                      if (groups.length > 1) ...[
                        Divider(height: 1, color: p.line),
                        _InfoRow(
                          icon: Icons.groups_outlined,
                          title: 'Поток · ${groups.length} ${plural(groups.length, 'группа', 'группы', 'групп')}',
                          text: groups.length > 3 ? '${groups.first} … ${groups.last}' : groups.join(', '),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              if (widget.own && !lesson.cancelled) LessonReactions(api: api, lesson: lesson),
              if (widget.own) LessonComments(api: api, lesson: lesson),
              FutureBuilder<LessonExtras>(
                future: _extras,
                builder: (context, snap) {
                  final x = snap.data;
                  if (x == null || (x.course == null && x.lectures.isEmpty)) return const SizedBox.shrink();
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Section('По предмету'),
                      if (x.course != null)
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: Space.l),
                          child: _CourseStrip(api: api, course: x.course!, color: c),
                        ),
                      for (final f in _uniqueLectures(x.lectures.reversed).take(3))
                        Padding(
                          padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, 0),
                          child: Tile(
                            onTap: () => showFileSheet(context, api, f),
                            padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                            child: Row(
                              children: [
                                Icon(Icons.menu_book_outlined, size: 20, color: p.muted),
                                const SizedBox(width: Space.m),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(f.head, style: s.body(15, weight: FontWeight.w600)),
                                      if (f.topic.isNotEmpty) Text(f.topic, style: s.body(13, color: p.muted)),
                                    ],
                                  ),
                                ),
                                if (f.hasText)
                                  Text(
                                    f.hasSummary ? 'Конспект' : 'Открыть',
                                    style: s.body(13, weight: FontWeight.w700, color: p.accent),
                                  ),
                              ],
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String title, text;
  final VoidCallback? onTap;

  /// Ещё строка под подписью (оценка преподавателя) — со своим нажатием.
  final Widget? extra;
  const _InfoRow({required this.icon, required this.title, required this.text, this.onTap, this.extra});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return InkWell(
      onTap: onTap == null
          ? null
          : () {
              tick();
              onTap!();
            },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
        child: Row(
          children: [
            Icon(icon, color: s.p.accent, size: 20),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: s.body(16, weight: FontWeight.w600)),
                  Text(text, style: s.body(13, color: s.p.muted)),
                  ?extra,
                ],
              ),
            ),
            if (onTap != null) Icon(Icons.chevron_right_rounded, color: s.p.muted),
          ],
        ),
      ),
    );
  }
}

/// Баллы и цель коротко; нажал — экран предмета.
class _CourseStrip extends StatelessWidget {
  final Api api;
  final Course course;
  final Color color;
  const _CourseStrip({required this.api, required this.course, required this.color});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final c = course;
    return Tile(
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => CourseScreen(api: api, course: c),
        ),
      ),
      child: Row(
        children: [
          ScoreRing(
            value: c.score / c.top,
            color: color,
            child: Text('${c.score}', style: s.number(18)),
          ),
          const SizedBox(width: Space.l),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Баллы БРС', style: s.body(13, color: s.p.muted)),
                Text(
                  c.need > 0 ? 'до «${c.needLabel}» ещё ${c.need}' : c.enoughText,
                  style: s.body(16, weight: FontWeight.w700),
                ),
                if (c.worksTotal > 0)
                  Text('работы: зачтено ${c.worksPassed} из ${c.worksTotal}', style: s.body(13, color: s.p.muted)),
              ],
            ),
          ),
          Icon(Icons.chevron_right_rounded, color: s.p.muted),
        ],
      ),
    );
  }
}

/// Расписание группы, преподавателя или аудитории: найти в справочнике МИРЭА
/// (тип 1 — группа, 2 — преподаватель, 3 — аудитория) и открыть (search.dart).
/// [subject] — предмет пары, с которой пришли: однофамилец, который его ведёт
/// (`match` от сервера), открывается сразу, без выбора (Никита 21.10).
Future<void> openTarget(BuildContext context, Api api, String query, int type, {String subject = ''}) async {
  final s = AppStyle.of(context);
  final toast = Overlay.of(context, rootOverlay: true);
  List items;
  try {
    final subj = subject.isEmpty ? '' : '&subject=${Uri.encodeQueryComponent(subject)}';
    items = (await api.get('/search?q=${Uri.encodeQueryComponent(query)}&type=$type$subj'))['items'] as List;
  } catch (_) {
    toastOn(toast, 'Расписание МИРЭА сейчас не отвечает', kind: ToastKind.error);
    return;
  }
  if (items.isEmpty) {
    toastOn(toast, '«$query» в расписании МИРЭА не нашёл');
    return;
  }
  Map pick = items.first;
  final match = [
    for (final it in items)
      if (it is Map && it['match'] == true) it,
  ];
  if (match.length == 1) {
    pick = match.first;
  } else if (items.length > 1 && context.mounted) {
    // однофамильцы: «Морозов В. А.» бывает трижды — подсказка у каждого
    final chosen = await showModalBottomSheet<Map>(
      useSafeArea: true,
      context: context,
      backgroundColor: s.p.cardSolid,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final it in items.take(8))
              ListTile(
                title: Text('${it['title']}', style: s.body(15, weight: FontWeight.w600)),
                subtitle: it['hint'] == null ? null : Text('${it['hint']}', style: s.body(13, color: s.p.muted)),
                onTap: () => Navigator.pop(ctx, it),
              ),
          ],
        ),
      ),
    );
    if (chosen == null) return;
    pick = chosen;
  }
  if (context.mounted) await openTargetScreen(context, api, Target.fromJson(pick));
}

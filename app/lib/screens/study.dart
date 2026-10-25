// «Учёба» — баллы БРС по предметам: кольцо «сколько набрано», сколько до
// следующей отметки, работы текущего контроля. Нажал предмет — его экран.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/common.dart';
import '../widgets/goal_card.dart';
import 'chat.dart';
import 'files.dart';
import 'sdo_connect.dart';
import 'task.dart';

class Course {
  final int id;
  final String title, needLabel, finalMark;
  final num score, max, need;
  final int worksTotal, worksPassed;
  final List<Map<String, dynamic>> works, categories;
  final List<({num at, String label})> marks;
  final Map<String, dynamic>? goal, attendance, history;

  Course.fromJson(Map<String, dynamic> j)
    : id = j['id'] as int,
      title = j['title'] ?? '',
      needLabel = j['need_label'] ?? '',
      finalMark = j['final'] ?? '',
      score = j['score'] ?? 0,
      max = j['max'] ?? 100,
      need = j['need'] ?? 0,
      worksTotal = j['works_total'] ?? 0,
      worksPassed = j['works_passed'] ?? 0,
      works = [for (final w in (j['works'] as List? ?? [])) Map<String, dynamic>.from(w)],
      categories = [for (final c in (j['categories'] as List? ?? [])) Map<String, dynamic>.from(c)],
      marks = [for (final m in (j['marks'] as List? ?? [])) (at: m['at'] as num, label: '${m['label']}')],
      goal = _map(j['goal']),
      attendance = _map(j['attendance']),
      history = _map(j['history']);

  static Map<String, dynamic>? _map(Object? v) => v is Map ? Map<String, dynamic>.from(v) : null;

  /// Порог высшей отметки — «полное» кольцо (у экзамена это 5 при 80).
  num get top => marks.isEmpty ? max : marks.last.at;

  /// Все пороги пройдены — need_label пуст («на «» уже хватает»):
  /// тогда называем высшую набранную отметку.
  String get enoughText {
    final got = [
      for (final m in marks)
        if (score >= m.at) m.label,
    ];
    final label = got.isNotEmpty ? got.last : needLabel;
    return label.isEmpty ? 'баллов уже хватает' : 'на ${markWord(label)} уже хватает';
  }
}

class StudyScreen extends StatelessWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const StudyScreen({super.key, required this.api, this.onUnauthorized});

  Future<_StudyData> _load() async {
    // статус входа — рядом, без него баллы всё равно показываем
    final status = api
        .get('/sdo/status')
        .then<String?>((r) => r is Map ? r['state'] as String? : null, onError: (_) => null);
    try {
      final j = await api.get('/sdo/grades');
      return (courses: [for (final c in j['courses'] as List) Course.fromJson(c)], problem: null, sdo: await status);
    } on ApiError catch (e) {
      return (courses: <Course>[], problem: e.message, sdo: await status);
    }
  }

  /// «Вход в СДО»; вернулся — баллы и статус заново.
  Future<void> _openConnect(BuildContext context, Future<void> Function() reload) async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => SdoConnectScreen(api: api)));
    await reload();
  }

  @override
  Widget build(BuildContext context) => Loader<_StudyData>(
    load: _load,
    onUnauthorized: onUnauthorized,
    builder: (context, d, reload) => ListView(
      padding: const EdgeInsets.only(bottom: 120),
      children: [
        ScreenTitle(
          title: 'Учёба',
          trailing: d.sdo == null ? null : _SdoBadge(state: d.sdo!, onTap: () => _openConnect(context, reload)),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.l),
          child: Row(
            children: [
              Expanded(
                child: _Door(
                  icon: Icons.auto_awesome_outlined,
                  title: 'Kapi ИИ',
                  text: 'Отвечает по лекциям',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => ChatScreen(api: api))),
                ),
              ),
              const SizedBox(width: Space.s),
              Expanded(
                child: _Door(
                  icon: Icons.folder_outlined,
                  title: 'Файлы',
                  text: 'лекции, практики',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => FilesScreen(api: api))),
                ),
              ),
            ],
          ),
        ),
        if (d.problem != null && needsSdo(d.problem!))
          _ConnectCard(problem: d.problem!, onTap: () => _openConnect(context, reload))
        else if (d.problem != null)
          Notice(title: 'Баллы не видны', text: d.problem!, onRetry: reload)
        else if (d.courses.isEmpty)
          const Notice(title: 'Пока пусто', text: 'Преподаватели ещё не завели журналы.'),
        for (final c in d.courses)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
            child: _CourseRow(
              c: c,
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => CourseScreen(api: api, course: c),
                ),
              ),
            ),
          ),
      ],
    ),
  );
}

typedef _StudyData = ({List<Course> courses, String? problem, String? sdo});

/// Статус СДО в шапке: точка (работает / устарел / нет) и «СДО».
class _SdoBadge extends StatelessWidget {
  final String state;
  final VoidCallback onTap;
  const _SdoBadge({required this.state, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final (color, label) = switch (state) {
      'ok' => (p.ok, 'СДО подключено'),
      'expired' => (p.danger, 'Вход в СДО устарел'),
      _ => (p.muted, 'СДО не подключено'),
    };
    return Semantics(
      container: true,
      button: true,
      label: label,
      child: Material(
        color: p.card,
        shape: StadiumBorder(side: BorderSide(color: p.line)),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () {
            tick();
            onTap();
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                ),
                const SizedBox(width: 6),
                ExcludeSemantics(
                  child: Text('СДО', style: s.body(13, weight: FontWeight.w600)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Баллы не видны без своего входа — объясняем, что он даст, и ведём подключить.
/// Новый дизайн (5.80, «Пусто и ошибка»): не подключено — это не ошибка, а
/// что появится: капибара, «Подключи СДО», одна строка и «Подключить».
/// Вход устарел — по-прежнему грустная карточка «подключи заново».
class _ConnectCard extends StatelessWidget {
  final String problem;
  final VoidCallback onTap;
  const _ConnectCard({required this.problem, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final expired = problem.contains('устарел');
    if (s.design2 && !expired) return _ConnectBenefit(onTap: onTap);
    final title = problem.replaceFirst(RegExp(r':\s*вкладка.*$'), '');
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: Tile(
        radius: Radii.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CapyImage(pose: expired ? CapyPose.sad : CapyPose.day, size: 64, color: p.accent),
                const SizedBox(width: Space.l),
                Expanded(
                  child: Text(
                    title.isEmpty ? title : title[0].toUpperCase() + title.substring(1),
                    style: s.body(17, weight: FontWeight.w600),
                  ),
                ),
              ],
            ),
            const SizedBox(height: Space.m),
            Text(
              'Баллы и задания у каждого свои — их видно только со своим входом в СДО.',
              style: s.body(14, color: p.muted),
            ),
            const SizedBox(height: Space.m),
            for (final (icon, text) in sdoPerks)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    Icon(icon, size: 18, color: p.accent),
                    const SizedBox(width: Space.m),
                    Expanded(child: Text(text, style: s.body(14))),
                  ],
                ),
              ),
            const SizedBox(height: Space.l),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: p.accent,
                  foregroundColor: p.onAccent,
                  shape: const StadiumBorder(),
                ),
                onPressed: () {
                  tick();
                  onTap();
                },
                child: Text(expired ? 'Подключить заново' : 'Подключить СДО'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ConnectBenefit extends StatelessWidget {
  final VoidCallback onTap;
  const _ConnectBenefit({required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: Tile(
        radius: Radii.card,
        child: Column(
          children: [
            const SizedBox(height: Space.s),
            CapyImage(pose: CapyPose.joy, size: 96, color: p.accent),
            const SizedBox(height: Space.m),
            Text('Подключи СДО', textAlign: TextAlign.center, style: s.title(22)),
            const SizedBox(height: Space.s),
            Text(
              'Баллы, посещения и сдача работ появятся здесь',
              textAlign: TextAlign.center,
              style: s.body(15, color: p.muted),
            ),
            const SizedBox(height: Space.l),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: p.accent,
                  foregroundColor: p.onAccent,
                  shape: const StadiumBorder(),
                ),
                onPressed: () {
                  tick();
                  onTap();
                },
                child: const Text('Подключить'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Вход в «Помощника» и «Файлы» — две плитки над баллами.
class _Door extends StatelessWidget {
  final IconData icon;
  final String title, text;
  final VoidCallback onTap;
  const _Door({required this.icon, required this.title, required this.text, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Tile(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: s.p.accent),
          const SizedBox(height: Space.m),
          Text(title, style: s.name(18)),
          const SizedBox(height: 2),
          Text(text, style: s.body(13, color: s.p.muted)),
        ],
      ),
    );
  }
}

/// Кольцо: доля набранного от высшей отметки, цвет — цвет предмета.
class ScoreRing extends StatelessWidget {
  final double value;
  final Color color;
  final double size, stroke;
  final Widget? child;
  const ScoreRing({super.key, required this.value, required this.color, this.size = 54, this.stroke = 5, this.child});

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
    tween: Tween(begin: 0, end: value.clamp(0, 1)),
    duration: const Duration(milliseconds: 900),
    curve: Curves.easeOutCubic,
    builder: (context, v, _) => CustomPaint(
      size: Size.square(size),
      painter: _Ring(v, color, AppStyle.of(context).p.line, stroke),
      child: SizedBox.square(
        dimension: size,
        child: Center(child: child),
      ),
    ),
  );
}

class _Ring extends CustomPainter {
  final double v, stroke;
  final Color c, bg;
  _Ring(this.v, this.c, this.bg, this.stroke);

  @override
  void paint(Canvas canvas, Size size) {
    final r = Offset.zero & size;
    final p = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(r.deflate(stroke / 2), 0, 2 * math.pi, false, p..color = bg);
    canvas.drawArc(r.deflate(stroke / 2), -math.pi / 2, 2 * math.pi * v, false, p..color = c);
  }

  @override
  bool shouldRepaint(_Ring old) => old.v != v || old.c != c || old.bg != bg;
}

class _CourseRow extends StatelessWidget {
  final Course c;
  final VoidCallback onTap;
  const _CourseRow({required this.c, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final color = s.ink(c.title);
    final status = c.finalMark.isNotEmpty
        ? 'итог — ${c.finalMark}'
        : c.need > 0
        ? 'до «${c.needLabel}» ещё ${c.need} ${plural(c.need.round(), 'балл', 'балла', 'баллов')}'
        : c.enoughText;
    return Tile(
      onTap: onTap,
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
                Text(c.title, style: s.body(15, weight: FontWeight.w600)),
                const SizedBox(height: 3),
                Text(status, style: s.body(13, color: c.need > 0 ? p.muted : p.ok)),
                if (c.worksTotal > 0)
                  Text('работы: зачтено ${c.worksPassed} из ${c.worksTotal}', style: s.body(13, color: p.muted)),
              ],
            ),
          ),
          Icon(Icons.chevron_right_rounded, color: p.muted),
        ],
      ),
    );
  }
}

const _workStatus = {
  'ok': (Icons.check_circle_rounded, 'зачтено'),
  'low': (Icons.error_outline_rounded, 'ниже порога'),
  'wait': (Icons.hourglass_top_rounded, 'ждёт оценки'),
  'open': (Icons.radio_button_unchecked_rounded, 'можно сдать'),
  'miss': (Icons.cancel_outlined, 'не сдано'),
};

class CourseScreen extends StatelessWidget {
  final Api api;
  final Course course;
  const CourseScreen({super.key, required this.api, required this.course});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final color = s.ink(course.title);
    return Scaffold(
      body: Backdrop(
        tint: subjectColor(course.title),
        child: SafeArea(
          child: Loader<Course>(
            load: () async => Course.fromJson(await api.get('/sdo/grades/${course.id}')),
            builder: (context, c, _) => ListView(
              padding: const EdgeInsets.only(bottom: Space.xxl),
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(left: Space.s),
                    child: IconButton(
                      onPressed: () => Navigator.pop(context),
                      icon: Icon(Icons.arrow_back_ios_new_rounded, size: 20, color: p.text),
                    ),
                  ),
                ),
                ScreenTitle(title: c.title, sub: c.marks.length > 1 ? 'экзамен' : 'зачёт'),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: Tile(
                    radius: Radii.card,
                    child: Row(
                      children: [
                        ScoreRing(
                          value: c.score / c.top,
                          color: color,
                          size: 120,
                          stroke: 10,
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text('${c.score}', style: s.number(40)),
                              Text('из ${c.top}', style: s.body(12, color: p.muted)),
                            ],
                          ),
                        ),
                        const SizedBox(width: Space.l),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Отметки', style: s.body(13, color: p.muted)),
                              const SizedBox(height: Space.s),
                              Wrap(
                                spacing: 6,
                                runSpacing: 6,
                                children: [
                                  for (final m in c.marks)
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                      decoration: BoxDecoration(
                                        color: c.score >= m.at ? color : p.line,
                                        borderRadius: BorderRadius.circular(Radii.pill),
                                      ),
                                      child: Text(
                                        '${m.label} · ${m.at}',
                                        style: s.body(
                                          13,
                                          weight: FontWeight.w600,
                                          color: c.score >= m.at ? Colors.white : p.muted,
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                              const SizedBox(height: Space.m),
                              Text(
                                c.need > 0 ? 'ещё ${c.need} до «${c.needLabel}»' : c.enoughText,
                                style: s.body(16, weight: FontWeight.w700),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                if (c.goal != null) ...[
                  const SizedBox(height: Space.m),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.l),
                    child: GoalCard(api: api, courseId: c.id, goal: c.goal!, color: color),
                  ),
                ],
                if (c.attendance != null && (c.attendance!['lectures'] as List? ?? []).isNotEmpty) ...[
                  const Section('Посещения лекций'),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.l),
                    child: Tile(
                      child: AttendanceStrip(att: c.attendance!, color: color, api: api, courseId: c.id),
                    ),
                  ),
                ],
                if (c.works.isNotEmpty) ...[
                  Section('Текущий контроль · ${c.worksPassed} из ${c.worksTotal} зачтено'),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.l),
                    child: Tile(
                      padding: EdgeInsets.zero,
                      child: Column(
                        children: [
                          for (var i = 0; i < c.works.length; i++) ...[
                            if (i > 0) Divider(height: 1, color: p.line),
                            _WorkRow(w: c.works[i], color: color, api: api, course: c.title),
                          ],
                        ],
                      ),
                    ),
                  ),
                ],
                if (c.categories.isNotEmpty) ...[
                  const Section('Из чего баллы'),
                  for (final cat in c.categories)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.m),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Expanded(child: Text('${cat['name']}', style: s.body(14))),
                              Text('${cat['score']} / ${cat['max']}', style: s.body(14, weight: FontWeight.w600)),
                            ],
                          ),
                          const SizedBox(height: 5),
                          ClipRRect(
                            borderRadius: BorderRadius.circular(3),
                            child: LinearProgressIndicator(
                              value: (cat['max'] ?? 0) == 0 ? 0 : (cat['score'] as num) / (cat['max'] as num),
                              minHeight: 5,
                              color: color,
                              backgroundColor: p.line,
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
                if (c.history != null) ...[
                  const Section('Как растут баллы'),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.l),
                    child: Tile(
                      child: HistoryChart(history: c.history!, color: color),
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

class _WorkRow extends StatelessWidget {
  final Map<String, dynamic> w;
  final Color color;
  final Api api;
  final String course;
  const _WorkRow({required this.w, required this.color, required this.api, required this.course});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final st = _workStatus[w['status']] ?? (Icons.radio_button_unchecked_rounded, '');
    final iconColor = switch (w['status']) {
      'ok' => p.ok,
      'low' || 'miss' => p.danger,
      'wait' => p.warn,
      _ => p.muted,
    };
    final grade = w['grade'];
    // Задание или тест — свой экран (описание, файлы, «Сдать»); прочее — страница в СДО.
    final isTask = (w['module'] == 'assign' || w['module'] == 'quiz') && w['cmid'] is int;
    final url = w['url'] is String ? w['url'] as String : null;
    return InkWell(
      onTap: !isTask && url == null
          ? null
          : () {
              tick();
              if (isTask) {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => TaskScreen(api: api, work: w, course: course),
                  ),
                );
              } else {
                launchUrl(Uri.parse(url!), mode: LaunchMode.externalApplication);
              }
            },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
        child: Row(
          children: [
            Icon(st.$1, size: 20, color: iconColor),
            const SizedBox(width: Space.m),
            Expanded(
              child: Text('${w['name']}', style: s.body(14, weight: FontWeight.w600)),
            ),
            const SizedBox(width: Space.s),
            Text(
              grade != null ? '$grade/${w['max']}' : st.$2,
              style: s.body(13, color: grade != null ? p.text : p.muted),
            ),
            if (isTask) ...[
              const SizedBox(width: Space.xs),
              Icon(Icons.chevron_right_rounded, size: 20, color: p.muted),
            ],
          ],
        ),
      ),
    );
  }
}

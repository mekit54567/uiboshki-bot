// «Учёба» и экран предмета нового дизайна (брендбук v1, вторая пачка
// макетов, Никита 11.11) — только при «Новом» в «Оформлении»
// ([AppStyle.fresh]); прежние экраны не меняются.
// «Учёба»: заголовок и строка «баллы из СДО · обновлено в 09:40» вместо
// метки «СДО» (нажал — «Вход в СДО»), маленькая карточка «2 автомата» (Никита
// 17.11: средний балл БРС никому не нужен), входы «Kapi ИИ» и «Файлы»,
// предметы одной карточкой.
// Предмет: кольцо и отметки, цель (как сейчас: автомат и «с экзаменом»),
// посещения квадратиками с короткой легендой, работы со статусом словами,
// файлы предмета, из чего баллы и как они росли.
part of 'study.dart';

/// Строка под «Учёбой»: откуда баллы и когда обновлены; без входа — что с ним.
({String text, Color? color}) _sdoLine(_StudyData d, Palette p) {
  if (d.problem != null && needsSdo(d.problem!)) {
    return d.problem!.contains('устарел')
        ? (text: 'вход в СДО устарел · подключить заново', color: p.danger)
        : (text: 'СДО не подключено', color: null);
  }
  if (d.sdo == 'expired') return (text: 'вход в СДО устарел · подключить заново', color: p.danger);
  final u = d.updated;
  return (text: u == null ? 'баллы из СДО' : 'баллы из СДО · обновлено ${updatedText(u, now())}', color: null);
}

class _FreshStudy extends StatelessWidget {
  final Api api;
  final _StudyData d;
  final Future<void> Function() reload;
  final VoidCallback onConnect;
  const _FreshStudy({required this.api, required this.d, required this.reload, required this.onConnect});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final line = _sdoLine(d, p);
    void push(Widget screen) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
    Widget pad(Widget child) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: child,
    );
    // «отвечает по лекциям» на узком экране — в две строки: двери всё равно одной высоты
    final doors = pad(
      IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: _FreshDoor(
                icon: Icons.auto_awesome_outlined,
                title: 'Kapi ИИ',
                text: 'отвечает по лекциям',
                onTap: () => push(ChatScreen(api: api)),
              ),
            ),
            const SizedBox(width: Space.s),
            Expanded(
              child: _FreshDoor(
                icon: Icons.folder_outlined,
                title: 'Файлы',
                text: 'лекции, практики',
                onTap: () => push(FilesScreen(api: api)),
              ),
            ),
          ],
        ),
      ),
    );
    return ListView(
      key: const ValueKey('study:fresh'),
      padding: const EdgeInsets.only(bottom: 120),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.m, Space.m),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Учёба', style: s.title(30)),
                    const SizedBox(height: 6),
                    Semantics(
                      button: true,
                      child: GestureDetector(
                        key: const Key('study:sdo'),
                        behavior: HitTestBehavior.opaque,
                        onTap: () {
                          tick();
                          onConnect();
                        },
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          child: Text(
                            line.text,
                            style: s.body(
                              13,
                              weight: line.color == null ? FontWeight.w400 : FontWeight.w600,
                              color: line.color ?? p.muted,
                            ),
                          ),
                        ),
                      ),
                    ),
                    if (pulseOpenNow.value) PulseStudyLine(api: api),
                  ],
                ),
              ),
              const SizedBox(width: Space.s),
              CapyImage(pose: CapyPose.evening, size: 62, color: p.text),
            ],
          ),
        ),
        if (d.problem != null && needsSdo(d.problem!)) ...[
          _ConnectCard(problem: d.problem!, onTap: onConnect),
          const SizedBox(height: Space.m),
          doors,
        ] else if (d.problem != null) ...[
          Notice(title: 'Баллы не видны', text: d.problem!, onRetry: reload),
          const SizedBox(height: Space.m),
          doors,
        ] else if (d.courses.isEmpty) ...[
          const Notice(title: 'Пока пусто', text: 'Преподаватели ещё не завели журналы.'),
          const SizedBox(height: Space.m),
          doors,
        ] else ...[
          if (d.courses.any((c) => c.firstReached)) ...[
            pad(_FreshAutos(courses: d.courses)),
            const SizedBox(height: Space.m),
          ],
          doors,
          Section('Предметы · ${d.courses.length}'),
          pad(
            Tile(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  for (final (i, c) in d.courses.indexed) ...[
                    if (i > 0) Divider(height: 1, color: p.line),
                    _FreshCourseRow(
                      c: c,
                      onTap: () => push(CourseScreen(api: api, course: c)),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

/// Сколько автоматов (Никита 17.11 — вместо среднего балла БРС): маленькая
/// карточка, только когда хоть где-то баллов уже хватает на «3» или зачёт.
/// Где баллов хватает, но работ зачтено меньше 75 %, — строкой ниже: автомат
/// там ещё не выходит (правило БРС, как в «Цели»).
class _FreshAutos extends StatelessWidget {
  final List<Course> courses;
  const _FreshAutos({required this.courses});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final autos = courses.where((c) => c.isAuto).length;
    final rest = courses.where((c) => c.firstReached && !c.isAuto).length;
    String where(int n) => '$n\u00A0${plural(n, 'предмете', 'предметах', 'предметах')}';
    final note = rest == 0
        ? null
        : autos == 0
        ? 'Баллов хватает в ${where(rest)}, осталось зачесть работы'
        : 'Ещё в ${where(rest)} баллов хватает, осталось зачесть работы';
    return Tile(
      key: const Key('study:autos'),
      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, Space.m),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (autos > 0)
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text('$autos', style: s.number(34)),
                const SizedBox(width: Space.s),
                Text(plural(autos, 'автомат', 'автомата', 'автоматов'), style: s.title(21)),
              ],
            )
          else
            Text('Автоматов пока нет', style: s.title(21)),
          if (note != null) ...[const SizedBox(height: 4), Text(note, style: s.body(13, color: p.muted))],
        ],
      ),
    );
  }
}

/// Вход в «Kapi ИИ» и «Файлы»: значок, название и строка.
class _FreshDoor extends StatelessWidget {
  final IconData icon;
  final String title, text;
  final VoidCallback onTap;
  const _FreshDoor({required this.icon, required this.title, required this.text, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Tile(
      onTap: onTap,
      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 24, color: s.p.accent),
          const SizedBox(height: Space.s),
          Text(title, style: s.title(21)),
          const SizedBox(height: 2),
          Text(text, style: s.body(13, color: s.p.muted)),
        ],
      ),
    );
  }
}

/// Кольцо в строке предмета: 50, а не 46, чтобы «18,5» не касалось края.
const double _ring = 50, _stroke = 4;

/// Строка предмета в общей карточке: кольцо с баллом, название, сколько работ зачтено.
class _FreshCourseRow extends StatelessWidget {
  final Course c;
  final VoidCallback onTap;
  const _FreshCourseRow({required this.c, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return InkWell(
      onTap: () {
        tick();
        onTap();
      },
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
        child: Row(
          children: [
            ScoreRing(
              value: c.score / c.top,
              color: s.ink(c.title),
              size: _ring,
              stroke: _stroke,
              // «18,5» не наползает на кольцо (Никита 19.11): кольцо чуть больше, а длинное число — мельче до влезания
              child: SizedBox(
                width: _ring - 2 * _stroke - 6,
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(fmtNum(c.score), style: s.number(c.score >= 100 ? 15 : 17)),
                ),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // «бизнес-процессов» не рвётся после дефиса; длинное слово на узком экране — мельче
                  FitWords(c.title, style: s.name(15)),
                  // только работы: «до зачёта ещё…» и «итог — 2» под названием не пишем (Никита 19.11)
                  if (c.worksTotal > 0) ...[
                    const SizedBox(height: 2),
                    Text(
                      'Работ зачтено\u00A0${c.worksPassed}\u00A0из\u00A0${c.worksTotal}',
                      style: s.body(13, color: p.muted),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: Space.xs),
            Icon(Icons.chevron_right_rounded, color: p.muted),
          ],
        ),
      ),
    );
  }
}

/// Экран предмета нового дизайна (макет 4).
class _FreshCourse extends StatelessWidget {
  final Api api;
  final Course c;
  const _FreshCourse({required this.api, required this.c});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final color = s.ink(c.title);
    final att = c.attendance;
    final lectures = att == null ? const [] : (att['lectures'] as List? ?? const []);
    Widget pad(Widget child) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: child,
    );
    return ListView(
      key: const ValueKey('course:fresh'),
      padding: const EdgeInsets.only(bottom: Space.xxl),
      children: [
        Row(
          children: [
            const BackRow(),
            const Spacer(),
            Padding(
              padding: const EdgeInsets.only(right: Space.l),
              child: AskKapi(
                tapKey: const Key('course:ask'),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => ChatScreen(api: api, subject: c.title),
                  ),
                ),
              ),
            ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.xl, Space.xs, Space.xl, Space.l),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    c.marks.length > 1 ? 'экзамен' : 'зачёт',
                    style: s.body(13, weight: FontWeight.w600, color: p.muted),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              FitWords(c.title, style: s.title(titleSize(c.title, 30)), maxLines: 3),
            ],
          ),
        ),
        pad(_FreshScore(c: c, color: color)),
        if (c.goal != null) ...[
          const SizedBox(height: Space.m),
          pad(GoalCard(api: api, courseId: c.id, goal: c.goal!, color: color, updated: c.updated)),
        ],
        if (att != null && lectures.isNotEmpty) ...[
          Section(
            (att['past'] as num? ?? 0) > 0
                ? 'Посещения лекций · был на ${att['attended'] ?? 0} из ${att['past']}'
                : 'Посещения лекций',
          ),
          pad(
            Tile(
              child: AttendanceStrip(att: att, color: color, api: api, courseId: c.id),
            ),
          ),
        ],
        if (c.works.isNotEmpty) ...[
          Section('Текущий контроль · зачтено ${c.worksPassed} из ${c.worksTotal}'),
          pad(
            Tile(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  for (var i = 0; i < c.works.length; i++) ...[
                    if (i > 0) Divider(height: 1, color: p.line),
                    _FreshWorkRow(w: c.works[i], api: api, course: c.title),
                  ],
                ],
              ),
            ),
          ),
        ],
        _SubjectFiles(api: api, subject: c.title),
        if (c.categories.isNotEmpty) ...[
          const Section('Из чего баллы'),
          pad(
            Tile(
              child: Column(
                children: [
                  for (final (i, cat) in c.categories.indexed) ...[
                    if (i > 0) const SizedBox(height: Space.m),
                    _FreshCategory(cat: cat, color: color),
                  ],
                ],
              ),
            ),
          ),
        ],
        if (c.history != null) ...[
          const Section('Как растут баллы'),
          pad(
            Tile(
              child: HistoryChart(history: c.history!, color: color),
            ),
          ),
        ],
      ],
    );
  }
}

/// Кольцо баллов и отметки: набранные — залиты цветом предмета.
class _FreshScore extends StatelessWidget {
  final Course c;
  final Color color;
  const _FreshScore({required this.c, required this.color});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final next = c.finalMark.isNotEmpty
        ? 'итог — ${c.finalMark}'
        : c.need > 0
        ? 'ещё ${fmtNum(c.need)} до ${c.needLabel == 'зачёт' ? 'зачёта' : '«${c.needLabel}»'}'
        : c.enoughText;
    return Tile(
      key: const Key('course:score'),
      radius: Radii.card,
      child: Row(
        children: [
          ScoreRing(
            value: c.score / c.top,
            color: color,
            size: 108,
            stroke: 9,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(fmtNum(c.score), style: s.number(34)),
                const SizedBox(height: 2),
                Text('из ${fmtNum(c.top)}', style: s.body(12, color: p.muted)),
              ],
            ),
          ),
          const SizedBox(width: Space.l),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Отметки', style: s.eyebrow()),
                const SizedBox(height: Space.s),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (final m in c.marks)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: c.score >= m.at ? color : p.bg,
                          borderRadius: BorderRadius.circular(Radii.pill),
                          border: Border.all(color: c.score >= m.at ? color : p.line),
                        ),
                        child: Text(
                          '${m.label} · ${fmtNum(m.at)}',
                          style: s.body(
                            12.5,
                            weight: FontWeight.w600,
                            color: c.score >= m.at ? (p.dark ? p.bg : Colors.white) : p.muted,
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: Space.m),
                Text(
                  next,
                  style: s.body(16, weight: FontWeight.w700, color: c.need > 0 && c.finalMark.isEmpty ? p.text : p.ok),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Срок работы из СДО («четверг, 15 октября 2026, 23:59») — коротко:
/// «сегодня до 23:59», «завтра до 23:59», «до 15 октября, 23:59».
String? workDue(String raw, DateTime at) {
  final m = RegExp(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})(?:\D+(\d{1,2}):(\d{2}))?').firstMatch(raw.toLowerCase());
  if (m == null) return null;
  final month = monthsGen.indexOf(m.group(2)!);
  if (month < 0) return null;
  final day = DateTime(int.parse(m.group(3)!), month + 1, int.parse(m.group(1)!));
  final time = m.group(4) == null ? '' : '${m.group(4)!.padLeft(2, '0')}:${m.group(5)}';
  final u = at.toUtc().add(const Duration(hours: 3));
  final n = day.difference(DateTime(u.year, u.month, u.day)).inHours / 24;
  if (n.round() == 0) return time.isEmpty ? 'сегодня' : 'сегодня до $time';
  if (n.round() == 1) return time.isEmpty ? 'завтра' : 'завтра до $time';
  return 'до ${day.day} ${monthsGen[month]}${time.isEmpty ? '' : ', $time'}';
}

/// Статус работы словами — теми же, что на экране «Сдать» и экране задания.
({String text, Color color}) _workLine(Map<String, dynamic> w, Palette p, DateTime at) {
  final due = w['due'] is String ? workDue(w['due'] as String, at) : null;
  return switch ('${w['status']}') {
    'ok' => (text: 'зачтено', color: p.ok),
    'low' => (text: 'ниже порога', color: p.danger),
    'wait' => (text: 'отправлено, ждёт оценки', color: p.warn),
    'late' => (text: 'срок прошёл, ждём оценку', color: p.warn),
    'miss' => (text: 'срок прошёл', color: p.danger),
    'offline' => (text: 'сдаётся на занятии', color: p.muted),
    'soon' => (text: 'ещё закрыто', color: p.muted),
    'todo' || 'open' => (text: due == null ? 'можно сдать' : 'сдать $due', color: p.accent),
    _ => (text: '', color: p.muted),
  };
}

/// Работа текущего контроля: название, статус словами, балл справа. Задание,
/// которое можно сдать, — с кнопкой «Сдать» (открывает экран задания).
class _FreshWorkRow extends StatelessWidget {
  final Map<String, dynamic> w;
  final Api api;
  final String course;
  const _FreshWorkRow({required this.w, required this.api, required this.course});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final line = _workLine(w, p, now());
    final grade = w['grade'];
    final isTask = (w['module'] == 'assign' || w['module'] == 'quiz') && w['cmid'] is int;
    final url = w['url'] is String ? w['url'] as String : null;
    final submit = isTask && w['module'] == 'assign' && (w['status'] == 'todo' || w['status'] == 'open');
    void open() {
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
    }

    return InkWell(
      onTap: !isTask && url == null ? null : open,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  FitWords('${w['name']}', style: s.body(15, weight: FontWeight.w600)),
                  if (line.text.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Row(
                      children: [
                        Container(
                          width: 7,
                          height: 7,
                          decoration: BoxDecoration(color: line.color, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: 6),
                        Flexible(
                          child: Text(
                            line.text,
                            style: s.body(13, weight: FontWeight.w600, color: line.color),
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: Space.s),
            if (submit)
              FilledButton(
                key: ValueKey('course:submit:${w['cmid']}'),
                style: FilledButton.styleFrom(
                  backgroundColor: p.accent,
                  foregroundColor: p.onAccent,
                  shape: const StadiumBorder(),
                  minimumSize: const Size(0, 40),
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                ),
                onPressed: open,
                child: const Text('Сдать'),
              )
            else
              Text(
                grade != null ? '${fmtNum(grade as num)} / ${w['max']}' : '– / ${w['max'] ?? '–'}',
                style: s.body(14, weight: FontWeight.w700, color: grade != null ? p.text : p.muted),
              ),
          ],
        ),
      ),
    );
  }
}

/// «Файлы предмета · 5 файлов · лекции, практики» — если в «Файлах» группы
/// есть файлы этого предмета; нажал — они списком.
class _SubjectFiles extends StatefulWidget {
  final Api api;
  final String subject;
  const _SubjectFiles({required this.api, required this.subject});

  @override
  State<_SubjectFiles> createState() => _SubjectFilesState();
}

class _SubjectFilesState extends State<_SubjectFiles> {
  late final Future<List<FileItem>> _files = _load();

  Future<List<FileItem>> _load() async {
    try {
      final f = await widget.api.get('/files');
      return [
        for (final x in f['items'] as List)
          if (sameSubject('${x['subject']}', widget.subject)) FileItem.fromJson(Map<String, dynamic>.from(x)),
      ];
    } catch (_) {
      return const [];
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<List<FileItem>>(
    future: _files,
    builder: (context, snap) {
      final files = snap.data ?? const <FileItem>[];
      if (files.isEmpty) return const SizedBox.shrink();
      final s = AppStyle.of(context);
      final p = s.p;
      const words = {'lecture': 'лекции', 'practice': 'практики', 'control': 'КР и тесты', 'method': 'методички'};
      final kinds = [
        for (final k in words.keys)
          if (files.any((f) => f.category == k)) words[k]!,
      ];
      final n = files.length;
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Section('Материалы'),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: Tile(
              key: const Key('course:files'),
              padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => SubjectFilesScreen(api: widget.api, subject: files.first.subject, files: files),
                ),
              ),
              child: Row(
                children: [
                  Icon(Icons.folder_outlined, size: 22, color: p.accent),
                  const SizedBox(width: Space.m),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Файлы предмета', style: s.body(15, weight: FontWeight.w600)),
                        Text(
                          [
                            '$n ${plural(n, 'файл', 'файла', 'файлов')}',
                            if (kinds.isNotEmpty) kinds.take(2).join(', '),
                          ].join(' · '),
                          style: s.body(13, color: p.muted),
                        ),
                      ],
                    ),
                  ),
                  Icon(Icons.chevron_right_rounded, size: 20, color: p.muted),
                ],
              ),
            ),
          ),
        ],
      );
    },
  );
}

/// Строка «Из чего баллы»: название, счёт и тонкая полоса цвета предмета.
class _FreshCategory extends StatelessWidget {
  final Map<String, dynamic> cat;
  final Color color;
  const _FreshCategory({required this.cat, required this.color});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final max = (cat['max'] as num?) ?? 0, score = (cat['score'] as num?) ?? 0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text('${cat['name']}', style: s.body(14))),
            Text('${fmtNum(score)} / ${fmtNum(max)}', style: s.body(14, weight: FontWeight.w600)),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: max == 0 ? 0 : (score / max).clamp(0, 1).toDouble(),
            minHeight: 5,
            color: color,
            backgroundColor: p.line,
          ),
        ),
      ],
    );
  }
}

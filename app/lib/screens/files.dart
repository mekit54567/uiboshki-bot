// Файлы курсов: предметы → файлы по типам (лекции, практики…). Нажал файл —
// лист: конспект (общий на всех, ИИ зовётся один раз), скачать (окно «Сохранить
// в Файлы»), просмотр в браузере, прислать в Telegram.
// Поиск сверху: файлы по названию и места в самих лекциях («где было про NPV?»
// → «Лекция 5 · слайд 12» и отрывок) — нажал, открылась страница (showPageSheet).
import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/capy_refresh.dart';
import '../widgets/common.dart';
import '../widgets/report.dart' show openReportMenu;
import '../widgets/tg_html.dart';
import 'lesson.dart' show sameSubject;

class FileItem {
  final int id;
  final String title, subject, fileName, category;

  /// «Лекция 8» и тема отдельно — тема строкой под номером (владелец, 09.10).
  final String head, topic;
  final bool hasText, hasSummary;

  /// Загрузил сам (или староста) — без «Пожаловаться» (сервер: can_edit).
  final bool canEdit;

  FileItem.fromJson(Map<String, dynamic> j)
    : id = j['id'] as int,
      title = j['title'] ?? '',
      head = (j['head'] as String?)?.isNotEmpty == true ? j['head'] : (j['title'] ?? ''),
      topic = j['topic'] ?? '',
      subject = j['subject'] ?? '',
      fileName = j['file_name'] ?? '',
      category = j['category'] ?? 'other',
      hasText = j['has_text'] == true,
      hasSummary = j['has_summary'] == true,
      canEdit = j['can_edit'] == true;
}

/// Подписи типов — без эмодзи (в интерфейсе их не используем).
const categoryLabels = {
  'lecture': 'Лекции',
  'practice': 'Практики и лабы',
  'control': 'КР и тесты',
  'method': 'Методички',
  'exam': 'Экзамен и зачёт',
  'other': 'Другое',
};

const _categoryIcons = {
  'lecture': Icons.menu_book_outlined,
  'practice': Icons.science_outlined,
  'control': Icons.fact_check_outlined,
  'method': Icons.library_books_outlined,
  'exam': Icons.workspace_premium_outlined,
  'other': Icons.insert_drive_file_outlined,
};

class FilesScreen extends StatefulWidget {
  final Api api;
  const FilesScreen({super.key, required this.api});

  @override
  State<FilesScreen> createState() => _FilesScreenState();
}

/// Место в тексте лекции из поиска (/api/lecture-search): лекция · слайд · отрывок.
class LectureHit {
  final int fileId, page;
  final String title, subject, place, snippet;

  LectureHit.fromJson(Map<String, dynamic> j)
    : fileId = j['file_id'] as int,
      page = (j['page'] as num?)?.toInt() ?? 1,
      title = j['title'] ?? '',
      subject = j['subject'] ?? '',
      place = j['place'] ?? '',
      snippet = j['snippet'] ?? '';
}

class _FilesScreenState extends State<FilesScreen> {
  final _search = TextEditingController();
  Timer? _debounce;
  String _query = '';
  int _seq = 0; // ответ старого запроса не перетирает новый
  List<FileItem>? _found; // по названию; null — ещё ищем
  List<LectureHit>? _hits; // в тексте лекций; null — ещё ищем
  bool _ready = true; // false — тексты лекций ещё индексируются

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _onQuery(String v) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _run(v.trim()));
  }

  Future<void> _run(String q) async {
    if (!mounted || q == _query) return;
    final my = ++_seq;
    setState(() {
      _query = q;
      _found = null;
      _hits = null;
      _ready = true;
    });
    if (q.isEmpty) return;
    final enc = Uri.encodeQueryComponent(q);
    final files = widget.api
        .get('/files?q=$enc')
        .then((j) => [for (final f in (j['items'] as List? ?? [])) FileItem.fromJson(Map<String, dynamic>.from(f))])
        .catchError((_) => <FileItem>[]);
    // короче трёх букв сервер в лекциях не ищет
    final lectures = q.length < 3
        ? Future.value((items: <LectureHit>[], ready: true))
        : widget.api
              .get('/lecture-search?q=$enc')
              .then(
                (j) => (
                  items: [
                    for (final h in (j['items'] as List? ?? [])) LectureHit.fromJson(Map<String, dynamic>.from(h)),
                  ],
                  ready: j['ready'] != false,
                ),
              )
              .catchError((_) => (items: <LectureHit>[], ready: true));
    final f = await files;
    if (mounted && my == _seq) setState(() => _found = f);
    final l = await lectures;
    if (mounted && my == _seq) {
      setState(() {
        _hits = l.items;
        _ready = l.ready;
      });
    }
  }

  /// Найденное: файлы по названию, ниже — места в самих лекциях.
  List<Widget> _results(BuildContext context) {
    final p = AppStyle.of(context).p;
    final found = _found, hits = _hits;
    final spinner = Padding(
      padding: const EdgeInsets.all(Space.xl),
      child: Center(child: CircularProgressIndicator(color: p.accent, strokeWidth: 2.5)),
    );
    if (found == null) return [spinner];
    if (found.isEmpty && hits != null && hits.isEmpty) {
      return [
        Notice(
          title: 'Ничего не нашлось',
          text: _ready ? 'Ни в названиях, ни в тексте лекций.' : 'Тексты лекций ещё индексируются.',
          pose: CapyPose.sad,
        ),
      ];
    }
    final stems = queryStems(_query);
    return [
      if (found.isNotEmpty) ...[
        Section('Файлы · ${found.length}'),
        _card(p, [for (final f in found) _FileRow(api: widget.api, f: f, withSubject: true)]),
      ],
      if (hits == null) spinner,
      if (hits != null && hits.isNotEmpty) ...[
        const Section('В тексте лекций'),
        _card(p, [for (final h in hits) _HitRow(api: widget.api, h: h, stems: stems)]),
      ],
    ];
  }

  Widget _card(Palette p, List<Widget> rows) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: Space.l),
    child: Tile(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          for (var i = 0; i < rows.length; i++) ...[if (i > 0) Divider(height: 1, color: p.line), rows[i]],
        ],
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final api = widget.api;
    return Scaffold(
      body: Backdrop(
        child: SafeArea(
          child: Loader<List<FileItem>>(
            load: () async => [for (final f in (await api.get('/files'))['items'] as List) FileItem.fromJson(f)],
            builder: (context, files, _) {
              final bySubject = <String, List<FileItem>>{};
              for (final f in files) {
                (bySubject[f.subject.isEmpty ? 'Без предмета' : f.subject] ??= []).add(f);
              }
              final subjects = bySubject.keys.toList()..sort();
              return ListView(
                padding: const EdgeInsets.only(bottom: Space.xxl),
                keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                children: [
                  const BackRow(),
                  const ScreenTitle(title: 'Файлы'),
                  if (files.isEmpty)
                    const Notice(title: 'Пока пусто', text: 'Файлы курсов появятся после выгрузки из СДО.')
                  else
                    _SearchField(key: const ValueKey('files-search'), controller: _search, onChanged: _onQuery),
                  if (_query.isNotEmpty)
                    ..._results(context)
                  else
                    for (final s in subjects)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
                        child: _SubjectRow(
                          subject: s,
                          count: bySubject[s]!.length,
                          onTap: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => SubjectFilesScreen(api: api, subject: s, files: bySubject[s]!),
                            ),
                          ),
                        ),
                      ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

class _SearchField extends StatelessWidget {
  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  const _SearchField({super.key, required this.controller, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
      child: Container(
        padding: const EdgeInsets.only(left: Space.l),
        decoration: BoxDecoration(
          color: p.card,
          borderRadius: BorderRadius.circular(Radii.pill),
          border: Border.all(color: p.line),
        ),
        child: ValueListenableBuilder<TextEditingValue>(
          valueListenable: controller,
          builder: (context, v, _) => TextField(
            controller: controller,
            onChanged: onChanged,
            textInputAction: TextInputAction.search,
            style: s.body(15),
            decoration: InputDecoration(
              border: InputBorder.none,
              icon: Icon(Icons.search_rounded, color: p.muted),
              hintText: 'Название или слово из лекции',
              hintStyle: s.body(15, color: p.muted),
              suffixIcon: v.text.isEmpty
                  ? null
                  : IconButton(
                      tooltip: 'Очистить',
                      icon: Icon(Icons.close_rounded, color: p.muted),
                      onPressed: () {
                        controller.clear();
                        onChanged('');
                      },
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Корни слов запроса — первые пять букв (без окончаний), как в WebApp.
List<String> queryStems(String q) => [
  for (final w in q.toLowerCase().split(RegExp(r'[^\p{L}\p{N}_]+', unicode: true)))
    if (w.length >= 3) w.length > 5 ? w.substring(0, 5) : w,
];

/// Отрывок, где слова запроса выделены.
TextSpan markStems(String text, List<String> stems, TextStyle base, TextStyle mark) {
  if (stems.isEmpty) return TextSpan(text: text, style: base);
  final re = RegExp('(${stems.map(RegExp.escape).join('|')})[\\p{L}\\p{N}_]*', caseSensitive: false, unicode: true);
  final parts = <TextSpan>[];
  var at = 0;
  for (final m in re.allMatches(text)) {
    if (m.start > at) parts.add(TextSpan(text: text.substring(at, m.start)));
    parts.add(TextSpan(text: m.group(0), style: mark));
    at = m.end;
  }
  if (at < text.length) parts.add(TextSpan(text: text.substring(at)));
  return TextSpan(style: base, children: parts);
}

class _HitRow extends StatelessWidget {
  final Api api;
  final LectureHit h;
  final List<String> stems;
  const _HitRow({required this.api, required this.h, required this.stems});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return InkWell(
      onTap: () {
        tick();
        showPageSheet(context, api, h.fileId, h.page, subject: h.subject);
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Icon(Icons.auto_stories_outlined, color: p.muted, size: 20),
            ),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(text: h.title),
                        if (h.place.isNotEmpty)
                          TextSpan(
                            text: ' · ${h.place}',
                            style: TextStyle(color: p.accent),
                          ),
                      ],
                    ),
                    style: s.body(15, weight: FontWeight.w600),
                  ),
                  const SizedBox(height: 2),
                  Text.rich(
                    markStems(
                      h.snippet,
                      stems,
                      s.body(13, color: p.muted),
                      TextStyle(color: p.text, fontWeight: FontWeight.w700),
                    ),
                  ),
                  if (h.subject.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(h.subject, style: s.body(12, color: p.muted)),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Кнопка «назад» вверху экранов, открытых поверх вкладок.
class BackRow extends StatelessWidget {
  const BackRow({super.key});

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: Padding(
      padding: const EdgeInsets.only(left: Space.s),
      child: IconButton(
        tooltip: 'Назад',
        onPressed: () => Navigator.pop(context),
        icon: Icon(Icons.arrow_back_ios_new_rounded, size: 20, color: AppStyle.of(context).p.text),
      ),
    ),
  );
}

class _SubjectRow extends StatelessWidget {
  final String subject;
  final int count;
  final VoidCallback onTap;
  const _SubjectRow({required this.subject, required this.count, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Tile(
      onTap: onTap,
      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
      child: Row(
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(color: AppStyle.of(context).ink(subject), shape: BoxShape.circle),
          ),
          const SizedBox(width: Space.m),
          Expanded(
            child: Text(subject, style: s.body(15, weight: FontWeight.w600)),
          ),
          Text('$count', style: s.body(14, color: s.p.muted)),
          Icon(Icons.chevron_right_rounded, color: s.p.muted),
        ],
      ),
    );
  }
}

/// Фильтр файлов предмета: «Лабы» отдельно от практик (в базе это один тип).
const fileFilters = {
  'lecture': 'Лекции',
  'practice': 'Практики',
  'lab': 'Лабы',
  'control': 'КР и тесты',
  'method': 'Методички',
  'exam': 'Экзамен',
  'other': 'Другое',
};

/// Название раздела: у зачётного предмета «Экзамен» — «Вопросы к зачёту»
/// (владелец, 2.15).
String filterLabel(String k, {bool credit = false}) =>
    k == 'exam' && credit ? 'Вопросы к зачёту' : fileFilters[k] ?? fileFilters['other']!;

/// Предмет зачётный — по журналу СДО: kind «credit», а у старых ответов без
/// kind — одна отметка («зачёт»). Нет предмета в журнале — null.
bool? isCreditCourse(Map grades, String subject) {
  for (final c in (grades['courses'] as List? ?? const [])) {
    if (c is! Map || !sameSubject('${c['title']}', subject)) continue;
    final kind = c['kind'];
    if (kind is String && kind.isNotEmpty) return kind == 'credit';
    final marks = c['marks'] as List? ?? const [];
    return marks.length == 1;
  }
  return null;
}

String fileFilterOf(FileItem f) =>
    f.category == 'practice' && RegExp(r'лаб|lab', caseSensitive: false).hasMatch(f.title) ? 'lab' : f.category;

/// Одинаковые названия (одна лекция в PDF и PPTX, повторная выгрузка) — одной
/// строкой; в группе первым — файл с конспектом или текстом. «Лекция 1» и
/// «Лекция 1. Презентация» — тоже одна лекция (у презентации темы нет).
List<List<FileItem>> groupSameTitle(List<FileItem> files) {
  final groups = <String, List<FileItem>>{};
  for (final f in files) {
    (groups['${f.head}|${f.topic}'.trim().toLowerCase()] ??= []).add(f);
  }
  int rank(FileItem f) => f.hasSummary ? 0 : (f.hasText ? 1 : 2);
  final out = [for (final g in groups.values) g..sort((a, b) => rank(a).compareTo(rank(b)))];
  out.sort((a, b) => naturalCompare(a.first.title, b.first.title));
  return out;
}

/// «Лекция 2» раньше «Лекция 10»: числа сравниваются как числа.
int naturalCompare(String a, String b) {
  final re = RegExp(r'\d+|\D+');
  final x = re.allMatches(a.toLowerCase()).map((m) => m.group(0)!).toList();
  final y = re.allMatches(b.toLowerCase()).map((m) => m.group(0)!).toList();
  for (var i = 0; i < x.length && i < y.length; i++) {
    final nx = int.tryParse(x[i]), ny = int.tryParse(y[i]);
    final c = nx != null && ny != null ? nx.compareTo(ny) : x[i].compareTo(y[i]);
    if (c != 0) return c;
  }
  return x.length.compareTo(y.length);
}

class SubjectFilesScreen extends StatefulWidget {
  final Api api;
  final String subject;
  final List<FileItem> files;
  const SubjectFilesScreen({super.key, required this.api, required this.subject, required this.files});

  @override
  State<SubjectFilesScreen> createState() => _SubjectFilesScreenState();
}

class _SubjectFilesScreenState extends State<SubjectFilesScreen> {
  String? _filter; // null — все типы
  bool _credit = false; // зачётный предмет — «Вопросы к зачёту»

  @override
  void initState() {
    super.initState();
    if (widget.files.any((f) => fileFilterOf(f) == 'exam')) _checkCredit();
  }

  /// Зачёт или экзамен — из журнала СДО; нет входа или сети — как было.
  Future<void> _checkCredit() async {
    try {
      final g = await widget.api.get('/sdo/grades');
      final credit = g is Map && isCreditCourse(g, widget.subject) == true;
      if (credit && mounted) setState(() => _credit = true);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final files = widget.files;
    final byKind = <String, List<FileItem>>{};
    for (final f in files) {
      (byKind[fileFilterOf(f)] ??= []).add(f);
    }
    final kinds = [
      for (final k in fileFilters.keys)
        if (byKind[k] != null) k,
    ];
    final s = AppStyle.of(context);
    final p = s.p;
    final color = s.ink(widget.subject);
    Widget chip(String? key, String label) {
      final on = _filter == key;
      return Padding(
        padding: const EdgeInsets.only(right: Space.s),
        child: Semantics(
          button: true,
          selected: on,
          child: GestureDetector(
            onTap: () {
              tick();
              setState(() => _filter = key);
            },
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: on ? color : p.card,
                borderRadius: BorderRadius.circular(Radii.pill),
                border: Border.all(color: on ? color : p.line),
              ),
              child: Text(
                label,
                style: s.body(14, weight: FontWeight.w600, color: on ? Colors.white : p.text),
              ),
            ),
          ),
        ),
      );
    }

    Widget card(List<FileItem> list) {
      final rows = groupSameTitle(list);
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l),
        child: Tile(
          padding: EdgeInsets.zero,
          child: Column(
            children: [
              for (var i = 0; i < rows.length; i++) ...[
                if (i > 0) Divider(height: 1, color: p.line),
                _FileRow(api: widget.api, f: rows[i].first, same: rows[i].sublist(1)),
              ],
            ],
          ),
        ),
      );
    }

    return Scaffold(
      body: Backdrop(
        tint: subjectColor(widget.subject),
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.only(bottom: Space.xxl),
            children: [
              const BackRow(),
              ScreenTitle(title: widget.subject),
              if (kinds.length > 1)
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
                  child: Row(
                    children: [
                      chip(null, 'Все'),
                      for (final k in kinds) chip(k, '${filterLabel(k, credit: _credit)} · ${byKind[k]!.length}'),
                    ],
                  ),
                ),
              if (_filter != null && byKind[_filter] != null) ...[
                const SizedBox(height: Space.s),
                card(byKind[_filter]!),
              ] else
                for (final k in kinds) ...[Section(filterLabel(k, credit: _credit)), card(byKind[k]!)],
            ],
          ),
        ),
      ),
    );
  }
}

class _FileRow extends StatelessWidget {
  final Api api;
  final FileItem f;
  final bool withSubject; // в результатах поиска — ещё и предмет
  final List<FileItem> same; // то же название в другом формате — кнопками справа
  const _FileRow({required this.api, required this.f, this.withSubject = false, this.same = const []});

  static String extOf(FileItem f) => f.fileName.contains('.') ? f.fileName.split('.').last.toUpperCase() : '';

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final ext = extOf(f);
    // в предмете тип уже в заголовке раздела — словом только в поиске
    final info = [
      if (withSubject && f.subject.isNotEmpty) f.subject,
      if (withSubject && _kindWord[fileFilterOf(f)] != null) _kindWord[fileFilterOf(f)]!,
    ].join(' · ');
    return InkWell(
      onTap: () {
        tick();
        showFileSheet(context, api, f);
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
        child: Row(
          children: [
            FormatBadge(ext: ext, category: f.category),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(f.head, style: s.name(15)),
                  if (f.topic.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(f.topic, style: s.body(14, color: s.p.text)),
                    ),
                  if (info.isNotEmpty || f.hasSummary)
                    Text.rich(
                      TextSpan(
                        children: [
                          if (f.hasSummary)
                            TextSpan(
                              text: 'есть конспект',
                              style: s.body(12, weight: FontWeight.w600, color: s.p.ok),
                            ),
                          if (f.hasSummary && info.isNotEmpty) const TextSpan(text: ' · '),
                          if (info.isNotEmpty) TextSpan(text: info),
                        ],
                      ),
                      style: s.body(12, color: s.p.muted),
                    ),
                ],
              ),
            ),
            for (final o in same)
              Padding(
                padding: const EdgeInsets.only(left: Space.s),
                child: ActionChip(
                  label: Text(
                    extOf(o).isEmpty ? 'ещё' : extOf(o),
                    style: s.body(12, weight: FontWeight.w700, color: formatColor(extOf(o), s.p)),
                  ),
                  visualDensity: VisualDensity.compact,
                  side: BorderSide(color: s.p.line),
                  backgroundColor: s.p.card,
                  onPressed: () {
                    tick();
                    showFileSheet(context, api, o);
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Тип файла словом под названием: «лекция», «лаба».
const _kindWord = {
  'lecture': 'лекция',
  'practice': 'практика',
  'lab': 'лаба',
  'control': 'контрольная',
  'method': 'методичка',
  'exam': 'к экзамену',
};

/// Тип файла для окна «Сохранить в Файлы».
String fileMime(String name) => switch (name.split('.').last.toLowerCase()) {
  'pdf' => 'application/pdf',
  'pptx' => 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'ppt' => 'application/vnd.ms-powerpoint',
  'docx' => 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'doc' => 'application/msword',
  'xlsx' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'txt' => 'text/plain',
  'zip' => 'application/zip',
  'png' => 'image/png',
  'jpg' || 'jpeg' => 'image/jpeg',
  _ => 'application/octet-stream',
};

/// Цвет формата: PDF красный, презентация оранжевая, Word синий, таблица
/// зелёная — как значки в самих программах (владелец, 09.10, 16А).
Color formatColor(String ext, Palette p) => switch (ext) {
  'PDF' => p.danger,
  'PPT' || 'PPTX' || 'ODP' || 'KEY' => const Color(0xFFF2994A),
  'DOC' || 'DOCX' || 'RTF' || 'ODT' => const Color(0xFF4F8CFF),
  'XLS' || 'XLSX' || 'CSV' || 'ODS' => p.ok,
  'ZIP' || 'RAR' || '7Z' => const Color(0xFF8B7CF6),
  'JPG' || 'JPEG' || 'PNG' || 'HEIC' => const Color(0xFF2EC4B6),
  _ => p.muted,
};

/// Значок формата слева от файла: «PDF» на подложке его цвета; без
/// расширения — значок типа файла.
class FormatBadge extends StatelessWidget {
  final String ext, category;
  const FormatBadge({super.key, required this.ext, this.category = 'other'});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final c = formatColor(ext, s.p);
    final label = ext.length > 4 ? ext.substring(0, 4) : ext;
    return Container(
      width: 40,
      height: 44,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: c.withValues(alpha: s.p.dark ? 0.18 : 0.14),
        borderRadius: BorderRadius.circular(10),
      ),
      child: label.isEmpty
          ? Icon(_categoryIcons[category] ?? Icons.insert_drive_file_outlined, color: c, size: 20)
          // «PPTX» при крупном системном шрифте уменьшается, а не обрезается
          : Padding(
              padding: const EdgeInsets.symmetric(horizontal: 3),
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(
                  label,
                  maxLines: 1,
                  style: s.body(10.5, weight: FontWeight.w800, color: c).copyWith(letterSpacing: 0.4),
                ),
              ),
            ),
    );
  }
}

/// Адрес картинки страницы: сервер даёт полный (WEBAPP_URL), стенд — относительный.
String pageImageUrl(String url) => url.startsWith('http') ? url : '${Api.base}/${url.replaceFirst(RegExp('^/'), '')}';

/// Страница лекции по ссылке из ответа ИИ или из поиска («Лекция 5 · слайд 12»):
/// у PDF — сама страница картинкой, ниже текст; листать соседние, «Весь файл» —
/// обычный лист файла.
Future<void> showPageSheet(BuildContext context, Api api, int fileId, int page, {String subject = ''}) {
  final s = AppStyle.of(context);
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: s.p.cardSolid,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) => _PageSheet(api: api, host: context, fileId: fileId, page: page, subject: subject),
  );
}

class _PageSheet extends StatefulWidget {
  final Api api;
  final BuildContext host; // экран под листом — с него откроется «Весь файл»
  final int fileId, page;
  final String subject;
  const _PageSheet({
    required this.api,
    required this.host,
    required this.fileId,
    required this.page,
    required this.subject,
  });

  @override
  State<_PageSheet> createState() => _PageSheetState();
}

class _PageSheetState extends State<_PageSheet> {
  Map<String, dynamic>? _p;
  String? _error;
  int _seq = 0, _page = 1;
  String _title = '';

  @override
  void initState() {
    super.initState();
    _open(widget.page);
  }

  Future<void> _open(int page) async {
    final my = ++_seq;
    setState(() {
      _error = null;
      _page = page;
    });
    try {
      final r = Map<String, dynamic>.from(await widget.api.get('/files/${widget.fileId}/page/$page'));
      if (!mounted || my != _seq) return;
      setState(() {
        _p = r;
        _title = r['title'] ?? _title;
      });
    } on ApiError catch (e) {
      if (mounted && my == _seq) setState(() => _error = e.message);
    } catch (e) {
      if (mounted && my == _seq) setState(() => _error = errorText(e));
    }
  }

  void _wholeFile() {
    tick();
    Navigator.pop(context);
    if (!widget.host.mounted) return;
    showFileSheet(
      widget.host,
      widget.api,
      FileItem.fromJson({'id': widget.fileId, 'title': _title, 'subject': widget.subject, 'has_text': true}),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final d = _p;
    final whole = FilledButton.icon(
      style: FilledButton.styleFrom(
        backgroundColor: p.accent,
        foregroundColor: p.onAccent,
        shape: const StadiumBorder(),
      ),
      onPressed: _wholeFile,
      icon: const Icon(Icons.description_outlined, size: 18),
      label: const Text('Весь файл'),
    );
    final List<Widget> children;
    if (_error != null) {
      children = [
        Text('Не открылось', style: s.title(22)),
        const SizedBox(height: Space.s),
        Text(_error!, style: s.body(15, color: p.muted)),
        const SizedBox(height: Space.l),
        SizedBox(width: double.infinity, child: whole),
      ];
    } else if (d == null) {
      children = [Padding(padding: const EdgeInsets.all(Space.xxl), child: const CapyLoading())];
    } else {
      final page = (d['page'] as num?)?.toInt() ?? _page;
      final pages = (d['pages'] as num?)?.toInt() ?? page;
      final kind = d['kind'] == 'слайд' ? 'Слайд' : (d['kind'] == 'стр.' ? 'Страница' : 'Часть');
      final image = d['image'] as String?;
      final text = (d['text'] as String? ?? '').trim();
      children = [
        Text('$kind $page из $pages', style: s.eyebrow()),
        const SizedBox(height: 4),
        Text(_title, style: s.name(20)),
        if (image != null && image.isNotEmpty) ...[
          const SizedBox(height: Space.l),
          ClipRRect(
            borderRadius: BorderRadius.circular(Radii.chip),
            child: Image.network(
              pageImageUrl(image),
              key: ValueKey(image),
              width: double.infinity,
              fit: BoxFit.fitWidth,
              semanticLabel: '$kind $page',
              errorBuilder: (_, _, _) => const SizedBox.shrink(),
            ),
          ),
        ],
        if (text.isNotEmpty) ...[
          const SizedBox(height: Space.l),
          SelectableText(text, style: image != null ? s.body(13, color: p.muted) : s.body(15)),
        ],
        const SizedBox(height: Space.l),
        Row(
          children: [
            IconButton(
              tooltip: 'Предыдущая',
              onPressed: page > 1 ? () => _open(page - 1) : null,
              icon: Icon(Icons.chevron_left_rounded, color: page > 1 ? p.text : p.line),
            ),
            Expanded(child: whole),
            IconButton(
              tooltip: 'Следующая',
              onPressed: page < pages ? () => _open(page + 1) : null,
              icon: Icon(Icons.chevron_right_rounded, color: page < pages ? p.text : p.line),
            ),
          ],
        ),
      ];
    }
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.88),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.xl),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
        ),
      ),
    );
  }
}

Future<void> showFileSheet(BuildContext context, Api api, FileItem f) {
  final s = AppStyle.of(context);
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: s.p.cardSolid,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) => _FileSheet(api: api, f: f),
  );
}

class _FileSheet extends StatefulWidget {
  final Api api;
  final FileItem f;
  const _FileSheet({required this.api, required this.f});

  @override
  State<_FileSheet> createState() => _FileSheetState();
}

class _FileSheetState extends State<_FileSheet> {
  String? _summary, _note;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    if (widget.f.hasSummary) _loadSummary(make: false);
  }

  Future<void> _loadSummary({required bool make}) async {
    setState(() {
      _busy = true;
      _note = make ? 'Делаю конспект — это до минуты…' : null;
    });
    try {
      final r = make
          ? await widget.api.post('/summary/${widget.f.id}')
          : await widget.api.get('/summary/${widget.f.id}');
      setState(() {
        _summary = r['summary'] as String?;
        _note = null;
      });
    } on ApiError catch (e) {
      setState(() => _note = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// «Скачать»: на телефоне — сразу системное окно «Сохранить в Файлы»
  /// (владелец, 09.10: раньше перекидывало в Safari, и то качало, то
  /// открывало); в браузере — обычная загрузка по ссылке.
  Future<void> _download() async {
    tick();
    try {
      final r = await widget.api.post('/files/${widget.f.id}/link');
      final url = r['url'] as String;
      if (kIsWeb) {
        await launchUrl(Uri.parse(url));
        return;
      }
      setState(() => _note = 'Скачиваю…');
      final name = r['file_name'] as String? ?? widget.f.fileName;
      final bytes = await widget.api.download(url);
      if (!mounted) return;
      final saved = await FilePicker.saveFile(fileName: name, bytes: bytes, mimeType: fileMime(name));
      if (mounted) setState(() => _note = saved == null ? null : 'Сохранил в Файлы.');
    } on ApiError catch (e) {
      // Больше 20 МБ Bot API не отдаёт — тогда файл придёт в Telegram.
      setState(() => _note = e.message);
      if (e.message.contains('отправлю в чат')) await _send();
    } on TimeoutException {
      if (mounted) setState(() => _note = 'Не скачалось — нажми ещё раз');
    }
  }

  /// «Просмотр»: файл открывается в Safari (или браузере) — листать там.
  Future<void> _view() async {
    tick();
    try {
      final r = await widget.api.post('/files/${widget.f.id}/link');
      await launchUrl(Uri.parse('${r['url']}&view=1'), mode: LaunchMode.externalApplication);
    } on ApiError catch (e) {
      setState(() => _note = e.message);
    }
  }

  Future<void> _send() async {
    tick();
    try {
      await widget.api.post('/files/${widget.f.id}/send');
      setState(() => _note = 'Отправил в Telegram — файл в чате с ботом.');
    } on ApiError catch (e) {
      setState(() => _note = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.85),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(widget.f.subject, style: s.eyebrow()),
              const SizedBox(height: 4),
              Text(widget.f.title, style: s.name(21)),
              const SizedBox(height: Space.l),
              Row(
                children: [
                  Expanded(
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                        backgroundColor: p.accent,
                        foregroundColor: p.onAccent,
                        shape: const StadiumBorder(),
                      ),
                      onPressed: _download,
                      icon: const Icon(Icons.download_rounded, size: 18),
                      label: const Text('Скачать'),
                    ),
                  ),
                  const SizedBox(width: Space.s),
                  Expanded(
                    child: OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: p.text,
                        side: BorderSide(color: p.line),
                        shape: const StadiumBorder(),
                      ),
                      onPressed: _view,
                      icon: const Icon(Icons.visibility_outlined, size: 18),
                      label: const Text('Просмотр'),
                    ),
                  ),
                ],
              ),
              TextButton.icon(
                style: TextButton.styleFrom(foregroundColor: p.muted),
                onPressed: _send,
                icon: const Icon(Icons.send_rounded, size: 16),
                label: const Text('Прислать в Telegram'),
              ),
              if (!widget.f.canEdit)
                TextButton.icon(
                  key: const Key('file:report'),
                  style: TextButton.styleFrom(foregroundColor: p.muted),
                  onPressed: () => openReportMenu(context, widget.api, kind: 'file', id: widget.f.id),
                  icon: const Icon(Icons.flag_outlined, size: 16),
                  label: const Text('Пожаловаться или скрыть'),
                ),
              if (_note != null) ...[const SizedBox(height: Space.m), Text(_note!, style: s.body(14, color: p.muted))],
              if (widget.f.hasText) ...[
                const SizedBox(height: Space.xl),
                Text('Конспект', style: s.title(20)),
                const SizedBox(height: Space.s),
                if (_summary != null)
                  Text.rich(tgHtml(_summary!, s.body(15), link: p.accent, codeBg: p.line))
                else if (_busy)
                  Padding(
                    padding: const EdgeInsets.all(Space.l),
                    child: Center(child: CircularProgressIndicator(color: p.accent, strokeWidth: 2.5)),
                  )
                else
                  TextButton.icon(
                    onPressed: () => _loadSummary(make: true),
                    icon: Icon(Icons.auto_awesome_outlined, color: p.accent),
                    label: Text(
                      'Сделать конспект',
                      style: s.body(15, weight: FontWeight.w600, color: p.accent),
                    ),
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

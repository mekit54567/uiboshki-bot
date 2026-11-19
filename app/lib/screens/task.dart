// Экран задания СДО (как в WebApp, js/sdo.js → renderTask): срок, сколько
// осталось, статус и оценка, описание, файлы преподавателя и мой ответ,
// «Сдать работу»; ответ уже есть и не оценён — «Редактировать ответ» и
// «Удалить ответ», как в СДО. У теста — попытки и лучший результат; пройти — на сайте.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/capy_refresh.dart';
import '../widgets/cheer.dart';
import '../widgets/common.dart';
import '../widgets/goal_card.dart';
import 'deadline_edit.dart';
import 'files.dart';
import 'sdo_connect.dart';
import 'submit.dart';

part 'task_fresh.dart';

/// Открыть ссылку — системным браузером; в тестах подменяется.
typedef OpenLink = Future<void> Function(Uri uri);

Future<void> openExternal(Uri uri) async {
  await launchUrl(uri, mode: LaunchMode.externalApplication);
}

/// Ссылка на файл из СДО (/sdl/…): сервер отдаёт полный адрес, а если путь — к нему адрес сервера.
Uri sdoLink(String dl) => Uri.parse(dl.startsWith('http') ? dl : '${Api.base}$dl');

/// Статус ответа — по-человечески, а не сырым текстом Moodle.
String humanStatus(String s) {
  const rules = [
    (r'не представлен|нет ответа|no attempt', 'Ещё не сдано'),
    (r'черновик|draft', 'Черновик — не отправлен'),
    (r'отправлено для оценивания|submitted for grading', 'Сдано, ждёт оценки'),
    (r'вне сайта', 'Сдаётся на занятии'),
  ];
  for (final (re, text) in rules) {
    if (RegExp(re, caseSensitive: false).hasMatch(s)) return text;
  }
  return s;
}

/// Подпись статуса работы из журнала (поле status у works).
const _tags = {
  'ok': (Icons.check_circle_rounded, 'зачтено'),
  'low': (Icons.error_outline_rounded, 'ниже порога'),
  'wait': (Icons.hourglass_top_rounded, 'ждёт оценки'),
  'offline': (Icons.groups_outlined, 'сдаётся на занятии'),
  'soon': (Icons.lock_outline_rounded, 'ещё закрыто'),
  'miss': (Icons.cancel_outlined, 'срок прошёл'),
  'late': (Icons.hourglass_top_rounded, 'ждём оценку'),
};

class TaskScreen extends StatefulWidget {
  final Api api;

  /// Работа из журнала предмета: name, module, cmid, status, grade, max, pass_mark, url.
  final Map<String, dynamic> work;
  final String course;
  final OpenLink open;
  final PickFiles pick;

  /// Срок из «Сдать» (новый вид): дата, отметки и действия со сроком на странице.
  final Deadline? deadline;
  final DlExtra? extra;
  final DeadlineAct? onDeadline;

  /// «Сейчас» для тестов; без него — часы.
  final DateTime? at;
  const TaskScreen({
    super.key,
    required this.api,
    required this.work,
    this.course = '',
    this.open = openExternal,
    this.pick = systemPick,
    this.deadline,
    this.extra,
    this.onDeadline,
    this.at,
  });

  @override
  State<TaskScreen> createState() => _TaskScreenState();
}

class _TaskScreenState extends State<TaskScreen> {
  Map<String, dynamic>? _t;
  String? _error;
  DateTime? _loadedAt;

  Map<String, dynamic> get w => widget.work;
  bool get _quiz => w['module'] == 'quiz';

  // новый вид: срок со страницы «Сдать», сдача и комментарии прямо здесь
  Deadline? _d;
  DlExtra? _x;
  SubmitRules? _rules;
  String? _rulesError, _sendError;
  final _files = <({Picked f, String? why})>[];
  bool _sending = false, _posting = false, _replace = false;
  final _noteCtl = TextEditingController();
  final _commentCtl = TextEditingController();

  void _setState(VoidCallback f) {
    if (mounted) setState(f);
  }

  /// Что уйдёт в СДО — только подходящие файлы.
  List<Picked> get _good => [
    for (final e in _files)
      if (e.why == null) e.f,
  ];

  @override
  void initState() {
    super.initState();
    _d = widget.deadline;
    _x = widget.extra;
    if (w['cmid'] is int) _load();
  }

  @override
  void dispose() {
    _noteCtl.dispose();
    _commentCtl.dispose();
    super.dispose();
  }

  void _retry() {
    _setState(() => _error = null);
    _load();
  }

  Future<void> _load() async {
    if (w['cmid'] is! int) return;
    try {
      final r = await widget.api.get('/sdo/task/${w['cmid']}${_quiz ? '?module=quiz' : ''}');
      if (!mounted) return;
      setState(() {
        _t = Map<String, dynamic>.from(r);
        _error = null;
        _loadedAt = DateTime.now();
      });
      if (_t?['can_submit'] == true && _rules == null && mounted && AppStyle.of(context).fresh) {
        await _loadRules();
      }
    } on ApiError catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    }
  }

  /// Что принимает задание — до выбора файлов (как в листе «Сдать файлом»).
  Future<void> _loadRules() async {
    try {
      final r = await widget.api.get('/sdo/submit-rules?cmid=${w['cmid']}&deadline_id=${_d?.id ?? 0}');
      _setState(() {
        _rules = SubmitRules.fromJson(Map<String, dynamic>.from(r));
        _rulesError = null;
      });
    } on ApiError catch (e) {
      _setState(() => _rulesError = e.message);
    } catch (e) {
      _setState(() => _rulesError = errorText(e));
    }
  }

  /// Прикрепить: плохой файл остаётся в списке с причиной, хорошие — до лимита задания.
  Future<void> _pick() async {
    final rules = _rules;
    if (rules == null) return;
    final got = await widget.pick(rules.accepted);
    if (!mounted) return;
    setState(() {
      for (final f in got) {
        final why = rules.problem(f);
        if (why == null ? _good.length < rules.perSubmit : _files.length < rules.perSubmit + 3) {
          _files.add((f: f, why: why));
        }
      }
      _sendError = null;
    });
  }

  /// «Отправить»: файлы в СДО своим входом, комментарий — следом.
  Future<void> _send() async {
    setState(() {
      _sending = true;
      _sendError = null;
    });
    final note = _noteCtl.text.trim();
    try {
      final r = await widget.api.post('/sdo/submit', {
        'deadline_id': _d?.id ?? 0,
        'cmid': w['cmid'],
        if (_replace) 'replace': true,
        if (note.isNotEmpty) 'comment': note,
        'files': [
          for (final f in _good) {'name': f.name, 'data': base64Encode(f.bytes)},
        ],
      });
      HapticFeedback.mediumImpact();
      if (!mounted) return;
      final m = r is Map ? r : const {};
      final state = m['state'] is String ? m['state'] as String : 'submitted';
      final url = m['url'] is String && (m['url'] as String).startsWith('https://') ? m['url'] as String : '';
      setState(() {
        _files.clear();
        _replace = false;
        if (m['comment'] != 'failed') _noteCtl.clear();
      });
      if (state == 'submitted') cheer(context);
      await showSubmitDone(
        context,
        status: m['status'] is String ? m['status'] as String : 'Отправлено в СДО',
        state: state,
        url: url,
      );
      if (!mounted) return;
      if (m['comment'] == 'failed') {
        showToast(context, 'Файл ушёл, а комментарий нет. Он ждёт в поле ниже, отправь ещё раз', kind: ToastKind.info);
        _commentCtl.text = note;
        _noteCtl.clear();
      }
      if (_d != null && _x != null) {
        // сдано в СДО — сервер сам отметил срок сданным; берём свежий срок
        final res = await widget.onDeadline?.call(null, _d!, _x!);
        if (res != null) {
          _setState(() {
            _d = res.d;
            _x = res.x;
          });
        }
      }
      await _load();
    } on ApiError catch (e) {
      _setState(() => _sendError = e.message);
    } catch (e) {
      // связь могла оборваться уже после сдачи — не пишем «не ушёл» наугад
      _setState(
        () => _sendError = isOffline(e)
            ? 'Связь оборвалась, и неизвестно, дошёл ли файл. Обнови страницу, прежде чем сдавать снова.'
            : errorText(e),
      );
    } finally {
      _setState(() => _sending = false);
    }
  }

  /// Комментарий к ответу — сразу в СДО.
  Future<void> _postComment() async {
    final text = _commentCtl.text.trim();
    if (text.isEmpty) return;
    tick();
    setState(() => _posting = true);
    try {
      final r = await widget.api.post('/sdo/task/${w['cmid']}/comment', {'text': text});
      _commentCtl.clear();
      if (r is Map && r['items'] is List) _setState(() => _t = {...?_t, 'comments': r});
    } on ApiError catch (e) {
      if (mounted) showToast(context, e.message, kind: ToastKind.error);
    } catch (e) {
      if (mounted) showToast(context, errorText(e), kind: ToastKind.error);
    } finally {
      _setState(() => _posting = false);
    }
  }

  /// Действие со сроком: делает экран «Сдать», страница берёт новые данные срока.
  Future<void> _deadlineAct(DlAction a) async {
    final d = _d, x = _x, act = widget.onDeadline;
    if (d == null || x == null || act == null) return;
    final res = await act(a, d, x);
    if (!mounted) return;
    if (res == null) {
      Navigator.of(context).maybePop(); // срок убран — страница ему больше не нужна
      return;
    }
    setState(() {
      _d = res.d;
      _x = res.x;
    });
  }

  /// Ссылки на файлы живут 10 минут — экран открыт дольше, берём свежие.
  Future<void> _download(bool mine, int i) async {
    tick();
    if (_loadedAt != null && DateTime.now().difference(_loadedAt!) > const Duration(minutes: 9)) await _load();
    final t = _t;
    if (t == null) return;
    final list = (mine ? t['mine'] : t['files']) as List? ?? [];
    if (i >= list.length) return;
    await widget.open(sdoLink('${list[i]['dl']}'));
  }

  Future<void> _submit({bool replace = false}) async {
    tick();
    final t = _t!;
    final ok = await showSubmitSheet(
      context,
      widget.api,
      title: '${t['title'] ?? w['name']}',
      cmid: w['cmid'] as int,
      pick: widget.pick,
      replace: replace,
    );
    if (ok == true) await _load(); // мой ответ и статус — заново
  }

  /// «Удалить ответ» — как в СДО: после «точно?» файлы ответа убираются.
  Future<void> _remove() async {
    final ok = await confirmSheet(
      context,
      title: 'Удалить ответ?',
      text: 'Файлы ответа уберутся из СДО. Сдать заново можно, пока не прошёл срок.',
      action: 'Удалить ответ',
      danger: true,
    );
    if (!ok || !mounted) return;
    final toast = Overlay.of(context, rootOverlay: true);
    try {
      await widget.api.post('/sdo/submission/remove', {'cmid': w['cmid']});
      toastOn(toast, 'Ответ удалён', kind: ToastKind.done);
    } on ApiError catch (e) {
      toastOn(toast, e.message, kind: ToastKind.error);
      return;
    } catch (e) {
      toastOn(toast, errorText(e), kind: ToastKind.error);
      return;
    }
    if (mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    final t = _t;
    if (AppStyle.of(context).fresh) {
      return Scaffold(
        body: Backdrop(
          child: SafeArea(
            child: CapyRefresh(onRefresh: _load, child: _fresh(context)),
          ),
        ),
      );
    }
    return Scaffold(
      body: Backdrop(
        tint: widget.course.isEmpty ? null : subjectColor(widget.course),
        child: SafeArea(
          child: CapyRefresh(
            onRefresh: _load,
            child: ListView(
              padding: const EdgeInsets.only(bottom: Space.xxl),
              children: [
                const BackRow(),
                ScreenTitle(
                  sub: [if (widget.course.isNotEmpty) widget.course, if (_quiz) 'тест'].join(' · '),
                  title: '${t?['title'] ?? w['name']}',
                ),
                if (t != null)
                  ..._body(context, t)
                else if (_error != null)
                  Notice(
                    title: 'Задание не открылось',
                    text: _error!,
                    onRetry: () {
                      setState(() => _error = null);
                      _load();
                    },
                  )
                else
                  Padding(padding: const EdgeInsets.all(Space.xxl), child: const CapyLoading()),
                // вход устарел или не подключён — сразу к подключению, потом задание заново
                if (t == null && _error != null && needsSdo(_error!))
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
                    child: FilledButton(
                      style: FilledButton.styleFrom(
                        backgroundColor: p.accent,
                        foregroundColor: p.onAccent,
                        shape: const StadiumBorder(),
                      ),
                      onPressed: () async {
                        tick();
                        await Navigator.of(context)
                            .push(MaterialPageRoute(builder: (_) => SdoConnectScreen(api: widget.api)));
                        if (mounted) setState(() => _error = null);
                        await _load();
                      },
                      child: const Text('Подключить СДО'),
                    ),
                  ),
                if (t == null && _error != null && w['url'] is String) _openSdo(context, '${w['url']}'),
              ],
            ),
          ),
        ),
      ),
    );
  }

  List<Widget> _body(BuildContext context, Map<String, dynamic> t) {
    final s = AppStyle.of(context);
    final p = s.p;
    const pad = EdgeInsets.symmetric(horizontal: Space.l);
    final status = '${w['status'] ?? ''}';
    final files = (t['files'] as List?) ?? [];
    final mine = (t['mine'] as List?) ?? [];
    final remaining = '${t['remaining'] ?? ''}'.replaceFirst(RegExp(r' осталось$'), '');
    final tag = status == 'todo' && remaining.isNotEmpty ? (Icons.schedule_rounded, remaining) : _tags[status];
    final tagColor = switch (status) {
      'ok' => p.ok,
      'low' || 'miss' => p.danger,
      'todo' => p.warn,
      _ => p.muted,
    };
    final graded = status == 'ok' || status == 'low';
    final limit = (t['limit'] as num?)?.toInt() ?? 1;
    final max = w['max'];
    return [
      Padding(
        padding: pad,
        child: Tile(
          radius: Radii.card,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (t['due'] != null) ...[
                Text('Срок сдачи', style: s.eyebrow()),
                const SizedBox(height: 2),
                Text('${t['due']}', style: s.title(20)),
                const SizedBox(height: Space.m),
              ],
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  if (tag != null) _Chip(icon: tag.$1, text: tag.$2, color: tagColor),
                  if (graded)
                    const _Chip(text: 'Оценено')
                  else if ('${t['status'] ?? ''}'.isNotEmpty)
                    _Chip(text: humanStatus('${t['status']}')),
                  _Chip(text: w['grade'] != null ? 'Оценка ${fmtNum(w['grade'])} / ${fmtNum(max ?? 0)}' : 'Не оценено'),
                ],
              ),
              if (max != null) ...[
                const SizedBox(height: Space.m),
                Text(
                  'до ${fmtNum(max)} ${plural((max as num).round(), 'балла', 'баллов', 'баллов')}'
                  '${w['pass_mark'] != null ? ' · зачёт от ${fmtNum(w['pass_mark'])}' : ''}',
                  style: s.body(13, color: p.muted),
                ),
              ],
              if (t['graded_by'] != null) ...[
                const SizedBox(height: 4),
                Text(
                  'Оценил(а): ${t['graded_by']}${t['graded_at'] != null ? ' · ${t['graded_at']}' : ''}',
                  style: s.body(13, color: p.muted),
                ),
              ],
            ],
          ),
        ),
      ),
      if ('${t['description'] ?? ''}'.isNotEmpty) ...[
        const Section('Задание'),
        Padding(
          padding: pad,
          child: Tile(child: SelectableText('${t['description']}', style: s.body(15))),
        ),
      ],
      if ('${t['feedback'] ?? ''}'.isNotEmpty) ...[
        const Section('Комментарий преподавателя'),
        Padding(
          padding: pad,
          child: Tile(child: SelectableText('${t['feedback']}', style: s.body(15))),
        ),
      ],
      if (t['quiz'] == true) ...[
        const Section('Тест'),
        Padding(
          padding: pad,
          child: _QuizCard(t: t, status: status),
        ),
      ],
      if (files.isNotEmpty) ...[
        const Section('Файлы задания'),
        Padding(
          padding: pad,
          child: _FileList(names: [for (final f in files) '${f['name']}'], onTap: (i) => _download(false, i)),
        ),
      ],
      if (mine.isNotEmpty) ...[
        const Section('Мой ответ'),
        Padding(
          padding: pad,
          child: _FileList(names: [for (final f in mine) '${f['name']}'], onTap: (i) => _download(true, i)),
        ),
      ],
      const SizedBox(height: Space.xl),
      if (t['can_edit'] == true || t['can_remove'] == true) ...[
        if (t['can_edit'] == true)
          Padding(
            padding: pad,
            child: SizedBox(
              height: 50,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                  backgroundColor: p.accent,
                  foregroundColor: p.onAccent,
                  shape: const StadiumBorder(),
                ),
                onPressed: () => _submit(replace: true),
                icon: const Icon(Icons.edit_outlined),
                label: const Text('Редактировать ответ'),
              ),
            ),
          ),
        if (t['can_remove'] == true)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, 0),
            child: SizedBox(
              height: 50,
              child: OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: p.danger,
                  side: BorderSide(color: p.danger.withValues(alpha: 0.5)),
                  shape: const StadiumBorder(),
                ),
                onPressed: _remove,
                icon: const Icon(Icons.delete_outline_rounded),
                label: const Text('Удалить ответ'),
              ),
            ),
          ),
      ] else if (t['can_submit'] == true)
        Padding(
          padding: pad,
          child: SizedBox(
            height: 50,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: p.accent,
                foregroundColor: p.onAccent,
                shape: const StadiumBorder(),
              ),
              onPressed: _submit,
              icon: const Icon(Icons.upload_rounded),
              label: Text(
                '${mine.isNotEmpty ? 'Сдать ещё / заменить' : 'Сдать работу'}'
                '${limit > 1 ? ' · до $limit ${plural(limit, 'файла', 'файлов', 'файлов')}' : ''}',
              ),
            ),
          ),
        )
      else if (status == 'offline')
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.xl),
          child: Text(
            'Эту работу сдают на занятии, не через СДО.',
            textAlign: TextAlign.center,
            style: s.body(14, color: p.muted),
          ),
        ),
      if (t['quiz'] == true && t['open_now'] == true)
        Padding(
          padding: pad,
          child: SizedBox(
            height: 50,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: p.accent,
                foregroundColor: p.onAccent,
                shape: const StadiumBorder(),
              ),
              onPressed: () => widget.open(Uri.parse('${t['url']}')),
              icon: const Icon(Icons.open_in_new_rounded),
              label: const Text('Пройти тест в СДО'),
            ),
          ),
        )
      else if (t['url'] is String)
        _openSdo(context, t['url'] as String),
    ];
  }

  Widget _openSdo(BuildContext context, String url) {
    final s = AppStyle.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, 0),
      child: TextButton.icon(
        onPressed: () {
          tick();
          widget.open(Uri.parse(url));
        },
        icon: Icon(Icons.open_in_new_rounded, size: 18, color: s.p.accent),
        label: Text(
          'Открыть в СДО',
          style: s.body(15, weight: FontWeight.w600, color: s.p.accent),
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final IconData? icon;
  final String text;
  final Color? color;
  const _Chip({this.icon, required this.text, this.color});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final c = color ?? s.p.muted;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(Radii.pill)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: 14, color: c), const SizedBox(width: 4)],
          Text(
            text,
            style: s.body(13, weight: FontWeight.w600, color: color ?? s.p.text),
          ),
        ],
      ),
    );
  }
}

IconData _fileIcon(String name) {
  final ext = name.contains('.') ? name.split('.').last.toLowerCase() : '';
  return switch (ext) {
    'pdf' => Icons.picture_as_pdf_outlined,
    'doc' || 'docx' || 'odt' || 'rtf' || 'txt' => Icons.description_outlined,
    'xls' || 'xlsx' || 'csv' => Icons.table_chart_outlined,
    'ppt' || 'pptx' => Icons.slideshow_outlined,
    'zip' || 'rar' || '7z' => Icons.folder_zip_outlined,
    'png' || 'jpg' || 'jpeg' => Icons.image_outlined,
    _ => Icons.insert_drive_file_outlined,
  };
}

/// Файлы карточкой: иконка по типу, имя, «скачать».
class _FileList extends StatelessWidget {
  final List<String> names;
  final ValueChanged<int> onTap;
  const _FileList({required this.names, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Tile(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          for (var i = 0; i < names.length; i++) ...[
            if (i > 0) Divider(height: 1, color: p.line),
            InkWell(
              onTap: () => onTap(i),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                child: Row(
                  children: [
                    Icon(_fileIcon(names[i]), size: 20, color: p.accent),
                    const SizedBox(width: Space.m),
                    Expanded(
                      child: Text(names[i], style: s.body(14, weight: FontWeight.w600)),
                    ),
                    Icon(Icons.download_rounded, size: 20, color: p.muted, semanticLabel: 'Скачать'),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Тест: открыт ли, попытки, лучший результат, проходная, время на попытку.
class _QuizCard extends StatelessWidget {
  final Map<String, dynamic> t;
  final String status;
  const _QuizCard({required this.t, required this.status});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final attempts = (t['attempts'] as List?) ?? [];
    final allowed = t['attempts_allowed'];
    final state = t['open_now'] == true
        ? 'Тест открыт — можно проходить'
        : t['no_more'] == true
        ? 'Попыток больше нет'
        : t['unavailable'] == true || status == 'soon'
        ? 'Ещё не открыт${t['opens'] != null ? ' · откроется ${t['opens']}' : ''}'
        : 'Сейчас пройти нельзя';
    final limit = (t['time_limit'] as num?)?.toInt();
    Widget line(IconData icon, String text, {bool bold = false}) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: p.muted),
          const SizedBox(width: Space.s),
          Expanded(
            child: Text(text, style: s.body(14, weight: bold ? FontWeight.w600 : FontWeight.w400)),
          ),
        ],
      ),
    );
    return Tile(
      child: Column(
        children: [
          line(t['open_now'] == true ? Icons.lock_open_rounded : Icons.lock_outline_rounded, state, bold: true),
          line(
            Icons.replay_rounded,
            'Попытки: ${allowed != null ? 'использовано ${attempts.length} из $allowed' : '${attempts.length} · без ограничения'}',
          ),
          if ('${t['best'] ?? ''}'.isNotEmpty)
            line(Icons.emoji_events_outlined, 'Лучший результат: ${'${t['best']}'.replaceFirst('/', ' из ')}'),
          if ('${t['pass_text'] ?? ''}'.isNotEmpty) line(Icons.flag_outlined, 'Проходная: ${t['pass_text']}'),
          if (limit != null && limit > 0)
            line(Icons.timer_outlined, 'На попытку: ${limit % 60 != 0 ? '$limit мин' : '${limit ~/ 60} ч'}'),
          for (var i = 0; i < attempts.length; i++)
            line(
              Icons.check_rounded,
              'Попытка ${i + 1}: ${'${attempts[i]['grade'] ?? ''}'.isNotEmpty ? attempts[i]['grade'] : attempts[i]['state'] ?? ''}'
              '${'${attempts[i]['finished'] ?? ''}'.isNotEmpty ? ' · ${attempts[i]['finished']}' : ''}',
            ),
        ],
      ),
    );
  }
}

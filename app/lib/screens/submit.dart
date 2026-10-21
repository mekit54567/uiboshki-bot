// «Сдать файлом»: сначала — что принимает задание (типы, сколько файлов,
// размер) прямо из СДО, потом выбор файлов и отправка своим входом в СДО.
// Сдал — капибара радуется, срок у себя отмечается сданным (сервер, sdo_done).
import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/common.dart';

typedef Picked = ({String name, Uint8List bytes});

/// Выбор файлов — системным окном; в тестах подменяется.
typedef PickFiles = Future<List<Picked>> Function(List<String> accepted);

Future<List<Picked>> systemPick(List<String> accepted) async {
  final exts = [for (final e in accepted) e.replaceFirst('.', '')];
  final files = await FilePicker.pickFiles(
    type: exts.isEmpty ? FileType.any : FileType.custom,
    allowedExtensions: exts.isEmpty ? null : exts,
  );
  return [for (final f in files) (name: f.name, bytes: await f.xFile.readAsBytes())];
}

class SubmitRules {
  final List<String> accepted, labels;
  final int maxFiles, maxBytes;
  final String? closed;

  SubmitRules.fromJson(Map<String, dynamic> j)
    : accepted = [for (final a in (j['accepted'] as List? ?? [])) '$a'.toLowerCase()],
      labels = [for (final a in (j['labels'] as List? ?? [])) '$a'],
      maxFiles = (j['maxfiles'] as num?)?.toInt() ?? 3,
      maxBytes = (j['maxbytes'] as num?)?.toInt() ?? 0,
      closed = j['closed'] as String?;

  /// Сколько файлов за раз: не больше трёх (как в WebApp) и не больше, чем даёт задание.
  int get perSubmit => maxFiles <= 0 ? 3 : (maxFiles < 3 ? maxFiles : 3);

  bool fits(String name) => accepted.isEmpty || accepted.any((e) => name.toLowerCase().endsWith(e));

  /// Предел размера: «20 МБ».
  String get limit => '${(maxBytes / 1048576).toStringAsFixed(maxBytes >= 10485760 ? 0 : 1)} МБ';

  String describe() {
    final parts = <String>[
      if (labels.isNotEmpty) labels.join(', ') else if (accepted.isNotEmpty) accepted.join(' ') else 'любые файлы',
      'до $perSubmit ${plural(perSubmit, 'файла', 'файлов', 'файлов')}',
      if (maxBytes > 0) 'до $limit',
    ];
    return parts.join(' · ');
  }

  /// Почему задание не примет файл; null — подходит (проверка файла, Никита 12.10).
  String? problem(Picked f) {
    if (!fits(f.name)) {
      final dot = f.name.lastIndexOf('.');
      final what = dot > 0 ? f.name.substring(dot).toLowerCase() : 'Файл без расширения';
      return '$what задание не примет — нужно ${labels.isNotEmpty ? labels.join(', ') : accepted.join(', ')}';
    }
    if (maxBytes > 0 && f.bytes.length > maxBytes) return 'больше $limit — задание не примет';
    return null;
  }
}

/// Размер по-человечески: «820 КБ», «1,2 МБ».
String fileSize(int bytes) {
  if (bytes < 1048576) return '${(bytes / 1024).ceil()} КБ';
  final mb = bytes / 1048576;
  return '${mb.toStringAsFixed(mb >= 10 ? 0 : 1).replaceAll('.', ',')} МБ';
}

/// Открыть лист сдачи. Задание — по сроку (deadlineId) или из работ предмета (cmid).
/// replace — «Редактировать ответ»: новые файлы заменят прежние (как в СДО).
Future<bool?> showSubmitSheet(
  BuildContext context,
  Api api, {
  required String title,
  int deadlineId = 0,
  int cmid = 0,
  PickFiles pick = systemPick,
  bool replace = false,
}) {
  final s = AppStyle.of(context);
  return showModalBottomSheet<bool>(
    context: context,
    backgroundColor: s.p.cardSolid,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (_) =>
        SubmitSheet(api: api, title: title, deadlineId: deadlineId, cmid: cmid, pick: pick, replace: replace),
  );
}

class SubmitSheet extends StatefulWidget {
  final Api api;
  final String title;
  final int deadlineId, cmid;
  final PickFiles pick;
  final bool replace;
  const SubmitSheet({
    super.key,
    required this.api,
    required this.title,
    this.deadlineId = 0,
    this.cmid = 0,
    this.pick = systemPick,
    this.replace = false,
  });

  @override
  State<SubmitSheet> createState() => _SubmitSheetState();
}

class _SubmitSheetState extends State<SubmitSheet> {
  SubmitRules? _rules;
  String? _error, _done;
  // submitted / draft / unknown (сервер, sdo_done.submit_state); старый сервер без state — как раньше
  String _state = 'submitted';
  // why — почему задание не примет (только в новом дизайне: плохой файл
  // остаётся в списке с причиной, а не отбрасывается молча).
  final _files = <({Picked f, String? why})>[];
  bool _sending = false;

  /// Что уйдёт в СДО — только подходящие.
  List<Picked> get _good => [
    for (final e in _files)
      if (e.why == null) e.f,
  ];

  @override
  void initState() {
    super.initState();
    _loadRules();
  }

  Future<void> _loadRules() async {
    try {
      final r = await widget.api.get('/sdo/submit-rules?cmid=${widget.cmid}&deadline_id=${widget.deadlineId}');
      setState(() => _rules = SubmitRules.fromJson(Map<String, dynamic>.from(r)));
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = errorText(e));
    }
  }

  Future<void> _pick() async {
    tick();
    final rules = _rules!;
    final got = await widget.pick(rules.accepted);
    if (!mounted) return;
    if (AppStyle.of(context).design2) {
      // Лимит — по подходящим; плохих в списке не больше трёх сверх него.
      setState(() {
        for (final f in got) {
          final why = rules.problem(f);
          if (why == null ? _good.length < rules.perSubmit : _files.length < rules.perSubmit + 3) {
            _files.add((f: f, why: why));
          }
        }
        _error = null;
      });
      return;
    }
    final bad = got.where((f) => !rules.fits(f.name)).map((f) => f.name).toList();
    final big = rules.maxBytes > 0 ? got.where((f) => f.bytes.length > rules.maxBytes).map((f) => f.name).toList() : [];
    setState(() {
      for (final f in got) {
        if (!bad.contains(f.name) && !big.contains(f.name) && _files.length < rules.perSubmit) {
          _files.add((f: f, why: null));
        }
      }
      _error = bad.isNotEmpty
          ? 'Задание не примет: ${bad.join(', ')} — нужно ${rules.labels.isNotEmpty ? rules.labels.join(', ') : rules.accepted.join(' ')}'
          : big.isNotEmpty
          ? 'Слишком большой: ${big.join(', ')}'
          : null;
    });
  }

  Future<void> _send() async {
    tick();
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final r = await widget.api.post('/sdo/submit', {
        'deadline_id': widget.deadlineId,
        'cmid': widget.cmid,
        if (widget.replace) 'replace': true,
        'files': [
          for (final f in _good) {'name': f.name, 'data': base64Encode(f.bytes)},
        ],
      });
      HapticFeedback.mediumImpact();
      if (!mounted) return;
      setState(() {
        _done = (r is Map && r['status'] is String) ? r['status'] as String : 'Отправлено в СДО';
        _state = (r is Map && r['state'] is String) ? r['state'] as String : 'submitted';
      });
    } on ApiError catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      // связь могла оборваться уже после сдачи — не пишем «не ушёл» наугад
      if (mounted) {
        setState(() => _error = isOffline(e)
            ? 'Связь оборвалась — не знаем, дошёл ли файл. Проверь задание в СДО, прежде чем сдавать снова.'
            : errorText(e));
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final rules = _rules;
    final d2 = s.design2;
    final good = _good.length;
    final verb = widget.replace ? 'Заменить' : 'Сдать';
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.xl + MediaQuery.viewInsetsOf(context).bottom),
        child: AnimatedSize(
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOutCubic,
          child: _done != null
              ? _Done(status: _done!, state: _state, onClose: () => Navigator.pop(context, true))
              : Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(widget.replace ? 'Редактировать ответ' : 'Сдать файлом', style: s.eyebrow()),
                    const SizedBox(height: 4),
                    Text(widget.title, style: s.name(20)),
                    const SizedBox(height: Space.l),
                    if (rules == null && _error == null)
                      Center(child: CircularProgressIndicator(color: p.accent, strokeWidth: 2.5))
                    else if (rules?.closed != null)
                      Text(rules!.closed!, style: s.body(15, color: p.danger))
                    else if (rules != null) ...[
                      Row(
                        children: [
                          Icon(Icons.rule_rounded, size: 18, color: p.muted),
                          const SizedBox(width: Space.s),
                          Expanded(
                            child: Text('Принимает: ${rules.describe()}', style: s.body(14, color: p.muted)),
                          ),
                        ],
                      ),
                      if (widget.replace) ...[
                        const SizedBox(height: Space.s),
                        Row(
                          children: [
                            Icon(Icons.swap_horiz_rounded, size: 18, color: p.muted),
                            const SizedBox(width: Space.s),
                            Expanded(
                              child: Text('Новые файлы заменят прежние', style: s.body(14, color: p.muted)),
                            ),
                          ],
                        ),
                      ],
                      const SizedBox(height: Space.m),
                      for (final e in _files)
                        Padding(
                          padding: const EdgeInsets.only(bottom: Space.s),
                          child: d2 ? _checkedFile(s, e.f, e.why) : _plainFile(s, e.f),
                        ),
                      if (d2
                          ? good < rules.perSubmit && _files.length < rules.perSubmit + 3
                          : _files.length < rules.perSubmit)
                        OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(
                            foregroundColor: p.text,
                            side: BorderSide(color: p.line),
                            shape: const StadiumBorder(),
                          ),
                          onPressed: _sending ? null : _pick,
                          icon: const Icon(Icons.attach_file_rounded, size: 18),
                          label: Text(_files.isEmpty ? 'Выбрать файл' : 'Ещё файл'),
                        ),
                    ],
                    if (_error != null) ...[
                      const SizedBox(height: Space.m),
                      Text(_error!, style: s.body(14, color: p.danger)),
                    ],
                    const SizedBox(height: Space.l),
                    SizedBox(
                      width: double.infinity,
                      height: 50,
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(
                          backgroundColor: p.accent,
                          foregroundColor: p.onAccent,
                          shape: const StadiumBorder(),
                        ),
                        onPressed: good == 0 || _sending ? null : _send,
                        icon: _sending
                            ? SizedBox.square(
                                dimension: 18,
                                child: CircularProgressIndicator(strokeWidth: 2, color: p.onAccent),
                              )
                            : const Icon(Icons.upload_rounded),
                        label: Text(
                          _sending
                              ? 'Отправляю…'
                              : d2 && good > 0
                              ? '$verb $good ${plural(good, 'файл', 'файла', 'файлов')}'
                              : verb,
                        ),
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }

  /// Файл, как было: имя, размер, «Убрать».
  Widget _plainFile(AppStyle s, Picked f) {
    final p = s.p;
    return Tile(
      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.s),
      child: Row(
        children: [
          Icon(Icons.insert_drive_file_outlined, size: 18, color: p.accent),
          const SizedBox(width: Space.s),
          Expanded(
            child: Text(f.name, style: s.body(14, weight: FontWeight.w600)),
          ),
          Text('${(f.bytes.length / 1024).ceil()} КБ', style: s.body(12, color: p.muted)),
          _remove(p, f),
        ],
      ),
    );
  }

  /// Проверка файла (новый дизайн, Никита 12.10): подходит — зелёная галочка,
  /// нет — красный «!» и причина под именем.
  Widget _checkedFile(AppStyle s, Picked f, String? why) {
    final p = s.p;
    return Tile(
      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.s),
      child: Row(
        children: [
          Icon(Icons.insert_drive_file_outlined, size: 18, color: why == null ? p.accent : p.danger),
          const SizedBox(width: Space.s),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(f.name, style: s.body(14, weight: FontWeight.w600)),
                if (why != null) ...[const SizedBox(height: 2), Text(why, style: s.body(12, color: p.danger))],
              ],
            ),
          ),
          const SizedBox(width: Space.s),
          Text(fileSize(f.bytes.length), style: s.body(12, color: p.muted)),
          const SizedBox(width: Space.s),
          Semantics(
            label: why == null ? 'Подходит' : 'Не подходит',
            child: why == null
                ? Icon(Icons.check_rounded, size: 18, color: p.ok)
                : Icon(Icons.priority_high_rounded, size: 18, color: p.danger),
          ),
          _remove(p, f),
        ],
      ),
    );
  }

  Widget _remove(Palette p, Picked f) => IconButton(
    tooltip: 'Убрать',
    onPressed: () => setState(() => _files.removeWhere((e) => identical(e.f, f))),
    icon: Icon(Icons.close_rounded, size: 18, color: p.muted),
  );
}

/// Сдал — капибара радуется: подпрыгивает, рядом зелёная галочка. Зелёное
/// «Сдано» — только когда СДО подтвердил отправку; черновик и непонятный
/// ответ — свой заголовок и цвет (аудит 21.10, R5).
class _Done extends StatelessWidget {
  final String status, state;
  final VoidCallback onClose;
  const _Done({required this.status, this.state = 'submitted', required this.onClose});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final ok = state == 'submitted';
    final color = ok ? p.ok : (state == 'draft' ? p.warn : p.accent);
    final title = ok ? 'Сдано' : (state == 'draft' ? 'Сохранено черновиком' : 'Файл в СДО');
    final hint = ok
        ? status
        : state == 'draft'
        ? 'На проверку ещё не отправлено — открой задание в СДО и нажми «Отправить». Статус: $status'
        : 'СДО не подтвердил сдачу — загляни в задание, чтобы убедиться.${status.isEmpty ? '' : ' Статус: $status'}';
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: 1),
          duration: const Duration(milliseconds: 700),
          curve: Curves.elasticOut,
          builder: (context, v, child) => Transform.scale(scale: 0.6 + 0.4 * v, child: child),
          child: SizedBox(
            width: 112,
            height: 112,
            child: Stack(
              children: [
                CapyHop(size: 104, color: color),
                Positioned(
                  right: 0,
                  bottom: 0,
                  child: Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      color: color,
                      shape: BoxShape.circle,
                      border: Border.all(color: p.cardSolid, width: 3),
                    ),
                    child: Icon(ok ? Icons.check_rounded : Icons.priority_high_rounded,
                        color: state == 'unknown' ? p.onAccent : Colors.white, size: 22),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: Space.l),
        Text(title, textAlign: TextAlign.center, style: s.title(28)),
        const SizedBox(height: Space.s),
        Text(
          hint,
          textAlign: TextAlign.center,
          style: s.body(14, color: p.muted),
        ),
        const SizedBox(height: Space.xl),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: color,
              foregroundColor: state == 'unknown' ? p.onAccent : Colors.white,
              shape: const StadiumBorder(),
            ),
            onPressed: onClose,
            child: Text(ok ? 'Отлично' : 'Понятно'),
          ),
        ),
      ],
    );
  }
}

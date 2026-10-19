// Обсуждение пары (Никита 19.10, вариант А): под реакциями — «Обсуждение
// группы», сообщения пузырями и поле ввода тут же. Видит и пишет только своя
// группа (lesson_comments.py на сервере). Правило Apple 1.2: долгое нажатие на
// чужое — «Пожаловаться» или «Скрыть автора» (report.dart), на своё — «Удалить».
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'common.dart';
import 'report.dart';

class LessonComments extends StatefulWidget {
  final Api api;
  final Lesson lesson;
  const LessonComments({super.key, required this.api, required this.lesson});

  @override
  State<LessonComments> createState() => _LessonCommentsState();
}

class _LessonCommentsState extends State<LessonComments> {
  List<Map<String, dynamic>> _items = [];
  bool _open = false, _loaded = false, _busy = false;
  int _max = 500;
  final _ctrl = TextEditingController();

  String get _start => widget.lesson.startAt!.toUtc().toIso8601String();
  String get _q => Uri(queryParameters: {'start': _start, 'title': widget.lesson.title}).query;

  @override
  void initState() {
    super.initState();
    if (widget.lesson.startAt != null) _load();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _take(Map j) {
    _items = [for (final i in j['items'] as List? ?? const []) Map<String, dynamic>.from(i as Map)];
    if (j.containsKey('open')) _open = j['open'] == true;
    if (j['max'] is int) _max = j['max'] as int;
  }

  Future<void> _load() async {
    try {
      final j = await widget.api.get('/lesson/comments?$_q');
      if (!mounted) return;
      setState(() {
        _take(j as Map);
        _loaded = true;
      });
    } catch (_) {} // нет связи или не своя группа — экран без блока
  }

  Future<void> _send() async {
    final text = _ctrl.text.trim();
    if (text.isEmpty || _busy) return;
    tick();
    setState(() => _busy = true);
    final toast = Overlay.of(context, rootOverlay: true);
    try {
      final j = await widget.api.post('/lesson/comments', {
        'start': _start,
        'title': widget.lesson.title,
        'text': text,
      });
      if (!mounted) return;
      _ctrl.clear();
      FocusScope.of(context).unfocus();
      setState(() => _take(j as Map));
    } on ApiError catch (e) {
      toastOn(toast, e.message, kind: ToastKind.error);
    } catch (e) {
      toastOn(toast, errorText(e), kind: ToastKind.error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _hold(Map<String, dynamic> c) async {
    final id = (c['id'] as num).toInt();
    if (c['mine'] != true) {
      await openReportMenu(context, widget.api, kind: 'comment', id: id, onChanged: _load);
      return;
    }
    tick();
    final ok = await confirmSheet(context, title: 'Удалить комментарий?', action: 'Удалить', danger: true);
    if (!ok || !mounted) return;
    final toast = Overlay.of(context, rootOverlay: true);
    try {
      await widget.api.delete('/lesson/comments/$id');
      await _load();
    } catch (e) {
      toastOn(toast, errorText(e), kind: ToastKind.error);
    }
  }

  String _time(String created) {
    final t = DateTime.tryParse('${created.replaceFirst(' ', 'T')}Z')?.toLocal();
    if (t == null) return '';
    final hm = '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
    final d = now();
    final same = t.year == d.year && t.month == d.month && t.day == d.day;
    return same ? hm : '${t.day}.${t.month.toString().padLeft(2, '0')} $hm';
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded || (!_open && _items.isEmpty)) return const SizedBox.shrink();
    final s = AppStyle.of(context);
    final p = s.p;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Section(_items.isEmpty ? 'Обсуждение группы' : 'Обсуждение группы · ${_items.length}'),
        for (final c in _items)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
            child: _Bubble(
              key: Key('comment:${c['id']}'),
              author: c['mine'] == true ? 'ты' : '${c['author']}',
              time: _time('${c['created_at'] ?? ''}'),
              text: '${c['text']}',
              mine: c['mine'] == true,
              onHold: () => _hold(c),
            ),
          ),
        if (_items.isEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.s),
            child: Text('Перенесли, где аудитория, что задали — напиши группе', style: s.body(14, color: p.muted)),
          ),
        if (_open)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.xs, Space.l, 0),
            child: Container(
              padding: const EdgeInsets.only(left: Space.l, right: Space.xs),
              decoration: BoxDecoration(
                color: p.card,
                borderRadius: BorderRadius.circular(28),
                border: Border.all(color: p.line),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      key: const Key('comment:input'),
                      controller: _ctrl,
                      minLines: 1,
                      maxLines: 4,
                      maxLength: _max,
                      textCapitalization: TextCapitalization.sentences,
                      style: s.body(15),
                      decoration: InputDecoration(
                        hintText: 'Написать группе…',
                        hintStyle: s.body(15, color: p.muted),
                        border: InputBorder.none,
                        counterText: '',
                      ),
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  IconButton.filled(
                    key: const Key('comment:send'),
                    tooltip: 'Отправить',
                    style: IconButton.styleFrom(backgroundColor: p.accent, foregroundColor: p.onAccent),
                    onPressed: _busy ? null : _send,
                    icon: const Icon(Icons.arrow_upward_rounded, size: 20),
                  ),
                ],
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.xl, Space.s, Space.xl, 0),
          child: Text(
            _open
                ? 'Видит только твоя группа. Долгое нажатие на чужое — пожаловаться или скрыть автора'
                : 'Писать можно за неделю до пары и две недели после',
            style: s.body(12, color: p.muted),
          ),
        ),
      ],
    );
  }
}

class _Bubble extends StatelessWidget {
  final String author, time, text;
  final bool mine;
  final VoidCallback onHold;
  const _Bubble({
    super.key,
    required this.author,
    required this.time,
    required this.text,
    required this.mine,
    required this.onHold,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    const r = Radius.circular(18);
    const tail = Radius.circular(6);
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.8),
        child: Column(
          crossAxisAlignment: mine ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.m, vertical: 2),
              child: Text(time.isEmpty ? author : '$author · $time', style: s.body(12, color: p.muted)),
            ),
            GestureDetector(
              onLongPress: onHold,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: mine ? p.accent : p.card,
                  border: mine ? null : Border.all(color: p.line),
                  borderRadius: BorderRadius.only(
                    topLeft: r,
                    topRight: r,
                    bottomLeft: mine ? r : tail,
                    bottomRight: mine ? tail : r,
                  ),
                ),
                child: Text(text, style: s.body(15, color: mine ? p.onAccent : p.text)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

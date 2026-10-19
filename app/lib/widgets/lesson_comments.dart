// Обсуждение пары (Никита 19.10): на экране пары — два последних сообщения и
// кнопка «Всё обсуждение · N» (пусто — «Написать группе»); всё обсуждение с
// полем ввода — листом. Видит и пишет только своя группа (lesson_comments.py
// на сервере). Правило Apple 1.2: долгое нажатие на чужое — «Пожаловаться» или
// «Скрыть автора» (report.dart), на своё — «Удалить».
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'common.dart';
import 'report.dart';

/// Сколько последних сообщений видно на экране пары.
const commentsPreview = 2;

class _Thread {
  final Api api;
  final Lesson lesson;
  _Thread(this.api, this.lesson);

  String get start => lesson.startAt!.toUtc().toIso8601String();
  String get q => Uri(queryParameters: {'start': start, 'title': lesson.title}).query;
}

class _State {
  List<Map<String, dynamic>> items;
  bool open;
  int max;
  _State(this.items, this.open, this.max);

  factory _State.from(Map j, [_State? old]) => _State(
    [for (final i in j['items'] as List? ?? const []) Map<String, dynamic>.from(i as Map)],
    j.containsKey('open') ? j['open'] == true : (old?.open ?? false),
    j['max'] is int ? j['max'] as int : (old?.max ?? 500),
  );
}

class LessonComments extends StatefulWidget {
  final Api api;
  final Lesson lesson;
  const LessonComments({super.key, required this.api, required this.lesson});

  @override
  State<LessonComments> createState() => _LessonCommentsState();
}

class _LessonCommentsState extends State<LessonComments> {
  late final _t = _Thread(widget.api, widget.lesson);
  _State? _s;

  @override
  void initState() {
    super.initState();
    if (widget.lesson.startAt != null) _load();
  }

  Future<void> _load() async {
    try {
      final j = await widget.api.get('/lesson/comments?${_t.q}');
      if (mounted) setState(() => _s = _State.from(j as Map));
    } catch (_) {} // нет связи или не своя группа — экран без блока
  }

  Future<void> _openAll() async {
    tick();
    final s = await appSheet<_State>(context, (_) => _DiscussionSheet(thread: _t, initial: _s!));
    if (s != null && mounted) setState(() => _s = s);
    if (mounted) await _load(); // закрыли смахиванием — тоже свежий список
  }

  @override
  Widget build(BuildContext context) {
    final st = _s;
    if (st == null || (!st.open && st.items.isEmpty)) return const SizedBox.shrink();
    final s = AppStyle.of(context);
    final p = s.p;
    final n = st.items.length;
    final last = st.items.length > commentsPreview ? st.items.sublist(n - commentsPreview) : st.items;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Section(n == 0 ? 'Обсуждение группы' : 'Обсуждение группы · $n'),
        for (final c in last)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
            child: _Bubble(
              key: Key('comment:${c['id']}'),
              c: c,
              maxLines: 3,
              onTap: _openAll,
              onHold: () => _hold(context, _t, c, _load),
            ),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.xs, Space.l, 0),
          child: OutlinedButton.icon(
            key: const Key('comments:open'),
            style: OutlinedButton.styleFrom(
              foregroundColor: p.accent,
              side: BorderSide(color: p.line),
              backgroundColor: p.card,
              minimumSize: const Size.fromHeight(48),
              shape: const StadiumBorder(),
            ),
            onPressed: _openAll,
            icon: Icon(n == 0 ? Icons.edit_outlined : Icons.forum_outlined, size: 20),
            label: Text(
              n == 0 ? 'Написать группе' : 'Всё обсуждение · $n',
              style: s.body(15, weight: FontWeight.w600, color: p.accent),
            ),
          ),
        ),
        if (n == 0)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.xl, Space.s, Space.xl, 0),
            child: Text(
              'Перенесли, где аудитория, что задали — видит только твоя группа',
              style: s.body(12, color: p.muted),
            ),
          ),
      ],
    );
  }
}

/// Долгое нажатие: своё — «Удалить», чужое — жалоба или «Скрыть автора».
Future<void> _hold(BuildContext context, _Thread t, Map<String, dynamic> c, Future<void> Function() reload) async {
  final id = (c['id'] as num).toInt();
  if (c['mine'] != true) {
    await openReportMenu(context, t.api, kind: 'comment', id: id, onChanged: reload);
    return;
  }
  tick();
  final ok = await confirmSheet(context, title: 'Удалить комментарий?', action: 'Удалить', danger: true);
  if (!ok || !context.mounted) return;
  final toast = Overlay.of(context, rootOverlay: true);
  try {
    await t.api.delete('/lesson/comments/$id');
    await reload();
  } catch (e) {
    toastOn(toast, errorText(e), kind: ToastKind.error);
  }
}

/// Всё обсуждение: сообщения и поле ввода снизу. Закрыл — новый список
/// возвращается экрану пары.
class _DiscussionSheet extends StatefulWidget {
  final _Thread thread;
  final _State initial;
  const _DiscussionSheet({required this.thread, required this.initial});

  @override
  State<_DiscussionSheet> createState() => _DiscussionSheetState();
}

class _DiscussionSheetState extends State<_DiscussionSheet> {
  late _State _s = widget.initial;
  bool _busy = false;
  final _ctrl = TextEditingController();
  final _scroll = ScrollController();

  _Thread get _t => widget.thread;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _toEnd());
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _toEnd() {
    if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
  }

  Future<void> _reload() async {
    try {
      final j = await _t.api.get('/lesson/comments?${_t.q}');
      if (mounted) setState(() => _s = _State.from(j as Map, _s));
    } catch (_) {}
  }

  Future<void> _send() async {
    final text = _ctrl.text.trim();
    if (text.isEmpty || _busy) return;
    tick();
    setState(() => _busy = true);
    final toast = Overlay.of(context, rootOverlay: true);
    try {
      final j = await _t.api.post('/lesson/comments', {'start': _t.start, 'title': _t.lesson.title, 'text': text});
      if (!mounted) return;
      _ctrl.clear();
      setState(() => _s = _State.from(j as Map, _s));
      WidgetsBinding.instance.addPostFrameCallback((_) => _toEnd());
    } on ApiError catch (e) {
      toastOn(toast, e.message, kind: ToastKind.error);
    } catch (e) {
      toastOn(toast, errorText(e), kind: ToastKind.error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final h = MediaQuery.sizeOf(context).height;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.pop(context, _s);
      },
      child: Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
        child: SizedBox(
          height: h * 0.8,
          child: SafeArea(
            top: false,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.s),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Обсуждение пары', style: s.title(24)),
                      Text(
                        'Видит только твоя группа. Долгое нажатие на чужое — пожаловаться или скрыть автора',
                        style: s.body(13, color: p.muted),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: _s.items.isEmpty
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(Space.xl),
                            child: Text(
                              'Пока тихо. Перенесли, где аудитория, что задали — напиши группе',
                              style: s.body(15, color: p.muted),
                              textAlign: TextAlign.center,
                            ),
                          ),
                        )
                      : ListView(
                          controller: _scroll,
                          padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, Space.s),
                          children: [
                            for (final c in _s.items)
                              Padding(
                                padding: const EdgeInsets.only(bottom: Space.s),
                                child: _Bubble(
                                  key: Key('sheet:comment:${c['id']}'),
                                  c: c,
                                  onHold: () => _hold(context, _t, c, _reload),
                                ),
                              ),
                          ],
                        ),
                ),
                if (_s.open)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Space.l, Space.xs, Space.l, Space.s),
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
                              maxLength: _s.max,
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
                  )
                else
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Space.xl, Space.xs, Space.xl, Space.s),
                    child: Text('Писать можно за неделю до пары и две недели после', style: s.body(13, color: p.muted)),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
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

class _Bubble extends StatelessWidget {
  final Map<String, dynamic> c;
  final VoidCallback? onTap;
  final VoidCallback onHold;

  /// На экране пары длинное — в три строки, целиком — в листе.
  final int? maxLines;
  const _Bubble({super.key, required this.c, this.onTap, required this.onHold, this.maxLines});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final mine = c['mine'] == true;
    final author = mine ? 'ты' : '${c['author']}';
    final time = _time('${c['created_at'] ?? ''}');
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
              onTap: onTap,
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
                child: Text(
                  '${c['text']}',
                  maxLines: maxLines,
                  overflow: maxLines == null ? null : TextOverflow.ellipsis,
                  style: s.body(15, color: mine ? p.onAccent : p.text),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

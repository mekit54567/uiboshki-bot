// Карточка задания нового вида (Никита 18.11: «как в СДО, только красивее и
// понятнее, полноценная страница, а не лист снизу»). Только при «Новом»
// ([AppStyle.fresh]); прежний экран задания не меняется.
//
// Сверху — предмет и название. Карточка «Срок»: сколько осталось (одна
// большая цифра), полоска от «открыто с» до срока, обе даты. Карточка «Ответ
// и оценка»: строки таблицы СДО по-человечески и шкала баллов (максимум,
// проходной, своя оценка). Дальше — задание и файлы преподавателя, «Твой
// ответ» со сдачей прямо здесь (прикрепил — видишь файл, пишешь комментарий,
// «Отправить»), комментарии к ответу, как в СДО, и — у срока из «Сдать» —
// напоминания и «Отметить / Изменить / Удалить».
part of 'task.dart';

/// Срок СДО словами («четверг, 26 ноября 2026, 00:00») → дата; не разобрали — null.
DateTime? sdoDate(String? raw) {
  if (raw == null) return null;
  final m = RegExp(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})(?:\D+(\d{1,2}):(\d{2}))?').firstMatch(raw.toLowerCase());
  if (m == null) return null;
  final month = monthsGen.indexOf(m.group(2)!);
  if (month < 0) return null;
  return DateTime(
    int.parse(m.group(3)!),
    month + 1,
    int.parse(m.group(1)!),
    int.parse(m.group(4) ?? '23'),
    int.parse(m.group(5) ?? '59'),
  );
}

/// «чт, 26 ноября, 00:00» — коротко, с днём недели.
String taskDay(DateTime d, {bool time = true}) {
  final hm = '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  return '${weekdaysShort[d.weekday - 1].toLowerCase()}, ${d.day} ${monthsGen[d.month - 1]}${time ? ', $hm' : ''}';
}

/// Номер задания и вид из ссылки СДО в описании срока; не задание — null.
({int cmid, String module})? taskOfLink(String url) {
  final m = RegExp(r'/mod/(assign|quiz)/view\.php\?(?:[^#\s"]*&)?id=(\d+)').firstMatch(url);
  return m == null ? null : (cmid: int.parse(m.group(2)!), module: m.group(1)!);
}

/// Срок из «Сдать» → работа для экрана задания (как из журнала «Учёбы»).
Map<String, dynamic> workOfDeadline(Deadline d, String description) {
  final link = taskOfLink(description);
  final i = d.subject.lastIndexOf(' · ');
  return {
    'name': i > 0 ? d.subject.substring(0, i).trim() : d.subject,
    if (link != null) 'cmid': link.cmid,
    if (link != null) 'module': link.module,
    if (description.startsWith('https://')) 'url': description,
  };
}

/// Действие со сроком на странице (null — просто перечитать) → новые данные срока или null — срок убран.
typedef DeadlineAct = Future<({Deadline d, DlExtra x})?> Function(DlAction? a, Deadline d, DlExtra x);

/// Состояние ответа одним словом и цветом — для строки и для капибары в шапке.
enum _Answer { none, draft, sent, graded, offline }

extension _FreshTask on _TaskScreenState {
  _Answer _answer(Map<String, dynamic>? t) {
    if (t == null) return _Answer.none;
    final st = '${t['status'] ?? ''}'.toLowerCase();
    final grading = '${t['grading'] ?? ''}'.toLowerCase();
    if (t['grade'] != null || w['grade'] != null || (grading.startsWith('оценено') && !grading.contains('не'))) {
      return _Answer.graded;
    }
    if (t['offline'] == true || st.contains('вне сайта')) return _Answer.offline;
    if (t['draft'] == true) return _Answer.draft;
    if (t['submitted'] == true) return _Answer.sent;
    return _Answer.none;
  }

  /// Комментарии видны, когда есть ответ или переписка; до сдачи комментарий
  /// пишется в форме ответа — два поля, уходящие в одно место, путают (сверка UI 19.11).
  bool _commentsShown(Map<String, dynamic> t, _Answer answer) {
    final c = t['comments'];
    if (c is! Map) return false;
    if (((c['items'] as List?) ?? const []).isNotEmpty) return true;
    return ((t['mine'] as List?) ?? const []).isNotEmpty || answer == _Answer.sent || answer == _Answer.graded;
  }

  /// Срок: у срока из «Сдать» — его дата (её мог поменять человек), иначе из СДО.
  DateTime? get _due => _d?.due ?? sdoDate(_t?['due'] as String?);

  Widget _fresh(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final t = _t;
    final at = widget.at ?? now();
    // «№3» не остаётся один на строке (сверка UI 19.11)
    final name = '${t?['title'] ?? w['name'] ?? ''}'.replaceAll(' №', '\u00A0№');
    final course = widget.course.isNotEmpty ? widget.course : (_d == null ? '' : splitCourse(_d!.subject));
    final answer = _answer(t);
    final due = _due;
    final done = _d?.done == true || answer == _Answer.sent || answer == _Answer.graded;
    final late = !done && due != null && !due.isAfter(at);
    final pose = done
        ? CapyPose.joy
        : late
        ? CapyPose.evening
        : CapyPose.day;
    Widget pad(Widget child) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: child,
    );
    final sdo = w['cmid'] is int;
    return ListView(
      key: const ValueKey('task:fresh'),
      padding: const EdgeInsets.only(bottom: Space.xxl),
      children: [
        const Align(alignment: Alignment.centerLeft, child: BackRow()),
        // предмет и название; капибара в углу шапки — настроение срока (брендбук, К1)
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.xl, Space.xs, Space.l, Space.l),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (course.isNotEmpty || _quiz)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Row(
                          children: [
                            if (course.isNotEmpty) ...[
                              Container(
                                width: 8,
                                height: 8,
                                decoration: BoxDecoration(color: s.ink(course), shape: BoxShape.circle),
                              ),
                              const SizedBox(width: 6),
                            ],
                            Flexible(
                              child: Text(
                                [if (course.isNotEmpty) course, if (_quiz) 'тест'].join(' · '),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: s.body(13, weight: FontWeight.w600, color: p.muted),
                              ),
                            ),
                          ],
                        ),
                      ),
                    FitWords(name, style: s.title(titleSize(name, 30)), maxLines: 4),
                  ],
                ),
              ),
              const SizedBox(width: Space.s),
              CapyImage(pose: pose, size: 58, color: p.text),
            ],
          ),
        ),
        pad(_dueCard(context, at, due, done: done, late: late)),
        if (t != null && sdo) ...[const SizedBox(height: Space.m), pad(_gradeCard(context, t, answer))],
        if (t == null && sdo && _error == null) const Padding(padding: EdgeInsets.all(Space.xxl), child: CapyLoading()),
        if (t == null && sdo && _error != null) ..._noSdo(context),
        if (t != null) ..._taskBody(context, t),
        if (t == null && !sdo && (_x?.description.isNotEmpty ?? false) && !(_x!.isLink)) ...[
          const Section('Описание'),
          pad(Tile(child: SelectableText(_x!.description, style: s.body(15)))),
        ],
        if (t != null && sdo) ..._answerBlock(context, t, answer),
        if (t != null && _commentsShown(t, answer)) ..._commentsBlock(context, t['comments'] as Map),
        if (t != null && '${t['feedback'] ?? ''}'.isNotEmpty) ...[
          const Section('Отзыв преподавателя'),
          pad(Tile(child: SelectableText('${t['feedback']}', style: s.body(15)))),
        ],
        if (_d != null) ..._deadlineBlock(context),
        if ((t?['url'] ?? w['url']) is String)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
            child: Center(child: _openSdo(context, '${t?['url'] ?? w['url']}')),
          ),
      ],
    );
  }

  /// «Срок»: отсчёт крупно, полоска от «открыто с» до срока, обе даты.
  Widget _dueCard(BuildContext context, DateTime at, DateTime? due, {required bool done, required bool late}) {
    final s = AppStyle.of(context);
    final p = s.p;
    final opened = sdoDate(_t?['opened'] as String?);
    final left = due?.difference(at);
    final burning = !done && left != null && !left.isNegative && left.inHours < 24;
    final color = done
        ? p.ok
        : late
        ? p.danger
        : burning
        ? p.warn
        : p.text; // акцент — только у главной кнопки и ссылок; у сроков свои цвета (брендбук)
    final head = done
        ? (_answer(_t) == _Answer.graded ? 'Оценено' : 'Сдано')
        : late
        ? 'Срок прошёл'
        : due == null
        ? 'Срок не указан'
        : 'Осталось';
    Widget unit(String u) => Padding(
      padding: const EdgeInsets.only(bottom: 7, left: 3, right: 10),
      child: Text(
        u,
        style: s.body(16, weight: FontWeight.w600, color: p.muted),
      ),
    );
    List<Widget> countdown(Duration d) {
      final days = d.inDays, h = d.inHours % 24, m = d.inMinutes % 60;
      final parts = days > 0
          ? [(days, 'дн'), if (h > 0) (h, 'ч')]
          : d.inHours > 0
          ? [(d.inHours, 'ч'), (m, 'мин')]
          : [(m < 1 ? 1 : m, 'мин')];
      return [
        for (final (n, u) in parts) ...[Text('$n', style: s.number(46, color: color)), unit(u)],
      ];
    }

    double? progress;
    if (opened != null && due != null && due.isAfter(opened)) {
      progress = (at.difference(opened).inMinutes / due.difference(opened).inMinutes).clamp(0.0, 1.0);
    }
    Widget dateRow(String label, String value, {Color? valueColor}) => Padding(
      padding: const EdgeInsets.only(top: Space.s),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 104,
            child: Text(label, style: s.body(14, color: p.muted)),
          ),
          Expanded(
            child: Text(
              value,
              style: s.body(15, weight: FontWeight.w600, color: valueColor),
            ),
          ),
        ],
      ),
    );
    final lateBy = late && left != null ? -left : null;
    // после сдачи отсчёт уже не нужен — когда сдано (последнее изменение в СДО)
    final sentOn = _answer(_t) == _Answer.sent || _answer(_t) == _Answer.graded
        ? sdoDate(_t?['modified'] as String?)
        : null;
    return Tile(
      key: const Key('task:due'),
      radius: Radii.card,
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
                head,
                style: s.body(14, weight: FontWeight.w700, color: color),
              ),
            ],
          ),
          if (!done && !late && left != null)
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.bottomLeft,
              child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: countdown(left)),
            )
          else if (lateBy != null)
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.bottomLeft,
              child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [...countdown(lateBy), unit('назад')]),
            )
          else if (done && sentOn != null) ...[
            const SizedBox(height: 4),
            Text(
              // под «Сдано» — просто дата, под «Оценено» — что это дата сдачи
              '${_answer(_t) == _Answer.graded ? 'сдано ' : ''}${taskDay(sentOn, time: false)}',
              key: const Key('task:sent-on'),
              style: s.body(16, weight: FontWeight.w600),
            ),
          ],
          if (progress != null && !done && !late) ...[
            const SizedBox(height: Space.m),
            // полоска: сколько времени от «открыто с» до срока уже прошло
            LayoutBuilder(
              builder: (context, box) => Container(
                height: 6,
                alignment: Alignment.centerLeft,
                decoration: BoxDecoration(color: p.line, borderRadius: BorderRadius.circular(3)),
                child: Container(
                  width: box.maxWidth * progress!,
                  decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3)),
                ),
              ),
            ),
          ],
          const SizedBox(height: Space.s),
          if (opened != null) dateRow('Открыто с', taskDay(opened)),
          dateRow(
            'Срок сдачи',
            due == null ? 'не указан' : taskDay(due, time: _d == null || _d!.dueTime.isNotEmpty),
            valueColor: late ? p.danger : null,
          ),
        ],
      ),
    );
  }

  /// «Ответ и оценка»: строки таблицы СДО и шкала баллов.
  Widget _gradeCard(BuildContext context, Map<String, dynamic> t, _Answer answer) {
    final s = AppStyle.of(context);
    final p = s.p;
    final max = (t['max_grade'] ?? w['max']) as num?;
    final pass = (t['pass'] ?? w['pass_mark']) as num?;
    final grade = (t['grade'] ?? w['grade']) as num?;
    final (String ans, Color ansColor) = switch (answer) {
      _Answer.graded => ('Сдано', p.ok),
      _Answer.sent => ('Сдано, ждёт оценки', p.ok),
      _Answer.draft => ('Черновик, не отправлен', p.warn),
      _Answer.offline => ('Сдаётся на занятии', p.muted),
      _Answer.none => (t['quiz'] == true ? 'Тест в СДО' : 'Ещё не сдано', p.muted),
    };
    Widget row(String label, Widget value) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 5,
            child: Text(label, style: s.body(14, color: p.muted)),
          ),
          const SizedBox(width: Space.s),
          Expanded(flex: 6, child: value),
        ],
      ),
    );
    Widget word(String text, {Color? color, bool dot = false}) => Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (dot)
          Padding(
            padding: const EdgeInsets.only(top: 6, right: 6),
            child: Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
          ),
        Expanded(
          child: Text(
            text,
            style: s.body(15, weight: FontWeight.w600, color: color ?? p.text),
          ),
        ),
      ],
    );
    final rows = <Widget>[
      row('Ответ', word(ans, color: ansColor, dot: true)),
      // оценка — шкалой сверху; строкой, только пока не проверено или шкалы нет (сверка UI 19.11)
      if (grade != null && (max == null || max <= 0))
        row('Оценка', word(fmtNum(grade), color: pass != null && grade < pass ? p.danger : p.ok))
      else if (answer == _Answer.sent || answer == _Answer.offline)
        row('Оценка', word('ещё не проверено', color: p.muted)),
      if ('${t['modified'] ?? ''}'.isNotEmpty) row('Изменено', word(_shortSdo('${t['modified']}'))),
      if ('${t['graded_by'] ?? ''}'.isNotEmpty) row('Преподаватель', word('${t['graded_by']}')),
    ];
    return Tile(
      key: const Key('task:grade'),
      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, Space.m),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (max != null && max > 0) ...[_Scale(max: max, pass: pass, grade: grade), const SizedBox(height: Space.s)],
          for (var i = 0; i < rows.length; i++) ...[if (i > 0) Divider(height: 1, color: p.line), rows[i]],
        ],
      ),
    );
  }

  /// Задание: описание, тест, файлы преподавателя.
  List<Widget> _taskBody(BuildContext context, Map<String, dynamic> t) {
    final s = AppStyle.of(context);
    const pad = EdgeInsets.symmetric(horizontal: Space.l);
    final files = (t['files'] as List?) ?? [];
    return [
      if ('${t['description'] ?? ''}'.isNotEmpty) ...[
        const Section('Задание'),
        Padding(
          padding: pad,
          child: Tile(child: SelectableText('${t['description']}', style: s.body(15.5))),
        ),
      ],
      if (t['quiz'] == true) ...[
        const Section('Тест'),
        Padding(
          padding: pad,
          child: _QuizCard(t: t, status: '${w['status'] ?? ''}'),
        ),
      ],
      if (files.isNotEmpty) ...[
        Section('Файлы задания · ${files.length}'),
        Padding(
          padding: pad,
          child: _FileList(names: [for (final f in files) '${f['name']}'], onTap: (i) => _download(false, i)),
        ),
      ],
    ];
  }

  /// СДО не подключено или задание не открылось: что есть со срока + как починить.
  List<Widget> _noSdo(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final login = needsSdo(_error!);
    return [
      const SizedBox(height: Space.m),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l),
        child: Tile(
          key: const Key('task:nosdo'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(login ? 'Подключи СДО' : 'СДО не ответило', style: s.body(17, weight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text(
                login
                    ? 'Тогда здесь будут баллы, состояние ответа и комментарии, а сдать можно будет прямо отсюда.'
                    : '${_error!}. Срок и твои отметки ниже работают и без СДО.',
                style: s.body(14, color: p.muted),
              ),
              const SizedBox(height: Space.m),
              FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: p.accent,
                  foregroundColor: p.onAccent,
                  shape: const StadiumBorder(),
                  minimumSize: const Size(0, 44),
                ),
                onPressed: () async {
                  tick();
                  if (login) {
                    await Navigator.of(context)
                        .push(MaterialPageRoute(builder: (_) => SdoConnectScreen(api: widget.api)));
                  }
                  _retry();
                },
                child: Text(login ? 'Подключить СДО' : 'Ещё раз'),
              ),
            ],
          ),
        ),
      ),
    ];
  }

  /// «Твой ответ»: свои файлы, сдача прямо здесь, «Заменить» и «Удалить».
  List<Widget> _answerBlock(BuildContext context, Map<String, dynamic> t, _Answer answer) {
    final s = AppStyle.of(context);
    final p = s.p;
    const pad = EdgeInsets.symmetric(horizontal: Space.l);
    final mine = (t['mine'] as List?) ?? [];
    final canSubmit = t['can_submit'] == true;
    final canEdit = t['can_edit'] == true;
    final canRemove = t['can_remove'] == true;
    final form = canSubmit && (mine.isEmpty && answer != _Answer.sent || _replace);
    if (t['quiz'] == true) {
      return [
        if (t['open_now'] == true)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
            child: _bigButton(
              context,
              icon: Icons.open_in_new_rounded,
              text: 'Пройти тест в СДО',
              onTap: () => widget.open(Uri.parse('${t['url']}')),
            ),
          ),
      ];
    }
    final note = answer == _Answer.offline
        ? 'Эту работу сдают на занятии, не через СДО. Ответ можно не прикреплять.'
        : !canSubmit && mine.isEmpty
        ? (t['closed'] is String && '${t['closed']}'.isNotEmpty
              ? 'Сдача закрыта: ${t['closed']}'
              : 'Сейчас СДО не даёт прикрепить ответ: срок прошёл или сдача закрыта.')
        : null;
    return [
      const Section('Твой ответ'),
      if (mine.isNotEmpty)
        Padding(
          padding: pad,
          child: _FileList(names: [for (final f in mine) '${f['name']}'], onTap: (i) => _download(true, i)),
        ),
      if (note != null && !form)
        Padding(
          padding: pad,
          child: Tile(
            child: Text(note, style: s.body(14.5, color: p.muted)),
          ),
        ),
      if (form) ...[
        if (mine.isNotEmpty) const SizedBox(height: Space.s),
        Padding(
          padding: pad,
          child: _SubmitForm(state: this, replace: _replace, comments: _commentsShown(t, answer)),
        ),
      ],
      if (!form && (canEdit || canRemove)) ...[
        const SizedBox(height: Space.m),
        Padding(
          padding: pad,
          child: Row(
            children: [
              if (canEdit)
                Expanded(
                  child: _pillButton(
                    context,
                    key: const Key('task:replace'),
                    icon: null,
                    text: 'Заменить файлы',
                    onTap: () => _setState(() => _replace = true),
                  ),
                ),
              if (canEdit && canRemove) const SizedBox(width: Space.s),
              if (canRemove)
                Expanded(
                  child: _pillButton(
                    context,
                    key: const Key('task:remove'),
                    icon: null,
                    text: 'Удалить ответ',
                    color: p.danger,
                    onTap: _remove,
                  ),
                ),
            ],
          ),
        ),
      ],
      if (!form && canSubmit && !canEdit && mine.isEmpty && answer == _Answer.sent)
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, 0),
          child: _pillButton(
            context,
            icon: Icons.attach_file_rounded,
            text: 'Прикрепить ещё',
            onTap: () => _setState(() => _replace = true),
          ),
        ),
    ];
  }

  /// Комментарии к ответу — переписка с преподавателем, как в СДО.
  List<Widget> _commentsBlock(BuildContext context, Map c) {
    final s = AppStyle.of(context);
    final p = s.p;
    final items = (c['items'] as List?) ?? const [];
    final count = (c['count'] as num?)?.toInt() ?? items.length;
    return [
      Section(count > 0 ? 'Комментарии · $count' : 'Комментарии'),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l),
        child: Tile(
          key: const Key('task:comments'),
          padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.s, Space.s),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (items.isEmpty)
                Padding(
                  padding: const EdgeInsets.only(right: Space.s, bottom: Space.s),
                  child: Text(
                    'Пока пусто. Преподаватель увидит комментарий в\u00A0СДО.',
                    style: s.body(14, color: p.muted),
                  ),
                ),
              for (final m in items)
                Padding(
                  padding: const EdgeInsets.only(right: Space.s, bottom: Space.m),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: '${m['author']}',
                              style: s.body(13.5, weight: FontWeight.w700),
                            ),
                            TextSpan(
                              text: '  ${_shortSdo('${m['time']}')}',
                              style: s.body(12.5, color: p.muted),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 3),
                      SelectableText('${m['text']}', style: s.body(15)),
                    ],
                  ),
                ),
              if (c['can_post'] == true)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Expanded(
                      child: _field(
                        context,
                        key: const Key('task:comment'),
                        controller: _commentCtl,
                        hint: 'Написать комментарий',
                      ),
                    ),
                    IconButton(
                      key: const Key('task:comment:send'),
                      tooltip: 'Отправить комментарий',
                      onPressed: _posting ? null : _postComment,
                      icon: _posting
                          ? SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(strokeWidth: 2, color: p.accent),
                            )
                          : Icon(Icons.arrow_upward_rounded, color: p.accent),
                    ),
                  ],
                ),
            ],
          ),
        ),
      ),
    ];
  }

  /// Срок в «Капибаре»: напоминания, отметка, правка, удаление — то, что было в листе.
  List<Widget> _deadlineBlock(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final d = _d!, x = _x!;
    final answer = _answer(_t);
    final sdoDone = answer == _Answer.sent || answer == _Answer.graded;
    Widget act(DlAction a, IconData icon, String text, {String? sub, Color? color}) => InkWell(
      key: ValueKey('task:act:${a.name}'),
      onTap: () {
        tick();
        _deadlineAct(a);
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: 13),
        child: Row(
          children: [
            Icon(icon, size: 21, color: color ?? p.muted),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    text,
                    style: s.body(15, weight: FontWeight.w600, color: color),
                  ),
                  if (sub != null) Text(sub, style: s.body(13, color: p.muted)),
                ],
              ),
            ),
            if (color == null) Icon(Icons.chevron_right_rounded, size: 20, color: p.muted),
          ],
        ),
      ),
    );
    final rows = <Widget>[
      if (!d.done)
        act(DlAction.remind, Icons.notifications_none_rounded, 'Напомнить', sub: 'за день, за час или в своё время'),
      if (d.done)
        act(DlAction.undone, Icons.undo_rounded, 'Вернуть в активные')
      // в СДО уже «Сдано» — отмечать нечего (сверка UI 19.11)
      else if (!sdoDone)
        act(
          DlAction.done,
          Icons.check_rounded,
          'Отметить сданным',
          sub: d.canSubmit ? 'только у тебя, в СДО ничего не\u00A0уйдёт' : null,
        ),
      if (x.canEdit) act(DlAction.edit, Icons.edit_outlined, 'Изменить', sub: 'название, дата и время'),
      if (x.mineChanged) act(DlAction.resetMine, Icons.restart_alt_rounded, 'Как у всех'),
      if (x.canEdit)
        act(
          DlAction.delete,
          Icons.delete_outline_rounded,
          x.editScope == 'me' ? 'Убрать у себя' : 'Удалить срок',
          color: p.danger,
        ),
      if (x.reportable) act(DlAction.report, Icons.flag_outlined, 'Пожаловаться или скрыть', color: p.muted),
    ];
    return [
      const Section('Срок в Капибаре'),
      if (x.hasChips(time: !d.done))
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
          child: DlChips(x: x, time: !d.done),
        ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l),
        child: Tile(
          key: const Key('task:deadline'),
          padding: EdgeInsets.zero,
          child: Column(
            children: [
              for (var i = 0; i < rows.length; i++) ...[if (i > 0) Divider(height: 1, color: p.line), rows[i]],
            ],
          ),
        ),
      ),
    ];
  }
}

/// «вторник, 10 ноября 2026, 21:14» → «вт, 10 ноября, 21:14»; не дата — как есть.
String _shortSdo(String raw) {
  final d = sdoDate(raw);
  if (d == null || !RegExp(r'\d{4}').hasMatch(raw)) return raw;
  return taskDay(d, time: RegExp(r'\d{1,2}:\d{2}').hasMatch(raw));
}

/// Предмет из названия срока («Практика 5 · Анализ данных (Экз)» → «Анализ данных»).
String splitCourse(String subject) {
  final i = subject.lastIndexOf(' · ');
  if (i <= 0) return '';
  return subject.substring(i + 3).replaceFirst(RegExp(r'\s*\((Экз|Зач)\)\s*$'), '').trim();
}

/// Главная кнопка страницы — акцентная пилюля во всю ширину.
Widget _bigButton(BuildContext context, {Key? key, required IconData icon, required String text, VoidCallback? onTap}) {
  final p = AppStyle.of(context).p;
  return SizedBox(
    width: double.infinity,
    height: 52,
    child: FilledButton.icon(
      key: key,
      style: FilledButton.styleFrom(
        backgroundColor: p.accent,
        foregroundColor: p.onAccent,
        disabledBackgroundColor: p.line,
        disabledForegroundColor: p.muted,
        shape: const StadiumBorder(),
      ),
      onPressed: onTap == null
          ? null
          : () {
              tick();
              onTap();
            },
      icon: Icon(icon, size: 20),
      label: Text(text),
    ),
  );
}

/// Второстепенная кнопка — пилюля с краем.
Widget _pillButton(
  BuildContext context, {
  Key? key,
  required IconData? icon,
  required String text,
  required VoidCallback onTap,
  Color? color,
}) {
  final p = AppStyle.of(context).p;
  final style = OutlinedButton.styleFrom(
    foregroundColor: color ?? p.text,
    side: BorderSide(color: color?.withValues(alpha: 0.6) ?? p.edge),
    shape: const StadiumBorder(),
    minimumSize: const Size(0, 46),
    padding: const EdgeInsets.symmetric(horizontal: 14),
  );
  void tap() {
    tick();
    onTap();
  }

  final label = Text(text, maxLines: 1, overflow: TextOverflow.ellipsis);
  return icon == null
      ? OutlinedButton(key: key, style: style, onPressed: tap, child: label)
      : OutlinedButton.icon(key: key, style: style, onPressed: tap, icon: Icon(icon, size: 18), label: label);
}

/// Поле ввода в карточке: бумажный фон, край, без подчёркивания.
Widget _field(
  BuildContext context, {
  Key? key,
  required TextEditingController controller,
  required String hint,
  int maxLines = 4,
}) {
  final s = AppStyle.of(context);
  final p = s.p;
  final border = OutlineInputBorder(
    borderRadius: BorderRadius.circular(Radii.chip),
    borderSide: BorderSide(color: p.edge),
  );
  return TextField(
    key: key,
    controller: controller,
    minLines: 1,
    maxLines: maxLines,
    maxLength: 2000,
    textCapitalization: TextCapitalization.sentences,
    style: s.body(15),
    decoration: InputDecoration(
      hintText: hint,
      hintStyle: s.body(15, color: p.muted),
      counterText: '',
      isDense: true,
      filled: true,
      fillColor: p.bg,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      enabledBorder: border,
      border: border,
      focusedBorder: border.copyWith(borderSide: BorderSide(color: p.accent, width: 1.5)),
    ),
  );
}

/// Шкала баллов: 0 — проходной — максимум; своя оценка — заливкой.
class _Scale extends StatelessWidget {
  final num max;
  final num? pass, grade;
  const _Scale({required this.max, this.pass, this.grade});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final g = grade;
    final fill = g == null ? 0.0 : (g / max).clamp(0.0, 1.0).toDouble();
    final passAt = pass == null ? null : (pass! / max).clamp(0.0, 1.0).toDouble();
    final color = g == null
        ? p.muted
        : pass != null && g < pass!
        ? p.danger
        : p.ok;
    return Semantics(
      label:
          'Максимум ${fmtNum(max)}${pass != null ? ', проходной ${fmtNum(pass!)}' : ''}'
          '${g != null ? ', у тебя ${fmtNum(g)}' : ''}',
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Text.rich(
                  TextSpan(
                    children: [
                      if (g != null)
                        TextSpan(
                          text: '${fmtNum(g)}  ',
                          style: s.body(22, weight: FontWeight.w700, color: color),
                        ),
                      TextSpan(
                        text: g != null ? 'из ' : 'Максимум ',
                        style: s.body(14, color: p.muted),
                      ),
                      TextSpan(
                        text:
                            '${fmtNum(max)} ${g != null ? plural(max.round(), 'балла', 'баллов', 'баллов') : plural(max.round(), 'балл', 'балла', 'баллов')}',
                        style: s.body(14, weight: FontWeight.w600, color: g != null ? p.muted : p.text),
                      ),
                    ],
                  ),
                ),
              ),
              if (pass != null)
                Text(
                  'проходной ${fmtNum(pass!)}',
                  style: s.body(13, weight: FontWeight.w600, color: p.muted),
                ),
            ],
          ),
          const SizedBox(height: Space.s),
          LayoutBuilder(
            builder: (context, box) => SizedBox(
              height: 14,
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  Positioned(
                    left: 0,
                    right: 0,
                    top: 4,
                    height: 6,
                    child: Container(
                      decoration: BoxDecoration(color: p.line, borderRadius: BorderRadius.circular(3)),
                    ),
                  ),
                  if (fill > 0)
                    Positioned(
                      left: 0,
                      top: 4,
                      height: 6,
                      width: box.maxWidth * fill,
                      child: Container(
                        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3)),
                      ),
                    ),
                  if (passAt != null)
                    Positioned(
                      left: (box.maxWidth * passAt - 1.5).clamp(0.0, box.maxWidth - 3),
                      top: 0,
                      width: 3,
                      height: 14,
                      child: Container(
                        decoration: BoxDecoration(color: p.text, borderRadius: BorderRadius.circular(1.5)),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Сдача прямо на странице: что принимает задание, прикреплённые файлы с
/// проверкой, комментарий преподавателю и «Отправить».
class _SubmitForm extends StatelessWidget {
  final _TaskScreenState state;
  final bool replace, comments;
  const _SubmitForm({required this.state, required this.replace, this.comments = false});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final st = state;
    final rules = st._rules;
    final good = st._good.length;
    if (rules == null && st._rulesError == null) {
      return Tile(
        child: Row(
          children: [
            SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2, color: p.accent)),
            const SizedBox(width: Space.m),
            Text('Смотрю, что принимает задание…', style: s.body(14, color: p.muted)),
          ],
        ),
      );
    }
    if (rules == null || rules.closed != null) {
      return Tile(
        child: Text(rules?.closed ?? st._rulesError!, style: s.body(14.5, color: p.danger)),
      );
    }
    final more = good < rules.perSubmit && st._files.length < rules.perSubmit + 3;
    return Tile(
      key: const Key('task:form'),
      radius: Radii.card,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${replace ? 'Новые файлы заменят прежние. ' : ''}Принимает: ${rules.describe()}',
            style: s.body(13.5, color: p.muted),
          ),
          const SizedBox(height: Space.m),
          for (final e in st._files)
            Padding(
              padding: const EdgeInsets.only(bottom: Space.s),
              child: _PickedFile(
                name: e.f.name,
                size: fileSize(e.f.bytes.length),
                why: e.why,
                onRemove: st._sending ? null : () => st._setState(() => st._files.remove(e)),
              ),
            ),
          if (more)
            _AttachButton(
              key: const Key('task:attach'),
              first: st._files.isEmpty,
              onTap: st._sending ? null : st._pick,
            ),
          // комментарий к ответу — здесь, пока ниже нет переписки (там своё поле)
          if (!comments) ...[
            const SizedBox(height: Space.m),
            _field(
              context,
              key: const Key('task:submit:comment'),
              controller: st._noteCtl,
              hint: 'Комментарий преподавателю, если нужно',
            ),
          ],
          if (st._sendError != null) ...[
            const SizedBox(height: Space.s),
            Text(st._sendError!, style: s.body(14, color: p.danger)),
          ],
          const SizedBox(height: Space.m),
          _bigButton(
            context,
            key: const Key('task:send'),
            icon: Icons.send_rounded,
            text: st._sending
                ? 'Отправляю…'
                : good == 0
                ? 'Отправить'
                : 'Отправить $good ${plural(good, 'файл', 'файла', 'файлов')}',
            onTap: good == 0 || st._sending ? null : st._send,
          ),
          const SizedBox(height: Space.s),
          Center(
            child: Text(
              replace ? 'Ответ обновится в СДО от твоего имени' : 'Уйдёт преподавателю в СДО от твоего имени',
              textAlign: TextAlign.center,
              style: s.body(12.5, color: p.muted),
            ),
          ),
          if (replace)
            Center(
              child: TextButton(
                onPressed: st._sending
                    ? null
                    : () => st._setState(() {
                        st._replace = false;
                        st._files.clear();
                      }),
                child: Text(
                  'Не заменять',
                  style: s.body(14, weight: FontWeight.w600, color: p.muted),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// «Прикрепить файл» — пунктирная рамка: сюда что-то кладут.
class _AttachButton extends StatelessWidget {
  final bool first;
  final VoidCallback? onTap;
  const _AttachButton({super.key, required this.first, this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Semantics(
      button: true,
      child: InkWell(
        borderRadius: BorderRadius.circular(Radii.chip),
        onTap: onTap == null
            ? null
            : () {
                tick();
                onTap!();
              },
        child: CustomPaint(
          painter: _DashedBorder(color: p.edge, radius: Radii.chip),
          child: Container(
            constraints: BoxConstraints(minHeight: first ? 72 : 48),
            alignment: Alignment.center,
            padding: const EdgeInsets.symmetric(horizontal: Space.m, vertical: Space.s),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.attach_file_rounded, size: 20, color: p.accent),
                const SizedBox(width: Space.s),
                Text(
                  first ? 'Прикрепить файл' : 'Ещё файл',
                  style: s.body(15, weight: FontWeight.w600, color: p.accent),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _DashedBorder extends CustomPainter {
  final Color color;
  final double radius;
  const _DashedBorder({required this.color, required this.radius});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    final path = Path()..addRRect(RRect.fromRectAndRadius(Offset.zero & size, Radius.circular(radius)).deflate(0.7));
    for (final m in path.computeMetrics()) {
      // штрихи ровно по длине контура: последний не обрубается на стыке
      final n = (m.length / 9).round().clamp(4, 10000);
      final step = m.length / n;
      for (var i = 0; i < n; i++) {
        canvas.drawPath(m.extractPath(i * step, i * step + step * 0.55), paint);
      }
    }
  }

  @override
  bool shouldRepaint(_DashedBorder old) => old.color != color || old.radius != radius;
}

/// Прикреплённый файл: иконка по типу, имя, размер, подходит ли, «убрать».
class _PickedFile extends StatelessWidget {
  final String name, size;
  final String? why;
  final VoidCallback? onRemove;
  const _PickedFile({required this.name, required this.size, this.why, this.onRemove});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final ok = why == null;
    return Container(
      padding: const EdgeInsets.fromLTRB(Space.m, Space.s, Space.xs, Space.s),
      decoration: BoxDecoration(
        color: p.bg,
        borderRadius: BorderRadius.circular(Radii.chip),
        border: Border.all(color: ok ? p.line : p.danger.withValues(alpha: 0.6)),
      ),
      child: Row(
        children: [
          Icon(_fileIcon(name), size: 22, color: ok ? p.accent : p.danger),
          const SizedBox(width: Space.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: s.body(14.5, weight: FontWeight.w600),
                ),
                const SizedBox(height: 1),
                Text(
                  ok ? '$size · подходит' : why!,
                  style: s.body(12.5, weight: ok ? FontWeight.w400 : FontWeight.w600, color: ok ? p.ok : p.danger),
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Убрать',
            onPressed: onRemove,
            icon: Icon(Icons.close_rounded, size: 19, color: p.muted),
          ),
        ],
      ),
    );
  }
}

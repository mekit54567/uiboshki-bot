// Экран предмета: цель (sdo_goal.py — без дат и раскладки по времени,
// решение владельца), посещения лекций (attendance.py) и как росли баллы
// (sdo_history.py). Данные — из /api/sdo/grades/<курс>, цель — POST /api/sdo/goal.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../screens/pulse.dart' show PulseScreen, pulseOpenNow;
import 'capy.dart';
import 'common.dart';

String markWord(String label) => label == 'зачёт' ? 'зачёт' : '«$label»';

String fmtNum(num v) => v == v.roundToDouble() ? '${v.round()}' : v.toStringAsFixed(1).replaceAll('.', ',');

/// «2026-08-27» → «27 августа»; не дата — пусто.
String dayMonth(String isoDate) {
  final d = DateTime.tryParse(isoDate);
  return d == null ? '' : '${d.day} ${monthsGen[d.month - 1]}';
}

String _points(num n) => '${fmtNum(n)} ${plural(n.ceil(), 'балл', 'балла', 'баллов')}';

/// Главная строка «Цели» называет то, что мешает (2.1, 2.19): «Нужно зачесть
/// ещё 4 работы», «Не хватает 12 баллов», ««4» выходит автоматом». С 14.10
/// сервер считает отдельно автомат и «с экзаменом» (поле `mode`): «не хватает»
/// — всегда до порога целиком, без путаницы с недобором при полном экзамене.
String goalHeadline(Map<String, dynamic> g) {
  final label = markWord('${g['label']}');
  final tk = Map<String, dynamic>.from(g['tk'] ?? {});
  final works = (tk['left'] as num?)?.toInt() ?? 0;
  final need = (g['need'] as num?) ?? 0;
  final mode = g['mode'];
  if (mode == 'auto' || mode == 'exam') {
    if (g['status'] == 'done') return mode == 'auto' ? '$label выходит автоматом' : 'Баллов хватает';
    if (need > 0) return 'Не хватает ${_points(need)}';
    if (works > 0) return 'Нужно зачесть ещё $works ${plural(works, 'работу', 'работы', 'работ')}';
    return mode == 'exam' ? 'Хватит любого балла на экзамене' : 'Баллов хватает';
  }
  final pending = g['exam_pending'] == true;
  if (pending && g['auto_ok'] != true) {
    final short = (g['exam_short'] as num?) ?? 0;
    if (short > 0) return 'Не хватает ${_points(short)}'; // даже с полным экзаменом
    final exam = (g['need_exam'] as num?) ?? 0;
    final onExam = exam > 0
        ? 'на $label нужно ${_points(exam)} на экзамене'
        : 'на $label хватит любого балла на экзамене';
    final auto = g['auto'];
    return auto != null ? '${markWord('$auto')} автоматом, $onExam' : onExam[0].toUpperCase() + onExam.substring(1);
  }
  if (g['status'] == 'done') return pending ? '$label выходит автоматом' : 'Баллов хватает';
  if (need > 0) return 'Не хватает ${_points(need)}';
  if (works > 0) return 'Нужно зачесть ещё $works ${plural(works, 'работу', 'работы', 'работ')}';
  return 'Баллов хватает';
}

/// Строка под главной: сколько нужно для цели и второй путь (экзамен, автомат).
String goalSubline(Map<String, dynamic> g) {
  final tk = Map<String, dynamic>.from(g['tk'] ?? {});
  final works = (tk['left'] as num?)?.toInt() ?? 0;
  final need = (g['need'] as num?) ?? 0;
  final mode = g['mode'];
  final what = g['label'] == 'зачёт' ? 'зачёта' : markWord('${g['label']}');
  final at = _points((g['at'] as num?) ?? 0);
  if (mode == 'auto') {
    return [
      'для $what автоматом нужно $at за семестр',
      if (works > 0) 'и зачесть ещё $works ${plural(works, 'работу', 'работы', 'работ')}',
    ].join(' ');
  }
  if (mode == 'exam') {
    final exam = (g['need_exam'] as num?) ?? 0, short = (g['exam_short'] as num?) ?? 0;
    return [
      'для $what нужно $at вместе с экзаменом',
      if (short > 0)
        'с полным экзаменом добрать ещё ${fmtNum(short)} работами и лекциями'
      else if (need > 0 && exam > 0)
        'хватит ${_points(exam)} на экзамене',
    ].join(' · ');
  }
  final pending = g['exam_pending'] == true, autoOk = g['auto_ok'] == true;
  final parts = ['для $what нужно $at'];
  if (pending && autoOk && need > 0 && ((g['need_exam'] as num?) ?? 0) > 0) {
    parts.add('или ${_points(g['need_exam'] as num)} на экзамене');
  }
  if (need > 0 && works > 0 && (autoOk || !pending)) {
    parts.add('и зачесть ещё $works ${plural(works, 'работу', 'работы', 'работ')}');
  }
  if (pending && !autoOk && g['auto'] == null && g['auto_best'] != null) {
    parts.add('${markWord('${g['auto_best']}')} можно получить автоматом');
  }
  return parts.join(' · ');
}

/// Какие работы нельзя пропустить (поле `must`, 14.10): без любой из них цель
/// уже не набрать. Прогноз без процентов — данных для них нет.
String? mustLine(Map<String, dynamic> g) {
  final must = [for (final m in (g['must'] as List? ?? const [])) '$m'];
  if (must.isEmpty) return null;
  final open = (g['open_count'] as num?)?.toInt() ?? 0;
  if (must.length > 1 && must.length >= open) return 'сдать нужно все открытые работы: без любой не дойдёшь';
  if (must.length > 3) return 'без ${must.length} открытых работ не дойдёшь — сдавай все';
  return 'без «${must.join('», «')}» не дойдёшь';
}

const goalNote = 'Это расчёт по баллам из СДО на сейчас. Оценку ставит преподаватель.';

/// «до 41 балла», «до 12 баллов», «до 2,5 балла» — после «до» родительный падеж.
String upToPoints(num v) {
  final whole = v == v.roundToDouble();
  return 'до ${fmtNum(v)} ${whole ? plural(v.round(), 'балла', 'баллов', 'баллов') : 'балла'}';
}

/// Когда сервер брал баллы из СДО ([unix] — секунды): «сегодня в 09:40»,
/// «вчера в 21:10», «8 октября в 09:40». Время — московское, как у пар.
String updatedText(int unix, DateTime at) {
  DateTime msk(DateTime t) {
    final u = t.toUtc().add(const Duration(hours: 3));
    return DateTime(u.year, u.month, u.day, u.hour, u.minute);
  }

  final t = msk(DateTime.fromMillisecondsSinceEpoch(unix * 1000, isUtc: true)), a = msk(at);
  final days = DateTime(a.year, a.month, a.day).difference(DateTime(t.year, t.month, t.day)).inHours ~/ 24;
  final hm = '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  if (days <= 0) return 'сегодня в\u00A0$hm';
  if (days == 1) return 'вчера в\u00A0$hm';
  return '${t.day}\u00A0${monthsGen[t.month - 1]} в\u00A0$hm';
}

/// Строки «откуда взять» цели в новом дизайне (макет 4, 11.11) — те же данные,
/// что значками в прежней карточке, но целыми фразами: «Открыто 4 работы,
/// они дают до 41 балла».
List<String> goalFreshLines(Map<String, dynamic> g) {
  final status = '${g['status'] ?? 'ok'}';
  final tk = Map<String, dynamic>.from(g['tk'] ?? {});
  final need = (g['need'] as num?) ?? 0;
  final open = (g['open_count'] as num?)?.toInt() ?? 0;
  final lost = (g['lost_count'] as num?)?.toInt() ?? 0;
  String up(String t) => t.isEmpty ? t : t[0].toUpperCase() + t.substring(1);
  return [
    if (open > 0)
      'Открыто $open ${plural(open, 'работа', 'работы', 'работ')}, ${open == 1 ? 'она даёт' : 'они дают'} '
          '${upToPoints((g['open_points'] as num?) ?? 0)}',
    if (((g['attendance_left'] as num?) ?? 0) > 0) 'Лекции впереди дают ${upToPoints(g['attendance_left'] as num)}',
    if (((g['exam_left'] as num?) ?? 0) > 0) 'Экзамен даёт ${upToPoints(g['exam_left'] as num)}',
    if (((tk['total'] as num?) ?? 0) > 0)
      'Зачтено ${tk['passed']} из ${tk['total']} ${plural((tk['total'] as num).toInt(), 'работы', 'работ', 'работ')}, '
          'нужно ${tk['need']}'
          '${((tk['left'] as num?) ?? 0) > 0 ? ': из ${tk['open']} открытых зачесть ${tk['left']}' : ''}',
    if (mustLine(g) case final must?) up(must),
    if (need > 0 && status != 'done')
      'Если сдать всё и ходить на лекции${((g['exam_left'] as num?) ?? 0) > 0 ? ', а потом сдать экзамен' : ''}, '
          'выйдет до ${fmtNum((g['best'] as num?) ?? 0)}',
    if (lost > 0) 'Ниже порога или срок прошёл: $lost. Их не считаю, пригодятся, если дадут пересдать',
  ];
}

class GoalCard extends StatefulWidget {
  final Api api;
  final int courseId;
  final Map<String, dynamic> goal;
  final Color color;

  /// Когда баллы брали из СДО (unix-секунды) — строкой внизу карточки нового дизайна.
  final int? updated;
  const GoalCard({
    super.key,
    required this.api,
    required this.courseId,
    required this.goal,
    required this.color,
    this.updated,
  });

  @override
  State<GoalCard> createState() => _GoalCardState();
}

class _GoalCardState extends State<GoalCard> {
  late Map<String, dynamic> _g = widget.goal;
  String? _error;

  Future<void> _set(String label) async {
    if (label == _g['label']) return;
    await _post({'label': label});
  }

  /// Счёт цели: «автомат» — без экзамена, «с экзаменом» — сумма (14.10).
  Future<void> _setMode(String mode) async {
    if (mode == _g['mode']) return;
    await _post({'mode': mode});
  }

  Future<void> _post(Map<String, Object?> body) async {
    tick();
    try {
      final r = await widget.api.post('/sdo/goal/${widget.courseId}', body);
      HapticFeedback.lightImpact();
      // Карточка в ленивом ListView: ушла за экран — создаётся заново из
      // widget.goal. Пишем выбор и туда, иначе цель «сбрасывалась» на первую.
      widget.goal
        ..clear()
        ..addAll(Map<String, dynamic>.from(r));
      setState(() {
        _g = Map<String, dynamic>.from(r);
        _error = null;
      });
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final g = _g;
    final status = '${g['status'] ?? 'ok'}';
    final (Color tone, String verdict) = switch (status) {
      'done' when g['exam_pending'] == true => (p.ok, 'автомат'),
      'done' => (p.ok, '${markWord('${g['label']}')} есть'),
      'tight' => (p.warn, 'впритык'),
      'no' => (p.danger, 'не хватит'),
      _ => (p.ok, 'дойдёшь'),
    };
    final need = (g['need'] as num?) ?? 0;
    final headline = goalHeadline(g);
    final tk = Map<String, dynamic>.from(g['tk'] ?? {});
    final marks = [for (final m in (g['marks'] as List? ?? [])) '$m'];
    if (s.fresh) return _fresh(s, status, tone, headline, tk, marks);
    final lines = <(IconData, String)>[
      if ((g['open_count'] ?? 0) > 0)
        (Icons.upload_rounded, 'работы: открыто ${g['open_count']} · до +${fmtNum(g['open_points'] ?? 0)}'),
      if ((g['attendance_left'] ?? 0) > 0)
        (Icons.groups_outlined, 'посещения лекций: до +${fmtNum(g['attendance_left'])}'),
      if ((g['exam_left'] ?? 0) > 0) (Icons.workspace_premium_outlined, 'экзамен: до +${fmtNum(g['exam_left'])}'),
      if ((tk['total'] ?? 0) > 0)
        (
          Icons.task_alt_rounded,
          'зачтено ${tk['passed']} из ${tk['total']} · нужно ${tk['need']}'
              '${(tk['left'] ?? 0) > 0 ? ' → из ${tk['open']} открытых зачесть ${tk['left']}' : ''}',
        ),
      if (mustLine(g) case final must?) (Icons.priority_high_rounded, must),
      if (need > 0 && status != 'done')
        (
          Icons.auto_awesome_outlined,
          'если сдать всё, ходить на лекции${(g['exam_left'] ?? 0) > 0 ? ' и сдать экзамен' : ''}'
              ' — до ${fmtNum(g['best'] ?? 0)}',
        ),
      if ((g['lost_count'] ?? 0) > 0)
        (
          Icons.warning_amber_rounded,
          'ниже порога или срок прошёл: ${g['lost_count']} — не считаю, пригодится, если дадут пересдать',
        ),
      if (g['skip'] is Map) _skipLine(Map<String, dynamic>.from(g['skip']), status),
    ];
    return Tile(
      radius: Radii.card,
      gradient: LinearGradient(
        begin: Alignment.topRight,
        end: Alignment.bottomLeft,
        colors: [
          tone.withValues(alpha: p.dark ? 0.28 : 0.16),
          p.cardSolid.withValues(alpha: p.dark ? 0.6 : 1),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Цель', style: s.title(20)),
              const Spacer(),
              // набрал — капибара прыгает, не хватит — грустит (17Б)
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 300),
                child: switch (status) {
                  'done' => CapyHop(key: const ValueKey('goal:joy'), size: 46, color: p.ok),
                  'no' => CapySigh(key: const ValueKey('goal:sad'), size: 46, color: p.muted),
                  _ => const SizedBox.shrink(),
                },
              ),
              const SizedBox(width: Space.s),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: tone.withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(Radii.pill),
                ),
                child: Text(
                  verdict,
                  style: s.body(13, weight: FontWeight.w700, color: tone),
                ),
              ),
            ],
          ),
          const SizedBox(height: Space.m),
          // пока экзамен впереди — маленький переключатель счёта, как вид «Недели»
          if (g['mode'] == 'auto' || g['mode'] == 'exam') ...[
            GoalModeToggle(mode: '${g['mode']}', onChanged: _setMode),
            const SizedBox(height: Space.s),
          ],
          // Выбор отметки — сегменты, выбранная залита цветом предмета
          Container(
            padding: const EdgeInsets.all(4),
            decoration: BoxDecoration(color: p.line, borderRadius: BorderRadius.circular(Radii.pill)),
            child: Row(
              children: [
                for (final m in marks)
                  Expanded(
                    child: Semantics(
                      button: true,
                      selected: m == g['label'],
                      label: 'Цель $m',
                      excludeSemantics: true,
                      child: GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTap: () => _set(m),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 240),
                          curve: Curves.easeOutCubic,
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          decoration: BoxDecoration(
                            color: m == g['label'] ? widget.color : Colors.transparent,
                            borderRadius: BorderRadius.circular(Radii.pill),
                          ),
                          alignment: Alignment.center,
                          child: Text(
                            m,
                            style: s.body(15, weight: FontWeight.w700, color: m == g['label'] ? Colors.white : p.muted),
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: Space.l),
          Text(headline, style: s.title(headline.length > 28 ? 21 : 26, color: status == 'done' ? p.ok : p.text)),
          const SizedBox(height: 4),
          Text(goalSubline(g), style: s.body(13, color: p.muted)),
          const SizedBox(height: Space.m),
          for (final (ic, text) in lines)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(ic, size: 16, color: p.muted),
                  const SizedBox(width: Space.s),
                  Expanded(child: Text(text, style: s.body(14))),
                ],
              ),
            ),
          if (status == 'no') ...[
            const SizedBox(height: Space.m),
            Text(
              tk['reachable'] == false
                  ? 'Открытых работ меньше, чем нужно зачесть. По правилам БРС так к экзамену не выйти — спроси преподавателя про пересдачу.'
                  : 'Даже если сдать всё и ходить на все лекции, будет ${fmtNum(g['best'] ?? 0)} — меньше ${fmtNum(g['at'] ?? 0)}. Можно выбрать цель ниже.',
              style: s.body(13, color: p.danger),
            ),
          ],
          // прогноз — не решение преподавателя (UX-аудит 02.11, п. 11)
          const SizedBox(height: Space.m),
          Text(goalNote, style: s.body(12, color: p.muted)),
          if (_error != null) ...[const SizedBox(height: Space.s), Text(_error!, style: s.body(13, color: p.danger))],
        ],
      ),
    );
  }

  /// Новый дизайн (макет 4, Никита 11.11): бумажная карточка с рамкой цвета
  /// прогноза, выбор отметки — капсулой справа от «Цель», прогноз начинается
  /// со слов «по текущим данным», откуда взять баллы — целыми фразами. Счёт
  /// и цели — те же, что в прежней карточке (автомат и «с экзаменом»).
  Widget _fresh(AppStyle s, String status, Color tone, String headline, Map<String, dynamic> tk, List<String> marks) {
    final p = s.p;
    final g = _g;
    final verdict = switch (status) {
      'done' when g['exam_pending'] == true => 'выходит автоматом',
      'done' => '${markWord('${g['label']}')} есть',
      'tight' => 'впритык',
      'no' => 'не хватит',
      _ => 'дойдёшь',
    };
    final skip = g['skip'] is Map ? _skipLine(Map<String, dynamic>.from(g['skip']), status).$2 : '';
    final lines = [...goalFreshLines(g), if (skip.isNotEmpty) skip[0].toUpperCase() + skip.substring(1)];
    final when = widget.updated;
    return Tile(
      key: const Key('goal:fresh'),
      radius: Radii.card,
      border: tone,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              // одна отметка (зачёт) — выбирать нечего, она просто названа
              Expanded(child: Text(marks.length > 1 ? 'Цель' : 'Цель · ${g['label']}', style: s.eyebrow())),
              if (marks.length > 1) _FreshMarks(marks: marks, label: '${g['label']}', onPick: _set),
            ],
          ),
          // пока экзамен впереди — счёт: автомат или с экзаменом
          if (g['mode'] == 'auto' || g['mode'] == 'exam') ...[
            const SizedBox(height: Space.s),
            Align(
              alignment: Alignment.centerRight,
              child: GoalModeToggle(mode: '${g['mode']}', onChanged: _setMode),
            ),
          ],
          const SizedBox(height: Space.m),
          Row(
            children: [
              Expanded(
                child: Text(
                  'По текущим данным: $verdict',
                  style: s.title(21, weight: FontWeight.w600, color: tone),
                ),
              ),
              // набрал — капибара прыгает, не хватит — грустит (17Б)
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 300),
                child: switch (status) {
                  'done' => CapyHop(key: const ValueKey('goal:joy'), size: 40, color: p.ok),
                  'no' => CapySigh(key: const ValueKey('goal:sad'), size: 40, color: p.muted),
                  _ => const SizedBox.shrink(),
                },
              ),
            ],
          ),
          const SizedBox(height: Space.xs),
          Text(headline, style: s.body(15, weight: FontWeight.w600)),
          const SizedBox(height: 2),
          Text(goalSubline(g), style: s.body(13, color: p.muted)),
          if (lines.isNotEmpty) const SizedBox(height: Space.s),
          for (final text in lines)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(text, style: s.body(14)),
            ),
          if (status == 'no') ...[
            const SizedBox(height: Space.m),
            Text(
              tk['reachable'] == false
                  ? 'Открытых работ меньше, чем нужно зачесть. По правилам БРС так к экзамену не выйти — спроси преподавателя про пересдачу.'
                  : 'Даже если сдать всё и ходить на все лекции, будет ${fmtNum(g['best'] ?? 0)} — меньше ${fmtNum(g['at'] ?? 0)}. Можно выбрать цель ниже.',
              style: s.body(13, color: p.danger),
            ),
          ],
          const SizedBox(height: Space.m),
          Text(
            when == null
                ? goalNote
                : 'Расчёт по баллам из СДО, обновлено ${updatedText(when, now())}. Оценку ставит преподаватель.',
            style: s.body(12, color: p.muted),
          ),
          if (_error != null) ...[const SizedBox(height: Space.s), Text(_error!, style: s.body(13, color: p.danger))],
        ],
      ),
    );
  }

  (IconData, String) _skipLine(Map<String, dynamic> skip, String now) {
    final day = dayMonth('${skip['date']}');
    final after = switch ('${skip['status']}') {
      _ when skip['status'] == now => 'ничего не изменится',
      'done' => 'всё равно есть',
      'tight' => 'станет впритык',
      'no' => 'уже не хватит',
      _ => 'дойдёшь',
    };
    return (Icons.schedule_rounded, 'пропущу лекцию $day: −${fmtNum(skip['value'] ?? 0)} → $after');
  }
}

/// Выбор отметки цели в новом дизайне: капсула «3 · 4 · 5», выбранная залита
/// цветом текста (как полки «Сдать»), а не цветом предмета.
class _FreshMarks extends StatelessWidget {
  final List<String> marks;
  final String label;
  final ValueChanged<String> onPick;
  const _FreshMarks({required this.marks, required this.label, required this.onPick});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: p.bg,
        borderRadius: BorderRadius.circular(Radii.pill),
        border: Border.all(color: p.line),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final m in marks)
            Semantics(
              button: true,
              selected: m == label,
              label: 'Цель $m',
              excludeSemantics: true,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => onPick(m),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 240),
                  curve: Curves.easeOutCubic,
                  constraints: const BoxConstraints(minWidth: 40, minHeight: 34),
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: m == label ? p.text : p.text.withValues(alpha: 0),
                    borderRadius: BorderRadius.circular(Radii.pill),
                  ),
                  child: Text(
                    m,
                    style: s.body(14, weight: FontWeight.w700, color: m == label ? p.bg : p.muted),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// «автомат · с экзаменом» — две подписи в капсуле, как переключатель вида
/// «Недели», только словами: значками смысл не передать.
class GoalModeToggle extends StatelessWidget {
  final String mode;
  final ValueChanged<String> onChanged;
  const GoalModeToggle({super.key, required this.mode, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    Widget seg(String value, String text) {
      final on = mode == value;
      return Semantics(
        button: true,
        selected: on,
        label: text == 'автомат' ? 'Считать автомат' : 'Считать с экзаменом',
        excludeSemantics: true,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => onChanged(value),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 240),
            curve: Curves.easeOutCubic,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: on ? p.text : p.text.withValues(alpha: 0),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              text,
              style: s.body(13, weight: FontWeight.w700, color: on ? p.bg : p.muted),
            ),
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: p.line, borderRadius: BorderRadius.circular(13)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [seg('auto', 'автомат'), const SizedBox(width: 2), seg('exam', 'с экзаменом')],
      ),
    );
  }
}

/// Посещения лекций квадратиками: был, пропуск, ждём балл, впереди.
/// С api и courseId нажатие открывает список лекций, где у лекций до начала
/// истории баллов можно отметить самому, на каких был (как в Mini App).
class AttendanceStrip extends StatefulWidget {
  final Map<String, dynamic> att;
  final Color color;
  final Api? api;
  final int? courseId;
  const AttendanceStrip({super.key, required this.att, required this.color, this.api, this.courseId});

  @override
  State<AttendanceStrip> createState() => _AttendanceStripState();
}

/// Откуда посещения (attendance.with_pulse, 01.11): из Пульса — строкой
/// сверху; Пульс отвалился — что он сказал, осталось, остальное по СДО.
String? attendanceSource(Map<String, dynamic> att) => switch (att['source']) {
  'pulse' => 'из Пульса МИРЭА',
  'pulse_lost' => 'Пульс отвалился — новые лекции считаю по СДО',
  _ => null,
};

/// Свои отметки — только у лекций до начала истории: знак «?», уже своя или
/// «Н», когда плюсики по баллам кончились (attendance.py, то же в sdo.js).
bool _lectureEditable(Map<String, dynamic> att, Map<String, dynamic> l) {
  final before = att['before'] as Map?;
  if (l['status'] == 'before' || l['manual'] == true) return true;
  if (l['status'] != 'miss' || before == null) return false;
  final anyManual = (att['lectures'] as List? ?? []).any((x) => (x as Map)['manual'] == true);
  return anyManual && '${l['date']}'.compareTo('${before['day']}') <= 0;
}

class _AttendanceStripState extends State<AttendanceStrip> {
  Future<void> _open() async {
    tick();
    await appSheet<void>(
      context,
      (ctx) => AttendanceSheet(
        api: widget.api!,
        courseId: widget.courseId!,
        att: widget.att,
        color: widget.color,
        // Лист пишет новые посещения в тот же map: карточка в ленивом
        // ListView создаётся заново из widget.att (как у GoalCard).
        onChanged: () => setState(() {}),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final att = widget.att;
    final color = widget.color;
    final lectures = [for (final l in (att['lectures'] as List? ?? [])) Map<String, dynamic>.from(l)];
    final total = att['total'] ?? lectures.length;
    final tappable = widget.api != null && widget.courseId != null && att['ok'] != false;
    final before = att['before'] as Map?;
    final toMark = lectures.any((l) => l['status'] == 'before');
    final source = attendanceSource(att);
    final more = !tappable
        ? null
        : Row(
            children: [
              Icon(toMark ? Icons.edit_rounded : Icons.list_rounded, size: 16, color: toMark ? color : p.muted),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  toMark && before != null
                      // в новом дизайне «7 сентября» не рвётся
                      ? 'отметь сам, на каких был до ${s.fresh ? dayMonth('${before['day']}').replaceAll(' ', '\u00A0') : dayMonth('${before['day']}')}'
                      : 'все лекции и отметки',
                  style: s.body(13, weight: FontWeight.w600, color: toMark ? color : p.muted),
                ),
              ),
              Icon(Icons.chevron_right_rounded, size: 18, color: p.muted),
            ],
          );
    if (s.fresh) {
      final fresh = _fresh(s, lectures, source, more);
      return tappable ? GestureDetector(behavior: HitTestBehavior.opaque, onTap: _open, child: fresh) : fresh;
    }
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (source != null) ...[
          Row(
            children: [
              Icon(
                att['source'] == 'pulse' ? Icons.verified_outlined : Icons.cloud_off_rounded,
                size: 15,
                color: att['source'] == 'pulse' ? p.ok : p.warn,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  source,
                  style: s.body(13, weight: FontWeight.w600, color: att['source'] == 'pulse' ? p.ok : p.warn),
                ),
              ),
            ],
          ),
          const SizedBox(height: Space.s),
        ],
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final l in lectures)
              Tooltip(
                message: '${l['n']} лекция · ${dayMonth('${l['date']}')}',
                child: Container(
                  width: 26,
                  height: 26,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: switch (l['status']) {
                      'ok' => color,
                      'excused' => color.withValues(alpha: 0.5),
                      'miss' => Colors.transparent,
                      _ => p.line,
                    },
                    borderRadius: BorderRadius.circular(7),
                    border: Border.all(
                      color: switch (l['status']) {
                        'miss' => p.danger,
                        'wait' => color,
                        'before' => p.muted,
                        _ => Colors.transparent,
                      },
                      width: 1.5,
                    ),
                  ),
                  child: l['status'] == 'before'
                      ? Text(
                          '?',
                          style: s.body(13, weight: FontWeight.w700, color: p.muted),
                        )
                      : null,
                ),
              ),
          ],
        ),
        const SizedBox(height: Space.s),
        Text(
          'был на ${att['attended'] ?? 0} из ${att['past'] ?? 0} прошедших · всего $total'
          '${(att['waiting'] ?? 0) > 0 ? ' · ждём балл за ${att['waiting']}' : ''}',
          style: s.body(13, color: p.muted),
        ),
        if (more != null) ...[const SizedBox(height: Space.s), more],
      ],
    );
    if (!tappable) return body;
    return GestureDetector(behavior: HitTestBehavior.opaque, onTap: _open, child: body);
  }

  /// Новый дизайн (Никита 11.11: «слишком много места занимает объяснение»):
  /// квадратики те же, «был на 3 из 6» — в заголовке раздела, а откуда отметка
  /// (по баллам СДО, отметил сам, ждём балл) — одной строкой-легендой внизу
  /// и только из тех отметок, что есть.
  Widget _fresh(AppStyle s, List<Map<String, dynamic>> lectures, String? source, Widget? more) {
    final p = s.p;
    final color = widget.color;
    String kind(Map<String, dynamic> l) => l['status'] == 'ok' && l['manual'] == true ? 'mine' : '${l['status']}';
    final kinds = {for (final l in lectures) kind(l)};
    const legend = [
      ('ok', 'был'),
      ('mine', 'отметил сам'),
      ('excused', 'уважительная'),
      ('wait', 'ждём балл'),
      ('miss', 'не был'),
      ('before', 'отметь сам'),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (source != null) ...[
          Text(
            source,
            style: s.body(13, weight: FontWeight.w600, color: widget.att['source'] == 'pulse' ? p.ok : p.warn),
          ),
          const SizedBox(height: Space.s),
        ],
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final l in lectures)
              Tooltip(
                message: '${l['n']} лекция · ${dayMonth('${l['date']}')}',
                child: _FreshBox(kind: kind(l), color: color, size: 26),
              ),
          ],
        ),
        const SizedBox(height: Space.m),
        Wrap(
          spacing: Space.m,
          runSpacing: 4,
          children: [
            for (final (k, label) in legend)
              if (kinds.contains(k))
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _FreshBox(kind: k, color: color, size: 12),
                    const SizedBox(width: 5),
                    Text(label, style: s.body(12.5, color: p.muted)),
                  ],
                ),
          ],
        ),
        if (more != null) ...[const SizedBox(height: Space.m), more],
      ],
    );
  }
}

/// Квадратик посещения нового дизайна: был — залит цветом предмета; отметил
/// сам — светлая заливка с рамкой; ждём балл — рамка «жду»; не был — красная
/// рамка; «?» — отметь сам; впереди — серый.
class _FreshBox extends StatelessWidget {
  final String kind;
  final Color color;
  final double size;
  const _FreshBox({required this.kind, required this.color, required this.size});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final (Color fill, Color edge) = switch (kind) {
      'ok' => (color, color),
      'mine' => (color.withValues(alpha: 0.3), color),
      'excused' => (color.withValues(alpha: 0.55), color.withValues(alpha: 0.55)),
      'wait' => (p.warn.withValues(alpha: 0), p.warn),
      'miss' => (p.danger.withValues(alpha: 0), p.danger),
      'before' => (p.muted.withValues(alpha: 0), p.muted),
      _ => (p.line, p.line),
    };
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(size * 0.27),
        border: Border.all(color: edge, width: size > 16 ? 1.5 : 1.2),
      ),
      child: kind == 'before' && size > 16
          ? Text(
              '?',
              style: s.body(13, weight: FontWeight.w700, color: p.muted),
            )
          : null,
    );
  }
}

/// Лист «Посещения»: все лекции семестра, у лекций до начала истории —
/// своя отметка нажатием: «?» → «+» (если плюсики по баллам остались) →
/// «У» (если есть уважительные) → снять. Сервер проверяет то же
/// (POST /api/sdo/attendance/<курс>, attendance.check_mark).
class AttendanceSheet extends StatefulWidget {
  final Api api;
  final int courseId;
  final Map<String, dynamic> att;
  final Color color;
  final VoidCallback onChanged;
  const AttendanceSheet({
    super.key,
    required this.api,
    required this.courseId,
    required this.att,
    required this.color,
    required this.onChanged,
  });

  @override
  State<AttendanceSheet> createState() => _AttendanceSheetState();
}

class _AttendanceSheetState extends State<AttendanceSheet> {
  String? _busy;

  Future<void> _tap(Map<String, dynamic> l) async {
    final a = widget.att;
    final b = Map<String, dynamic>.from(a['before'] as Map? ?? {});
    final leftOk = (b['left_ok'] as num?) ?? 0, leftEx = (b['left_excused'] as num?) ?? 0;
    final String? next;
    if (l['manual'] == true && l['status'] == 'ok') {
      next = ((b['excused'] as num?) ?? 0) > 0 && leftEx > 0 ? 'excused' : null;
    } else if (l['manual'] == true) {
      next = null;
    } else if (leftOk > 0) {
      next = 'ok';
    } else if (leftEx > 0) {
      next = 'excused';
    } else {
      showToast(context, 'По баллам посещено ${b['attended'] ?? 0} — сначала сними плюсик с другой лекции');
      return;
    }
    tick();
    setState(() => _busy = '${l['date']}');
    try {
      final r = await widget.api.post('/sdo/attendance/${widget.courseId}', {'day': l['date'], 'mark': next});
      HapticFeedback.lightImpact();
      widget.att
        ..clear()
        ..addAll(Map<String, dynamic>.from(r));
      widget.onChanged();
    } on ApiError catch (e) {
      if (mounted) showToast(context, e.message, kind: ToastKind.error);
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final a = widget.att;
    final color = widget.color;
    final lectures = [for (final l in (a['lectures'] as List? ?? [])) Map<String, dynamic>.from(l)];
    final b = a['before'] as Map?;
    final unit = (a['unit'] as num?) ?? 0;
    String hint;
    if (a['source'] == 'pulse') {
      hint = 'Отметки — из Пульса МИРЭА, как их поставил преподаватель или QR. Сам их не меняешь: что в Пульсе, то и здесь.';
    } else if (b == null) {
      hint = a['source'] == 'pulse_lost'
          ? 'Что Пульс уже сказал, осталось. Новые лекции бот отмечает по баллам за посещаемость в СДО.'
          : 'Бот отмечает лекции сам — по баллам за посещаемость в СДО.';
    } else {
      final open = ((b['left_ok'] as num?) ?? 0) > 0 || ((b['left_excused'] as num?) ?? 0) > 0;
      hint =
          'До ${dayMonth('${b['day']}')} бот баллы не записывал: из ${b['past']} лекций по баллам посещено '
          '${b['attended']}${((b['excused'] as num?) ?? 0) > 0 ? ', по уважительной ${b['excused']}' : ''}. '
          '${open ? 'Нажми на лекцию со знаком «?», на которой был: осталось +${b['left_ok']}'
                    '${((b['left_excused'] as num?) ?? 0) > 0 ? ' и У ${b['left_excused']}' : ''}.' : 'Всё отмечено, на остальных — «Н». Нажми на свою отметку, чтобы снять.'}';
    }
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.85),
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
          children: [
            Text('Посещения', style: s.title(24)),
            const SizedBox(height: Space.s),
            Text(
              'был на ${a['attended'] ?? 0} из ${a['past'] ?? 0} · баллы ${fmtNum((a['score'] as num?) ?? 0)} из ${fmtNum((a['max'] as num?) ?? 0)}'
              '${unit > 0 ? ' · ${fmtNum(unit)} за лекцию' : ''}',
              style: s.body(15, weight: FontWeight.w600),
            ),
            const SizedBox(height: Space.s),
            Text(hint, style: s.body(14, color: p.muted)),
            // посещения не из Пульса — предложить его (18.11: Пульс для всех)
            if (a['source'] != 'pulse' && pulseOpenNow.value) ...[
              const SizedBox(height: Space.m),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  key: const Key('att:pulse'),
                  style: TextButton.styleFrom(
                    foregroundColor: p.accent,
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                    shape: StadiumBorder(side: BorderSide(color: p.edge)),
                  ),
                  icon: const Icon(Icons.verified_outlined, size: 17),
                  label: Text(
                    a['source'] == 'pulse_lost' ? 'Войти в Пульс заново' : 'Брать посещения из Пульса',
                    style: s.body(13.5, weight: FontWeight.w600),
                  ),
                  onPressed: () async {
                    tick();
                    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => PulseScreen(api: widget.api)));
                    widget.onChanged();
                  },
                ),
              ),
            ],
            const SizedBox(height: Space.m),
            for (final l in lectures) _row(s, p, color, unit, l),
          ],
        ),
      ),
    );
  }

  Widget _row(AppStyle s, Palette p, Color color, num unit, Map<String, dynamic> l) {
    final status = '${l['status']}';
    final editable = _lectureEditable(widget.att, l);
    final (String sign, String label, Color tone) = switch (status) {
      'ok' => ('+', 'был', color),
      'excused' => ('У', 'уважительная причина', p.warn),
      'miss' => ('Н', 'не был', p.danger),
      'wait' => ('', 'ждём отметку', color),
      'before' => ('?', 'отметь сам', p.muted),
      _ => ('', 'впереди', p.muted),
    };
    final busy = _busy == '${l['date']}';
    return InkWell(
      onTap: editable && _busy == null ? () => _tap(l) : null,
      borderRadius: BorderRadius.circular(Radii.chip),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: tone.withValues(alpha: status == 'future' ? 0.08 : 0.16),
                borderRadius: BorderRadius.circular(9),
                border: editable ? Border.all(color: tone, width: 1.5) : null,
              ),
              child: busy
                  ? SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: tone))
                  : status == 'wait'
                  ? Icon(Icons.schedule_rounded, size: 16, color: tone)
                  : Text(
                      sign,
                      style: s.body(15, weight: FontWeight.w800, color: tone),
                    ),
            ),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Лекция ${l['n']}', style: s.body(15, weight: FontWeight.w600)),
                  Text(
                    '${dayMonth('${l['date']}')} · $label${l['manual'] == true ? ' · твоя отметка' : ''}',
                    style: s.body(13, color: p.muted),
                  ),
                ],
              ),
            ),
            if (status == 'ok' && unit > 0)
              Text(
                '+${fmtNum(unit)}',
                style: s.body(14, weight: FontWeight.w700, color: color),
              ),
          ],
        ),
      ),
    );
  }
}

/// Как росли баллы: линия по дням и «+8 за неделю».
class HistoryChart extends StatelessWidget {
  final Map<String, dynamic> history;
  final Color color;
  const HistoryChart({super.key, required this.history, required this.color});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final pts = [
      for (final x in (history['points'] as List? ?? []))
        (DateTime.parse('${x[0]}'), ((x as List)[1] as num).toDouble()),
    ];
    final delta = history['week_delta'] as num?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (delta != null)
          Text(
            '${delta > 0 ? '+' : ''}${fmtNum(delta)} за неделю',
            style: s.body(14, weight: FontWeight.w700, color: delta > 0 ? p.ok : p.muted),
          ),
        const SizedBox(height: Space.s),
        if (pts.length < 2)
          Text(
            'График появится, когда наберётся история: бот запоминает сумму раз в день, когда ты смотришь баллы.',
            style: s.body(13, color: p.muted),
          )
        else
          SizedBox(
            height: 90,
            width: double.infinity,
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: 1),
              duration: const Duration(milliseconds: 900),
              curve: Curves.easeOutCubic,
              builder: (context, k, _) => CustomPaint(painter: _Line(pts, color, p.line, k)),
            ),
          ),
      ],
    );
  }
}

class _Line extends CustomPainter {
  final List<(DateTime, double)> pts;
  final Color c, grid;
  final double k;
  _Line(this.pts, this.c, this.grid, this.k);

  @override
  void paint(Canvas canvas, Size size) {
    final t0 = pts.first.$1.millisecondsSinceEpoch.toDouble();
    final t1 = pts.last.$1.millisecondsSinceEpoch.toDouble();
    final lo = pts.map((e) => e.$2).reduce(math.min), hi = pts.map((e) => e.$2).reduce(math.max);
    final span = hi - lo == 0 ? 1 : hi - lo;
    Offset at((DateTime, double) e) => Offset(
      t1 == t0 ? size.width : (e.$1.millisecondsSinceEpoch - t0) / (t1 - t0) * size.width,
      size.height - 6 - (e.$2 - lo) / span * (size.height - 12),
    );
    canvas.drawLine(Offset(0, size.height - 1), Offset(size.width, size.height - 1), Paint()..color = grid);
    final path = Path()..moveTo(at(pts.first).dx, at(pts.first).dy);
    for (final e in pts.skip(1)) {
      path.lineTo(at(e).dx, at(e).dy);
    }
    canvas.save();
    canvas.clipRect(Rect.fromLTWH(0, 0, size.width * k, size.height));
    final fill = Path.from(path)
      ..lineTo(at(pts.last).dx, size.height)
      ..lineTo(at(pts.first).dx, size.height)
      ..close();
    canvas.drawPath(
      fill,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [c.withValues(alpha: 0.3), c.withValues(alpha: 0)],
        ).createShader(Offset.zero & size),
    );
    canvas.drawPath(
      path,
      Paint()
        ..color = c
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5
        ..strokeJoin = StrokeJoin.round,
    );
    canvas.restore();
    if (k >= 1) canvas.drawCircle(at(pts.last), 4.5, Paint()..color = c);
  }

  @override
  bool shouldRepaint(_Line old) => old.k != k || old.c != c;
}

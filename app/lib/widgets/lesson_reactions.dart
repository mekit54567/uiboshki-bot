// Реакции на пару (5.100, Никита 18.10): пять поз капибары, счёт видит
// своя группа, кто как отметил — никто. Отметить — когда пара началась и
// две недели после; до начала блока нет. Нажал свою ещё раз — снял.
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'capy.dart';
import 'common.dart';

/// Порядок и id — как в lesson_reactions.KINDS на сервере.
const lessonReactions = [
  ('joy', CapyPose.joy, 'Класс'),
  ('calm', CapyPose.morning, 'Норм'),
  ('hard', CapyPose.sad, 'Сложно'),
  ('sleep', CapyPose.night, 'Скучно'),
  ('angry', CapyPose.angry, 'Злой препод'), // 5.100.6
];

class LessonReactions extends StatefulWidget {
  final Api api;
  final Lesson lesson;
  const LessonReactions({super.key, required this.api, required this.lesson});

  @override
  State<LessonReactions> createState() => _LessonReactionsState();
}

class _LessonReactionsState extends State<LessonReactions> {
  Map<String, int> _counts = {};
  String? _mine;
  bool _open = false, _loaded = false, _busy = false;

  String get _start => widget.lesson.startAt!.toUtc().toIso8601String();

  @override
  void initState() {
    super.initState();
    if (widget.lesson.startAt != null) _load();
  }

  void _take(Map j) {
    _counts = {for (final e in (j['counts'] as Map? ?? const {}).entries) '${e.key}': (e.value as num).toInt()};
    _mine = j['mine'] as String?;
    _open = j['open'] == true;
  }

  Future<void> _load() async {
    try {
      final q = Uri(queryParameters: {'start': _start, 'title': widget.lesson.title}).query;
      final j = await widget.api.get('/lesson/reactions?$q');
      if (!mounted) return;
      setState(() {
        _take(j as Map);
        _loaded = true;
      });
    } catch (_) {} // нет связи или не своя группа — экран просто без блока
  }

  Future<void> _tap(String kind) async {
    if (_busy) return;
    tick();
    final was = (Map.of(_counts), _mine);
    final next = _mine == kind ? null : kind;
    setState(() {
      // сразу на экране, ответ сервера потом поправит
      if (_mine != null) _counts[_mine!] = ((_counts[_mine!] ?? 1) - 1).clamp(0, 1 << 30);
      if (next != null) _counts[next] = (_counts[next] ?? 0) + 1;
      _mine = next;
      _busy = true;
    });
    final toast = Overlay.of(context, rootOverlay: true);
    try {
      final j = await widget.api.post('/lesson/reactions', {
        'start': _start,
        'title': widget.lesson.title,
        'kind': next ?? '',
      });
      if (mounted) setState(() => _take(j as Map));
    } catch (_) {
      if (mounted) {
        setState(() {
          _counts = was.$1;
          _mine = was.$2;
        });
      }
      toastOn(toast, 'Не отметилось, попробуй ещё раз', kind: ToastKind.error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final total = _counts.values.fold(0, (a, b) => a + b);
    if (!_loaded || (!_open && total == 0)) return const SizedBox.shrink();
    final s = AppStyle.of(context);
    final p = s.p;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Section('Как пара'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l),
          child: Tile(
            padding: const EdgeInsets.all(Space.s),
            child: Column(
              children: [
                Row(
                  children: [
                    for (final (id, pose, label) in lessonReactions)
                      Expanded(
                        child: _Choice(
                          key: ValueKey('reaction-$id'),
                          pose: pose,
                          label: label,
                          count: _counts[id] ?? 0,
                          on: _mine == id,
                          onTap: _open ? () => _tap(id) : null,
                        ),
                      ),
                  ],
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(Space.s, Space.xs, Space.s, Space.xs),
                  child: Text(
                    _open ? 'Видит только твоя группа, без имён' : 'Отметить можно две недели после пары',
                    style: s.body(12, color: p.muted),
                    textAlign: TextAlign.center,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _Choice extends StatelessWidget {
  final CapyPose pose;
  final String label;
  final int count;
  final bool on;
  final VoidCallback? onTap;
  const _Choice({
    super.key,
    required this.pose,
    required this.label,
    required this.count,
    required this.on,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final ink = on ? p.accent : p.text;
    return Semantics(
      button: onTap != null,
      selected: on,
      label: '$label, $count',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(Radii.tile - 4),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(vertical: Space.s),
          decoration: BoxDecoration(
            color: on ? p.accent.withValues(alpha: 0.14) : p.accent.withValues(alpha: 0),
            borderRadius: BorderRadius.circular(Radii.tile - 4),
          ),
          child: ExcludeSemantics(
            child: Column(
              children: [
                CapyImage(pose: pose, size: 44, color: ink),
                const SizedBox(height: Space.xs),
                // пять в ряд: длинная подпись («Злой препод») — мельче, не в две строки
                FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    label,
                    maxLines: 1,
                    style: s.body(12, weight: on ? FontWeight.w700 : FontWeight.w500, color: ink),
                  ),
                ),
                Text(
                  count > 0 ? '$count' : ' ',
                  style: s.body(13, weight: FontWeight.w700, color: on ? ink : p.muted),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

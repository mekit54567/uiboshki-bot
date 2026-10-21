// Оценка преподавателя в капибарах (Никита 19.10, вариант А): под именем —
// ряд из пяти капибар, как звёзды («4,5 · 12 оценок»); нажал — лист: тапаешь
// по капибарам, под ними капибара-эмоция и подпись. Только цифра, без отзывов
// (правило Apple 1.2); среднее — от трёх оценок (teacher_rating.py на сервере).
// Иконки — assets/rating/ (силуэты-маски, цвет даёт тема).
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart' show plural;
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'common.dart';

/// Подпись к оценке — настроение капибары-эмоции.
const ratingMoods = ['злюсь', 'грустно', 'нормально', 'довольна', 'в восторге'];
const _emotions = ['emotion_1_angry', 'emotion_2_sad', 'emotion_3_calm', 'emotion_4_pleased', 'emotion_5_delighted'];

class RatingCapy extends StatelessWidget {
  final String name;
  final double size;
  final Color color;
  const RatingCapy(this.name, {super.key, required this.size, required this.color});

  @override
  Widget build(BuildContext context) => Image.asset(
    'assets/rating/$name.png',
    width: size,
    height: size * 0.95,
    fit: BoxFit.contain,
    color: color,
    colorBlendMode: BlendMode.srcIn,
    excludeFromSemantics: true,
  );
}

/// Пять капибар для среднего: целая, половинка, пустая.
class RatingRow extends StatelessWidget {
  final double value;
  final double size;
  final Color color;
  const RatingRow({super.key, required this.value, this.size = 18, required this.color});

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      for (var i = 1; i <= 5; i++)
        Padding(
          padding: const EdgeInsets.only(right: 2),
          child: RatingCapy(
            value >= i - 0.25
                ? 'rating_full'
                : value >= i - 0.75
                ? 'rating_half'
                : 'rating_empty',
            size: size,
            color: color,
          ),
        ),
    ],
  );
}

String _num(double v) => v.toStringAsFixed(1).replaceAll('.', ',');

/// Строка с капибарами под именем преподавателя (экран пары). Сервер не
/// ответил или оценивать нельзя и оценок мало — строки нет.
class TeacherRatingLine extends StatefulWidget {
  final Api api;
  final String name;
  const TeacherRatingLine({super.key, required this.api, required this.name});

  @override
  State<TeacherRatingLine> createState() => _TeacherRatingLineState();
}

class _TeacherRatingLineState extends State<TeacherRatingLine> {
  Map<String, dynamic>? _r;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final j = await widget.api.get('/teacher/rating?${Uri(queryParameters: {'name': widget.name}).query}');
      if (mounted) setState(() => _r = Map<String, dynamic>.from(j as Map));
    } catch (_) {}
  }

  Future<void> _rate() async {
    tick();
    final r = await appSheet<Map<String, dynamic>>(
      context,
      (_) => RateSheet(api: widget.api, name: widget.name, mine: _r?['mine'] as int?),
    );
    if (r != null && mounted) setState(() => _r = r);
  }

  @override
  Widget build(BuildContext context) {
    final r = _r;
    if (r == null) return const SizedBox.shrink();
    final s = AppStyle.of(context);
    final p = s.p;
    final avg = (r['avg'] as num?)?.toDouble();
    final n = (r['count'] as num? ?? 0).toInt();
    final mine = r['mine'] as int?;
    final can = r['can_rate'] == true;
    if (avg == null && !can) return const SizedBox.shrink();
    final note = avg != null
        ? '${_num(avg)} · $n ${plural(n, 'оценка', 'оценки', 'оценок')}'
        : mine != null
        ? 'твоя — $mine · среднее покажем от ${r['show_min'] ?? 3} оценок'
        : 'пока без оценок';
    // Кнопкой во всю строку, а не мелкими капибарами: в них было не попасть
    // (Никита 21.10: «сам первые разы не понимал, как на это попасть»)
    final action = !can ? null : (mine != null ? 'Изменить' : 'Оценить');
    return Semantics(
      button: can,
      label: 'Оценка преподавателя: $note',
      child: Padding(
        padding: const EdgeInsets.only(top: Space.s),
        child: Material(
          color: can ? p.accent.withValues(alpha: 0.12) : Colors.transparent,
          borderRadius: BorderRadius.circular(Radii.chip),
          child: InkWell(
            key: const Key('teacher:rating'),
            onTap: can ? _rate : null,
            borderRadius: BorderRadius.circular(Radii.chip),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 44),
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: can ? Space.m : 0, vertical: 6),
                child: ExcludeSemantics(
                  child: Row(
                    children: [
                      RatingRow(
                        value: avg ?? (mine ?? 0).toDouble(),
                        color: avg == null && mine == null ? p.muted : p.text,
                      ),
                      const SizedBox(width: Space.s),
                      Expanded(
                        child: Text(
                          note,
                          style: s.body(13, color: p.muted, weight: avg != null ? FontWeight.w600 : FontWeight.w400),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (action != null) ...[
                        const SizedBox(width: Space.s),
                        Text(
                          action,
                          style: s.body(14, color: p.accent, weight: FontWeight.w600),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Лист оценки: пять капибар, капибара-эмоция и «N из 5»; «Готово» — сохранить.
/// → ответ сервера (новое среднее) или null, если закрыл.
class RateSheet extends StatefulWidget {
  final Api api;
  final String name;
  final int? mine;
  const RateSheet({super.key, required this.api, required this.name, this.mine});

  @override
  State<RateSheet> createState() => _RateSheetState();
}

class _RateSheetState extends State<RateSheet> {
  late int _score = widget.mine ?? 0;
  bool _busy = false;

  Future<void> _send(int score) async {
    if (_busy) return;
    setState(() => _busy = true);
    final toast = Overlay.of(context, rootOverlay: true);
    try {
      final j = await widget.api.post('/teacher/rating', {'name': widget.name, 'score': score});
      if (mounted) Navigator.pop(context, Map<String, dynamic>.from(j as Map));
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
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Как тебе ${widget.name}?', style: s.title(24)),
            const SizedBox(height: Space.xs),
            Text('Только цифра, без отзывов. Видно среднее всех оценок — от трёх', style: s.body(14, color: p.muted)),
            const SizedBox(height: Space.l),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                for (var i = 1; i <= 5; i++)
                  Semantics(
                    button: true,
                    selected: _score == i,
                    label: '$i из 5',
                    child: GestureDetector(
                      key: Key('rate:$i'),
                      behavior: HitTestBehavior.opaque,
                      onTap: () {
                        tick();
                        setState(() => _score = i);
                      },
                      child: AnimatedScale(
                        scale: _score == i ? 1.12 : 1,
                        duration: const Duration(milliseconds: 160),
                        child: RatingCapy(
                          i <= _score ? 'rating_full' : 'rating_empty',
                          size: 54,
                          color: i <= _score ? p.accent : p.muted,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: Space.l),
            SizedBox(
              height: 80,
              child: _score == 0
                  ? Center(
                      child: Text('Нажми на капибару', style: s.body(15, color: p.muted)),
                    )
                  : Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        AnimatedSwitcher(
                          duration: const Duration(milliseconds: 200),
                          child: RatingCapy(_emotions[_score - 1], key: ValueKey(_score), size: 72, color: p.accent),
                        ),
                        const SizedBox(width: Space.m),
                        Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('$_score из 5', style: s.title(30)),
                            Text(ratingMoods[_score - 1], style: s.body(14, color: p.muted)),
                          ],
                        ),
                      ],
                    ),
            ),
            const SizedBox(height: Space.l),
            FilledButton(
              key: const Key('rate:done'),
              style: FilledButton.styleFrom(
                backgroundColor: p.accent,
                foregroundColor: p.onAccent,
                minimumSize: const Size.fromHeight(52),
                shape: const StadiumBorder(),
              ),
              onPressed: _score == 0 || _busy ? null : () => _send(_score),
              child: Text(
                'Готово',
                style: s.body(16, weight: FontWeight.w600, color: p.onAccent),
              ),
            ),
            if (widget.mine != null)
              TextButton(
                key: const Key('rate:clear'),
                onPressed: _busy ? null : () => _send(0),
                child: Text(
                  'Убрать мою оценку',
                  style: s.body(15, weight: FontWeight.w600, color: p.accent),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

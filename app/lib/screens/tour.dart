// Знакомство при первом запуске (владелец, 09.10, 2.8): пять коротких шагов
// поверх самих экранов — вкладка под шагом открывается, меню-капсула
// подсвечена, остальное притушено. «Дальше» / «Пропустить»; повторить —
// «Ещё → Как пользоваться». В «Новом» последний шаг — «Каким сделать меню»
// (шаг 8, Никита 11.11): «Коротко» или «С подписями», образцы настоящие, а
// подсвеченное меню внизу меняется сразу. По умолчанию «Коротко», как было.
import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../theme/look.dart';
import '../theme/tokens.dart';
import '../widgets/capsule_tabbar.dart';
import '../widgets/common.dart';
import 'shell.dart' show tabs;

class TourStep {
  final IconData icon;
  final String title, text;

  /// Какая вкладка открыта под шагом (shell.dart, tabs).
  final int tab;
  const TourStep(this.icon, this.title, this.text, this.tab);
}

const tourSteps = [
  TourStep(
    Icons.space_dashboard_outlined,
    'Что где',
    'Сегодня — пары и что дальше. Неделя — всё расписание. Сдать — сроки и заметки. '
        'Учёба — баллы и цели. Ещё — настройки.',
    0,
  ),
  TourStep(
    Icons.swipe_rounded,
    'Листай недели',
    'Проведи по неделе влево или вправо — откроется соседняя. Нажми на день сверху — лента приедет к нему.',
    1,
  ),
  TourStep(
    Icons.task_alt_rounded,
    'Сдал — смахни вправо',
    'Смахни срок вправо — он отметится «Сдано». Нажми на срок — сдать файлом, напомнить или изменить.',
    2,
  ),
  TourStep(
    Icons.touch_app_outlined,
    'Нажми на пару',
    'Откроется карточка пары: кабинет и корпус, преподаватель, файлы и баллы по предмету.',
    0,
  ),
  TourStep(
    Icons.flag_outlined,
    'Цель по предмету',
    'Открой предмет и выбери оценку — капибара посчитает, сколько баллов и работ не хватает.',
    3,
  ),
];

/// Последний шаг в «Новом»: каким сделать меню внизу.
const tourMenuStep = TourStep(Icons.view_week_outlined, 'Каким сделать меню', '', 0);

/// Показать тур. onStep — открыть вкладку шага; barRect — где меню-капсула
/// (подсветить), null — без подсветки; onLook — сменить вид (шаг про меню).
Future<void> showTour(
  BuildContext context, {
  required ValueChanged<int> onStep,
  Rect? Function()? barRect,
  ValueChanged<Look>? onLook,
}) => showGeneralDialog<void>(
  context: context,
  barrierDismissible: false,
  barrierColor: Colors.transparent,
  transitionDuration: const Duration(milliseconds: 260),
  pageBuilder: (context, appear, _) => FadeTransition(
    opacity: appear,
    child: TourOverlay(onStep: onStep, barRect: barRect, onLook: onLook),
  ),
);

class TourOverlay extends StatefulWidget {
  final ValueChanged<int> onStep;
  final Rect? Function()? barRect;
  final ValueChanged<Look>? onLook;
  const TourOverlay({super.key, required this.onStep, this.barRect, this.onLook});

  @override
  State<TourOverlay> createState() => _TourOverlayState();
}

class _TourOverlayState extends State<TourOverlay> {
  int _i = 0;

  /// Шаг про меню — в «Новом», решается один раз на весь тур.
  bool? _menu;
  List<TourStep> get _steps => [...tourSteps, if (_menu ?? false) tourMenuStep];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _menu ??= widget.onLook != null && AppStyle.of(context).fresh;
  }

  void _next() {
    tick();
    if (_i + 1 >= _steps.length) return _close();
    setState(() => _i++);
    widget.onStep(_steps[_i].tab);
  }

  void _close() {
    widget.onStep(0);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final steps = _steps;
    final step = steps[_i];
    final last = _i == steps.length - 1;
    final menu = identical(step, tourMenuStep);
    final mq = MediaQuery.of(context);
    final hole = widget.barRect?.call();
    // карточка — над капсулой (её и подсвечиваем), а без неё — у нижнего края
    final bottom = hole != null ? mq.size.height - hole.top + Space.l : mq.viewPadding.bottom + Space.l;
    return Material(
      type: MaterialType.transparency,
      child: Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(
              painter: _Dim(color: Colors.black.withValues(alpha: 0.55), hole: hole),
            ),
          ),
          Positioned(
            left: Space.l,
            right: Space.l,
            bottom: bottom,
            top: mq.viewPadding.top + Space.l,
            child: Align(
              alignment: Alignment.bottomCenter,
              child: SingleChildScrollView(
                reverse: true,
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 220),
                  transitionBuilder: (child, a) => FadeTransition(
                    opacity: a,
                    child: SlideTransition(
                      position: Tween(begin: const Offset(0.06, 0), end: Offset.zero).animate(a),
                      child: child,
                    ),
                  ),
                  child: Container(
                    key: ValueKey('tour:$_i'),
                    padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, Space.m),
                    decoration: BoxDecoration(
                      color: p.cardSolid,
                      borderRadius: BorderRadius.circular(Radii.card),
                      border: Border.all(color: p.line),
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              width: 44,
                              height: 44,
                              decoration: BoxDecoration(
                                color: p.accent.withValues(alpha: 0.16),
                                borderRadius: BorderRadius.circular(14),
                              ),
                              child: Icon(step.icon, color: p.accent),
                            ),
                            const Spacer(),
                            // шаги точками: где ты сейчас
                            for (var k = 0; k < steps.length; k++)
                              AnimatedContainer(
                                duration: const Duration(milliseconds: 220),
                                margin: const EdgeInsets.only(left: 5),
                                width: k == _i ? 18 : 6,
                                height: 6,
                                decoration: BoxDecoration(
                                  color: k == _i ? p.accent : p.line,
                                  borderRadius: BorderRadius.circular(3),
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: Space.m),
                        Text(step.title, style: s.title(26)),
                        if (menu)
                          _MenuChoice(
                            labels: s.look.tabLabels,
                            onPick: (v) {
                              if (v == s.look.tabLabels) return;
                              tick();
                              widget.onLook?.call(s.look.copyWith(tabLabels: v));
                            },
                          )
                        else ...[
                          const SizedBox(height: Space.s),
                          Text(step.text, style: s.body(15, color: p.muted)),
                        ],
                        const SizedBox(height: Space.m),
                        // узкий экран и крупный шрифт — надписи чуть мельче, а не за край
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            if (!last)
                              Flexible(
                                child: TextButton(
                                  onPressed: _close,
                                  child: FittedBox(
                                    fit: BoxFit.scaleDown,
                                    child: Text(
                                      'Пропустить',
                                      style: s.body(15, weight: FontWeight.w600, color: p.muted),
                                    ),
                                  ),
                                ),
                              ),
                            const SizedBox(width: Space.s),
                            Flexible(
                              child: FilledButton(
                                style: FilledButton.styleFrom(
                                  backgroundColor: p.accent,
                                  foregroundColor: p.onAccent,
                                  shape: const StadiumBorder(),
                                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                                ),
                                onPressed: _next,
                                child: FittedBox(
                                  fit: BoxFit.scaleDown,
                                  child: Text(menu ? 'Готово' : (last ? 'Понятно' : 'Дальше')),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// «Коротко» / «С подписями»: две карточки с настоящими образцами меню.
class _MenuChoice extends StatelessWidget {
  final bool labels;
  final ValueChanged<bool> onPick;
  const _MenuChoice({required this.labels, required this.onPick});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    Widget option(bool v, String title, String sub) {
      final on = v == labels;
      return Semantics(
        button: true,
        selected: on,
        child: GestureDetector(
          key: Key('tour:menu:${v ? 'labels' : 'short'}'),
          behavior: HitTestBehavior.opaque,
          onTap: () => onPick(v),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            // рамка выбранной толще на 1 — отступ меньше на 1, текст не прыгает
            padding: EdgeInsets.all(Space.m - (on ? 1 : 0)),
            decoration: BoxDecoration(
              color: p.card,
              borderRadius: BorderRadius.circular(Radii.tile),
              border: Border.all(color: on ? p.accent : p.line, width: on ? 2 : 1),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(title, style: s.body(15, weight: FontWeight.w700)),
                          Text(sub, style: s.body(13, color: p.muted)),
                        ],
                      ),
                    ),
                    Icon(
                      on ? Icons.check_circle_rounded : Icons.radio_button_unchecked_rounded,
                      color: on ? p.accent : p.muted,
                    ),
                  ],
                ),
                const SizedBox(height: Space.s),
                CapsuleTabBar.sample(items: tabs, index: 0, labels: v),
              ],
            ),
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(top: Space.m),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          option(false, 'Коротко', 'Подпись только у открытой вкладки'),
          const SizedBox(height: Space.s),
          option(true, 'С подписями', 'Каждая вкладка подписана'),
          const SizedBox(height: Space.m),
          Text('Поменять можно в любой момент: «Ещё», «Оформление».', style: s.body(13, color: p.muted)),
        ],
      ),
    );
  }
}

/// Притушенный экран с окном-подсветкой (скруглённым, как капсула).
class _Dim extends CustomPainter {
  final Color color;
  final Rect? hole;
  const _Dim({required this.color, this.hole});

  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()..addRect(Offset.zero & size);
    if (hole != null) {
      path
        ..addRRect(RRect.fromRectAndRadius(hole!.inflate(4), const Radius.circular(Radii.tabbar + 4)))
        ..fillType = PathFillType.evenOdd;
    }
    canvas.drawPath(path, Paint()..color = color);
  }

  @override
  bool shouldRepaint(_Dim old) => old.color != color || old.hole != hole;
}

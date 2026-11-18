// Нижнее меню «капсула»: выбранная вкладка — пилюля с подписью, остальные —
// только значки. Пилюля плавно перетекает, касание — лёгкий отклик.
// В длинном списке (новый дизайн) капсула уезжает вниз, пока читаешь дальше
// ([hidden], решает shell.dart). «С подписями» ([labels], Н1, шаг 8) —
// подписана каждая вкладка, все одной ширины, ничего не прыгает.
import 'dart:ui';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'common.dart';

class TabItem {
  final IconData icon;
  final String label;
  const TabItem(this.icon, this.label);
}

class CapsuleTabBar extends StatelessWidget {
  final List<TabItem> items;
  final int index;
  final ValueChanged<int> onTap;

  /// Спрятана под край экрана. Место под ней в вёрстке остаётся: конец
  /// списка и плашки не прыгают.
  final bool hidden;

  /// Подписи у всех вкладок, а не только у открытой (Look.tabLabels).
  final bool labels;
  const CapsuleTabBar({
    super.key,
    required this.items,
    required this.index,
    required this.onTap,
    this.hidden = false,
    this.labels = false,
  });

  /// Образец меню — в выборе «Коротко / С подписями» (знакомство): та же
  /// капсула, без нажатий и размытия. Уже настоящей — уменьшенной копией
  /// во всю ширину экрана, а не сжатой: иначе подписи упираются в пилюлю.
  static Widget sample({Key? key, required List<TabItem> items, required int index, required bool labels}) =>
      IgnorePointer(
        key: key,
        child: ExcludeSemantics(
          child: LayoutBuilder(
            builder: (context, box) {
              final real = MediaQuery.sizeOf(context).width - 2 * Space.l;
              final bar = ClipRRect(
                borderRadius: BorderRadius.circular(Radii.tabbar),
                child: _row(context, items, index, labels, (_) {}),
              );
              if (real <= box.maxWidth) return bar;
              return FittedBox(
                fit: BoxFit.scaleDown,
                child: SizedBox(width: real, child: bar),
              );
            },
          ),
        ),
      );

  static Widget _row(BuildContext context, List<TabItem> items, int index, bool labels, ValueChanged<int> onTap) {
    final p = AppStyle.of(context).p;
    return Container(
      height: 64,
      padding: const EdgeInsets.all(7),
      decoration: BoxDecoration(
        color: kIsWeb ? Color.alphaBlend(p.tabbar, p.bg) : p.tabbar,
        borderRadius: BorderRadius.circular(Radii.tabbar),
        border: Border.all(color: p.line),
      ),
      child: Row(
        children: [
          for (var i = 0; i < items.length; i++)
            labels
                ? _LabeledSlot(
                    item: items[i],
                    selected: i == index,
                    onTap: () {
                      if (i != index) tick();
                      onTap(i);
                    },
                  )
                : _Slot(
                    item: items[i],
                    selected: i == index,
                    onTap: () {
                      if (i != index) tick();
                      onTap(i);
                    },
                  ),
        ],
      ),
    );
  }

  /// Сколько едет капсула: motion.sheet_ms из design/tokens.json.
  static const slide = Duration(milliseconds: 280);

  @override
  Widget build(BuildContext context) {
    final still = MediaQuery.disableAnimationsOf(context);
    return AnimatedSlide(
      offset: hidden ? const Offset(0, 1) : Offset.zero,
      duration: still ? Duration.zero : slide,
      curve: hidden ? Curves.easeInCubic : Curves.easeOutCubic,
      child: _bar(context),
    );
  }

  Widget _bar(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    // мягкий градиент под капсулой (14.10, совет Gemini): строки списка уходят
    // под меню, а не обрезаются пополам. Рисуется и выше полосы меню, касания
    // пропускает
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned(
          left: 0,
          right: 0,
          top: -28,
          bottom: 0,
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [p.bg.withValues(alpha: 0), p.bg.withValues(alpha: 0.85)],
                  stops: const [0, 0.55],
                ),
              ),
            ),
          ),
        ),
        _capsule(context),
      ],
    );
  }

  Widget _capsule(BuildContext context) {
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.only(bottom: Space.m),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(Radii.tabbar),
          // В браузере (PWA) размытие под меню перерисовывается каждый кадр и
          // тормозит (Никита 15.10: «ПВА стала лаганной») — там меню плотное,
          // того же цвета, что размытое поверх фона.
          child: _Blur(child: _row(context, items, index, labels, onTap)),
        ),
      ),
    );
  }
}

class _Slot extends StatelessWidget {
  final TabItem item;
  final bool selected;
  final VoidCallback onTap;
  const _Slot({required this.item, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    const dur = Duration(milliseconds: 320);
    const curve = Curves.easeOutCubic;
    return AnimatedFlex(
      flex: selected ? 26 : 10,
      duration: dur,
      curve: curve,
      child: Semantics(
        button: true,
        selected: selected,
        label: item.label,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: AnimatedContainer(
            duration: dur,
            curve: curve,
            decoration: BoxDecoration(
              color: selected ? p.accent : Colors.transparent,
              borderRadius: BorderRadius.circular(Radii.pill),
            ),
            alignment: Alignment.center,
            child: ClipRect(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(item.icon, size: 22, color: selected ? p.onAccent : p.muted),
                  AnimatedSize(
                    duration: dur,
                    curve: curve,
                    child: selected
                        ? Padding(
                            padding: const EdgeInsets.only(left: 7),
                            child: Text(
                              item.label,
                              maxLines: 1,
                              overflow: TextOverflow.clip,
                              style: s.body(14, weight: FontWeight.w600, color: p.onAccent),
                            ),
                          )
                        : const SizedBox.shrink(),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Вкладка «С подписями»: значок над подписью, все одной ширины; открытая —
/// пилюлей цвета акцента.
class _LabeledSlot extends StatelessWidget {
  final TabItem item;
  final bool selected;
  final VoidCallback onTap;
  const _LabeledSlot({required this.item, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final fg = selected ? p.onAccent : p.muted;
    return Expanded(
      child: Semantics(
        button: true,
        selected: selected,
        label: item.label,
        excludeSemantics: true,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
            decoration: BoxDecoration(
              color: selected ? p.accent : Colors.transparent,
              borderRadius: BorderRadius.circular(Radii.pill),
            ),
            alignment: Alignment.center,
            padding: const EdgeInsets.symmetric(horizontal: 2),
            // крупный системный шрифт — подпись мельчает, а не обрезается
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(item.icon, size: 22, color: fg),
                  const SizedBox(height: 2),
                  Text(
                    item.label,
                    maxLines: 1,
                    style: s.body(11, weight: FontWeight.w600, color: fg).copyWith(height: 1.15),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Expanded с анимацией доли: пилюля плавно растёт, соседи сжимаются.
class AnimatedFlex extends ImplicitlyAnimatedWidget {
  final int flex;
  final Widget child;
  const AnimatedFlex({super.key, required this.flex, required this.child, required super.duration, super.curve});

  @override
  AnimatedWidgetBaseState<AnimatedFlex> createState() => _AnimatedFlexState();
}

class _AnimatedFlexState extends AnimatedWidgetBaseState<AnimatedFlex> {
  Tween<double>? _flex;

  @override
  void forEachTween(TweenVisitor<dynamic> visitor) {
    _flex = visitor(_flex, widget.flex.toDouble(), (v) => Tween<double>(begin: v as double)) as Tween<double>?;
  }

  @override
  Widget build(BuildContext context) => Expanded(flex: (_flex!.evaluate(animation) * 10).round(), child: widget.child);
}

class _Blur extends StatelessWidget {
  final Widget child;
  const _Blur({required this.child});

  @override
  Widget build(BuildContext context) =>
      kIsWeb ? child : BackdropFilter(filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18), child: child);
}

/// Кнопка над меню справа — кружок QR на «Сегодня» (Никита 01.11: всегда,
/// над меню справа). Залит акцентом, как раньше, но крупнее (56, было 40 —
/// меньше 44 pt для пальца), без тени и с тонким вырезом цвета фона: над
/// карточкой он ровно режет её край, видно, что кружок лежит сверху.
class CapsuleAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onPressed;
  const CapsuleAction({super.key, required this.icon, required this.label, required this.onPressed});

  /// Поперечник кружка без выреза.
  static const size = 56.0;

  /// Вырез вокруг кружка.
  static const ring = 2.0;

  /// Сколько добавить снизу списку, чтобы докрученная до конца последняя
  /// карточка уходила выше кружка, а не садилась под него.
  static const reserve = size + 8;

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    return Semantics(
      button: true,
      label: label,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          tick();
          onPressed();
        },
        child: Container(
          width: size + 2 * ring,
          height: size + 2 * ring,
          padding: const EdgeInsets.all(ring),
          decoration: BoxDecoration(shape: BoxShape.circle, color: p.bg),
          child: DecoratedBox(
            decoration: BoxDecoration(shape: BoxShape.circle, color: p.accent),
            child: Center(child: Icon(icon, size: 26, color: p.onAccent)),
          ),
        ),
      ),
    );
  }
}

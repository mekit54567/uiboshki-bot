// Долгое нажатие на сообщение — как в iMessage и Telegram на iPhone (Никита,
// 20.10): фон гаснет, пузырь чуть приподнимается, рядом меню «Копировать»
// (всё сообщение) и «Выбрать текст». В приподнятом пузыре текст выделяется
// ещё одним долгим нажатием — кусочек. На компьютере то же — правой кнопкой.
import 'dart:math' as math;
import 'dart:ui' show ImageFilter;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'common.dart';

/// Обёртка сообщения: зажал — меню. [bubble] рисует сам пузырь (его же
/// показываем приподнятым), [text] — что уходит в буфер целиком.
class MessageHold extends StatelessWidget {
  final Widget child;
  final WidgetBuilder bubble;
  final String Function() text;

  /// Пузырь справа (своё сообщение) — меню под правым краем.
  final bool right;

  /// Насколько приподнятый пузырь шире места в переписке (у ответа помощника
  /// пузыря нет — в меню он получает подложку с этим отступом).
  final double inflate;
  const MessageHold({
    super.key,
    required this.child,
    required this.bubble,
    required this.text,
    this.right = false,
    this.inflate = 0,
  });

  void _open(BuildContext context) {
    final box = context.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return;
    HapticFeedback.mediumImpact();
    final rect = (box.localToGlobal(Offset.zero) & box.size).inflate(inflate);
    FocusManager.instance.primaryFocus?.unfocus();
    Navigator.of(context).push(
      PageRouteBuilder<void>(
        opaque: false,
        barrierDismissible: true,
        barrierColor: Colors.transparent,
        transitionDuration: const Duration(milliseconds: 220),
        reverseTransitionDuration: const Duration(milliseconds: 160),
        pageBuilder: (ctx, anim, _) => _HoldOverlay(anim: anim, rect: rect, right: right, bubble: bubble, text: text),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => GestureDetector(
    behavior: HitTestBehavior.opaque,
    onLongPress: () => _open(context),
    onSecondaryTap: () => _open(context),
    child: child,
  );
}

/// Скопировать всё сообщение: плашка «Скопировано».
Future<void> copyMessage(OverlayState toast, String text) async {
  try {
    await Clipboard.setData(ClipboardData(text: text));
  } catch (_) {
    toastOn(toast, 'Не удалось скопировать — попробуй ещё раз.', kind: ToastKind.error);
    return;
  }
  toastOn(toast, 'Скопировано', kind: ToastKind.done);
}

/// Лист «Выбрать текст»: весь текст сообщения, выделяй сколько нужно.
Future<void> showSelectSheet(BuildContext context, String text) => appSheet<void>(context, (ctx) {
  final s = AppStyle.of(ctx);
  final mq = MediaQuery.of(ctx);
  return ConstrainedBox(
    constraints: BoxConstraints(maxHeight: mq.size.height * 0.8),
    child: SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Выбрать текст', style: s.title(20)),
            const SizedBox(height: 4),
            Text('Зажми слово и потяни за края выделения', style: s.body(13, color: s.p.muted)),
            const SizedBox(height: Space.m),
            Flexible(
              child: SingleChildScrollView(
                child: SelectableText(text, style: s.body(16, color: s.p.text)),
              ),
            ),
          ],
        ),
      ),
    ),
  );
});

class _HoldOverlay extends StatelessWidget {
  final Animation<double> anim;
  final Rect rect;
  final bool right;
  final WidgetBuilder bubble;
  final String Function() text;
  const _HoldOverlay({
    required this.anim,
    required this.rect,
    required this.right,
    required this.bubble,
    required this.text,
  });

  static const _menuW = 230.0, _menuH = 2 * 52.0, _gap = 8.0;

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final mq = MediaQuery.of(context);
    final top = mq.viewPadding.top + Space.m;
    final bottom = mq.size.height - math.max(mq.viewPadding.bottom, Space.m) - Space.m;
    // пузырь остаётся на месте, если влезает вместе с меню; иначе — сдвигаем,
    // а слишком длинный листается в своей рамке
    final maxBubble = math.max(80.0, bottom - top - _menuH - _gap);
    final h = math.min(rect.height, maxBubble);
    final y = rect.top.clamp(top, math.max(top, bottom - _menuH - _gap - h)).toDouble();
    final curve = CurvedAnimation(parent: anim, curve: Curves.easeOutBack, reverseCurve: Curves.easeIn);
    final fade = CurvedAnimation(parent: anim, curve: Curves.easeOut);
    final close = Navigator.of(context).pop;

    Widget dim = ColoredBox(color: Colors.black.withValues(alpha: 0.35), child: const SizedBox.expand());
    // в вебе размытие тормозит (Никита 15.10) — только затемнение
    if (!kIsWeb) dim = BackdropFilter(filter: ImageFilter.blur(sigmaX: 6, sigmaY: 6), child: dim);

    final menuLeft = right
        ? (rect.right - _menuW).clamp(Space.l, mq.size.width - _menuW - Space.l).toDouble()
        : rect.left.clamp(Space.l, math.max(Space.l, mq.size.width - _menuW - Space.l)).toDouble();

    return Stack(
      children: [
        Positioned.fill(
          child: GestureDetector(
            key: const ValueKey('hold-dim'),
            onTap: close,
            child: FadeTransition(opacity: fade, child: dim),
          ),
        ),
        Positioned(
          left: rect.left,
          width: rect.width,
          top: y,
          height: h,
          child: ScaleTransition(
            scale: Tween(begin: 1.0, end: 1.03).animate(curve),
            alignment: right ? Alignment.centerRight : Alignment.centerLeft,
            child: Material(
              type: MaterialType.transparency,
              child: SelectionArea(
                child: SingleChildScrollView(physics: const ClampingScrollPhysics(), child: bubble(context)),
              ),
            ),
          ),
        ),
        Positioned(
          left: menuLeft,
          width: _menuW,
          top: y + h + _gap,
          child: FadeTransition(
            opacity: fade,
            child: ScaleTransition(
              scale: Tween(begin: 0.85, end: 1.0).animate(curve),
              alignment: right ? Alignment.topRight : Alignment.topLeft,
              child: Material(
                color: p.cardSolid,
                elevation: 8,
                shadowColor: Colors.black38,
                borderRadius: BorderRadius.circular(Radii.chip),
                clipBehavior: Clip.antiAlias,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _item(context, 'Копировать', Icons.copy_rounded, () {
                      final toast = Overlay.of(context, rootOverlay: true);
                      close();
                      copyMessage(toast, text());
                    }),
                    Divider(height: 1, thickness: 1, color: p.line),
                    _item(context, 'Выбрать текст', Icons.text_fields_rounded, () {
                      final nav = Navigator.of(context);
                      close();
                      showSelectSheet(nav.context, text());
                    }),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _item(BuildContext context, String label, IconData icon, VoidCallback onTap) {
    final s = AppStyle.of(context);
    return InkWell(
      onTap: () {
        tick();
        onTap();
      },
      child: SizedBox(
        height: 52,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l),
          child: Row(
            children: [
              Expanded(
                child: Text(label, style: s.body(16, color: s.p.text)),
              ),
              Icon(icon, size: 20, color: s.p.text),
            ],
          ),
        ),
      ),
    );
  }
}

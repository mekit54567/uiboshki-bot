// Вырез и «чёлка» iPhone в PWA (веб-сборка на /app). Flutter в браузере не
// знает отступов под часы и полоску «Домой» (MediaQuery.padding = 0), поэтому
// приложение раньше не заходило под часы — сверху была чёрная полоса (Никита
// 15.10). Отступы меряет web/index.html (window.uibInsets, CSS
// env(safe-area-inset-*)), здесь они попадают в MediaQuery — дальше SafeArea
// и экраны работают как в приложении на iPhone.
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import 'web_insets_stub.dart' if (dart.library.js_interop) 'web_insets_web.dart' as impl;

/// «t,r,b,l» в логических пикселях → отступы; пусто или мусор — нули.
EdgeInsets parseInsets(String raw) {
  final v = raw.split(',').map((s) => double.tryParse(s.trim()) ?? 0).toList();
  if (v.length != 4 || v.any((x) => x.isNaN || x < 0)) return EdgeInsets.zero;
  return EdgeInsets.fromLTRB(v[3], v[0], v[1], v[2]);
}

/// Цвет для CSS: #rrggbb (прозрачность фону страницы не нужна).
String cssColor(Color c) =>
    '#${[c.r, c.g, c.b].map((v) => (v * 255).round().toRadixString(16).padLeft(2, '0')).join()}';

/// Фон страницы под Flutter — цветом приложения (Никита 17.10: снизу чёрная
/// полоса, при свайпе недели сначала чёрная страница). Где Flutter ещё не
/// нарисовал — под полоской «Домой», новая неделя до первого кадра, — видно
/// фон страницы, а он был тёмным при любой теме.
void paintPage(Color bg) => impl.paint(cssColor(bg));

/// [child] с отступами браузера в MediaQuery (у клавиатуры низ не нужен).
/// Отступы появляются, когда браузер применит viewport-fit=cover (уже после
/// запуска Flutter), поэтому перемеряем их ещё пару раз после старта.
class WebSafeArea extends StatefulWidget {
  final Widget child;
  const WebSafeArea({super.key, required this.child});

  @override
  State<WebSafeArea> createState() => _WebSafeAreaState();
}

class _WebSafeAreaState extends State<WebSafeArea> {
  EdgeInsets _i = parseInsets(impl.insets());
  final _timers = <Timer>[];

  @override
  void initState() {
    super.initState();
    for (final ms in const [300, 1000, 3000]) {
      _timers.add(Timer(Duration(milliseconds: ms), _measure));
    }
  }

  void _measure() {
    final i = parseInsets(impl.insets());
    if (i != _i && mounted) setState(() => _i = i);
  }

  @override
  void dispose() {
    for (final t in _timers) {
      t.cancel();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final i = parseInsets(impl.insets()); // поворот экрана — новый размер, новые отступы
    if (i != _i) _i = i;
    if (i == EdgeInsets.zero) return widget.child;
    final pad = EdgeInsets.fromLTRB(
      math.max(mq.viewPadding.left, i.left),
      math.max(mq.viewPadding.top, i.top),
      math.max(mq.viewPadding.right, i.right),
      math.max(mq.viewPadding.bottom, i.bottom),
    );
    return MediaQuery(
      data: mq.copyWith(
        viewPadding: pad,
        padding: pad.copyWith(bottom: math.max(0.0, pad.bottom - mq.viewInsets.bottom)),
      ),
      child: widget.child,
    );
  }
}

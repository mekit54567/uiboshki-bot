// Лёгкий график по неделям (рейтинг, 5.100.5): одна линия с заливкой под ней,
// без библиотек и без бесконечных анимаций — рисуется одним CustomPainter.
// Палец на графике — вертикальная черта и подпись «неделя · значение».
// [invert] — для места: первое место сверху. Слева — подписи оси (робот 18.10:
// у места без них не понять, какое оно), по ним же — линии сетки.
import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../theme/tokens.dart';

class TrendChart extends StatefulWidget {
  /// Значения по неделям (null — нет значения: группа ещё не в рейтинге).
  final List<num?> values;

  /// Подписи недель («12.10») — под осью первая и последняя.
  final List<String> labels;

  /// Меньше — лучше (место): ось перевёрнута, 1 сверху.
  final bool invert;

  /// Подпись значения: «1188» или «2 место».
  final String Function(num v) format;
  final double height;
  const TrendChart({
    super.key,
    required this.values,
    required this.labels,
    required this.format,
    this.invert = false,
    this.height = 132,
  });

  @override
  State<TrendChart> createState() => _TrendChartState();
}

/// Шкала: нижняя и верхняя граница и подписи оси. Опыт — от нуля; место —
/// от первого, каждое место подписано, если их немного, иначе три.
({double lo, double hi, List<int> ticks}) trendScale(List<num?> values, bool invert) {
  final known = values.whereType<num>().toList();
  if (known.isEmpty) return (lo: 0, hi: 1, ticks: const []);
  var hi = known.reduce((a, b) => a > b ? a : b).toDouble();
  final lo = invert ? 1.0 : 0.0;
  if (hi - lo < 1) hi = lo + 1;
  final top = hi.round();
  final List<int> ticks;
  if (invert && top <= 6) {
    ticks = [for (var v = 1; v <= top; v++) v];
  } else {
    ticks = {lo.round(), ((lo + hi) / 2).round(), top}.toList();
  }
  return (lo: lo, hi: hi, ticks: ticks);
}

class _TrendChartState extends State<TrendChart> {
  int? _hover;

  /// Ширина полосы подписей слева.
  double _gutter(BuildContext context, TextStyle style, List<int> ticks) {
    var w = 0.0;
    for (final t in ticks) {
      final tp = TextPainter(
        text: TextSpan(text: '$t', style: style),
        textScaler: MediaQuery.textScalerOf(context),
        textDirection: TextDirection.ltr,
      )..layout();
      if (tp.width > w) w = tp.width;
      tp.dispose();
    }
    return ticks.isEmpty ? 0 : w + 8;
  }

  void _touch(Offset at, double width, double gutter) {
    final n = widget.values.length;
    if (n == 0) return;
    final i = ((at.dx - gutter) / (width - gutter) * (n - 1)).round().clamp(0, n - 1);
    if (i != _hover) setState(() => _hover = i);
  }

  /// Прирост за неделю у опыта: « · +128 за неделю» (у места — не пишем).
  String _delta(int i) {
    if (widget.invert || i == 0) return '';
    final now = widget.values[i], before = widget.values[i - 1];
    if (now == null || before == null || now == before) return '';
    final d = (now - before).toInt();
    return ' · ${d > 0 ? '+' : '−'}${d.abs()} за неделю';
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final n = widget.values.length;
    final shown = _hover ?? _lastIndex(widget.values);
    final scale = trendScale(widget.values, widget.invert);
    final axis = s.body(11, color: p.muted);
    final gutter = _gutter(context, axis, scale.ticks);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // подпись выбранной недели — сверху, чтобы палец её не закрывал
        SizedBox(
          height: 20,
          child: shown == null
              ? null
              : Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: widget.format(widget.values[shown]!),
                        style: s.body(14, weight: FontWeight.w700),
                      ),
                      TextSpan(
                        text:
                            '  ${shown == n - 1 ? 'сейчас' : 'неделя с ${widget.labels[shown]}'}'
                            '${_delta(shown)}',
                        style: s.body(12.5, color: p.muted),
                      ),
                    ],
                  ),
                ),
        ),
        const SizedBox(height: Space.s),
        LayoutBuilder(
          builder: (context, box) => GestureDetector(
            behavior: HitTestBehavior.opaque,
            onPanDown: (d) => _touch(d.localPosition, box.maxWidth, gutter),
            onPanUpdate: (d) => _touch(d.localPosition, box.maxWidth, gutter),
            onPanEnd: (_) => setState(() => _hover = null),
            onPanCancel: () => setState(() => _hover = null),
            child: CustomPaint(
              size: Size(box.maxWidth, widget.height),
              painter: _TrendPainter(
                values: widget.values,
                invert: widget.invert,
                lo: scale.lo,
                hi: scale.hi,
                ticks: scale.ticks,
                gutter: gutter,
                axis: axis,
                scaler: MediaQuery.textScalerOf(context),
                hover: _hover,
                line: p.accent,
                grid: p.line,
                surface: p.cardSolid,
              ),
            ),
          ),
        ),
        const SizedBox(height: 6),
        if (n > 1)
          Row(
            children: [
              SizedBox(width: gutter),
              Text(widget.labels.first, style: s.body(11.5, color: p.muted)),
              const Spacer(),
              Text('сейчас', style: s.body(11.5, color: p.muted)),
            ],
          ),
      ],
    );
  }
}

int? _lastIndex(List<num?> v) {
  for (var i = v.length - 1; i >= 0; i--) {
    if (v[i] != null) return i;
  }
  return null;
}

class _TrendPainter extends CustomPainter {
  final List<num?> values;
  final bool invert;
  final double lo, hi, gutter;
  final List<int> ticks;
  final TextStyle axis;
  final TextScaler scaler;
  final int? hover;
  final Color line, grid, surface;
  _TrendPainter({
    required this.values,
    required this.invert,
    required this.lo,
    required this.hi,
    required this.ticks,
    required this.gutter,
    required this.axis,
    required this.scaler,
    required this.hover,
    required this.line,
    required this.grid,
    required this.surface,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final n = values.length;
    const pad = 6.0;
    final plot = size.width - gutter;
    double x(int i) => gutter + (n == 1 ? plot / 2 : i * plot / (n - 1));
    // опыт — от нуля (иначе рост кажется больше, чем есть), место — от первого
    double y(num v) {
      final t = (v - lo) / (hi - lo);
      final h = size.height - pad * 2;
      return invert ? pad + t * h : size.height - pad - t * h;
    }

    // сетка и подписи оси: тонкие линии — фон, а не данные
    final gridPaint = Paint()
      ..color = grid
      ..strokeWidth = 1;
    for (final v in ticks) {
      final ty = y(v);
      canvas.drawLine(Offset(gutter, ty), Offset(size.width, ty), gridPaint);
      final tp = TextPainter(
        text: TextSpan(text: '$v', style: axis),
        textScaler: scaler,
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(gutter - 8 - tp.width, ty - tp.height / 2));
      tp.dispose();
    }
    if (n == 0 || values.every((v) => v == null)) return;

    // отрезки без пропусков (null рвёт линию)
    final runs = <List<int>>[];
    for (var i = 0; i < n; i++) {
      if (values[i] == null) continue;
      if (runs.isEmpty || runs.last.last != i - 1) {
        runs.add([i]);
      } else {
        runs.last.add(i);
      }
    }
    for (final run in runs) {
      final path = Path()..moveTo(x(run.first), y(values[run.first]!));
      for (final i in run.skip(1)) {
        path.lineTo(x(i), y(values[i]!));
      }
      if (!invert && run.length > 1) {
        final area = Path.from(path)
          ..lineTo(x(run.last), size.height)
          ..lineTo(x(run.first), size.height)
          ..close();
        canvas.drawPath(
          area,
          Paint()
            ..shader = LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [line.withValues(alpha: 0.28), line.withValues(alpha: 0.02)],
            ).createShader(Offset.zero & size),
        );
      }
      canvas.drawPath(
        path,
        Paint()
          ..color = line
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.2
          ..strokeJoin = StrokeJoin.round
          ..strokeCap = StrokeCap.round,
      );
    }
    void dot(int i, double r) {
      final c = Offset(x(i), y(values[i]!));
      canvas.drawCircle(c, r + 2, Paint()..color = surface);
      canvas.drawCircle(c, r, Paint()..color = line);
    }

    for (var i = 0; i < n; i++) {
      if (values[i] != null && invert) dot(i, 3); // у места каждая неделя — точка
    }
    final h = hover;
    if (h != null) {
      canvas.drawLine(
        Offset(x(h), 0),
        Offset(x(h), size.height),
        Paint()
          ..color = grid
          ..strokeWidth = 1.5,
      );
      if (values[h] != null) dot(h, 5);
    } else {
      final last = _lastIndex(values);
      if (last != null) dot(last, 5);
    }
  }

  @override
  bool shouldRepaint(_TrendPainter old) =>
      old.values != values ||
      old.hover != hover ||
      old.line != line ||
      old.invert != invert ||
      old.gutter != gutter ||
      old.axis != axis;
}

/// Из чего сложился опыт: строки «название — тонкая полоса — число», полосы в
/// одном цвете (это величины, а не разные сущности), длина — доля от большей.
class PartsBars extends StatelessWidget {
  final List<(String, num)> parts;
  const PartsBars({super.key, required this.parts});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final top = parts.fold<num>(0, (m, e) => e.$2 > m ? e.$2 : m);
    final sum = parts.fold<num>(0, (m, e) => m + e.$2);
    return Column(
      children: [
        for (final (title, v) in parts)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Expanded(child: Text(title, style: s.body(14))),
                    if (sum > 0 && v > 0) Text('${(v * 100 / sum).round()}%  ', style: s.body(12.5, color: p.muted)),
                    Text('${v.toInt()}', style: s.number(15, color: p.text)),
                  ],
                ),
                const SizedBox(height: 6),
                ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: SizedBox(
                    height: 6,
                    child: Stack(
                      children: [
                        Positioned.fill(child: ColoredBox(color: p.line)),
                        FractionallySizedBox(
                          widthFactor: top > 0 ? (v / top).clamp(0, 1).toDouble() : 0,
                          child: DecoratedBox(
                            decoration: BoxDecoration(color: p.accent, borderRadius: BorderRadius.circular(3)),
                            child: const SizedBox.expand(),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

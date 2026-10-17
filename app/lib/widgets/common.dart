// Общие кирпичики экранов: фон с подсветкой, карточка, заголовок экрана,
// плашка-сообщение и листы-вопросы.
import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api.dart';
import '../theme/app_theme.dart';
import '../theme/look.dart';
import '../theme/tokens.dart';
import 'capy.dart';
import 'capy_refresh.dart';

/// «Сейчас». Для стенда и скриншотов время можно сдвинуть: --dart-define=NOW=2026-10-08T10:07:00+03:00
DateTime now() {
  final shift = _shift;
  return shift == null ? DateTime.now() : DateTime.now().add(shift);
}

const _fakeNow = String.fromEnvironment('NOW');
final Duration? _shift = _fakeNow.isEmpty ? null : DateTime.parse(_fakeNow).difference(_started);
final _started = DateTime.now();

/// Лёгкий отклик на касание — как в системе, без «дребезга».
void tick() => HapticFeedback.selectionClick();

/// Фон экрана: цвет темы и две мягкие подсветки сверху и снизу.
class Backdrop extends StatelessWidget {
  final Widget child;
  final Color? tint;
  const Backdrop({super.key, required this.child, this.tint});

  /// В браузере фон — одна готовая картинка, а не три заливки на весь экран
  /// каждый кадр (Никита 17.10: PWA на iPhone листается рывками; без
  /// подсветок кадр при прокрутке вдвое легче). Тесты включают сами.
  static bool cheap = kIsWeb;

  static List<RadialGradient> glows(Palette p, Color? tint) => [
        RadialGradient(
          center: const Alignment(-0.6, -1.1),
          radius: 1.2,
          colors: [(tint ?? p.glow1).withValues(alpha: p.dark ? 0.85 : 0.6), p.bg.withValues(alpha: 0)],
        ),
        RadialGradient(
          center: const Alignment(-1, 1.2),
          radius: 1.1,
          colors: [p.glow2.withValues(alpha: p.dark ? 0.8 : 0.5), p.bg.withValues(alpha: 0)],
        ),
      ];

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final paper = !p.dark && s.look.light == LightTheme.notebook ? s.look.paper : Paper.smooth;
    final g = glows(p, tint);
    return DecoratedBox(
      decoration: BoxDecoration(color: cheap ? null : p.bg),
      child: Stack(
        children: [
          if (cheap)
            Positioned.fill(child: _GlowImage(bg: p.bg, glows: g))
          else
            for (final gradient in g) Positioned.fill(child: DecoratedBox(decoration: BoxDecoration(gradient: gradient))),
          if (paper != Paper.smooth)
            Positioned.fill(
              child: IgnorePointer(child: CustomPaint(painter: PaperPainter(paper, p.text))),
            ),
          child,
        ],
      ),
    );
  }
}

/// Фон с подсветками, нарисованный один раз в маленькую картинку (1/8 —
/// подсветки плавные, растянутая картинка не отличается) и растянутый на экран.
/// Пока картинка готовится — просто цвет темы.
class _GlowImage extends StatefulWidget {
  final Color bg;
  final List<RadialGradient> glows;
  const _GlowImage({required this.bg, required this.glows});

  @override
  State<_GlowImage> createState() => _GlowImageState();
}

class _GlowImageState extends State<_GlowImage> {
  static const scale = 8;
  // готовые фоны — общие для всех экранов (картинки крошечные: 1/8 экрана)
  static final _cache = <Object, ui.Image>{};
  static final _making = <Object, Future<ui.Image>>{};

  static Future<ui.Image> _make(Size size, Color bg, List<RadialGradient> glows, Object key) =>
      _making[key] ??= () async {
        final w = math.max(1, (size.width / scale).ceil()), h = math.max(1, (size.height / scale).ceil());
        final rect = Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble());
        final rec = ui.PictureRecorder();
        final c = Canvas(rec, rect);
        c.drawRect(rect, Paint()..color = bg);
        for (final g in glows) {
          c.drawRect(rect, Paint()..shader = g.createShader(rect));
        }
        final pic = rec.endRecording();
        final img = await pic.toImage(w, h);
        pic.dispose();
        if (_cache.length >= 12) _cache.remove(_cache.keys.first);
        _making.remove(key);
        return _cache[key] = img;
      }();

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      final size = box.biggest;
      if (!size.isFinite) return ColoredBox(color: widget.bg);
      // размер — с шагом 32 px: клавиатура и поворот не перерисовывают на каждый пиксель
      final key = (widget.bg, Object.hashAll(widget.glows), (size.width / 32).ceil(), (size.height / 32).ceil());
      final img = _cache[key];
      if (img == null) {
        _make(size, widget.bg, widget.glows, key).then((_) {
          if (mounted) setState(() {});
        });
        return ColoredBox(color: widget.bg);
      }
      return RawImage(image: img, fit: BoxFit.fill, filterQuality: FilterQuality.low);
    });
  }
}

/// Бумага «Тетради» (5.79, настройка в «Оформлении»): клетка, линейка,
/// точки или миллиметровка — тонко, чтобы не спорить с карточками.
class PaperPainter extends CustomPainter {
  final Paper paper;
  final Color ink;
  const PaperPainter(this.paper, this.ink);

  @override
  void paint(Canvas canvas, Size size) {
    final thin = Paint()
      ..color = ink.withValues(alpha: 0.06)
      ..strokeWidth = 1;
    switch (paper) {
      case Paper.smooth:
        return;
      case Paper.cell:
        for (var x = 0.0; x < size.width; x += 22) {
          canvas.drawLine(Offset(x, 0), Offset(x, size.height), thin);
        }
        for (var y = 0.0; y < size.height; y += 22) {
          canvas.drawLine(Offset(0, y), Offset(size.width, y), thin);
        }
      case Paper.line:
        for (var y = 28.0; y < size.height; y += 28) {
          canvas.drawLine(Offset(0, y), Offset(size.width, y), thin);
        }
      case Paper.dots:
        final dot = Paint()..color = ink.withValues(alpha: 0.13);
        for (var y = 9.0; y < size.height; y += 18) {
          for (var x = 9.0; x < size.width; x += 18) {
            canvas.drawCircle(Offset(x, y), 1, dot);
          }
        }
      case Paper.grid:
        final fine = Paint()
          ..color = const Color(0xFFC9784B).withValues(alpha: 0.07)
          ..strokeWidth = 0.6;
        final bold = Paint()
          ..color = const Color(0xFFC9784B).withValues(alpha: 0.13)
          ..strokeWidth = 1;
        var i = 0;
        for (var x = 0.0; x < size.width; x += 8, i++) {
          canvas.drawLine(Offset(x, 0), Offset(x, size.height), i % 5 == 0 ? bold : fine);
        }
        i = 0;
        for (var y = 0.0; y < size.height; y += 8, i++) {
          canvas.drawLine(Offset(0, y), Offset(size.width, y), i % 5 == 0 ? bold : fine);
        }
    }
  }

  @override
  bool shouldRepaint(PaperPainter old) => old.paper != paper || old.ink != ink;
}

class Tile extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;
  final Color? color;
  final Gradient? gradient;
  final VoidCallback? onTap;
  final double radius;

  /// Рамка другого цвета — у идущей пары (по умолчанию линия темы).
  final Color? border;
  const Tile({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(Space.l),
    this.color,
    this.gradient,
    this.onTap,
    this.radius = Radii.tile,
    this.border,
  });

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    final r = BorderRadius.circular(radius);
    // Скруглённые углы режет ClipRRect, а не форма Material: та режет по
    // контуру-пути, а в вебе это дорого на каждом кадре прокрутки (17.10).
    return ClipRRect(
      borderRadius: r,
      child: Material(
        type: MaterialType.transparency,
        child: Ink(
          decoration: BoxDecoration(
            color: gradient == null ? (color ?? p.card) : null,
            gradient: gradient,
            borderRadius: r,
            border: Border.all(color: border ?? p.line),
          ),
          child: InkWell(
            borderRadius: r,
            onTap: onTap == null
                ? null
                : () {
                    tick();
                    onTap!();
                  },
            child: Padding(padding: padding, child: child),
          ),
        ),
      ),
    );
  }
}

/// Бледнее (прошедшая пара, отменённая). В приложении — Opacity. В вебе
/// Opacity — отдельный слой на каждую строку на каждом кадре прокрутки
/// (Никита 17.10: «Неделя» в PWA листается рывками), поэтому там поверх
/// кладём фон карточки с прозрачностью: на вид то же, а слоёв нет.
class Faded extends StatelessWidget {
  final double opacity;
  final double radius;
  final Widget child;
  const Faded({super.key, required this.opacity, this.radius = 0, required this.child});

  static bool cheap = kIsWeb;

  @override
  Widget build(BuildContext context) {
    if (opacity >= 1) return child;
    if (!cheap) return Opacity(opacity: opacity, child: child);
    final p = AppStyle.of(context).p;
    return DecoratedBox(
      position: DecorationPosition.foreground,
      decoration: BoxDecoration(
        color: p.cardSolid.withValues(alpha: 1 - opacity),
        borderRadius: radius > 0 ? BorderRadius.circular(radius) : null,
      ),
      child: child,
    );
  }
}

/// Заголовок экрана: крупное название с короткой прямой чертой под ним (без
/// дуги — решение владельца). Мелких курсивных подписей над ним нет
/// (владелец, 2.4): нужное по смыслу («экзамен», предмет задания) — строкой
/// [sub] под названием обычным шрифтом. Длинное название — мельче, до трёх
/// строк (2.3).
class ScreenTitle extends StatelessWidget {
  final String title;
  final Widget? trailing;

  /// Строка под названием: «экзамен», «Анализ данных · тест».
  final String? sub;

  /// Строка над заголовком, если в ней не только текст (даты недели со стрелками).
  final Widget? lead;
  const ScreenTitle({super.key, required this.title, this.trailing, this.lead, this.sub});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final row = Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              FitWords(title, style: s.title(titleSize(title, 34)), maxLines: 3),
              if (sub != null && sub!.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(sub!, style: s.body(15, color: s.p.muted)),
              ],
              const SizedBox(height: 10),
              Container(
                width: 34,
                height: 3,
                decoration: BoxDecoration(color: s.p.accent, borderRadius: BorderRadius.circular(2)),
              ),
            ],
          ),
        ),
        ?trailing,
      ],
    );
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.xl, Space.l, Space.xl, Space.m),
      // строка над заголовком — во всю ширину, кнопки справа её не теснят (Б5)
      child: lead == null
          ? row
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [lead!, const SizedBox(height: 6), row]),
    );
  }
}

/// Кегль заголовка по длине: длинные названия предметов («Анализ и
/// диагностика финансово-хозяйственной…») — мельче (владелец, 2.3).
double titleSize(String text, double base) {
  final n = text.length;
  if (n > 60) return base * 0.62;
  if (n > 40) return base * 0.72;
  if (n > 26) return base * 0.86;
  return base;
}

/// Крупный заголовок без разрыва слов посередине («Безопасн/ость»,
/// «хозяйственн/ой») и после дефиса («финансово-/хозяйственной»): если самое
/// длинное слово не влезает в строку (узкий экран, крупный системный шрифт),
/// шрифт уменьшается ровно до влезания; с [maxLines] — ещё и пока текст
/// не уляжется в столько строк.
class FitWords extends StatelessWidget {
  final String text;
  final TextStyle style;

  /// Ширина строки, если известна заранее (внутри IntrinsicHeight
  /// LayoutBuilder нельзя); без неё — по месту.
  final double? width;
  final int? maxLines;
  const FitWords(this.text, {super.key, required this.style, this.width, this.maxLines});

  static final _gaps = RegExp(r'[\s/]+');

  /// Слово через дефис не рвётся: после дефиса — «соединитель слов» (U+2060).
  static String glue(String text) => text.replaceAllMapped(RegExp(r'(\S)-(?=\S)'), (m) => '${m[1]}-\u2060');

  Widget _fit(BuildContext context, double max) {
    final scaler = MediaQuery.textScalerOf(context);
    final dir = Directionality.of(context);
    final shown = glue(text);
    var size = style.fontSize ?? 14;
    if (max.isFinite) {
      var widest = 0.0;
      for (final w in shown.split(_gaps)) {
        final tp = TextPainter(
          text: TextSpan(text: w, style: style),
          textScaler: scaler,
          textDirection: dir,
        )..layout();
        if (tp.width > widest) widest = tp.width;
        tp.dispose();
      }
      if (widest > max) size = size * max / widest * 0.98;
      // в [maxLines] строк — мельче, но не меньше 60 % от начального
      final floor = (style.fontSize ?? 14) * 0.6;
      while (maxLines != null && size > floor) {
        final tp = TextPainter(
          text: TextSpan(
            text: shown,
            style: style.copyWith(fontSize: size),
          ),
          textScaler: scaler,
          textDirection: dir,
          maxLines: maxLines,
        )..layout(maxWidth: max);
        final over = tp.didExceedMaxLines;
        tp.dispose();
        if (!over) break;
        size *= 0.93;
      }
    }
    return Text(
      shown,
      style: size == style.fontSize ? style : style.copyWith(fontSize: size),
      maxLines: maxLines,
      overflow: maxLines == null ? null : TextOverflow.ellipsis,
    );
  }

  @override
  Widget build(BuildContext context) =>
      width != null ? _fit(context, width!) : LayoutBuilder(builder: (context, box) => _fit(context, box.maxWidth));
}

/// Подпись раздела внутри экрана: «Весь день», «На неделе».
class Section extends StatelessWidget {
  final String text;
  const Section(this.text, {super.key});

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(Space.xl, Space.xl, Space.xl, Space.s),
    child: Text(text, style: AppStyle.of(context).eyebrow()),
  );
}

/// Пусто или ошибка — спокойная карточка с подсказкой и кнопкой «Ещё раз».
class Notice extends StatelessWidget {
  final String title, text;
  final VoidCallback? onRetry;

  /// Капибара слева: радостная — «всё хорошо, пусто», грустная — «не вышло».
  final CapyPose? pose;

  /// Подпись кнопки повтора (по умолчанию «Ещё раз»).
  final String retryLabel;
  const Notice({
    super.key,
    required this.title,
    required this.text,
    this.onRetry,
    this.pose,
    this.retryLabel = 'Ещё раз',
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final words = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: s.body(17, weight: FontWeight.w600)),
        const SizedBox(height: 4),
        Text(text, style: s.body(14, color: s.p.muted)),
        if (onRetry != null) ...[
          const SizedBox(height: Space.m),
          TextButton(
            onPressed: onRetry,
            child: Text(retryLabel, style: s.body(15, color: s.p.accent)),
          ),
        ],
      ],
    );
    // «Пусто, всё хорошо» — капибара выглядывает снизу справа из-за края карточки
    if (pose != null && pose != CapyPose.sad) {
      const size = 84.0;
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l),
        child: Tile(
          padding: EdgeInsets.zero,
          child: Stack(
            children: [
              ConstrainedBox(
                constraints: const BoxConstraints(minHeight: size * CapyPeek.shown + 30),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(Space.l, Space.l, size + Space.l, Space.l),
                  child: words,
                ),
              ),
              Positioned(
                right: Space.m,
                bottom: 0,
                child: CapyPeek(pose: pose!, size: size),
              ),
            ],
          ),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: Tile(
        child: Row(
          children: [
            if (pose != null) ...[CapyImage(pose: pose!, size: 72, color: s.p.muted), const SizedBox(width: Space.l)],
            Expanded(child: words),
          ],
        ),
      ),
    );
  }
}

/// Загрузка экрана: Future → данные, ошибка или «потяни, чтобы обновить».
class Loader<T> extends StatefulWidget {
  final Future<T> Function() load;
  final Widget Function(BuildContext, T, Future<void> Function() reload) builder;
  final VoidCallback? onUnauthorized;
  const Loader({super.key, required this.load, required this.builder, this.onUnauthorized});

  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  T? _data;
  Object? _error;

  /// Сеть уже ответила (или не смогла) хоть раз.
  bool _netDone = false;

  /// Показан запас и ждём сеть — ключ в [Api.refreshing] (строка «Обновляю»).
  Object? _wait;

  @override
  void initState() {
    super.initState();
    _fromCache();
    _reload();
  }

  @override
  void dispose() {
    // не посреди сборки дерева: строку наверху перерисуем после кадра
    final k = _wait;
    if (k != null) scheduleMicrotask(() => Api.refreshDone(k));
    super.dispose();
  }

  /// Пока идёт сеть — прошлые данные из запаса телефона, без крутилки.
  Future<void> _fromCache() async {
    final c = await Api.fromCacheAt(widget.load);
    if (c != null && mounted && _data == null) {
      setState(() => _data = c.value);
      final at = c.at;
      if (!_netDone && at != null) _wait = Api.refreshStart(at);
    }
  }

  void _fresh() {
    _netDone = true;
    Api.refreshDone(_wait);
    _wait = null;
  }

  Future<void> _reload() async {
    try {
      final d = await widget.load();
      if (mounted) {
        setState(() {
          _data = d;
          _error = null;
        });
      }
    } catch (e) {
      if (e is Unauthorized) {
        widget.onUnauthorized?.call();
        return;
      }
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) _fresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_data != null) {
      return CapyRefresh(onRefresh: _reload, child: widget.builder(context, _data as T, _reload));
    }
    if (_error != null) {
      return ListView(
        children: [
          const SizedBox(height: 120),
          Notice(title: 'Не загрузилось', text: errorText(_error!), onRetry: _reload, pose: CapyPose.sad),
        ],
      );
    }
    return const CapyLoading();
  }
}

// ── Плашка и листы-вопросы ──────────────────────────────────────────────

/// Значок плашки по смыслу: готово, не вышло, просто сообщение.
enum ToastKind { done, error, info }

OverlayEntry? _toast;

/// Видна ли плашка: плашка новой ачивки тогда встаёт над ней.
final toastShown = ValueNotifier<bool>(false);

void _hideToast() {
  final e = _toast;
  _toast = null;
  toastShown.value = false;
  e?.remove();
}

/// Отступ снизу для плашек: над капсулой (64 + отступ снизу), а при
/// клавиатуре — над ней.
double aboveCapsule(MediaQueryData mq) =>
    math.max(math.max(mq.viewPadding.bottom, Space.m) + 64 + Space.s, mq.viewInsets.bottom + Space.s);

/// Плашка над меню-капсулой вместо белой системной (владелец, 09.10, 3.10):
/// карточка цвета темы со значком, выезжает снизу и сама уходит.
void showToast(BuildContext context, String text, {ToastKind kind = ToastKind.info}) {
  final overlay = Overlay.maybeOf(context, rootOverlay: true);
  if (overlay != null) toastOn(overlay, text, kind: kind);
}

/// То же, когда экран мог уже закрыться: оверлей берут до запроса
/// (`final toast = Overlay.of(context, rootOverlay: true)`).
void toastOn(OverlayState overlay, String text, {ToastKind kind = ToastKind.info}) {
  if (!overlay.mounted) return;
  _hideToast();
  late final OverlayEntry entry;
  entry = OverlayEntry(
    builder: (_) => AppToast(
      text: text,
      kind: kind,
      onGone: () {
        if (identical(_toast, entry)) _hideToast();
      },
    ),
  );
  _toast = entry;
  overlay.insert(entry);
  toastShown.value = true;
}

class AppToast extends StatefulWidget {
  final String text;
  final ToastKind kind;
  final VoidCallback onGone;
  const AppToast({super.key, required this.text, required this.kind, required this.onGone});

  @override
  State<AppToast> createState() => _AppToastState();
}

class _AppToastState extends State<AppToast> with SingleTickerProviderStateMixin {
  // вся жизнь плашки одним счётчиком: выезд, пауза на чтение, уход
  late final _life = AnimationController(
    vsync: this,
    duration: Duration(milliseconds: 2600 + 35 * widget.text.length.clamp(0, 80)),
  );

  @override
  void initState() {
    super.initState();
    _life.forward().whenComplete(() {
      if (mounted) widget.onGone();
    });
  }

  @override
  void dispose() {
    _life.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final mq = MediaQuery.of(context);
    final bottom = aboveCapsule(mq);
    final (icon, color) = switch (widget.kind) {
      ToastKind.done => (Icons.check_circle_rounded, p.ok),
      ToastKind.error => (Icons.error_outline_rounded, p.danger),
      ToastKind.info => (Icons.info_outline_rounded, p.accent),
    };
    final still = mq.disableAnimations;
    return Positioned(
      left: Space.l,
      right: Space.l,
      bottom: bottom,
      child: IgnorePointer(
        child: AnimatedBuilder(
          animation: _life,
          builder: (context, child) {
            final v = _life.value;
            final outV = Curves.easeIn.transform(((v - 0.93) / 0.07).clamp(0.0, 1.0));
            if (still) return Opacity(opacity: 1 - outV, child: child);
            final inV = Curves.easeOutBack.transform((v / 0.07).clamp(0.0, 1.0));
            return Opacity(
              opacity: ((v / 0.05).clamp(0.0, 1.0) * (1 - outV)).clamp(0.0, 1.0),
              child: Transform.translate(offset: Offset(0, 24 * (1 - inV) + 12 * outV), child: child),
            );
          },
          child: Semantics(
            liveRegion: true,
            child: Material(
              type: MaterialType.transparency,
              child: Container(
                key: const ValueKey('toast'),
                padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                decoration: BoxDecoration(
                  color: p.cardSolid,
                  borderRadius: BorderRadius.circular(Radii.tile),
                  border: Border.all(color: p.line),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: p.dark ? 0.4 : 0.14),
                      blurRadius: 24,
                      offset: const Offset(0, 8),
                    ),
                  ],
                ),
                child: Row(
                  children: [
                    Icon(icon, color: color, size: 22),
                    const SizedBox(width: Space.m),
                    Expanded(
                      child: Text(widget.text, style: s.body(15, weight: FontWeight.w600)),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Лист снизу в дизайне приложения (как «Тема и шрифт»).
Future<T?> appSheet<T>(BuildContext context, WidgetBuilder builder) => showModalBottomSheet<T>(
  context: context,
  backgroundColor: AppStyle.of(context).p.cardSolid,
  showDragHandle: true,
  isScrollControlled: true,
  builder: builder,
);

/// «Точно?» листом снизу вместо системного окна: заголовок, пояснение,
/// главная кнопка с действием и «Отмена». true — согласился.
Future<bool> confirmSheet(
  BuildContext context, {
  required String title,
  String? text,
  required String action,
  String cancel = 'Отмена',
  bool danger = false,
}) async =>
    await appSheet<bool>(
      context,
      (ctx) => SheetFrame(
        title: title,
        text: text,
        action: action,
        cancel: cancel,
        danger: danger,
        onAction: () => Navigator.pop(ctx, true),
      ),
    ) ??
    false;

/// Число или строка листом снизу (своё время напоминания и т. п.):
/// null — отменил.
Future<String?> inputSheet(
  BuildContext context, {
  required String title,
  String? text,
  String hint = '',
  String initial = '',
  String action = 'Сохранить',
  TextInputType keyboard = TextInputType.text,
}) => appSheet<String>(
  context,
  (ctx) => _InputSheet(title: title, text: text, hint: hint, initial: initial, action: action, keyboard: keyboard),
);

class _InputSheet extends StatefulWidget {
  final String title, hint, initial, action;
  final String? text;
  final TextInputType keyboard;
  const _InputSheet({
    required this.title,
    this.text,
    required this.hint,
    required this.initial,
    required this.action,
    required this.keyboard,
  });

  @override
  State<_InputSheet> createState() => _InputSheetState();
}

class _InputSheetState extends State<_InputSheet> {
  late final _ctrl = TextEditingController(text: widget.initial);

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return SheetFrame(
      title: widget.title,
      text: widget.text,
      action: widget.action,
      onAction: () => Navigator.pop(context, _ctrl.text.trim()),
      child: TextField(
        controller: _ctrl,
        autofocus: true,
        keyboardType: widget.keyboard,
        style: s.body(17),
        cursorColor: s.p.accent,
        onSubmitted: (v) => Navigator.pop(context, v.trim()),
        decoration: fieldDecoration(s, widget.hint),
      ),
    );
  }
}

/// Поле ввода в листах: подложка цвета карточки, рамка акцентом при вводе.
InputDecoration fieldDecoration(AppStyle s, String hint) {
  final p = s.p;
  OutlineInputBorder line(Color c) => OutlineInputBorder(
    borderRadius: BorderRadius.circular(Radii.chip),
    borderSide: BorderSide(color: c),
  );
  return InputDecoration(
    hintText: hint,
    hintStyle: s.body(17, color: p.muted),
    filled: true,
    fillColor: p.card,
    contentPadding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
    border: line(p.line),
    enabledBorder: line(p.line),
    focusedBorder: line(p.accent),
  );
}

/// Каркас листа-вопроса: заголовок, пояснение, своё поле (если есть) и две
/// кнопки одна под другой — на узком экране с крупным шрифтом не тесно.
class SheetFrame extends StatelessWidget {
  final String title, action, cancel;
  final String? text;
  final bool danger;
  final Widget? child;
  final VoidCallback onAction;

  /// Вторая кнопка вместо «Отмена» (например «Скопировать ссылку»); без неё
  /// вторая кнопка просто закрывает лист.
  final VoidCallback? onCancel;
  const SheetFrame({
    super.key,
    required this.title,
    this.text,
    required this.action,
    this.cancel = 'Отмена',
    this.danger = false,
    this.child,
    required this.onAction,
    this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final fg = danger ? Colors.white : p.onAccent;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(title, style: s.title(24)),
              if (text != null) ...[const SizedBox(height: Space.s), Text(text!, style: s.body(15, color: p.muted))],
              if (child != null) ...[const SizedBox(height: Space.l), child!],
              const SizedBox(height: Space.xl),
              FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: danger ? p.danger : p.accent,
                  foregroundColor: fg,
                  minimumSize: const Size.fromHeight(50),
                  shape: const StadiumBorder(),
                ),
                onPressed: () {
                  tick();
                  onAction();
                },
                child: Text(
                  action,
                  style: s.body(16, weight: FontWeight.w600, color: fg),
                ),
              ),
              const SizedBox(height: Space.s),
              TextButton(
                style: TextButton.styleFrom(minimumSize: const Size.fromHeight(46)),
                onPressed: onCancel ?? () => Navigator.pop(context),
                child: Text(
                  cancel,
                  style: s.body(16, weight: FontWeight.w600, color: p.muted),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

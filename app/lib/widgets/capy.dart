// Капибара — талисман приложения: 8 поз из ChatGPT (те же, что в WebApp,
// webapp/static/img/capy). В углу «Сегодня» — по времени суток: утро с
// кофе, день за ноутбуком, вечер с книгой и лампой, ночь — спит на мяче;
// радуется, когда сдал или всё хорошо, грустит, когда не загрузилось;
// на сёрфе (на четырёх лапах, владелец 09.10) — пока обновляется экран.
// Нажал на неё на «Сегодня» — крупно по центру с подписью (К5, 09.10).
import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' show ImageFilter;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../achievements/captions.dart';
import '../achievements/store.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'common.dart';

enum CapyPose { morning, day, evening, night, joy, sad, splash, surf, angry }

/// Часы — как в WebApp (core.js: capyForHour).
CapyPose poseAt(int hour) {
  if (hour >= 5 && hour < 12) return CapyPose.morning;
  if (hour >= 12 && hour < 17) return CapyPose.day;
  if (hour >= 17 && hour < 23) return CapyPose.evening;
  return CapyPose.night;
}

/// Подписи капибары по позе — выбрал владелец (09.10) из вариантов; при
/// каждом нажатии — следующая по кругу.
const capyLines = {
  CapyPose.morning: [
    'Сначала кофе, потом пары',
    'Глаза открыты наполовину. Этого хватит',
    'Проснулась раньше будильника. Почти',
    'Кофе горячий, дедлайны пока холодные',
    'Утро начинается с кружки, а не с СДО',
    'Ещё глоток, и можно в метро',
    'Утро доброе, если пары не с девяти',
    'Капибара и кофе: лучший старт дня',
    'Сделай вид, что ты жаворонок',
  ],
  CapyPose.day: [
    'Пишу лабу. Не отвлекай, пожалуйста',
    'Ctrl+S каждые пять минут',
    'Капибара в потоке',
    'Ещё одна вкладка, и точно всё пойму',
    'Обед был? Если нет, иди поешь',
    'Компилируется… можно моргнуть',
  ],
  CapyPose.evening: [
    'Вечер. Лампа горит, дела тают',
    'Ещё одна глава, и спать',
    'Читаю лекцию, которую проспала',
    'Тёплый свет и ни одного дедлайна. Мечта',
    'Пары кончились, учёба нет',
    'Сегодня ты молодец. Даже если нет',
  ],
  CapyPose.night: [
    'Тсс, капибара спит',
    'Zzz… дедлайны подождут до утра',
    'Спит и видит зачёт автоматом',
    'Сон тоже подготовка к экзамену',
    'Пять минут… ещё пять минут…',
    'Снится, что СДО не упал',
    'Мяч мягкий, сон крепкий',
  ],
};

/// Подписи по случаю — идут первыми, перед подписями позы.
enum CapyMoment { dayOver, weekOver, dayOff, rain }

const momentLines = {
  CapyMoment.dayOver: 'На сегодня всё. Свобода',
  // после последней пары недели, а не «в пятницу»: бывает и суббота (владелец)
  CapyMoment.weekOver: 'Неделя закончилась, а капибара нет',
  CapyMoment.dayOff: 'Выходной. Отдыхаю и тебе советую',
  CapyMoment.rain: 'Зонт не забудь',
};

/// Пятое нажатие подряд.
const tickleLine = 'Ну хватит щекотать';

/// Случай для редких фраз и волны (ачивки); тесты подменяют.
math.Random capyRandom = math.Random();

/// Поза — силуэт-маска: цвет даёт тема (как CSS в WebApp), поэтому одна
/// картинка годится и для «Глубины», и для «Тетради».
class CapyImage extends StatelessWidget {
  final CapyPose pose;
  final double size;
  final Color? color;
  const CapyImage({super.key, this.pose = CapyPose.splash, required this.size, this.color});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    return Image.asset(
      'assets/capy/${pose.name}.png',
      width: size,
      height: size,
      fit: BoxFit.contain,
      color: color ?? p.text,
      colorBlendMode: BlendMode.srcIn,
      semanticLabel: null,
      excludeFromSemantics: true,
    );
  }
}

/// Капибара в углу «Сегодня»: поза по времени суток и мягкое «дыхание».
/// Нажал или зажал — она по центру, фон размыт, подпись печатается (К5).
class CapyBadge extends StatefulWidget {
  final int hour;
  final double size;

  /// Что сейчас за случай (пары кончились, дождь…) — его подписи первыми.
  final List<CapyMoment> moments;
  const CapyBadge({super.key, required this.hour, this.size = 64, this.moments = const []});

  @override
  State<CapyBadge> createState() => _CapyBadgeState();
}

class _CapyBadgeState extends State<CapyBadge> with SingleTickerProviderStateMixin {
  // в браузере дыхание бесконечно перерисовывало экран (PWA тормозила) —
  // там капибара дышит пару раз и замирает
  late final _breath = AnimationController(vsync: this, duration: const Duration(milliseconds: 3200))
    ..repeat(count: kIsWeb ? 2 : null);
  int? _at; // какая подпись была последней
  int _taps = 0;
  DateTime? _lastTap;

  @override
  void dispose() {
    _breath.dispose();
    super.dispose();
  }

  List<String> _lines(CapyPose pose) => [for (final m in widget.moments) momentLines[m]!, ...capyLines[pose]!];

  /// Следующая подпись: сначала случай, потом подписи позы по кругу (начиная
  /// со случайной); пятое нажатие подряд — «хватит щекотать».
  String _next(CapyPose pose) {
    // редкие фразы — полночные ачивки (captions.dart)
    if (capyRandom.nextInt(oneOfUsChance) == 0) return oneOfUsLine;
    if (capyRandom.nextInt(secretChance) == 0) return secretLine;
    final t = DateTime.now();
    final last = _lastTap;
    _taps = last != null && t.difference(last) < const Duration(seconds: 12) ? _taps + 1 : 1;
    _lastTap = t;
    if (_taps >= 5) {
      _taps = 0;
      return tickleLine;
    }
    final lines = _lines(pose);
    final first = widget.moments.isEmpty ? math.Random().nextInt(lines.length) : 0;
    final i = _at == null ? first : (_at! + 1) % lines.length;
    _at = i;
    return lines[i];
  }

  void _open(CapyPose pose) {
    // заметный «тык» (14.10): щелчок выбора на iPhone почти не чувствуется;
    // пятое касание подряд — щекотка, отклик сильнее. В вебе вибрации нет — тихо
    final line = _next(pose);
    AchStore.capyTouched(now());
    final turn = line == oneOfUsLine;
    if (turn) {
      HapticFeedback.heavyImpact();
      AchStore.unlock('one_of_us');
    } else if (line == tickleLine) {
      HapticFeedback.mediumImpact();
    } else {
      HapticFeedback.lightImpact();
    }
    if (line == secretLine) AchStore.unlock('secret');
    showCapy(context, pose, line, turn: turn);
  }

  @override
  Widget build(BuildContext context) {
    final pose = poseAt(widget.hour);
    final sleepy = pose == CapyPose.night;
    return Semantics(
      button: true,
      label: 'Капибара',
      child: GestureDetector(
        onTap: () => _open(pose),
        onLongPress: () => _open(pose),
        child: AnimatedBuilder(
          animation: _breath,
          builder: (context, child) {
            final k = math.sin(_breath.value * 2 * math.pi);
            return Transform.scale(
              scale: 1 + k * (sleepy ? 0.035 : 0.015),
              alignment: Alignment.bottomCenter,
              child: child,
            );
          },
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 600),
            child: CapyImage(key: ValueKey(pose), pose: pose, size: widget.size),
          ),
        ),
      ),
    );
  }
}

/// Капибара крупно по центру поверх размытого экрана, подпись печатается по
/// буквам (владелец, 09.10, К5). Закрывается нажатием в любом месте.
///
/// [turn] — сверхредкая фраза (Никита 15.10): экран темнеет сильнее, капибара
/// медленно поворачивается к тебе и чуть приближается, подпись — потом.
Future<void> showCapy(BuildContext context, CapyPose pose, String text, {bool turn = false}) => showGeneralDialog(
  context: context,
  barrierDismissible: true,
  barrierLabel: 'Закрыть',
  barrierColor: Colors.transparent,
  transitionDuration: const Duration(milliseconds: 380),
  // Material — иначе у текста в диалоге жёлтое подчёркивание «нет темы»
  pageBuilder: (context, appear, _) => Material(
    type: MaterialType.transparency,
    child: CapyOverlay(pose: pose, text: text, appear: appear, turn: turn),
  ),
);

class CapyOverlay extends StatefulWidget {
  final CapyPose pose;
  final String text;
  final Animation<double> appear;
  final bool turn;
  const CapyOverlay({super.key, required this.pose, required this.text, required this.appear, this.turn = false});

  @override
  State<CapyOverlay> createState() => _CapyOverlayState();
}

class _CapyOverlayState extends State<CapyOverlay> with TickerProviderStateMixin {
  late final _bob = AnimationController(vsync: this, duration: const Duration(milliseconds: 2600));
  late final _caret = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000));
  // поворот к тебе: пауза, разворот ребром, вторая половина — уже лицом
  late final _turn = AnimationController(vsync: this, duration: const Duration(milliseconds: 2600));
  Timer? _typing;
  int _shown = 0;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_typing != null || _shown > 0) return;
    if (MediaQuery.of(context).disableAnimations) {
      _shown = widget.text.length;
      if (widget.turn) _turn.value = 1;
      return;
    }
    if (widget.turn) {
      _turn.forward();
    } else {
      _bob.repeat();
    }
    _caret.repeat();
    // печатать начинает, когда капибара уже выпрыгнула (или повернулась)
    final wait = widget.turn ? 50 : 6;
    _typing = Timer.periodic(Duration(milliseconds: widget.turn ? 70 : 45), (t) {
      if (t.tick < wait) return;
      setState(() => _shown++);
      if (_shown >= widget.text.length) t.cancel();
    });
  }

  @override
  void dispose() {
    _typing?.cancel();
    _turn.dispose();
    _bob.dispose();
    _caret.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final size = math.min(190.0, MediaQuery.sizeOf(context).width * 0.5);
    final style = s.title(24, color: p.text);
    return Semantics(
      label: widget.text,
      button: true,
      hint: 'Закрыть',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => Navigator.of(context).maybePop(),
        child: AnimatedBuilder(
          animation: widget.appear,
          builder: (context, child) {
            final v = widget.appear.value;
            // в браузере без размытия (тормозит) — фон плотнее
            final shade = ColoredBox(
              color: widget.turn
                  ? Colors.black.withValues(alpha: 0.82 * v)
                  : p.bg.withValues(alpha: (kIsWeb ? 0.85 : 0.45) * v),
              child: child,
            );
            if (kIsWeb) return shade;
            return BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 14 * v, sigmaY: 14 * v),
              child: shade,
            );
          },
          child: Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.xxl),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ScaleTransition(
                    scale: CurvedAnimation(parent: widget.appear, curve: Curves.easeOutBack),
                    child: AnimatedBuilder(
                      animation: _bob,
                      builder: (context, child) =>
                          Transform.translate(offset: Offset(0, -7 * math.sin(_bob.value * math.pi)), child: child),
                      child: widget.turn
                          ? CapyTurn(turn: _turn, pose: widget.pose, size: size)
                          : CapyImage(pose: widget.pose, size: size),
                    ),
                  ),
                  const SizedBox(height: Space.l),
                  ExcludeSemantics(
                    // ненапечатанное — прозрачным: строка не прыгает, пока печатается
                    child: Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(text: widget.text.substring(0, _shown)),
                          WidgetSpan(
                            alignment: PlaceholderAlignment.middle,
                            child: FadeTransition(
                              opacity: _caret.drive(
                                TweenSequence([
                                  TweenSequenceItem(tween: ConstantTween(1.0), weight: 1),
                                  TweenSequenceItem(tween: ConstantTween(0.0), weight: 1),
                                ]),
                              ),
                              child: Container(
                                width: 2,
                                height: 24,
                                margin: const EdgeInsets.only(left: 2),
                                color: p.accent,
                              ),
                            ),
                          ),
                          TextSpan(
                            text: widget.text.substring(_shown),
                            style: const TextStyle(color: Colors.transparent),
                          ),
                        ],
                      ),
                      textAlign: TextAlign.center,
                      style: widget.turn ? style.copyWith(color: const Color(0xFFFFE9A8)) : style,
                    ),
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

/// Капибара поворачивается к тебе (сверхредкая фраза): стоит боком, на
/// первой половине уходит в ребро, на второй выходит уже другой стороной и
/// ближе — как будто обернулась и шагнула; сзади разгорается свет.
class CapyTurn extends StatelessWidget {
  final Animation<double> turn;
  final CapyPose pose;
  final double size;
  const CapyTurn({super.key, required this.turn, required this.pose, required this.size});

  static const _glow = Color(0xFFFFE9A8);

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: turn,
    builder: (context, _) {
      final v = turn.value;
      // 0–0.25 — смотрит в сторону, 0.25–0.85 — поворот, дальше — замерла
      final k = Curves.easeInOutCubic.transform(((v - 0.25) / 0.6).clamp(0.0, 1.0));
      final back = k > 0.5; // вторая половина: уже лицом, картинка отражена
      final angle = back ? (k - 1) * math.pi : k * math.pi;
      final near = 1 + 0.28 * k;
      return Stack(
        alignment: Alignment.center,
        children: [
          Opacity(
            opacity: k,
            child: Container(
              width: size * 1.3,
              height: size * 1.3,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(colors: [_glow.withValues(alpha: 0.35), _glow.withValues(alpha: 0)]),
              ),
            ),
          ),
          Transform(
            alignment: Alignment.center,
            transform: Matrix4.identity()
              ..setEntry(3, 2, 0.0018)
              ..scaleByDouble(near, near, 1, 1)
              ..rotateY(angle)
              ..scaleByDouble(back ? -1 : 1, 1, 1, 1),
            child: CapyImage(pose: pose, size: size, color: Color.lerp(Colors.white, _glow, k)),
          ),
        ],
      );
    },
  );
}

/// Радость: капибара подпрыгивает дважды, когда появилась (сдал работу, цель
/// набрана), и ещё раз — если на неё нажать (владелец, 09.10, 17Б).
class CapyHop extends StatefulWidget {
  final CapyPose pose;
  final double size;
  final Color? color;
  const CapyHop({super.key, this.pose = CapyPose.joy, required this.size, this.color});

  @override
  State<CapyHop> createState() => _CapyHopState();
}

class _CapyHopState extends State<CapyHop> with SingleTickerProviderStateMixin {
  late final _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))..forward();

  // высота прыжка в долях роста: большой, приземлился, маленький, приземлился
  static final _jump = TweenSequence<double>([
    TweenSequenceItem(tween: Tween(begin: 0.0, end: 1.0).chain(CurveTween(curve: Curves.easeOut)), weight: 30),
    TweenSequenceItem(tween: Tween(begin: 1.0, end: 0.0).chain(CurveTween(curve: Curves.easeIn)), weight: 25),
    TweenSequenceItem(tween: Tween(begin: 0.0, end: 0.32).chain(CurveTween(curve: Curves.easeOut)), weight: 15),
    TweenSequenceItem(tween: Tween(begin: 0.32, end: 0.0).chain(CurveTween(curve: Curves.easeIn)), weight: 30),
  ]);

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: () {
      tick();
      _c.forward(from: 0);
    },
    child: AnimatedBuilder(
      animation: _c,
      builder: (context, child) {
        final h = _jump.transform(_c.value);
        return Transform.translate(
          offset: Offset(0, -h * widget.size * 0.2),
          child: Transform.rotate(angle: -h * 6 * math.pi / 180, child: child),
        );
      },
      child: CapyImage(pose: widget.pose, size: widget.size, color: widget.color),
    ),
  );
}

/// Грусть («не хватит»): капибара появляется и тихо оседает, один раз.
class CapySigh extends StatelessWidget {
  final double size;
  final Color? color;
  const CapySigh({super.key, required this.size, this.color});

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
    tween: Tween(begin: 0, end: 1),
    duration: const Duration(milliseconds: 900),
    curve: Curves.easeOutCubic,
    builder: (context, v, child) => Opacity(
      opacity: v,
      child: Transform.translate(
        offset: Offset(0, -size * 0.12 * (1 - v)),
        child: Transform.rotate(angle: v * 4 * math.pi / 180, child: child),
      ),
    ),
    child: CapyImage(pose: CapyPose.sad, size: size, color: color),
  );
}

/// В пустых экранах капибара выглядывает снизу из-за края карточки; ночью
/// спит, над ней плывут «z». Нажал — повернулась (владелец, 09.10, 17Г).
class CapyPeek extends StatefulWidget {
  final CapyPose pose;
  final double size;
  final Color? color;

  /// Час для «ночью спит» (в тестах и на стенде — свой).
  final int? hour;
  const CapyPeek({super.key, this.pose = CapyPose.joy, required this.size, this.color, this.hour});

  /// Сколько капибары видно над краем карточки.
  static const shown = 0.8;

  @override
  State<CapyPeek> createState() => _CapyPeekState();
}

class _CapyPeekState extends State<CapyPeek> with TickerProviderStateMixin {
  late final _rise = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..forward();
  AnimationController? _zz;
  bool _turned = false;

  bool get _night {
    final h = widget.hour ?? now().hour;
    return h >= 23 || h < 5;
  }

  @override
  void initState() {
    super.initState();
    _sleep();
  }

  @override
  void didUpdateWidget(CapyPeek old) {
    super.didUpdateWidget(old);
    _sleep();
  }

  /// «z» над спящей — только ночью; наступило утро — перестали.
  void _sleep() {
    if (_night && _zz == null) {
      _zz = AnimationController(vsync: this, duration: const Duration(milliseconds: 2400))
        ..repeat(count: kIsWeb ? 3 : null);
    } else if (!_night && _zz != null) {
      _zz!.dispose();
      _zz = null;
    }
  }

  @override
  void dispose() {
    _rise.dispose();
    _zz?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    final size = widget.size;
    final color = widget.color ?? p.accent;
    const top = 26.0; // место над головой для «z»
    final visible = size * CapyPeek.shown;
    final rise = CurvedAnimation(parent: _rise, curve: Curves.easeOutBack);
    return GestureDetector(
      onTap: () {
        tick();
        setState(() => _turned = !_turned);
      },
      child: ClipRect(
        child: SizedBox(
          width: size + 18,
          height: visible + top,
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              AnimatedBuilder(
                animation: rise,
                builder: (context, child) =>
                    Positioned(left: 0, top: top + (1 - rise.value) * (visible + 4), child: child!),
                child: TweenAnimationBuilder<double>(
                  tween: Tween(end: _turned ? 1 : 0),
                  duration: const Duration(milliseconds: 520),
                  curve: Curves.easeInOutCubic,
                  builder: (context, v, child) => Transform(
                    alignment: Alignment.center,
                    transform: Matrix4.identity()
                      ..setEntry(3, 2, 0.0015)
                      ..rotateY(v * math.pi),
                    child: child,
                  ),
                  child: CapyImage(pose: _night ? CapyPose.night : widget.pose, size: size, color: color),
                ),
              ),
              if (_zz != null)
                for (var k = 0; k < 2; k++)
                  AnimatedBuilder(
                    animation: _zz!,
                    builder: (context, _) {
                      final v = (_zz!.value + k * 0.5) % 1;
                      // вылетают из нарисованных «zzz» над головой и тают вверх-вправо
                      return Positioned(
                        left: size * 0.52 + v * 18,
                        top: top + size * 0.02 - v * 26,
                        child: Opacity(
                          opacity: v < 0.3 ? v / 0.3 : 1 - (v - 0.3) / 0.7,
                          child: Text(
                            'z',
                            style: AppStyle.of(context).body(11 + k * 3.0, weight: FontWeight.w800, color: color),
                          ),
                        ),
                      );
                    },
                  ),
            ],
          ),
        ),
      ),
    );
  }
}

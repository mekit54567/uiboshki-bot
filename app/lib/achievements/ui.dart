// Ачивки на экране (Никита 15.10, вариант Б): значок — небо своего времени
// суток и капибара в той же позе, что на «Сегодня»; экран «Ещё → Ачивки»;
// плашка сверху «Новая ачивка · Посмотреть»; лист ачивки — полароид с
// подписью маркером, «Поделиться» картинкой и «Показать где».
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/common.dart';
import 'captions.dart';
import 'catalog.dart';
import 'store.dart';

/// Навигатор приложения: плашка новой ачивки живёт поверх любого экрана.
final appNavigator = GlobalKey<NavigatorState>();

/// Имя на полароиде — из профиля (оболочка кладёт после /me).
String achName = '';

/// Адрес бота на полароиде и в «Поделиться» — из /api/meta (BOT_USERNAME
/// на сервере), до ответа — нынешний.
String achBot = '@UiboshkiBot';

/// links.bot из /api/meta: «https://t.me/Имя» → «@Имя».
void setAchBot(String? link) {
  final m = RegExp(r't\.me/(\w+)').firstMatch(link ?? '');
  if (m != null) achBot = '@${m.group(1)}';
}

/// «'26 10 15 08:41» — как дата на плёночной мыльнице.
String filmStamp(DateTime d) {
  String two(int v) => v.toString().padLeft(2, '0');
  return "'${two(d.year % 100)} ${two(d.month)} ${two(d.day)} ${two(d.hour)}:${two(d.minute)}";
}

// ── значок ─────────────────────────────────────────────────────────────

/// Круглый значок ранга: небо, солнце или луна и капибара. Закрытая —
/// серая и бледная; закрытая полночная — тёмная, с вопросом.
class RankBadge extends StatelessWidget {
  final Rank rank;
  final double size;
  final bool open;
  const RankBadge({super.key, required this.rank, this.size = 64, this.open = true});

  @override
  Widget build(BuildContext context) {
    if (!open && rank == Rank.midnight) {
      final p = AppStyle.of(context).p;
      return Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: p.line,
          border: Border.all(color: p.line),
        ),
        child: Text(
          '?',
          style: TextStyle(fontSize: size * 0.4, fontWeight: FontWeight.w800, color: p.muted),
        ),
      );
    }
    Widget badge = SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Positioned.fill(child: CustomPaint(painter: _SkyPainter(rank))),
          Positioned(
            top: size * 0.3,
            child: CapyImage(pose: rank.pose, size: size * 0.58, color: rank.ink),
          ),
        ],
      ),
    );
    badge = ClipOval(child: badge);
    if (!open) {
      badge = Opacity(
        opacity: 0.4,
        child: ColorFiltered(
          colorFilter: const ColorFilter.matrix([
            0.33, 0.33, 0.33, 0, 0, //
            0.33, 0.33, 0.33, 0, 0, //
            0.33, 0.33, 0.33, 0, 0, //
            0, 0, 0, 1, 0,
          ]),
          child: badge,
        ),
      );
    }
    return Semantics(label: open ? rank.title : 'Не открыта', child: badge);
  }
}

class _SkyPainter extends CustomPainter {
  final Rank rank;
  _SkyPainter(this.rank);

  @override
  void paint(Canvas canvas, Size size) {
    final r = Offset.zero & size;
    final w = size.width;
    canvas.drawOval(
      r,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: rank.sky,
        ).createShader(r),
    );
    _drawLight(canvas, w, rank, badge: true);
    if (rank == Rank.midnight) {
      // радужная кайма у полночных
      final ring = w * 0.045;
      canvas.drawCircle(
        r.center,
        w / 2 - ring / 2,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = ring
          ..shader = const SweepGradient(
            colors: [Color(0xFF7B5CFF), Color(0xFF29D3C4), Color(0xFFFF7AD9), Color(0xFFFFD36B), Color(0xFF7B5CFF)],
          ).createShader(r),
      );
    }
  }

  @override
  bool shouldRepaint(_SkyPainter old) => old.rank != rank;
}

// ── полароид ───────────────────────────────────────────────────────────

/// Карточка-полароид (Никита 15.10): фото — небо ранга с капибарой, наклейка
/// ранга, дата как на плёнке, кусочек скотча; подпись маркером; внизу имя,
/// сколько собрано и бот. Цвета свои, не темы: картинка уходит в чат.
class Polaroid extends StatelessWidget {
  final Achievement a;
  final DateTime at;
  final String name;
  final int count;
  const Polaroid({super.key, required this.a, required this.at, this.name = '', required this.count});

  static const width = 300.0;

  @override
  Widget build(BuildContext context) {
    const paper = Color(0xFFFDFBF6), muted = Color(0xFF7D776B);
    final caption = polaroidCaptions[a.id] ?? a.title;
    final who = [if (name.isNotEmpty) name, '$count из ${achievements.length}'].join(' · ');
    return SizedBox(
      width: width,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 10),
            padding: const EdgeInsets.fromLTRB(14, 14, 14, 16),
            decoration: BoxDecoration(
              color: paper,
              borderRadius: BorderRadius.circular(6),
              boxShadow: const [BoxShadow(color: Color(0x55000000), blurRadius: 30, offset: Offset(0, 14))],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                AspectRatio(
                  aspectRatio: 1,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(3),
                    child: Stack(
                      children: [
                        Positioned.fill(child: CustomPaint(painter: _PhotoPainter(a.rank))),
                        Align(
                          alignment: const Alignment(0, 0.55),
                          child: CapyImage(pose: a.rank.pose, size: 170, color: a.rank.ink),
                        ),
                        Positioned(
                          left: 10,
                          top: 10,
                          child: Transform.rotate(
                            angle: -6 * math.pi / 180,
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(color: a.rank.sticker, borderRadius: BorderRadius.circular(99)),
                              child: Text(
                                a.rank.title.toUpperCase(),
                                style: const TextStyle(
                                  fontFamily: 'Onest',
                                  fontSize: 11,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: 0.9,
                                  color: Color(0xFF141823),
                                ),
                              ),
                            ),
                          ),
                        ),
                        // дата на тёмной подложке: на светлом небе «Рассвета» не читалась (15.10)
                        Positioned(
                          right: 8,
                          bottom: 8,
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                            decoration: BoxDecoration(
                              color: const Color(0x8C140A05),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              filmStamp(at),
                              // свой шрифт с ровными цифрами: «Courier» есть не везде,
                              // а дата должна читаться на любом телефоне и в вебе
                              style: const TextStyle(
                                fontFamily: 'Onest',
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 1.2,
                                color: Color(0xFFFF9A3C),
                                fontFeatures: [FontFeature.tabularFigures()],
                                shadows: [Shadow(color: Color(0x99FF7A1A), blurRadius: 6)],
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                Transform.rotate(
                  angle: -3 * math.pi / 180,
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(left: 6),
                    child: Text(
                      caption,
                      key: const Key('polaroid:caption'),
                      maxLines: 2,
                      style: const TextStyle(
                        fontFamily: 'Neucha',
                        fontSize: 30,
                        height: 1.05,
                        color: Color(0xFF1D3B8F),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          who,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontFamily: 'Onest', fontSize: 12, color: muted),
                        ),
                      ),
                      Text(
                        achBot,
                        style: const TextStyle(fontFamily: 'Onest', fontSize: 12, color: muted),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          // скотч сверху
          Positioned(
            top: 0,
            left: width / 2 - 45,
            child: Transform.rotate(
              angle: -4 * math.pi / 180,
              child: Container(
                width: 90,
                height: 22,
                decoration: const BoxDecoration(
                  color: Color(0xCCF3D98A),
                  boxShadow: [BoxShadow(color: Color(0x22000000), blurRadius: 2, offset: Offset(0, 1))],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Фото полароида — то же небо, что у значка, только квадратом.
class _PhotoPainter extends CustomPainter {
  final Rank rank;
  _PhotoPainter(this.rank);

  @override
  void paint(Canvas canvas, Size size) {
    final r = Offset.zero & size;
    canvas.drawRect(
      r,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: rank.sky,
        ).createShader(r),
    );
    // солнце или луна — из значка, растянутые на квадрат (без каймы)
    canvas.save();
    canvas.clipRect(r);
    _drawLight(canvas, size.width, rank, badge: false);
    canvas.restore();
  }

  @override
  bool shouldRepaint(_PhotoPainter old) => old.rank != rank;
}

/// Солнце, закат или луна со звёздами: на значке и на фото полароида.
void _drawLight(Canvas canvas, double w, Rank rank, {required bool badge}) {
  final glow = Paint()..maskFilter = MaskFilter.blur(BlurStyle.normal, w * 0.08);
  switch (rank) {
    case Rank.dawn: // встаёт солнце
      final c = Offset(w * 0.5, w * 1.0);
      canvas.drawCircle(c, w * 0.3, glow..color = const Color(0xFFFFE1A6));
      canvas.drawCircle(c, w * 0.23, Paint()..color = const Color(0xFFFFF4D6));
    case Rank.noon: // солнце в зените
      final c = badge ? Offset(w * 0.75, w * 0.23) : Offset(w * 0.78, w * 0.2);
      final k = badge ? 0.13 : 0.09;
      canvas.drawCircle(c, w * (k + 0.04), glow..color = const Color(0xAAFFF3B0));
      canvas.drawCircle(c, w * k, Paint()..color = const Color(0xFFFFF3B0));
    case Rank.dusk: // закат
      final c = Offset(w * 0.5, w * (badge ? 0.72 : 0.78));
      canvas.drawCircle(c, w * 0.26, glow..color = const Color(0x99FF9A5A));
      canvas.drawCircle(c, w * 0.2, Paint()..color = const Color(0xFFFFCF7A));
    case Rank.midnight: // луна и звёзды
      final star = Paint()..color = Colors.white;
      if (badge) {
        for (final (x, y, k) in const [(0.25, 0.25, 1.0), (0.6, 0.15, 0.7), (0.18, 0.6, 0.6), (0.85, 0.55, 0.6)]) {
          canvas.drawCircle(Offset(w * x, w * y), w * 0.018 * k, star);
        }
      } else {
        final rnd = math.Random(13); // одни и те же звёзды на каждой карточке
        for (var i = 0; i < 26; i++) {
          final at = Offset(w * rnd.nextDouble(), w * 0.7 * rnd.nextDouble());
          canvas.drawCircle(at, w * (0.003 + 0.004 * rnd.nextDouble()), star);
        }
      }
      final m = badge ? Offset(w * 0.74, w * 0.27) : Offset(w * 0.76, w * 0.22);
      final k = badge ? 0.12 : 0.09;
      canvas.saveLayer(Offset.zero & Size(w, w), Paint());
      canvas.drawCircle(m, w * k, Paint()..color = const Color(0xFFFFE9A8));
      canvas.drawCircle(m + Offset(-w * k / 2, -w * k / 4), w * k * 0.92, Paint()..blendMode = BlendMode.clear);
      canvas.restore();
  }
}

/// Полароид картинкой и системное «Поделиться» (на iPhone — Telegram,
/// фото, сторис; в вебе — Web Share или скачивание).
Future<void> sharePolaroid(GlobalKey key, Achievement a, {Rect? origin}) async {
  final box = key.currentContext?.findRenderObject();
  if (box is! RenderRepaintBoundary) return;
  final image = await box.toImage(pixelRatio: 3);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  if (data == null) return;
  final file = 'kapibara-${a.id}.png';
  await SharePlus.instance.share(
    ShareParams(
      files: [XFile.fromData(data.buffer.asUint8List(), mimeType: 'image/png', name: file)],
      fileNameOverrides: [file],
      text: 'Ачивка «${a.title}» в Капибаре · $achBot',
      sharePositionOrigin: origin,
    ),
  );
}

// ── лист ачивки ────────────────────────────────────────────────────────

Future<void> showAchievement(BuildContext context, Achievement a) =>
    appSheet<void>(context, (_) => AchievementSheet(a: a));

class AchievementSheet extends StatefulWidget {
  final Achievement a;
  const AchievementSheet({super.key, required this.a});

  @override
  State<AchievementSheet> createState() => _AchievementSheetState();
}

class _AchievementSheetState extends State<AchievementSheet> {
  final _card = GlobalKey();
  final _shareBtn = GlobalKey();
  bool _sharing = false;

  Future<void> _share() async {
    tick();
    setState(() => _sharing = true);
    final b = _shareBtn.currentContext?.findRenderObject() as RenderBox?;
    final origin = b == null ? null : b.localToGlobal(Offset.zero) & b.size;
    try {
      await sharePolaroid(_card, widget.a, origin: origin);
    } catch (_) {
      if (mounted) showToast(context, 'Не получилось поделиться', kind: ToastKind.error);
    } finally {
      if (mounted) setState(() => _sharing = false);
    }
  }

  /// «Показать где»: закрыть всё до вкладок, открыть нужную и подсказать.
  void _where() {
    final place = widget.a.place;
    if (place == null) return;
    tick();
    final nav = appNavigator.currentState ?? Navigator.of(context);
    nav.popUntil((r) => r.isFirst);
    AchStore.openTab?.call(place.tab);
    final overlay = nav.overlay;
    if (overlay != null) toastOn(overlay, place.hint);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final a = widget.a;
    final at = AchStore.got.value[a.id];
    final open = at != null;
    final how = a.secret && !open ? 'Секрет. Как получить — не скажу' : a.how;
    final buttons = <Widget>[
      if (open)
        FilledButton.icon(
          key: _shareBtn,
          style: FilledButton.styleFrom(
            backgroundColor: p.accent,
            foregroundColor: p.onAccent,
            minimumSize: const Size.fromHeight(50),
            shape: const StadiumBorder(),
          ),
          onPressed: _sharing ? null : _share,
          icon: const Icon(Icons.ios_share_rounded, size: 20),
          label: const Text('Поделиться'),
        ),
      if (a.place != null && !(a.secret && !open)) ...[
        if (open) const SizedBox(height: Space.s),
        (open ? OutlinedButton.new : FilledButton.new)(
          key: const Key('ach:where'),
          style: open
              ? OutlinedButton.styleFrom(
                  foregroundColor: p.text,
                  side: BorderSide(color: p.line),
                  minimumSize: const Size.fromHeight(50),
                  shape: const StadiumBorder(),
                )
              : FilledButton.styleFrom(
                  backgroundColor: p.accent,
                  foregroundColor: p.onAccent,
                  minimumSize: const Size.fromHeight(50),
                  shape: const StadiumBorder(),
                ),
          onPressed: _where,
          child: const Text('Показать где'),
        ),
      ],
    ];
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (open)
              Center(
                child: FittedBox(
                  child: Padding(
                    padding: const EdgeInsets.all(Space.m),
                    child: RepaintBoundary(
                      key: _card,
                      child: Polaroid(a: a, at: at, name: achName, count: AchStore.got.value.length),
                    ),
                  ),
                ),
              )
            else
              Center(child: RankBadge(rank: a.rank, size: 96, open: false)),
            const SizedBox(height: Space.l),
            Text('${a.rank.title} · ${a.title}', style: s.title(24), textAlign: TextAlign.center),
            const SizedBox(height: Space.s),
            Text(
              how,
              style: s.body(15, color: p.muted),
              textAlign: TextAlign.center,
            ),
            if (buttons.isNotEmpty) ...[const SizedBox(height: Space.xl), ...buttons],
          ],
        ),
      ),
    );
  }
}

// ── экран «Ачивки» ─────────────────────────────────────────────────────

class AchievementsScreen extends StatelessWidget {
  const AchievementsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Scaffold(
      body: Backdrop(
        child: SafeArea(
          child: ValueListenableBuilder(
            valueListenable: AchStore.got,
            builder: (context, got, _) => ListView(
              padding: const EdgeInsets.only(bottom: Space.xxl),
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(left: Space.s),
                    child: IconButton(
                      onPressed: () => Navigator.pop(context),
                      icon: Icon(Icons.arrow_back_ios_new_rounded, size: 20, color: p.text),
                    ),
                  ),
                ),
                ScreenTitle(title: 'Ачивки', sub: '${got.length} из ${achievements.length}'),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.xl),
                  child: _Bar(value: got.length / achievements.length),
                ),
                for (final rank in Rank.values) _RankSection(rank: rank, got: got),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Bar extends StatelessWidget {
  final double value;
  const _Bar({required this.value});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    return ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: LinearProgressIndicator(value: value, minHeight: 6, color: p.accent, backgroundColor: p.line),
    );
  }
}

class _RankSection extends StatelessWidget {
  final Rank rank;
  final Map<String, DateTime> got;
  const _RankSection({required this.rank, required this.got});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final list = [
      for (final a in achievements)
        if (a.rank == rank) a,
    ];
    final have = list.where((a) => got.containsKey(a.id)).length;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.xl, Space.l, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.s),
            child: Row(
              children: [
                RankBadge(rank: rank, size: 30),
                const SizedBox(width: Space.m),
                Text(rank.title, style: s.title(22)),
                const Spacer(),
                Text('$have из ${list.length}', style: s.body(14, color: p.muted)),
              ],
            ),
          ),
          if (rank == Rank.midnight)
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.s, Space.xs, Space.s, 0),
              child: Text('Секретные: как получить, видно, когда найдёшь', style: s.body(13, color: p.muted)),
            ),
          const SizedBox(height: Space.m),
          LayoutBuilder(
            builder: (context, box) {
              final cols = box.maxWidth >= 520 ? 5 : (box.maxWidth >= 300 ? 3 : 2);
              final w = (box.maxWidth - (cols - 1) * Space.s) / cols;
              return Wrap(
                spacing: Space.s,
                runSpacing: Space.s,
                children: [
                  for (final a in list)
                    SizedBox(
                      width: w,
                      child: _AchTile(a: a, open: got.containsKey(a.id)),
                    ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

class _AchTile extends StatelessWidget {
  final Achievement a;
  final bool open;
  const _AchTile({required this.a, required this.open});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Semantics(
      button: true,
      label: '${a.title}, ${open ? 'открыта' : 'не открыта'}',
      excludeSemantics: true,
      child: Tile(
        key: Key('ach:${a.id}'),
        padding: const EdgeInsets.fromLTRB(Space.s, Space.m, Space.s, Space.m),
        onTap: () => showAchievement(context, a),
        child: Column(
          children: [
            RankBadge(rank: a.rank, size: 56, open: open),
            const SizedBox(height: Space.s),
            Text(
              a.title,
              maxLines: 2,
              textAlign: TextAlign.center,
              overflow: TextOverflow.ellipsis,
              style: s.body(12.5, weight: FontWeight.w600, color: open ? s.p.text : s.p.muted),
            ),
          ],
        ),
      ),
    );
  }
}

/// Строка «Ачивки · 3 из 25» в «Ещё»: последние открытые значки и полоска.
class AchievementsRow extends StatelessWidget {
  const AchievementsRow({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return ValueListenableBuilder(
      valueListenable: AchStore.got,
      builder: (context, got, _) {
        final last = (got.entries.toList()..sort((a, b) => b.value.compareTo(a.value)))
            .take(3)
            .map((e) => achievementById(e.key)!)
            .toList();
        return Tile(
          key: const Key('more:achievements'),
          onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const AchievementsScreen())),
          child: Row(
            children: [
              SizedBox(
                width: 36.0 + 18 * math.max(0, last.length - 1),
                height: 36,
                child: Stack(
                  children: [
                    if (last.isEmpty) const RankBadge(rank: Rank.dawn, size: 36, open: false),
                    for (final (i, a) in last.reversed.indexed)
                      Positioned(
                        left: 18.0 * (last.length - 1 - i),
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border: Border.all(color: p.cardSolid, width: 2),
                          ),
                          child: RankBadge(rank: a.rank, size: 36),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: Space.m),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text('Ачивки', style: s.body(15, weight: FontWeight.w700)),
                        const Spacer(),
                        Text('${got.length} из ${achievements.length}', style: s.body(13, color: p.muted)),
                      ],
                    ),
                    const SizedBox(height: 6),
                    _Bar(value: got.length / achievements.length),
                  ],
                ),
              ),
              const SizedBox(width: Space.s),
              Icon(Icons.chevron_right_rounded, color: p.muted),
            ],
          ),
        );
      },
    );
  }
}

// ── плашка новой ачивки ────────────────────────────────────────────────

OverlayEntry? _banner;

/// Плашки новых ачивок; тесты выключают (test/flutter_test_config.dart), чтобы
/// плашка не закрывала кнопки внизу экрана.
bool achBanners = true;

/// Плашка «Новая ачивка» с «Посмотреть» — поверх любого экрана, снизу над
/// меню, как остальные плашки. Сверху она закрывала «назад» и стрелки недели
/// (робот-проверка 16.10): ачивка открывается ровно тогда, когда человек там
/// нажимает. Снизу «Посмотреть» и под большим пальцем.
void showUnlockBanner(Achievement a) {
  final overlay = appNavigator.currentState?.overlay;
  if (!achBanners || overlay == null || !overlay.mounted) return;
  _banner?.remove();
  late final OverlayEntry entry;
  entry = OverlayEntry(
    builder: (_) => UnlockBanner(
      a: a,
      onGone: () {
        if (identical(_banner, entry)) {
          _banner = null;
          entry.remove();
        }
      },
      onOpen: () {
        final ctx = appNavigator.currentState?.overlay?.context;
        if (ctx != null) showAchievement(ctx, a);
      },
    ),
  );
  _banner = entry;
  overlay.insert(entry);
  // в браузере вибрация без касания — ошибка в консоли (ачивка бывает от ответа API)
  if (!kIsWeb) HapticFeedback.mediumImpact();
}

class UnlockBanner extends StatefulWidget {
  final Achievement a;
  final VoidCallback onGone, onOpen;
  const UnlockBanner({super.key, required this.a, required this.onGone, required this.onOpen});

  @override
  State<UnlockBanner> createState() => _UnlockBannerState();
}

class _UnlockBannerState extends State<UnlockBanner> with SingleTickerProviderStateMixin {
  late final _life = AnimationController(vsync: this, duration: const Duration(milliseconds: 5200));

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

  void _open() {
    _life.stop();
    widget.onGone();
    widget.onOpen();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final mq = MediaQuery.of(context);
    final a = widget.a;
    // над плашкой, если она есть; при клавиатуре — ещё и над полем ввода
    final base = aboveCapsule(mq) + (mq.viewInsets.bottom > 0 ? 64 : 0);
    return ValueListenableBuilder<bool>(
      valueListenable: toastShown,
      builder: (context, toast, child) =>
          Positioned(left: Space.l, right: Space.l, bottom: base + (toast ? 64 : 0), child: child!),
      child: AnimatedBuilder(
        animation: _life,
        builder: (context, child) {
          final v = _life.value;
          final inV = Curves.easeOutBack.transform((v / 0.07).clamp(0.0, 1.0));
          final outV = Curves.easeIn.transform(((v - 0.94) / 0.06).clamp(0.0, 1.0));
          if (mq.disableAnimations) return Opacity(opacity: 1 - outV, child: child);
          return Opacity(
            opacity: (1 - outV).clamp(0.0, 1.0),
            child: Transform.translate(offset: Offset(0, 40 * (1 - inV) + 20 * outV), child: child),
          );
        },
        child: Semantics(
          liveRegion: true,
          child: Material(
            type: MaterialType.transparency,
            child: GestureDetector(
              key: const Key('ach:banner'),
              onTap: _open,
              onVerticalDragEnd: (_) => widget.onGone(),
              child: Container(
                padding: const EdgeInsets.fromLTRB(Space.m, Space.m, Space.l, Space.m),
                decoration: BoxDecoration(
                  color: p.cardSolid,
                  borderRadius: BorderRadius.circular(Radii.tile),
                  border: Border.all(color: p.line),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: p.dark ? 0.45 : 0.16),
                      blurRadius: 24,
                      offset: const Offset(0, 8),
                    ),
                  ],
                ),
                child: Row(
                  children: [
                    RankBadge(rank: a.rank, size: 44),
                    const SizedBox(width: Space.m),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Новая ачивка · ${a.rank.title}', style: s.body(12, color: p.muted)),
                          const SizedBox(height: 2),
                          Text(a.title, style: s.body(16, weight: FontWeight.w700)),
                        ],
                      ),
                    ),
                    Text(
                      'Посмотреть',
                      style: s.body(14, weight: FontWeight.w700, color: p.accent),
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

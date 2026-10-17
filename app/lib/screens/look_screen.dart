// «Оформление» (5.79, второй круг дизайна, Никита 12.10): все настройки вида
// в одном экране — сверху живой пример, ниже выборы группами. По умолчанию
// всё как было; «Вернуть как было» убирает новое разом. Сервер может
// выключить экран целиком (features.design2) — тогда в «Ещё» старый лист
// «Тема и шрифт».
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../achievements/store.dart';
import '../api/models.dart';
import '../theme/app_icon.dart';
import '../theme/app_theme.dart';
import '../theme/look.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/cheer.dart';
import '../widgets/common.dart';
import 'files.dart' show BackRow;
import 'today.dart' show LessonCard, LessonList;

class LookScreen extends StatelessWidget {
  final ValueChanged<FontChoice> onFont;
  final ValueChanged<ThemeChoice>? onTheme;
  final ValueChanged<Look>? onLook;
  const LookScreen({super.key, required this.onFont, this.onTheme, this.onLook});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final look = s.look;
    void set(Look l) {
      tick();
      onLook?.call(l);
    }

    final sun = moscowSun(now());
    String hm(DateTime t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
    final changed = look != Look.classic || s.font.index > 1 || s.theme == ThemeChoice.sunset;

    return Scaffold(
      body: Backdrop(
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.only(bottom: Space.xxl),
            children: [
              const BackRow(),
              const ScreenTitle(title: 'Оформление'),
              const Padding(padding: EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, 0), child: _Preview()),

              const Section('когда тёмная'),
              _Pad(
                _Seg<ThemeChoice>(
                  id: 'theme',
                  value: s.theme,
                  items: const [
                    (ThemeChoice.system, 'Как в телефоне'),
                    (ThemeChoice.sunset, 'По закату'),
                    (ThemeChoice.light, 'Светлая'),
                    (ThemeChoice.dark, 'Тёмная'),
                  ],
                  onPick: onTheme == null ? null : (t) => onTheme!(t),
                ),
              ),
              if (s.theme == ThemeChoice.sunset)
                _Hint('Сегодня тёмная с ${hm(sun.set)} до ${hm(sun.rise)} завтра, за час до заката фон мягко темнеет.'),

              const Section('светлая тема'),
              _Pad(
                Row(
                  children: [
                    for (final t in LightTheme.values) ...[
                      if (t != LightTheme.values.first) const SizedBox(width: Space.s),
                      Expanded(
                        child: _Swatch(
                          key: Key('look:light:${t.name}'),
                          palette: Palette.ofLight(t),
                          paper: t == LightTheme.notebook ? look.paper : Paper.smooth,
                          title: t == LightTheme.notebook ? 'Тетрадь' : 'Кампус',
                          sub: t == LightTheme.notebook ? 'тёплая бумага' : 'белая, синий акцент',
                          selected: look.light == t,
                          onTap: () => set(look.copyWith(light: t)),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (look.light == LightTheme.notebook) ...[
                const SizedBox(height: Space.s),
                _Pad(
                  _Seg<Paper>(
                    id: 'paper',
                    value: look.paper,
                    items: const [
                      (Paper.smooth, 'Гладкая'),
                      (Paper.cell, 'Клетка'),
                      (Paper.line, 'Линейка'),
                      (Paper.dots, 'Точки'),
                      (Paper.grid, 'Милли­метровка'),
                    ],
                    onPick: (v) => onLook?.call(look.copyWith(paper: v)),
                    small: true,
                  ),
                ),
              ],

              const Section('тёмная тема'),
              _Pad(
                Row(
                  children: [
                    for (final t in DarkTheme.values) ...[
                      if (t != DarkTheme.values.first) const SizedBox(width: Space.s),
                      Expanded(
                        child: _Swatch(
                          key: Key('look:dark:${t.name}'),
                          palette: Palette.ofDark(t),
                          paper: Paper.smooth,
                          title: t == DarkTheme.depth ? 'Глубина' : 'Библиотека',
                          sub: t == DarkTheme.depth ? 'синее свечение' : 'тёмно-зелёная',
                          selected: look.dark == t,
                          onTap: () => set(look.copyWith(dark: t)),
                        ),
                      ),
                    ],
                  ],
                ),
              ),

              const Section('шрифт заголовков'),
              _Pad(
                GridView.count(
                  crossAxisCount: 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  mainAxisSpacing: Space.s,
                  crossAxisSpacing: Space.s,
                  childAspectRatio: 1.9,
                  children: [
                    for (final f in FontChoice.values)
                      _FontCard(
                        choice: f,
                        selected: s.font == f,
                        onTap: () {
                          tick();
                          onFont(f);
                        },
                      ),
                  ],
                ),
              ),

              const Section('пары на «сегодня»'),
              _Pad(
                _Seg<DayView>(
                  id: 'day',
                  value: look.day,
                  items: const [(DayView.cards, 'Карточками'), (DayView.rows, 'Строками')],
                  onPick: (v) => onLook?.call(look.copyWith(day: v)),
                ),
              ),
              if (look.day == DayView.cards) ...[
                const SizedBox(height: Space.s),
                _Pad(
                  _Seg<CardStyle>(
                    id: 'card',
                    value: look.card,
                    items: const [(CardStyle.tint, 'С цветом'), (CardStyle.stripe, 'С полоской')],
                    onPick: (v) => onLook?.call(look.copyWith(card: v)),
                  ),
                ),
              ],

              const Section('когда отметил «сдано»'),
              _Pad(
                _Seg<Cheer>(
                  id: 'cheer',
                  value: look.cheer,
                  items: const [(Cheer.quiet, 'Тихо'), (Cheer.capy, 'Капибара'), (Cheer.confetti, 'Конфетти')],
                  onPick: (v) {
                    onLook?.call(look.copyWith(cheer: v));
                    // сразу показать, как это будет (после перестройки темы)
                    WidgetsBinding.instance.addPostFrameCallback((_) {
                      if (context.mounted) cheer(context);
                    });
                  },
                ),
              ),

              // иконка на телефоне (5.79; картинки — 5.84) — только в приложении
              // на Android и iPhone. В «Оформлении» одна строка, все — листом.
              if (appIconSupported) ...[
                const Section('иконка приложения'),
                _Pad(
                  _IconRow(
                    icon: look.icon,
                    dark: _iconDark(context, look),
                    onPick: (i) => set(look.copyWith(icon: i)),
                  ),
                ),
                if (defaultTargetPlatform == TargetPlatform.android && look.icon.art) ...[
                  const SizedBox(height: Space.s),
                  _Pad(
                    _Seg<_Shade>(
                      id: 'icon-shade',
                      value: look.iconDark ? _Shade.dark : _Shade.light,
                      items: const [(_Shade.light, 'Светлая'), (_Shade.dark, 'Тёмная')],
                      onPick: (v) => set(look.copyWith(iconDark: v == _Shade.dark)),
                    ),
                  ),
                ],
                if (defaultTargetPlatform == TargetPlatform.android)
                  const _Hint('На Android ярлык на рабочем столе может переставиться.')
                else if (look.icon.art)
                  const _Hint('В тёмной теме iPhone (iOS 18) иконка сама станет тёмной.'),
              ],

              if (changed) ...[
                const SizedBox(height: Space.xl),
                Center(
                  child: TextButton.icon(
                    key: const Key('look:reset'),
                    onPressed: () {
                      tick();
                      onLook?.call(Look.classic);
                      if (s.font.index > 1) onFont(FontChoice.book);
                      if (s.theme == ThemeChoice.sunset) onTheme?.call(ThemeChoice.system);
                    },
                    icon: Icon(Icons.undo_rounded, color: p.muted),
                    label: Text('Вернуть как было', style: s.body(15, color: p.muted)),
                  ),
                ),
              ],

              // виджеты рабочего стола — одной строкой, без отдельного экрана
              if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) ...[
                const SizedBox(height: Space.l),
                const _Hint('Виджеты: долгое нажатие на рабочем столе → Виджеты → Капибара'),
              ] else if (!kIsWeb && defaultTargetPlatform == TargetPlatform.iOS) ...[
                const SizedBox(height: Space.l),
                const _Hint('Виджеты: долгое нажатие на рабочем столе → «+» → Капибара'),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Pad extends StatelessWidget {
  final Widget child;
  const _Pad(this.child);

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: Space.l),
    child: child,
  );
}

class _Hint extends StatelessWidget {
  final String text;
  const _Hint(this.text);

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.xl, Space.s, Space.xl, 0),
      child: Text(text, style: s.body(13, color: s.p.muted)),
    );
  }
}

/// Живой пример: фон темы (с бумагой), заголовок выбранным шрифтом и пары
/// так, как они будут на «Сегодня».
class _Preview extends StatelessWidget {
  const _Preview();

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final t = now();
    final day = DateTime(t.year, t.month, t.day);
    String hm(DateTime x) => '${x.hour.toString().padLeft(2, '0')}:${x.minute.toString().padLeft(2, '0')}';
    Lesson at(int h, int m, String title, String kind, String room, String teacher, String n) {
      final a = day.add(Duration(hours: h, minutes: m));
      final b = a.add(const Duration(minutes: 90));
      return Lesson(
        start: hm(a),
        end: hm(b),
        title: title,
        kind: kind,
        room: room,
        teacher: teacher,
        status: '',
        number: n,
        startAt: a,
        endAt: b,
      );
    }

    final lessons = [
      at(9, 0, 'Анализ данных', 'лекция', 'А-332 (МП-1)', 'Иванова А. С.', '1'),
      at(10, 40, 'Основы предпринимательства', 'практика', 'Г-412 (МП-1)', '', '2'),
    ];
    // «сейчас» — середина первой пары, чтобы было видно, как выглядит идущая
    final now0 = day.add(const Duration(hours: 9, minutes: 40));
    return ClipRRect(
      borderRadius: BorderRadius.circular(Radii.tile),
      child: DecoratedBox(
        position: DecorationPosition.foreground,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(Radii.tile),
          border: Border.all(color: p.line),
        ),
        child: Backdrop(
          child: Padding(
            padding: const EdgeInsets.all(Space.m),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Идёт первая пара', style: s.title(26)),
                const SizedBox(height: Space.m),
                if (s.look.day == DayView.rows)
                  LessonList(lessons: lessons, at: now0)
                else
                  for (final l in lessons)
                    Padding(
                      padding: const EdgeInsets.only(bottom: Space.s),
                      child: LessonCard(lesson: l, at: now0),
                    ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Выбор из нескольких — капсулами в ряд, выбранная залита акцентом.
class _Seg<T extends Enum> extends StatelessWidget {
  final String id;
  final T value;
  final List<(T, String)> items;
  final ValueChanged<T>? onPick;
  final bool small;
  const _Seg({required this.id, required this.value, required this.items, required this.onPick, this.small = false});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final r = BorderRadius.circular(Radii.chip);
    return Wrap(
      spacing: Space.s,
      runSpacing: Space.s,
      children: [
        for (final (v, label) in items)
          Semantics(
            selected: v == value,
            button: true,
            child: Material(
              color: v == value ? p.accent : p.card,
              shape: RoundedRectangleBorder(
                borderRadius: r,
                side: BorderSide(color: v == value ? p.accent : p.line),
              ),
              child: InkWell(
                key: Key('look:$id:${v.name}'),
                borderRadius: r,
                onTap: onPick == null || v == value
                    ? null
                    : () {
                        tick();
                        onPick!(v);
                      },
                child: Padding(
                  padding: EdgeInsets.symmetric(horizontal: small ? 12 : 14, vertical: small ? 8 : 10),
                  child: Text(
                    label,
                    style: s.body(
                      small ? 13.5 : 14.5,
                      weight: FontWeight.w600,
                      color: v == value ? p.onAccent : p.text,
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// Тема образцом: её фон, карточка, акцент и строки текста.
class _Swatch extends StatelessWidget {
  final Palette palette;
  final Paper paper;
  final String title, sub;
  final bool selected;
  final VoidCallback onTap;
  const _Swatch({
    super.key,
    required this.palette,
    required this.paper,
    required this.title,
    required this.sub,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final q = palette;
    final r = BorderRadius.circular(Radii.tile);
    Widget bar(double w, Color c) => Container(
      width: w,
      height: 6,
      decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(3)),
    );
    return Semantics(
      selected: selected,
      button: true,
      child: InkWell(
        borderRadius: r,
        onTap: selected ? null : onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            borderRadius: r,
            border: Border.all(color: selected ? p.accent : p.line, width: selected ? 2 : 1),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(Radii.tile - 4),
                child: Container(
                  height: 78,
                  color: q.bg,
                  child: Stack(
                    children: [
                      if (paper != Paper.smooth)
                        Positioned.fill(child: CustomPaint(painter: PaperPainter(paper, q.text))),
                      Positioned(
                        left: 10,
                        right: 10,
                        top: 12,
                        child: Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color: q.dark ? q.cardSolid : q.card,
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: q.line),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              bar(54, q.text),
                              const SizedBox(height: 5),
                              bar(34, q.muted),
                              const SizedBox(height: 7),
                              Row(
                                children: [
                                  Container(
                                    width: 22,
                                    height: 8,
                                    decoration: BoxDecoration(color: q.accent, borderRadius: BorderRadius.circular(4)),
                                  ),
                                  const SizedBox(width: 4),
                                  Container(
                                    width: 8,
                                    height: 8,
                                    decoration: BoxDecoration(color: q.ok, shape: BoxShape.circle),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(6, 8, 6, 4),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: s.body(14.5, weight: FontWeight.w600)),
                    Text(sub, style: s.body(12, color: p.muted)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Шрифт заголовков образцом «Аа 73» — самим шрифтом.
class _FontCard extends StatelessWidget {
  final FontChoice choice;
  final bool selected;
  final VoidCallback onTap;
  const _FontCard({required this.choice, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final (family, weight, size, title, sub) = switch (choice) {
      FontChoice.book => ('SourceSerif', FontWeight.w500, 26.0, 'Книжный', 'с засечками'),
      FontChoice.strict => ('Onest', FontWeight.w800, 26.0, 'Строгий', 'ровный'),
      FontChoice.hand => ('Neucha', FontWeight.w400, 28.0, 'Рукописный', 'как от руки'),
      FontChoice.wide => ('Unbounded', FontWeight.w500, 21.0, 'Широкий', 'плакатный'),
    };
    return Semantics(
      selected: selected,
      button: true,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(Radii.tile),
          border: Border.all(color: selected ? p.accent : Colors.transparent, width: 2),
        ),
        child: Tile(
          key: Key('look:font:${choice.name}'),
          onTap: selected ? null : onTap,
          padding: const EdgeInsets.symmetric(horizontal: Space.m, vertical: 10),
          child: Row(
            children: [
              Text(
                'Аа',
                style: TextStyle(fontFamily: family, fontSize: size, fontWeight: weight, color: p.text, height: 1),
              ),
              const SizedBox(width: Space.s),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: s.body(14, weight: FontWeight.w600),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      sub,
                      style: s.body(12, color: p.muted),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

enum _Shade { light, dark }

/// Какую версию иконки-картинки показывать образцом: на Android — выбранную,
/// на iPhone — по теме телефона (её подставляет сама iOS 18).
bool _iconDark(BuildContext context, Look look) => defaultTargetPlatform == TargetPlatform.android
    ? look.iconDark
    : MediaQuery.platformBrightnessOf(context) == Brightness.dark;

/// Строка «иконка приложения»: нынешняя и «Выбрать» — все листом.
class _IconRow extends StatelessWidget {
  final AppIcon icon;
  final bool dark;
  final ValueChanged<AppIcon> onPick;
  const _IconRow({required this.icon, required this.dark, required this.onPick});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Material(
      color: p.cardSolid,
      borderRadius: BorderRadius.circular(Radii.tile),
      child: InkWell(
        key: const Key('look:icon'),
        borderRadius: BorderRadius.circular(Radii.tile),
        onTap: () async {
          final picked = await appSheet<AppIcon>(context, (_) => IconPicker(current: icon, dark: dark));
          if (picked != null && picked != icon) onPick(picked);
        },
        child: Padding(
          padding: const EdgeInsets.all(Space.m),
          child: Row(
            children: [
              SizedBox(
                width: 52,
                child: IconArt(icon: icon, dark: dark),
              ),
              const SizedBox(width: Space.m),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(icon.label, style: s.body(16, weight: FontWeight.w600)),
                    Text('${AppIcon.choosable.length} на выбор', style: s.body(13, color: p.muted)),
                  ],
                ),
              ),
              Text('Выбрать', style: s.body(15, color: p.accent)),
              Icon(Icons.chevron_right_rounded, color: p.accent),
            ],
          ),
        ),
      ),
    );
  }
}

/// Лист со всеми иконками по группам, по четыре в ряд. Нажал — выбрал.
class IconPicker extends StatelessWidget {
  final AppIcon current;
  final bool dark;
  const IconPicker({super.key, required this.current, required this.dark});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final all = AppIcon.choosable;
    return ValueListenableBuilder<Map<String, DateTime>>(
      valueListenable: AchStore.got,
      builder: (context, got, _) => _grid(context, s, all, got),
    );
  }

  /// Закрытая: как открыть (5.91) — своей плашкой, не системным окном.
  void _howTo(BuildContext context, AppIcon i) => showToast(context, i.howToOpen);

  Widget _grid(BuildContext context, AppStyle s, List<AppIcon> all, Map<String, DateTime> got) {
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.86,
      child: CustomScrollView(
        key: const Key('look:icons'),
        slivers: [
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.s),
            sliver: SliverToBoxAdapter(child: Text('Иконка приложения', style: s.title(24))),
          ),
          for (final g in [classicGroup, ...artGroups]) ...[
            SliverToBoxAdapter(child: Section(g)),
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: Space.l),
              sliver: SliverGrid.count(
                crossAxisCount: 4,
                mainAxisSpacing: Space.s,
                crossAxisSpacing: Space.s,
                childAspectRatio: 0.68,
                children: [
                  for (final i in all)
                    if (i.group == g)
                      _IconTile(
                        icon: i,
                        dark: dark,
                        selected: i == current,
                        locked: !i.isOpen(got),
                        onTap: () => i.isOpen(got) ? Navigator.of(context).pop(i) : _howTo(context, i),
                      ),
                ],
              ),
            ),
          ],
          SliverToBoxAdapter(child: SizedBox(height: Space.xl + MediaQuery.paddingOf(context).bottom)),
        ],
      ),
    );
  }
}

/// Иконка образцом: картинка (5.84) или нарисованная кодом (как в
/// tools/app_icons.py: фон и капибара на мяче, 82 % по центру; «Из-за
/// страницы» — крупнее, низ под листом). Скругление — как у iOS.
class IconArt extends StatelessWidget {
  final AppIcon icon;
  final bool dark;
  const IconArt({super.key, required this.icon, this.dark = false});

  @override
  Widget build(BuildContext context) => AspectRatio(
    aspectRatio: 1,
    child: LayoutBuilder(
      builder: (context, box) {
        final w = box.maxWidth;
        return ClipRRect(
          borderRadius: BorderRadius.circular(w * 0.225),
          child: icon.art
              ? Image.asset(
                  icon.preview(dark: dark),
                  fit: BoxFit.cover,
                  filterQuality: FilterQuality.medium,
                )
              : DecoratedBox(decoration: icon.background, child: _art(w)),
        );
      },
    ),
  );

  Widget _art(double w) {
    if (icon != AppIcon.page) {
      return Center(
        child: CapyImage(size: w * 0.8164, color: icon.capy),
      );
    }
    // как в tools/app_icons.py: маска 0.96 от иконки с отступом сверху 0.06,
    // край листа на 0.60; между лапами и мячом над листом — сплошное тело
    final c = w * 0.96, x = w * 0.02, y = w * 0.06, edge = w * 0.6;
    final bodyTop = y + c * 100 / 256;
    return Stack(
      children: [
        Positioned(
          left: x + c * 42 / 256,
          width: c * 124 / 256,
          top: bodyTop,
          height: edge - bodyTop,
          child: ColoredBox(color: icon.capy),
        ),
        Positioned(
          left: x,
          top: y,
          child: CapyImage(size: c, color: icon.capy),
        ),
        Positioned(
          left: 0,
          right: 0,
          top: edge,
          bottom: 0,
          child: const ColoredBox(color: pagePaper),
        ),
        Positioned(
          left: 0,
          right: 0,
          top: edge,
          height: w * 0.022,
          child: const ColoredBox(color: pageLine),
        ),
      ],
    );
  }
}

/// Плитка в листе выбора: образец и подпись, выбранная — в рамке.
class _IconTile extends StatelessWidget {
  final AppIcon icon;
  final bool dark;
  final bool selected;
  final bool locked;
  final VoidCallback onTap;
  const _IconTile({
    required this.icon,
    required this.dark,
    required this.selected,
    required this.onTap,
    this.locked = false,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Semantics(
      selected: selected,
      button: true,
      label: locked ? '${icon.label}, закрыта' : icon.label,
      excludeSemantics: true,
      child: InkWell(
        key: Key('look:icon:${icon.name}'),
        borderRadius: BorderRadius.circular(Radii.tile),
        onTap: onTap,
        child: Column(
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.all(3),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(Radii.tile + 3),
                border: Border.all(color: selected ? p.accent : Colors.transparent, width: 2),
              ),
              child: !locked
                  ? IconArt(icon: icon, dark: dark)
                  : Stack(
                      alignment: Alignment.center,
                      children: [
                        Opacity(
                          opacity: 0.4,
                          child: IconArt(icon: icon, dark: dark),
                        ),
                        Container(
                          padding: const EdgeInsets.all(6),
                          decoration: BoxDecoration(color: p.cardSolid, shape: BoxShape.circle),
                          child: Icon(Icons.lock_rounded, size: 16, color: p.muted),
                        ),
                      ],
                    ),
            ),
            const SizedBox(height: 4),
            Text(
              icon.label,
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: s.body(
                12,
                weight: selected ? FontWeight.w600 : FontWeight.w400,
                color: selected ? p.text : p.muted,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

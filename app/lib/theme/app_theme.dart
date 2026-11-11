// Тема приложения из дизайн-токенов (design/tokens.json → tokens.dart):
// тёмная «Глубина» и светлая «Тетрадь» — как в телефоне или своя (настройка);
// шрифт — настройка («Книжный»: засечки в заголовках и цифрах, «Строгий»: Onest).
// С 5.79 (экран «Оформление», look.dart): ещё «Кампус» и «Библиотека»,
// тёмная по закату, шрифты «Рукописный» и «Широкий».
import 'package:flutter/material.dart';

import 'look.dart';
import 'tokens.dart';

enum FontChoice { book, strict, hand, wide }

/// Тема: как в телефоне (по умолчанию), по закату в Москве (5.79), всегда
/// светлая или всегда тёмная.
enum ThemeChoice { system, sunset, light, dark }

class Palette {
  final bool dark;
  final Color bg, glow1, glow2, card, cardSolid, line, edge, text, muted, accent, onAccent, ok, warn, danger, tabbar;

  const Palette({
    required this.dark,
    required this.bg,
    required this.glow1,
    required this.glow2,
    required this.card,
    required this.cardSolid,
    required this.line,
    required this.edge,
    required this.text,
    required this.muted,
    required this.accent,
    required this.onAccent,
    required this.ok,
    required this.warn,
    required this.danger,
    required this.tabbar,
  });

  static const depth = Palette(
    dark: true,
    bg: ThemeDepth.bg,
    glow1: ThemeDepth.bgGlow1,
    glow2: ThemeDepth.bgGlow2,
    card: ThemeDepth.card,
    cardSolid: ThemeDepth.cardSolid,
    line: ThemeDepth.line,
    edge: ThemeDepth.edge,
    text: ThemeDepth.text,
    muted: ThemeDepth.muted,
    accent: ThemeDepth.accent,
    onAccent: ThemeDepth.onAccent,
    ok: ThemeDepth.ok,
    warn: ThemeDepth.warn,
    danger: ThemeDepth.danger,
    tabbar: ThemeDepth.tabbar,
  );

  static const notebook = Palette(
    dark: false,
    bg: ThemeNotebook.bg,
    glow1: ThemeNotebook.bgGlow1,
    glow2: ThemeNotebook.bgGlow2,
    card: ThemeNotebook.card,
    cardSolid: ThemeNotebook.cardSolid,
    line: ThemeNotebook.line,
    edge: ThemeNotebook.edge,
    text: ThemeNotebook.text,
    muted: ThemeNotebook.muted,
    accent: ThemeNotebook.accent,
    onAccent: ThemeNotebook.onAccent,
    ok: ThemeNotebook.ok,
    warn: ThemeNotebook.warn,
    danger: ThemeNotebook.danger,
    tabbar: ThemeNotebook.tabbar,
  );

  static const campus = Palette(
    dark: false,
    bg: ThemeCampus.bg,
    glow1: ThemeCampus.bgGlow1,
    glow2: ThemeCampus.bgGlow2,
    card: ThemeCampus.card,
    cardSolid: ThemeCampus.cardSolid,
    line: ThemeCampus.line,
    edge: ThemeCampus.edge,
    text: ThemeCampus.text,
    muted: ThemeCampus.muted,
    accent: ThemeCampus.accent,
    onAccent: ThemeCampus.onAccent,
    ok: ThemeCampus.ok,
    warn: ThemeCampus.warn,
    danger: ThemeCampus.danger,
    tabbar: ThemeCampus.tabbar,
  );

  static const library = Palette(
    dark: true,
    bg: ThemeLibrary.bg,
    glow1: ThemeLibrary.bgGlow1,
    glow2: ThemeLibrary.bgGlow2,
    card: ThemeLibrary.card,
    cardSolid: ThemeLibrary.cardSolid,
    line: ThemeLibrary.line,
    edge: ThemeLibrary.edge,
    text: ThemeLibrary.text,
    muted: ThemeLibrary.muted,
    accent: ThemeLibrary.accent,
    onAccent: ThemeLibrary.onAccent,
    ok: ThemeLibrary.ok,
    warn: ThemeLibrary.warn,
    danger: ThemeLibrary.danger,
    tabbar: ThemeLibrary.tabbar,
  );

  /// «Тетрадь» по брендбуку v1 (11.11) — светлая тема нового дизайна.
  static const paper = Palette(
    dark: false,
    bg: ThemePaper.bg,
    glow1: ThemePaper.bgGlow1,
    glow2: ThemePaper.bgGlow2,
    card: ThemePaper.card,
    cardSolid: ThemePaper.cardSolid,
    line: ThemePaper.line,
    edge: ThemePaper.edge,
    text: ThemePaper.text,
    muted: ThemePaper.muted,
    accent: ThemePaper.accent,
    onAccent: ThemePaper.onAccent,
    ok: ThemePaper.ok,
    warn: ThemePaper.warn,
    danger: ThemePaper.danger,
    tabbar: ThemePaper.tabbar,
  );

  /// «Ночная тетрадь» по брендбуку v1 — та же бумага при лампе, без свечений.
  static const night = Palette(
    dark: true,
    bg: ThemeNight.bg,
    glow1: ThemeNight.bgGlow1,
    glow2: ThemeNight.bgGlow2,
    card: ThemeNight.card,
    cardSolid: ThemeNight.cardSolid,
    line: ThemeNight.line,
    edge: ThemeNight.edge,
    text: ThemeNight.text,
    muted: ThemeNight.muted,
    accent: ThemeNight.accent,
    onAccent: ThemeNight.onAccent,
    ok: ThemeNight.ok,
    warn: ThemeNight.warn,
    danger: ThemeNight.danger,
    tabbar: ThemeNight.tabbar,
  );

  static Palette ofLight(LightTheme t) => t == LightTheme.campus ? campus : notebook;
  static Palette ofDark(DarkTheme t) => t == DarkTheme.library ? library : depth;

  /// Палитра по «Оформлению»: «Новое» — «Тетрадь» и «Ночная тетрадь» (или
  /// «Глубина», запасной выход), «Классика» — прежние четыре темы.
  static Palette of(Look look, {required bool dark}) {
    if (look.fresh) return dark ? (look.freshDepth ? depth : night) : paper;
    return dark ? ofDark(look.dark) : ofLight(look.light);
  }

  /// Перед закатом (режим «по закату»): фон и карточки светлой темы чуть
  /// темнеют, текст тот же — читается при любом [k] (0…1).
  Palette dusk(double k) {
    if (k <= 0 || dark) return this;
    final a = 0.14 * k.clamp(0.0, 1.0);
    Color d(Color c) => Color.alphaBlend(const Color(0xFF1B1E2B).withValues(alpha: a), c);
    return Palette(
      dark: dark,
      bg: d(bg),
      glow1: d(glow1),
      glow2: d(glow2),
      card: d(card),
      cardSolid: d(cardSolid),
      line: line,
      edge: edge,
      text: text,
      muted: muted,
      accent: accent,
      onAccent: onAccent,
      ok: ok,
      warn: warn,
      danger: danger,
      tabbar: d(tabbar),
    );
  }
}

/// Палитра и шрифт — всем экранам через контекст.
class AppStyle extends InheritedWidget {
  final Palette p;
  final FontChoice font;

  /// Что выбрано в «Тема и шрифт» (палитра [p] — уже по нему).
  final ThemeChoice theme;

  /// Настройки «Оформления» (5.79); выключен новый дизайн — [Look.classic].
  final Look look;

  /// Новый дизайн включён сервером (/api/meta → features.design2).
  final bool design2;

  /// Дизайн по брендбуку v1: 'off' — сервер выключил, в «Оформлении» нет
  /// переключателя «Новое / Классика».
  final String design3;

  const AppStyle({
    super.key,
    required this.p,
    required this.font,
    this.theme = ThemeChoice.system,
    this.look = Look.classic,
    this.design2 = false,
    this.design3 = 'opt',
    required super.child,
  });

  static AppStyle of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<AppStyle>()!;

  String get headFamily => switch (font) {
    FontChoice.book => 'SourceSerif',
    FontChoice.strict => 'Onest',
    FontChoice.hand => 'Neucha',
    FontChoice.wide => 'Unbounded',
  };

  /// Цифры: у «Рукописного» — Onest (рукописные цифры в счётчиках не читаются).
  String get numberFamily => font == FontChoice.hand ? 'Onest' : headFamily;

  TextStyle title(double size, {FontWeight? weight, Color? color}) => TextStyle(
    fontFamily: headFamily,
    // широкий шрифт крупнее остальных — заголовки чуть меньше, чтобы влезали
    fontSize: font == FontChoice.wide ? size * 0.8 : (font == FontChoice.hand ? size * 1.08 : size),
    fontWeight:
        weight ??
        switch (font) {
          FontChoice.book || FontChoice.wide => FontWeight.w500,
          FontChoice.strict => FontWeight.w700,
          FontChoice.hand => FontWeight.w400,
        },
    letterSpacing: font == FontChoice.wide || font == FontChoice.hand ? 0 : -size * 0.03,
    height: 1.1,
    color: color ?? p.text,
  );

  TextStyle number(double size, {Color? color}) => TextStyle(
    fontFamily: numberFamily,
    fontSize: font == FontChoice.wide ? size * 0.85 : size,
    fontWeight: switch (font) {
      FontChoice.book || FontChoice.wide => FontWeight.w500,
      FontChoice.strict || FontChoice.hand => FontWeight.w800,
    },
    letterSpacing: font == FontChoice.wide ? -size * 0.02 : -size * 0.05,
    height: 0.95,
    color: color ?? p.text,
    fontFeatures: const [FontFeature.tabularFigures()],
  );

  /// Названия пар, работ и файлов — жирным без засечек при любом шрифте:
  /// длинное «Объектно-ориентированный…» с засечками рвалось и раздувало
  /// карточку (владелец, 09.10, 18Б). Засечки — только у цифр и заголовков.
  TextStyle name(double size, {Color? color}) => TextStyle(
    fontFamily: 'Onest',
    fontSize: size,
    fontWeight: FontWeight.w700,
    letterSpacing: -size * 0.01,
    height: 1.2,
    color: color ?? p.text,
  );

  TextStyle body(double size, {FontWeight weight = FontWeight.w400, Color? color}) =>
      TextStyle(fontFamily: 'Onest', fontSize: size, fontWeight: weight, height: 1.3, color: color ?? p.text);

  TextStyle eyebrow({Color? color}) => font == FontChoice.book && !fresh
      ? TextStyle(fontFamily: 'SourceSerif', fontStyle: FontStyle.italic, fontSize: 15, color: color ?? p.muted)
      : TextStyle(
          fontFamily: 'Onest',
          fontSize: 12,
          fontWeight: FontWeight.w600,
          letterSpacing: 1,
          color: color ?? p.muted,
        );

  /// Тёмные оттенки предметов (5.79.6, Никита 12.10): светлая тема нового
  /// дизайна, где яркие цвета предметов на бумаге читаются плохо.
  bool get darkInk => design2 && !p.dark;

  /// Новый дизайн по брендбуку v1 («Новое» в «Оформлении», сервер не выключил).
  bool get fresh => look.fresh;

  /// Цвет предмета для текста, цифр, колец, полос и заливки под белым
  /// текстом: в светлых темах нового дизайна — тот же оттенок темнее, иначе
  /// [subjectColor]. Подсветка фона и светлые заливки — [subjectColor].
  Color ink(String title) => darkInk ? subjectInkColors[_subjectIndex(title)] : subjectColor(title);

  @override
  bool updateShouldNotify(AppStyle old) =>
      old.p != p ||
      old.font != font ||
      old.theme != theme ||
      old.look != look ||
      old.design2 != design2 ||
      old.design3 != design3;
}

/// Цвет предмета: у каждого свой во всём приложении (по названию).
Color subjectColor(String title) => subjectColors[_subjectIndex(title)];

int _subjectIndex(String title) {
  var h = 0;
  for (final c in title.toLowerCase().codeUnits) {
    h = (h * 31 + c) & 0x7fffffff;
  }
  return h % subjectColors.length;
}

ThemeData materialTheme(Palette p) => ThemeData(
  brightness: p.dark ? Brightness.dark : Brightness.light,
  scaffoldBackgroundColor: p.bg,
  fontFamily: 'Onest',
  colorScheme: ColorScheme.fromSeed(
    seedColor: p.accent,
    brightness: p.dark ? Brightness.dark : Brightness.light,
    surface: p.bg,
  ),
  splashFactory: InkSparkle.splashFactory,
);

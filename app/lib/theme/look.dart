// «Оформление» (дизайн 5.79, второй круг, Никита 12.10): все новые настройки
// вида — в одном месте, по умолчанию всё как было.
//
// Откат одной кнопкой: сервер отдаёт /api/meta → features.design2 (переменная
// DESIGN2=0 выключает). Выключено — приложение берёт [Look.classic], шрифт и
// тема сводятся к прежним, «Оформление» открывает старый лист «Тема и шрифт».
// Последний ответ сервера помнится, чтобы без сети вид не прыгал.
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_icon.dart';

/// Светлая тема: «Тетрадь» (бумага) или «Кампус» (белые карточки, синий).
enum LightTheme { notebook, campus }

/// Тёмная тема: «Глубина» (синее свечение) или «Библиотека» (зелёная).
enum DarkTheme { depth, library }

/// Бумага под карточками — только у «Тетради».
enum Paper { smooth, cell, line, dots, grid }

/// Карточка пары: как сейчас (подкрашена цветом предмета) или белая с
/// полоской цвета предмета слева.
enum CardStyle { tint, stripe }

/// Пары на «Сегодня»: карточками (как сейчас) или строками, как в «Неделе».
enum DayView { cards, rows }

/// Что бывает, когда отметил «сдано»: как сейчас, капибара или конфетти.
enum Cheer { quiet, capy, confetti }

@immutable
class Look {
  final LightTheme light;
  final DarkTheme dark;
  final Paper paper;
  final CardStyle card;
  final DayView day;
  final Cheer cheer;

  /// Иконка приложения на телефоне (theme/app_icon.dart).
  final AppIcon icon;

  /// Тёмная версия иконки-картинки — только Android (iOS 18 меняет сам).
  final bool iconDark;

  const Look({
    this.light = LightTheme.notebook,
    this.dark = DarkTheme.depth,
    this.paper = Paper.smooth,
    this.card = CardStyle.tint,
    this.day = DayView.cards,
    this.cheer = Cheer.quiet,
    this.icon = AppIcon.base,
    this.iconDark = false,
  });

  /// Как до 5.79 — и по умолчанию, и при выключенном новом дизайне.
  static const classic = Look();

  Look copyWith({
    LightTheme? light,
    DarkTheme? dark,
    Paper? paper,
    CardStyle? card,
    DayView? day,
    Cheer? cheer,
    AppIcon? icon,
    bool? iconDark,
  }) => Look(
    light: light ?? this.light,
    dark: dark ?? this.dark,
    paper: paper ?? this.paper,
    card: card ?? this.card,
    day: day ?? this.day,
    cheer: cheer ?? this.cheer,
    icon: icon ?? this.icon,
    iconDark: iconDark ?? this.iconDark,
  );

  static T _pick<T extends Enum>(List<T> values, String? name, T fallback) =>
      values.firstWhere((v) => v.name == name, orElse: () => fallback);

  static Look fromPrefs(SharedPreferences p) => Look(
    light: _pick(LightTheme.values, p.getString('uib_look_light'), LightTheme.notebook),
    dark: _pick(DarkTheme.values, p.getString('uib_look_dark'), DarkTheme.depth),
    paper: _pick(Paper.values, p.getString('uib_look_paper'), Paper.smooth),
    card: _pick(CardStyle.values, p.getString('uib_look_card'), CardStyle.tint),
    day: _pick(DayView.values, p.getString('uib_look_day'), DayView.cards),
    cheer: _pick(Cheer.values, p.getString('uib_look_cheer'), Cheer.quiet),
    icon: AppIcon.byName(p.getString('uib_look_icon')),
    iconDark: p.getBool('uib_look_icon_dark') ?? false,
  );

  Future<void> save(SharedPreferences p) => Future.wait([
    p.setString('uib_look_light', light.name),
    p.setString('uib_look_dark', dark.name),
    p.setString('uib_look_paper', paper.name),
    p.setString('uib_look_card', card.name),
    p.setString('uib_look_day', day.name),
    p.setString('uib_look_cheer', cheer.name),
    p.setString('uib_look_icon', icon.name),
    p.setBool('uib_look_icon_dark', iconDark),
  ]);

  @override
  bool operator ==(Object other) =>
      other is Look &&
      other.light == light &&
      other.dark == dark &&
      other.paper == paper &&
      other.card == card &&
      other.day == day &&
      other.cheer == cheer &&
      other.icon == icon &&
      other.iconDark == iconDark;

  @override
  int get hashCode => Object.hash(light, dark, paper, card, day, cheer, icon, iconDark);
}

/// Включён ли новый дизайн: последнее слово сервера, без ответа — включён.
bool design2FromPrefs(SharedPreferences p) => p.getBool('uib_design2') ?? true;

/// Спросить сервер (/api/meta → features.design2) и запомнить ответ.
/// [get] — запрос к API; ошибка сети — остаётся то, что помнили. Выключает
/// только явное `design2: false` (DESIGN2=0); сервер без этого поля (ещё
/// старый) — новый дизайн включён (Никита 12.10: «врубай», тест до мержа).
Future<bool?> refreshDesign2(Future<dynamic> Function(String) get) async {
  try {
    final m = await get('/meta');
    final f = m is Map ? m['features'] : null;
    final on = !(f is Map && f['design2'] == false);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('uib_design2', on);
    return on;
  } catch (_) {
    return null;
  }
}

/// Восход и закат в Москве (часы МСК, UTC+3) на день [d] — упрощённая
/// формула NOAA, точности до пары минут хватает для смены темы.
({DateTime rise, DateTime set}) moscowSun(DateTime d) {
  const lat = 55.7558, lon = 37.6173;
  final day = DateTime(d.year, d.month, d.day);
  final n = day.difference(DateTime(d.year)).inDays + 1;
  final g = 2 * math.pi / 365 * (n - 1);
  final eqt =
      229.18 *
      (0.000075 +
          0.001868 * math.cos(g) -
          0.032077 * math.sin(g) -
          0.014615 * math.cos(2 * g) -
          0.040849 * math.sin(2 * g));
  final decl =
      0.006918 -
      0.399912 * math.cos(g) +
      0.070257 * math.sin(g) -
      0.006758 * math.cos(2 * g) +
      0.000907 * math.sin(2 * g) -
      0.002697 * math.cos(3 * g) +
      0.00148 * math.sin(3 * g);
  final latR = lat * math.pi / 180;
  final cosH = (math.cos(90.833 * math.pi / 180) / (math.cos(latR) * math.cos(decl))) - math.tan(latR) * math.tan(decl);
  final ha = math.acos(cosH.clamp(-1.0, 1.0)) * 180 / math.pi;
  DateTime at(double minutesUtc) => day.add(Duration(minutes: (minutesUtc + 180).round()));
  return (rise: at(720 - 4 * (lon + ha) - eqt), set: at(720 - 4 * (lon - ha) - eqt));
}

/// Режим «по закату»: тёмная после заката и до восхода. За час до заката
/// светлая тема понемногу темнеет (0…1) — смена не бьёт по глазам.
({bool dark, double dusk}) sunsetPhase(DateTime t) {
  final sun = moscowSun(t);
  final dark = t.isBefore(sun.rise) || !t.isBefore(sun.set);
  if (dark) return (dark: true, dusk: 0);
  final left = sun.set.difference(t).inMinutes;
  return (dark: false, dusk: left >= 60 ? 0 : (60 - left) / 60);
}

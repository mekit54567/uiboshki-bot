// Иконка приложения на выбор (5.79, второй круг дизайна, Никита 12.10) —
// как в Telegram: меняется без переустановки. Android — activity-alias на
// каждую (MainActivity.kt), iOS — альтернативные иконки (AppDelegate.swift),
// картинки — tools/app_icons.py. Канал «uiboshki/icon»; на вебе и в тестах
// его нет — тихо ничего не делаем.
//
// 5.84: плюс иконки-картинки (Никита 13.10: 47 из 288 вариантов ChatGPT),
// каждая светлая и тёмная — по выбору человека: Android — alias …Dark, iOS —
// свой набор Icon<Имя>Dark (5.91.6, Никита 18.10: «выбираешь тёмную, а она не
// тёмная» — appearance dark у альтернативной иконки iPhone не включал).
// Список — design/app_icons.json → app_icons_art.dart.
//
// 5.91: часть иконок открывается ачивкой (ранг, все ачивки) или подпиской —
// поле unlock в том же json; закрытые видны в листе с замком.
//
// 5.114.1: на iPhone подписочные открываются набором ачивок ([iosCombo],
// Никита 20.10) — подписка куплена не через Apple (App Store 3.1.1), а
// ачивки — можно.
//
// 5.117.12: основная иконка — «Мел» (Никита 28.10: «базовой везде»), открыта
// всем и стоит по умолчанию; прежняя синяя капибара на мяче — «Первая».
import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:flutter/services.dart';

import '../achievements/catalog.dart';

part 'app_icons_art.dart';

/// Группа нарисованных кодом вариантов (капибара на мяче, как на прежней основной).
const classicGroup = 'Капибара на мяче';

/// Первая строка в листе выбора — основная иконка ([AppIcon.base]).
const baseGroup = 'Основная';

class AppIcon {
  /// Имя в канале и в настройках: classic, depth, kremlin…
  final String name;
  final String label;
  final String group;

  /// Картинка (5.84), а не капибара на мяче, нарисованная кодом.
  final bool art;

  /// Только для подписчиков — пока подписки нет, в списке не показываем.
  final bool sub;

  /// «MM-dd»: в этот день стоит у всех, выбрать её нельзя (Хэллоуин 31.10).
  final String? season;

  const AppIcon._(this.name, this.label) : group = classicGroup, art = false, sub = false, season = null;
  const AppIcon._art(this.name, this.label, this.group, {this.sub = false, this.season}) : art = true;

  /// «Мел» — основная иконка приложения (5.117.12), по умолчанию. Та же, что
  /// в списке картинок (app_icons_art.dart): светлая — сама основная иконка,
  /// тёмная — альтернативная IconChalkDark.
  static const base = AppIcon._art('chalk', 'Мел', 'Фактуры');

  /// «Первая» — прежняя основная (до 5.117.12 — «Обычная», имя classic).
  static const original = AppIcon._('original', 'Первая');
  static const depth = AppIcon._('depth', 'Глубина');
  static const indigo = AppIcon._('indigo', 'Индиго');
  static const terracotta = AppIcon._('terracotta', 'Терракота');
  static const page = AppIcon._('page', 'Из-за страницы');
  static const sunset = AppIcon._('sunset', 'Закат');
  static const library = AppIcon._('library', 'Библиотека');

  static const drawn = <AppIcon>[original, depth, indigo, terracotta, page, sunset, library];

  /// Все, что есть в приложении (и в сборке под iOS/Android).
  static const values = <AppIcon>[...drawn, ...artIcons];

  /// Есть подписка (/api/me plus). Задаёт оболочка.
  static final premium = ValueNotifier<bool>(false);

  /// Как открыть (design/app_icons.json → unlock): null — бесплатно, `sub`,
  /// `ach:<id>`, `rank:<dawn|noon|dusk|midnight>`, `all`, `none` — убрана;
  /// `combo` — подписочная на iPhone ([iosCombo]).
  String? get unlock {
    final u = sub ? 'sub' : (unlockForTest ?? iconUnlock)[name];
    return u == 'sub' && _ios ? 'combo' : u;
  }

  /// Набор ачивок, которым на iPhone открываются подписочные (Никита 20.10).
  static const iosCombo = ['secret', 't2222', 'calm', 'found', 'submit', 'sdo'];

  @visibleForTesting
  static Map<String, String>? unlockForTest;

  /// Что видно в «Оформлении»: без праздничных и убранных; подписочные —
  /// только подписчикам (купить в приложении нельзя — нечего и дразнить);
  /// на iPhone они всем, с замком до набора ачивок ([iosCombo]).
  static List<AppIcon> get choosable => [
    for (final i in values)
      if (i.season == null && i.unlock != 'none' && (i.unlock != 'sub' || premium.value)) i,
  ];

  static bool get _ios => !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;

  /// Открыта ли: [got] — открытые ачивки (AchStore.got).
  bool isOpen(Map<String, Object> got) {
    final u = unlock;
    if (u == null) return true;
    if (u == 'sub') return premium.value;
    if (u == 'all') return achievements.every((a) => got.containsKey(a.id));
    if (u == 'combo') return iosCombo.every(got.containsKey);
    if (u.startsWith('ach:')) return got.containsKey(u.substring(4));
    if (u.startsWith('rank:')) {
      final rank = Rank.values.where((r) => r.name == u.substring(5)).firstOrNull;
      return rank != null && achievements.where((a) => a.rank == rank).every((a) => got.containsKey(a.id));
    }
    return false;
  }

  /// Как открыть — подпись для закрытой.
  String get howToOpen {
    final u = unlock ?? '';
    if (u == 'sub') return 'Откроется с подпиской';
    if (u == 'all') return 'Откроется, когда соберёшь все ачивки';
    if (u == 'combo') {
      final list = [for (final id in iosCombo) achievementById(id)].whereType<Achievement>();
      final open = [for (final a in list.where((a) => !a.secret)) '«${a.title}»'];
      final hidden = list.where((a) => a.secret).length;
      return 'Откроется за ачивки ${open.join(', ')}'
          '${hidden > 0 ? ' и ${hidden == 1 ? 'секретную' : '$hidden секретные'} ранга «${Rank.midnight.title}»' : ''}';
    }
    if (u.startsWith('ach:')) {
      final a = achievementById(u.substring(4));
      if (a == null) return 'Откроется ачивкой';
      return a.secret ? 'Откроется секретной ачивкой ранга «${a.rank.title}»' : 'Откроется ачивкой «${a.title}»';
    }
    if (u.startsWith('rank:')) {
      final rank = Rank.values.where((r) => r.name == u.substring(5)).firstOrNull;
      if (rank != null) return 'Откроется, когда соберёшь все ачивки ранга «${rank.title}»';
    }
    return 'Пока закрыта';
  }

  /// Не выбрана или «classic» (до 5.117.12 — прежняя основная) — «Мел».
  static AppIcon byName(String? name) => values.firstWhere((i) => i.name == name, orElse: () => base);

  /// Праздничная на этот день, если есть.
  static AppIcon? seasonal(DateTime now) {
    final d = '${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    for (final i in artIcons) {
      if (i.season == d) return i;
    }
    return null;
  }

  /// Образец для «Оформления» (assets/appicons, 192 px).
  String preview({bool dark = false}) => 'assets/appicons/$name${dark ? '_dark' : ''}.png';

  /// Цвет капибары — как на самой иконке (для нарисованных кодом).
  Color get capy => switch (name) {
    'original' => const Color(0xFFFFF8EE),
    'terracotta' => const Color(0xFFF3EEE5),
    'page' => const Color(0xFF2A2721),
    'library' => const Color(0xFFB9DCA3),
    _ => const Color(0xFFFFFFFF),
  };

  /// Фон иконки (для образца в «Оформлении»).
  Decoration get background => switch (name) {
    // прежняя основная: индиго с градиентом из левого верхнего угла
    'original' => const BoxDecoration(
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFF7B7EF4), Color(0xFF4B4FD6)],
      ),
    ),
    'depth' => const BoxDecoration(color: Color(0xFF141823)),
    'indigo' => const BoxDecoration(color: Color(0xFF5B5FE0)),
    'terracotta' => const BoxDecoration(color: Color(0xFFB75438)),
    'page' => const BoxDecoration(color: pagePaper),
    // 160° как в CSS: концы линии — так, чтобы углы квадрата попали в 0 и 1
    'sunset' => const BoxDecoration(
      gradient: LinearGradient(
        begin: Alignment(-0.438, -1.205),
        end: Alignment(0.438, 1.205),
        colors: [Color(0xFFF2994A), Color(0xFFB75438), Color(0xFF5B3A8F)],
        stops: [0, 0.6, 1],
      ),
    ),
    'library' => const BoxDecoration(color: Color(0xFF111715)),
    _ => const BoxDecoration(),
  };

  @override
  String toString() => 'AppIcon.$name';
}

/// «Из-за страницы»: бумага и терракотовая линия по краю листа.
const pagePaper = Color(0xFFF3EEE5);
const pageLine = Color(0xFFB75438);

const _channel = MethodChannel('uiboshki/icon');

/// Меняется ли иконка на этом устройстве: только Android и iPhone/iPad.
/// Стенд (веб-сборка для скринов) показывает выбор с --dart-define=ICONS=true.
bool get appIconSupported =>
    const bool.fromEnvironment('ICONS') ||
    !kIsWeb && (defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS);

/// Имя для канала: у картинок тёмная версия — отдельная иконка (Android —
/// alias, iOS — набор Icon<Имя>Dark). null — основная иконка («Мел» светлый).
@visibleForTesting
String? channelName(AppIcon icon, {bool dark = false}) {
  if (icon == AppIcon.base && !dark) return null;
  if (icon.art && dark) return '${icon.name}Dark';
  return icon.name;
}

/// Поставить иконку [want], если на телефоне стоит другая. В праздник
/// (31.10) — праздничная у всех, на следующий день — снова своя ([holiday]:
/// при выключенном новом дизайне — нет). Нет канала
/// (веб, тесты, старая сборка) или система отказала — молча ничего.
Future<void> syncAppIcon(AppIcon want, {bool dark = false, bool holiday = true, DateTime? now}) async {
  if (!appIconSupported) return;
  final day = holiday ? AppIcon.seasonal(now ?? DateTime.now()) : null;
  final target = channelName(day ?? want, dark: dark);
  try {
    final have = await _channel.invokeMethod<String>('getIcon');
    if (have == target) return;
    await _channel.invokeMethod<void>('setIcon', target);
  } on MissingPluginException {
    // канала нет — и не надо
  } on PlatformException {
    // iOS без альтернативных иконок, Android не дал переключить
  }
}

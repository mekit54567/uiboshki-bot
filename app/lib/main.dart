// УИБО — своё приложение (этап 3). Тема — как в телефоне или своя: тёмная
// «Глубина», светлая «Тетрадь»; тема и шрифт — настройка в «Ещё».
// С 5.79 — экран «Оформление» (theme/look.dart), его сервер может выключить.
import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'achievements/store.dart';
import 'achievements/ui.dart' show appNavigator;
import 'api/api.dart';
import 'screens/login.dart';
import 'screens/sdo_relogin.dart';
import 'screens/shell.dart';
import 'theme/app_icon.dart';
import 'theme/app_theme.dart';
import 'theme/look.dart';
import 'web_safe_area.dart';
import 'widget_data.dart';
import 'widgets/capy.dart';
import 'widgets/common.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final api = Api();
  await api.load();
  final prefs = await SharedPreferences.getInstance();
  runApp(
    UiboApp(
      api: api,
      font: fontFromPrefs(prefs.getString('uib_font')),
      theme: themeFromPrefs(prefs.getString('uib_theme')),
      look: Look.fromPrefs(prefs),
      design2: design2FromPrefs(prefs),
    ),
  );
}

/// Сохранённая тема: 'light' / 'dark' / 'sunset', иначе — как в телефоне.
ThemeChoice themeFromPrefs(String? v) =>
    ThemeChoice.values.firstWhere((t) => t.name == v, orElse: () => ThemeChoice.system);

/// Сохранённый шрифт: 'strict' / 'hand' / 'wide', иначе «Книжный».
FontChoice fontFromPrefs(String? v) => FontChoice.values.firstWhere((f) => f.name == v, orElse: () => FontChoice.book);

class UiboApp extends StatefulWidget {
  final Api api;
  final FontChoice font;
  final ThemeChoice theme;
  final Look look;

  /// Новый дизайн (5.79) — по последнему ответу сервера; тесты включают сами.
  final bool design2;
  const UiboApp({
    super.key,
    required this.api,
    this.font = FontChoice.book,
    this.theme = ThemeChoice.system,
    this.look = Look.classic,
    this.design2 = false,
  });

  @override
  State<UiboApp> createState() => _UiboAppState();
}

class _UiboAppState extends State<UiboApp> {
  late FontChoice _font = widget.font;
  late ThemeChoice _theme = widget.theme;
  late Look _look = widget.look;
  late bool _design2 = widget.design2;
  late bool _loggedIn = widget.api.token != null;
  bool _cached = false;
  Timer? _sun;

  @override
  void initState() {
    super.initState();
    // сервер мог выключить новый дизайн (откат) — узнаём при запуске
    refreshDesign2(widget.api.get).then((on) {
      if (on == false) HomeWidgets.clear(); // откат дизайна — виджеты без данных
      if (on != null && on != _design2 && mounted) setState(() => _design2 = on);
      // иконка на телефоне — по выбору, а без нового дизайна — обычная
      // (откат DESIGN2=0 убирает и её; включат снова — выбор вернётся)
      final d2 = on ?? _design2;
      syncAppIcon(d2 ? _look.icon : AppIcon.classic, dark: d2 && _look.iconDark, holiday: d2);
    });
    // «по закату»: раз в минуту проверить, не пора ли темнеть
    _sun = Timer.periodic(const Duration(minutes: 1), (_) {
      if (_design2 && _theme == ThemeChoice.sunset && mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _sun?.cancel();
    super.dispose();
  }

  /// Капибары — в память сразу: на экране загрузки сцена без мигания.
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_cached) return;
    _cached = true;
    for (final pose in CapyPose.values) {
      precacheImage(AssetImage('assets/capy/${pose.name}.png'), context);
    }
  }

  Future<void> _setFont(FontChoice f) async {
    AchStore.unlock('look');
    setState(() => _font = f);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('uib_font', f.name);
  }

  Future<void> _setLook(Look l) async {
    AchStore.unlock('look');
    final icon = l.icon != _look.icon || l.iconDark != _look.iconDark;
    setState(() => _look = l);
    await l.save(await SharedPreferences.getInstance());
    if (icon && _design2) await syncAppIcon(l.icon, dark: l.iconDark);
  }

  Future<void> _setTheme(ThemeChoice t) async {
    AchStore.unlock('look');
    setState(() => _theme = t);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('uib_theme', t.name);
  }

  Future<void> _logout() async {
    await widget.api.logout();
    unawaited(HomeWidgets.clear()); // чужому телефону — без расписания на экране
    unawaited(SdoRelogin.forget()); // и без единого входа МИРЭА в окне СДО
    if (mounted) setState(() => _loggedIn = false);
  }

  @override
  Widget build(BuildContext context) {
    // новый дизайн выключен сервером — всё как до 5.79
    final look = _design2 ? _look : Look.classic;
    final font = _design2 || _font.index < 2 ? _font : FontChoice.book;
    final theme = _theme == ThemeChoice.sunset && !_design2 ? ThemeChoice.system : _theme;
    final sun = theme == ThemeChoice.sunset ? sunsetPhase(now()) : null;
    final dark = switch (theme) {
      ThemeChoice.light => false,
      ThemeChoice.dark => true,
      ThemeChoice.sunset => sun!.dark,
      ThemeChoice.system => MediaQuery.platformBrightnessOf(context) == Brightness.dark,
    };
    final p = dark ? Palette.ofDark(look.dark) : Palette.ofLight(look.light).dusk(sun?.dusk ?? 0);
    SystemChrome.setSystemUIOverlayStyle(dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark);
    if (kIsWeb) paintPage(p.bg);
    return AppStyle(
      p: p,
      font: font,
      theme: theme,
      look: look,
      design2: _design2,
      child: MaterialApp(
        title: 'Капибара',
        navigatorKey: appNavigator,
        debugShowCheckedModeBanner: false,
        theme: materialTheme(p),
        builder: kIsWeb ? (context, child) => WebSafeArea(child: child!) : null,
        home: _loggedIn
            ? Shell(
                api: widget.api,
                onFont: _setFont,
                onTheme: _setTheme,
                onLook: _setLook,
                onLogout: _logout,
                onUnauthorized: _logout,
                initialTab: tabByName(Uri.base.queryParameters['tab']),
              )
            : LoginScreen(api: widget.api, onDone: () => setState(() => _loggedIn = true)),
      ),
    );
  }
}

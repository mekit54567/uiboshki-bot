// Вход: код → ссылка в бота → «Да, это я» в Telegram → приложение получает
// токен сессии устройства (тот же путь, что у PWA, этап 2). Или VK ID /
// Яндекс ID: окно входа провайдера, назад — ru.uiboshki.app://auth#token=…
import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart' show TargetPlatform, defaultTargetPlatform, kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api.dart';
import '../api/guest.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/common.dart';
import 'search.dart' show SearchScreen;

/// Окно входа провайдера → адрес возврата (в тестах подменяется).
typedef WebAuth = Future<String> Function(String url);

Future<String> systemWebAuth(String url) =>
    FlutterWebAuth2.authenticate(url: url, callbackUrlScheme: 'ru.uiboshki.app');

/// Ссылка в бота. PWA (веб-сборка) на телефоне: t.me в новом окне iPhone
/// открывал поверх приложения встроенным браузером — тот уводил в Telegram и
/// оставался белой страницей вместо числа для входа (Никита, 14.10). Поэтому
/// там сразу tg:// — Telegram открывается без промежуточной страницы.
Uri botUri(String link, {required bool web, required TargetPlatform platform}) {
  final m = RegExp(r'^https://t\.me/(\w+)\?start=([\w-]+)$').firstMatch(link);
  final phone = platform == TargetPlatform.iOS || platform == TargetPlatform.android;
  if (web && phone && m != null) return Uri.parse('tg://resolve?domain=${m[1]}&start=${m[2]}');
  return Uri.parse(link);
}

Future<void> openBot(String link) {
  final uri = botUri(link, web: kIsWeb, platform: defaultTargetPlatform);
  return launchUrl(uri, mode: LaunchMode.externalApplication, webOnlyWindowName: uri.scheme == 'tg' ? '_self' : null);
}

class LoginScreen extends StatefulWidget {
  final Api api;
  final VoidCallback onDone;
  final WebAuth webAuth;
  const LoginScreen({super.key, required this.api, required this.onDone, this.webAuth = systemWebAuth});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with WidgetsBindingObserver {
  Timer? _poll;
  String? _code, _link, _note;
  int? _pick;
  bool _busy = false;
  List<({String id, String name})> _providers = [];

  // Начатый вход в вебе помним 10 минут (как код на сервере): iPhone часто
  // перезапускает PWA, пока человек в Telegram, — без этого число и ожидание
  // пропадали, и вход начинался заново.
  static const _pendingKey = 'uib_login';

  Future<void> _savePending() async {
    if (!kIsWeb) return;
    final prefs = await SharedPreferences.getInstance();
    if (_code == null) {
      await prefs.remove(_pendingKey);
    } else {
      final until = DateTime.now().add(const Duration(minutes: 10)).millisecondsSinceEpoch;
      await prefs.setString(_pendingKey, jsonEncode({'code': _code, 'link': _link, 'pick': _pick, 'until': until}));
    }
  }

  Future<void> _restorePending() async {
    if (!kIsWeb) return;
    try {
      final raw = (await SharedPreferences.getInstance()).getString(_pendingKey);
      if (raw == null) return;
      final j = jsonDecode(raw) as Map<String, dynamic>;
      if ((j['until'] as int) < DateTime.now().millisecondsSinceEpoch || !mounted || _code != null) return;
      setState(() {
        _code = j['code'] as String;
        _link = j['link'] as String?;
        _pick = j['pick'] as int?;
        _busy = true;
        _note = _pick == null ? 'Подтверди вход в боте — «Да, это я»' : 'В боте — «Да, это я», потом это число:';
      });
      _poll?.cancel();
      _poll = Timer.periodic(const Duration(seconds: 2), (_) => _check());
      _check();
    } catch (_) {}
  }

  // вернулся из Telegram — проверить вход сразу, не ждать таймера
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _code != null) _check();
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _restorePending();
    widget.api
        .providers()
        .then((p) {
          if (mounted) setState(() => _providers = p);
        })
        .catchError((_) {});
  }

  Future<void> _oauth(String provider) async {
    tick();
    if (kIsWeb) {
      // PWA: уходим к провайдеру в этом же окне, назад — /app#token=…
      // (токен забирает web/index.html, если вход начат здесь)
      try {
        final url = await widget.api.startOAuth(provider, client: 'web');
        final prefs = await SharedPreferences.getInstance();
        await prefs.setInt('uib_oauth_at', DateTime.now().millisecondsSinceEpoch);
        await launchUrl(Uri.parse(url), webOnlyWindowName: '_self');
      } catch (e) {
        if (mounted) setState(() => _note = errorText(e));
      }
      return;
    }
    try {
      final back = await widget.webAuth(await widget.api.startOAuth(provider));
      if (await widget.api.finishOAuth(back) != null) {
        widget.onDone();
      } else {
        setState(() => _note = 'Вход не завершён — попробуй ещё раз.');
      }
    } catch (_) {
      if (mounted) setState(() => _note = 'Вход отменён.');
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _start() async {
    tick();
    setState(() {
      _busy = true;
      _note = null;
    });
    try {
      final r = await widget.api.startLogin();
      _code = r.code;
      _link = r.link;
      _pick = r.pick;
      await _savePending();
      await openBot(r.link);
      _poll?.cancel();
      _poll = Timer.periodic(const Duration(seconds: 2), (_) => _check());
      setState(
        () => _note = _pick == null ? 'Подтверди вход в боте — «Да, это я»' : 'В боте — «Да, это я», потом это число:',
      );
    } catch (e) {
      setState(() {
        _busy = false;
        _note = e is PlatformException ? 'Не открылся Telegram — попробуй ещё раз.' : errorText(e);
      });
    }
  }

  Future<void> _check() async {
    final code = _code;
    if (code == null) return;
    try {
      final status = await widget.api.pollLogin(code);
      if (status == null) return;
      _poll?.cancel();
      _code = null;
      await _savePending();
      if (status == 'ok') {
        widget.onDone();
        return;
      }
      if (!mounted) return;
      setState(() {
        _busy = false;
        _note = status == 'denied' ? 'Вход отклонён в боте.' : 'Код устарел — попробуй ещё раз.';
      });
    } catch (_) {
      /* сеть моргнула — спросим ещё раз через 2 с */
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Scaffold(
      body: Backdrop(
        child: SafeArea(
          // маленький экран и крупный шрифт — кнопки не влезают: тогда прокрутка,
          // а на обычном экране — как было, капибара посередине, кнопки внизу
          child: LayoutBuilder(
            builder: (context, box) => SingleChildScrollView(
              padding: const EdgeInsets.all(Space.xl),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: math.max(0, box.maxHeight - 2 * Space.xl)),
                child: IntrinsicHeight(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Spacer(),
                      CapyImage(pose: CapyPose.splash, size: 120, color: p.accent),
                      const SizedBox(height: Space.xl),
                      FitWords('Капибара', style: s.title(54), width: box.maxWidth - 2 * Space.xl),
                      const SizedBox(height: 10),
                      Container(
                        width: 34,
                        height: 3,
                        decoration: BoxDecoration(color: p.accent, borderRadius: BorderRadius.circular(2)),
                      ),
                      const SizedBox(height: Space.l),
                      Text(
                        'Расписание, сроки и баллы МИРЭА. Без паролей и кодов из SMS: '
                        'через бота в Telegram, VK или Яндекс.',
                        style: s.body(16, color: p.muted),
                      ),
                      const Spacer(),
                      if (_note != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: Space.m),
                          child: Text(_note!, style: s.body(14, color: p.muted)),
                        ),
                      if (_pick != null && _busy)
                        Padding(
                          padding: const EdgeInsets.only(bottom: Space.m),
                          child: Text('$_pick', key: const Key('login-pick'), style: s.title(48)),
                        ),
                      SizedBox(
                        width: double.infinity,
                        height: 54,
                        child: FilledButton(
                          style: FilledButton.styleFrom(
                            backgroundColor: p.accent,
                            foregroundColor: p.onAccent,
                            shape: const StadiumBorder(),
                            textStyle: s.body(16, weight: FontWeight.w700),
                          ),
                          onPressed: _busy && _link == null ? null : (_busy ? () => openBot(_link!) : _start),
                          child: Text(_busy ? 'Открыть бота ещё раз' : 'Войти через Telegram'),
                        ),
                      ),
                      for (final pr in _providers) ...[
                        const SizedBox(height: Space.s),
                        SizedBox(
                          width: double.infinity,
                          height: 50,
                          child: OutlinedButton(
                            style: OutlinedButton.styleFrom(
                              foregroundColor: p.text,
                              side: BorderSide(color: p.line),
                              shape: const StadiumBorder(),
                              textStyle: s.body(15, weight: FontWeight.w600),
                            ),
                            onPressed: () => _oauth(pr.id),
                            child: Text('Войти через ${pr.name}'),
                          ),
                        ),
                      ],
                      // правило Apple 5.1.1(v): чужое расписание — публичное, смотреть можно без входа
                      const SizedBox(height: Space.s),
                      Center(
                        child: TextButton(
                          key: const Key('login-guest'),
                          style: TextButton.styleFrom(foregroundColor: p.muted),
                          onPressed: () {
                            tick();
                            Navigator.of(context)
                                .push(MaterialPageRoute(builder: (_) => SearchScreen(api: GuestApi())));
                          },
                          child: Text('Расписание без входа', style: s.body(15, weight: FontWeight.w600)),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

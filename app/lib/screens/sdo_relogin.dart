// Тихое обновление входа в СДО (5.102.0). Вход в СДО у МИРЭА иногда гаснет
// (перезапуск СДО, ночной сбой), а единый вход МИРЭА в окне приложения ещё
// помнит человека. Тогда приложение само, без экрана, открывает СДО в
// невидимом окне: СДО отправляет на единый вход, тот сразу обратно — с новой
// MoodleSession, и она уходит на сервер (/sdo/connect, via=silent), как при
// обычном входе страницей. Пароль тут не нужен и не вводится: если МИРЭА
// спрашивает пароль, обновить не вышло, остаётся обычная кнопка «Войти в СДО».
// Только у тех, кто входил страницей на этом телефоне, и не чаще раза в 30 минут.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../api/api.dart';
import '../widgets/common.dart';
import 'sdo_login.dart';

const sdoPageLoginKey = 'sdo_page_login';
const _lastKey = 'sdo_relogin_at';
const reloginEvery = Duration(minutes: 30);
const reloginTimeout = Duration(seconds: 20);

/// Невидимый вход: новая MoodleSession или null (МИРЭА не помнит, нет сети).
typedef SdoSilentLogin = Future<String?> Function(BuildContext context);

class SdoRelogin {
  /// Тесты подменяют окно и «телефон ли это».
  static SdoSilentLogin? silent;
  static bool? available;
  static Future<bool>? _running;

  /// Вошёл страницей СДО на этом телефоне — у окна есть единый вход МИРЭА.
  static Future<void> rememberPageLogin() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(sdoPageLoginKey, true);
    await prefs.remove(_lastKey);
  }

  /// Отключил СДО или вышел из аккаунта: окно забывает вход МИРЭА, чтобы
  /// следующий человек на этом телефоне не подключился чужим СДО.
  static Future<void> forget() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(sdoPageLoginKey);
    await prefs.remove(_lastKey);
    if (!(available ?? sdoWebLoginAvailable)) return;
    try {
      await WebViewCookieManager().clearCookies();
    } catch (_) {}
  }

  /// Вход устарел — попробовать обновить. true — обновился, сервер говорит «ok».
  static Future<bool> run(BuildContext context, Api api) =>
      _running ??= _run(context, api).whenComplete(() => _running = null);

  /// Для оболочки приложения: спросить сервер, только если обновлять есть кому и пора.
  static Future<bool> refreshIfExpired(BuildContext context, Api api) async {
    if (!await due()) return false;
    try {
      final st = await api.get('/sdo/status');
      if (st is! Map || st['state'] != 'expired' || st['shared'] == true) return false;
    } catch (_) {
      return false;
    }
    if (!context.mounted) return false;
    return run(context, api);
  }

  /// Есть кому обновлять (вход страницей на этом телефоне) и прошло 30 минут с прошлой попытки.
  static Future<bool> due() async {
    if (!(available ?? sdoWebLoginAvailable)) return false;
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getBool(sdoPageLoginKey) != true) return false;
    final last = prefs.getInt(_lastKey);
    return last == null || now().difference(DateTime.fromMillisecondsSinceEpoch(last)) >= reloginEvery;
  }

  static Future<bool> _run(BuildContext context, Api api) async {
    if (!await due()) return false;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_lastKey, now().millisecondsSinceEpoch);
    if (!context.mounted) return false;
    final cookie = await (silent ?? hiddenSdoLogin)(context);
    if (cookie == null || cookie.isEmpty) return false;
    try {
      final r = await api.post('/sdo/connect', {'cookie': cookie, 'via': 'silent'});
      return r is Map && r['state'] == 'ok';
    } catch (_) {
      return false;
    }
  }
}

/// На странице входа СДО — единственная кнопка единого входа МИРЭА (её бы нажал
/// сам человек); на странице МИРЭА — поле пароля: значит, человека не помнят.
const _probe = '''(function(){
  if (location.host !== 'online-edu.mirea.ru') return document.querySelector('input[type=password]') ? 'password' : '';
  var a = Array.prototype.map.call(document.querySelectorAll('a[href]'), function(x){ return x.href; })
    .filter(function(h){ return /auth\\/(oauth2|saml2|cas|shibboleth)\\/|authCAS=|sso\\.mirea\\.ru/.test(h); });
  return a.length === 1 ? a[0] : '';
})()''';

Future<String?> hiddenSdoLogin(BuildContext context) async {
  final overlay = Overlay.maybeOf(context, rootOverlay: true);
  if (overlay == null) return null;
  final done = Completer<String?>();
  void finish(String? v) {
    if (!done.isCompleted) done.complete(v);
  }

  var followed = false;
  final web = WebViewController();
  Future<void> check(String? url) async {
    if (done.isCompleted || !await sdoUserShown(web, url)) return;
    final v = await readSdoCookie();
    if (v.isNotEmpty) finish(v);
  }

  Future<void> finished(String url) async {
    await check(url);
    if (done.isCompleted) return;
    try {
      final r = probeResult(await web.runJavaScriptReturningResult(_probe));
      if (r == 'password') {
        finish(null);
      } else if (r.startsWith('https://') && !followed) {
        followed = true;
        await web.loadRequest(Uri.parse(r));
      } else if (Uri.tryParse(url)?.path.startsWith('/login') == true) {
        finish(null); // вход СДО без единой кнопки МИРЭА — тут нужен сам человек
      }
    } catch (_) {}
  }

  await web.setJavaScriptMode(JavaScriptMode.unrestricted);
  await web.setNavigationDelegate(
    NavigationDelegate(
      onPageFinished: finished,
      onWebResourceError: (e) {
        if (e.isForMainFrame ?? false) finish(null);
      },
    ),
  );
  // окно 1×1 почти прозрачное и без касаний: так iPhone и Android честно
  // выполняют страницу (вне экрана система может её притормозить)
  final entry = OverlayEntry(
    builder: (_) => Positioned(
      left: 0,
      top: 0,
      width: 1,
      height: 1,
      child: IgnorePointer(
        child: Opacity(opacity: 0.01, child: WebViewWidget(controller: web)),
      ),
    ),
  );
  overlay.insert(entry);
  try {
    await web.loadRequest(Uri.parse('$sdoBase/my/'));
    return await done.future.timeout(reloginTimeout, onTimeout: () => null);
  } catch (_) {
    return null;
  } finally {
    entry.remove();
  }
}

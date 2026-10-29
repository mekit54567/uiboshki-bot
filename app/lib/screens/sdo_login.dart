// «Войти в СДО»: обычная страница входа СДО (единый вход МИРЭА) внутри
// приложения. Логин и пароль вводятся на сайте МИРЭА, приложение их не видит;
// когда СДО открылся уже не на странице входа, из куки WebView берётся только
// MoodleSession и уходит на сервер (/sdo/connect) — как ручная вставка.
// Куку HttpOnly из Dart не прочитать — её отдаёт канал uiboshki/cookies
// (MainActivity.kt: CookieManager, AppDelegate.swift: WKHTTPCookieStore).
// В браузере (PWA) чужую куку не прочитать — там остаётся ручная вставка.
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'files.dart';

const sdoBase = 'https://online-edu.mirea.ru';
const _cookies = MethodChannel('uiboshki/cookies');

/// Открыть вход и вернуть MoodleSession (null — человек закрыл экран).
typedef SdoWebLogin = Future<String?> Function(BuildContext context);

/// Вход страницей есть только в приложении на телефоне.
bool get sdoWebLoginAvailable =>
    !kIsWeb && (defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.android);

Future<String?> systemSdoLogin(BuildContext context) =>
    Navigator.of(context).push<String>(MaterialPageRoute(builder: (_) => const SdoLoginPage()));

/// MoodleSession из куки окна (HttpOnly — через канал uiboshki/cookies); '' — нет.
Future<String> readSdoCookie() async =>
    await _cookies.invokeMethod<String>('get', {'url': sdoBase, 'name': 'MoodleSession'}) ?? '';

/// Открыта страница СДО, и это не вход (единый вход МИРЭА — на другом адресе).
/// Одного адреса мало: окно сперва открывает /my/ со старой кукой и только
/// потом СДО уводит на /login — поэтому куку берём лишь после [sdoUserShown].
bool sdoLoggedIn(Uri? url) => url != null && url.host == Uri.parse(sdoBase).host && !url.path.startsWith('/login');

/// На странице есть ссылка «Выйти» — её Moodle рисует только вошедшему (не
/// гостю и не на странице входа).
const sdoUserProbe = '''(function(){
  return document.querySelector('a[href*="/login/logout.php"]') ? 'in' : '';
})()''';

/// Ответ пробы: Android отдаёт строку в кавычках JSON, iPhone — как есть.
String probeResult(Object? r) {
  final s = '${r ?? ''}';
  return s.length >= 2 && s.startsWith('"') && s.endsWith('"') ? s.substring(1, s.length - 1) : s;
}

/// Страница догрузилась, это СДО и в нём виден вошедший человек.
Future<bool> sdoUserShown(WebViewController web, String? url) async {
  if (!sdoLoggedIn(Uri.tryParse(url ?? ''))) return false;
  try {
    return probeResult(await web.runJavaScriptReturningResult(sdoUserProbe)) == 'in';
  } catch (_) {
    return false;
  }
}

class SdoLoginPage extends StatefulWidget {
  const SdoLoginPage({super.key});

  @override
  State<SdoLoginPage> createState() => _SdoLoginPageState();
}

class _SdoLoginPageState extends State<SdoLoginPage> {
  double _progress = 0;
  bool _done = false;
  late final WebViewController _web = WebViewController()
    ..setJavaScriptMode(JavaScriptMode.unrestricted)
    ..setNavigationDelegate(
      NavigationDelegate(
        onProgress: (v) {
          if (mounted) setState(() => _progress = v / 100);
        },
        // только когда страница догрузилась: смена адреса приходит раньше
        // переадресации на вход, и тогда в окне ещё старая, мёртвая кука
        onPageFinished: (url) => _check(url),
      ),
    )
    ..loadRequest(Uri.parse('$sdoBase/my/'));

  Future<void> _check(String? url) async {
    if (_done || !await sdoUserShown(_web, url)) return;
    final v = await readSdoCookie();
    if (v.isEmpty || _done || !mounted) return;
    _done = true;
    Navigator.pop(context, v);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Scaffold(
      backgroundColor: p.bg,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Row(
              children: [
                const BackRow(),
                Expanded(
                  child: Text('Вход в СДО МИРЭА', style: s.body(17, weight: FontWeight.w600)),
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
              child: Row(
                children: [
                  Icon(Icons.lock_outline_rounded, size: 16, color: p.muted),
                  const SizedBox(width: Space.s),
                  Expanded(
                    child: Text(
                      'Пароль вводится на сайте МИРЭА — приложение его не видит и сохраняет только вход.',
                      style: s.body(13, color: p.muted),
                    ),
                  ),
                ],
              ),
            ),
            if (_progress < 1) LinearProgressIndicator(value: _progress, minHeight: 2, color: p.accent),
            Expanded(child: WebViewWidget(controller: _web)),
          ],
        ),
      ),
    );
  }
}

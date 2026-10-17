// «Войти в СДО»: обычная страница входа СДО (единый вход МИРЭА) внутри
// приложения. Логин и пароль вводятся на сайте МИРЭА, приложение их не видит;
// когда СДО открылся уже не на странице входа, из куки WebView берётся только
// MoodleSession и уходит на сервер (/sdo/connect) — как ручная вставка.
// В браузере (PWA) чужую куку не прочитать — там остаётся ручная вставка.
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'files.dart';

const sdoBase = 'https://online-edu.mirea.ru';

/// Открыть вход и вернуть MoodleSession (null — человек закрыл экран).
typedef SdoWebLogin = Future<String?> Function(BuildContext context);

/// Вход страницей есть только в приложении на телефоне.
bool get sdoWebLoginAvailable =>
    !kIsWeb && (defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.android);

Future<String?> systemSdoLogin(BuildContext context) =>
    Navigator.of(context).push<String>(MaterialPageRoute(builder: (_) => const SdoLoginPage()));

/// Человек уже вошёл: открыта страница СДО, и это не вход (единый вход МИРЭА — на другом адресе).
bool sdoLoggedIn(Uri? url) => url != null && url.host == Uri.parse(sdoBase).host && !url.path.startsWith('/login');

class SdoLoginPage extends StatefulWidget {
  const SdoLoginPage({super.key});

  @override
  State<SdoLoginPage> createState() => _SdoLoginPageState();
}

class _SdoLoginPageState extends State<SdoLoginPage> {
  double _progress = 0;
  bool _done = false;

  Future<void> _check(WebUri? url) async {
    if (_done || !sdoLoggedIn(url)) return;
    final c = await CookieManager.instance().getCookie(url: WebUri(sdoBase), name: 'MoodleSession');
    final v = c?.value?.toString() ?? '';
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
            Expanded(
              child: InAppWebView(
                initialUrlRequest: URLRequest(url: WebUri('$sdoBase/my/')),
                initialSettings: InAppWebViewSettings(incognito: false, clearCache: false),
                onProgressChanged: (_, v) => setState(() => _progress = v / 100),
                onLoadStop: (_, url) => _check(url),
                onUpdateVisitedHistory: (_, url, _) => _check(url),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

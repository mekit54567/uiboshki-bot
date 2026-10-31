// «Пульс · эксперимент» (31.10, Никита): вход в Пульс МИРЭА окном внутри
// приложения и разведка — что сайт Пульса реально отдаёт. Видно только
// старосте (/me → lab). Человек входит единым входом МИРЭА сам (пароль
// приложение не видит), потом одна кнопка: приложение само обходит разделы
// Пульса, записывает запросы сайта и ответы (только чтение, только свои
// данные), а вместо токенов и кук пишет их форму — длину и срок жизни.
// Журнал уходит на сервер (/pulse/lab), тот присылает архив в бота.
// Вход живёт только в окне на телефоне — сервер его не хранит.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../api/api.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'files.dart';

const pulseBase = 'https://pulse.mirea.ru';
const _loginKey = 'pulse_lab_login_at';
const _aliveKey = 'pulse_lab_alive_at';

/// «3 ч 20 мин», «45 мин», «2 дн 4 ч».
String pulseAgo(int ms) {
  final m = ms ~/ 60000;
  if (m < 60) return '$m мин';
  if (m < 24 * 60) return '${m ~/ 60} ч ${m % 60} мин';
  return '${m ~/ (24 * 60)} дн ${m % (24 * 60) ~/ 60} ч';
}

/// Страницы, которые обход не открывает: выход, отметка по QR (и экран
/// преподавателя с QR), правки.
final pulseSkip = RegExp(
    r'logout|log-out|signout|sign-out|exit|selfapprove|self-approve|token=|delete|remove|edit|create|/new|save|send|submit',
    caseSensitive: false);

/// Разделы, которые стоит проверить, даже если на главной нет ссылки.
const pulseSeeds = [
  '/',
  '/lessons',
  '/lessons/visiting-logs',
  '/schedule',
  '/attendance',
  '/services',
  '/services/maps',
  '/profile',
  '/notifications',
  '/news',
];

/// Ответ runJavaScriptReturningResult строкой: Android отдаёт JSON-строку в
/// кавычках (с экранированием), iPhone — как есть.
String jsString(Object? r) {
  final s = '${r ?? ''}';
  if (s.length >= 2 && s.startsWith('"') && s.endsWith('"')) {
    try {
      return jsonDecode(s) as String;
    } catch (_) {
      return s.substring(1, s.length - 1);
    }
  }
  return s;
}

/// Это сам Пульс, а не страница единого входа МИРЭА.
bool onPulse(String? url) {
  final u = Uri.tryParse(url ?? '');
  return u != null && u.host == Uri.parse(pulseBase).host && !u.path.contains('login');
}

/// Перехват запросов сайта (fetch и XHR). Ставится после каждой загрузки
/// страницы и только на pulse.mirea.ru — на странице входа МИРЭА не работает,
/// пароль не пишется. Тела ответов у адресов входа и токенов не пишутся —
/// только ключи JSON и сроки (expires_in).
const pulseHookJs = r'''(function(){
if (location.host !== 'pulse.mirea.ru') return 'skip';
if (window.__capy) return 'ok';
var C = window.__capy = {calls: [], total: 0, pages: []};
var MAX_CALLS = 600, MAX_BODY = 262144, MAX_TOTAL = 6000000;
var AUTHY = /sso|oauth|openid|oidc|token|login|auth/i;
var SECRET = /authorization|cookie|token|session|secret|password|passwd|key/i;
var STATIC = /\.(js|mjs|css|png|jpe?g|gif|svg|webp|woff2?|ttf|ico|map)(\?|$)/i;
function jwtShape(t){
  try { var p = t.split('.')[1]; p = p.replace(/-/g,'+').replace(/_/g,'/'); while (p.length % 4) p += '=';
    var c = JSON.parse(decodeURIComponent(escape(atob(p)))); var o = {};
    ['exp','iat','nbf','auth_time','iss','aud','azp','typ','scope'].forEach(function(k){ if (k in c) o[k] = c[k]; });
    if (c.exp && c.iat) o.lifetime_min = Math.round((c.exp - c.iat) / 6) / 10;
    return o; } catch (e) { return 'не разобран'; }
}
function redact(v){
  v = String(v); var o = {redacted: true, len: v.length, scheme: v.indexOf(' ') > 0 ? v.split(' ')[0] : ''};
  var m = v.match(/[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}/); if (m) o.jwt = jwtShape(m[0]);
  return o;
}
C.redact = redact;
function shapeJson(v, depth){
  if (v === null || typeof v === 'number' || typeof v === 'boolean') return v;
  if (typeof v === 'string') return (v.length > 40 || /[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}/.test(v)) ? redact(v) : v;
  if (depth > 4) return '…';
  if (Array.isArray(v)) return v.slice(0, 5).map(function(x){ return shapeJson(x, depth + 1); });
  var o = {}; Object.keys(v).slice(0, 40).forEach(function(k){ o[k] = SECRET.test(k) && typeof v[k] === 'string' ? redact(v[k]) : shapeJson(v[k], depth + 1); });
  return o;
}
C.shape = function(s){ try { return shapeJson(JSON.parse(s), 0); } catch (e) { return (s && s.length > 40) ? redact(s) : s; } };
function hdr(name, v){ name = String(name).toLowerCase(); return [name, SECRET.test(name) ? redact(v) : String(v).slice(0, 300)]; }
function b64(buf){
  var a = new Uint8Array(buf), n = Math.min(a.length, MAX_BODY), s = '';
  for (var i = 0; i < n; i += 0x8000) s += String.fromCharCode.apply(null, a.subarray(i, Math.min(n, i + 0x8000)));
  C.total += n; return btoa(s);
}
function bodyOf(b){
  if (b == null) return null;
  if (typeof b === 'string') return b64(new TextEncoder().encode(b));
  if (b instanceof ArrayBuffer) return b64(b);
  if (ArrayBuffer.isView(b)) return b64(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
  return '(' + Object.prototype.toString.call(b) + ')';
}
function wanted(url){ return !STATIC.test(url) && C.calls.length < MAX_CALLS; }
function keep(rec){ C.calls.push(rec); }
var of = window.fetch;
if (of) window.fetch = function(input, init){
  var url = String((input && input.url) || input), t0 = Date.now();
  if (!wanted(url)) return of.apply(this, arguments);
  var rec = {kind: 'fetch', t: t0, page: location.pathname, url: url,
    method: (init && init.method) || (input && input.method) || 'GET', req_headers: {}};
  try {
    var h = new Headers((init && init.headers) || (input && input.headers) || {});
    h.forEach(function(v, k){ var p = hdr(k, v); rec.req_headers[p[0]] = p[1]; });
    if (!AUTHY.test(url) && init && init.body != null) rec.req = bodyOf(init.body);
  } catch (e) { rec.note = 'req: ' + e; }
  keep(rec);
  return of.apply(this, arguments).then(function(r){
    rec.status = r.status; rec.ms = Date.now() - t0; rec.resp_headers = {};
    r.headers.forEach(function(v, k){ var p = hdr(k, v); rec.resp_headers[p[0]] = p[1]; });
    if (C.total < MAX_TOTAL) r.clone().arrayBuffer().then(function(b){
      if (AUTHY.test(url)) rec.resp_shape = C.shape(new TextDecoder().decode(b)); else rec.resp = b64(b);
    }).catch(function(e){ rec.note = 'resp: ' + e; });
    return r;
  }, function(e){ rec.err = String(e); rec.ms = Date.now() - t0; throw e; });
};
var X = XMLHttpRequest.prototype, xo = X.open, xs = X.send, xh = X.setRequestHeader;
X.open = function(m, url){ this.__capy = {kind: 'xhr', method: m, url: String(url), page: location.pathname, req_headers: {}}; return xo.apply(this, arguments); };
X.setRequestHeader = function(k, v){ if (this.__capy) { var p = hdr(k, v); this.__capy.req_headers[p[0]] = p[1]; } return xh.apply(this, arguments); };
X.send = function(body){
  var rec = this.__capy, xhr = this;
  if (rec && wanted(rec.url)) {
    rec.t = Date.now();
    try { if (!AUTHY.test(rec.url)) rec.req = bodyOf(body); } catch (e) { rec.note = 'req: ' + e; }
    keep(rec);
    xhr.addEventListener('loadend', function(){
      rec.status = xhr.status; rec.ms = Date.now() - rec.t; rec.resp_headers = {};
      (xhr.getAllResponseHeaders() || '').trim().split(/[\r\n]+/).forEach(function(line){
        var i = line.indexOf(':'); if (i > 0) { var p = hdr(line.slice(0, i).trim(), line.slice(i + 1).trim()); rec.resp_headers[p[0]] = p[1]; } });
      try {
        if (C.total >= MAX_TOTAL) return;
        var r = xhr.response;
        if (AUTHY.test(rec.url)) rec.resp_shape = C.shape(typeof r === 'string' ? r : (r instanceof ArrayBuffer ? new TextDecoder().decode(r) : ''));
        else if (r instanceof ArrayBuffer) rec.resp = b64(r);
        else if (typeof r === 'string') rec.resp = b64(new TextEncoder().encode(r));
      } catch (e) { rec.note = 'resp: ' + e; }
    });
  }
  return xs.apply(this, arguments);
};
var md = navigator.mediaDevices;
if (md && md.getUserMedia) { var gum = md.getUserMedia.bind(md);
  md.getUserMedia = function(c){ var rec = {kind: 'camera', t: Date.now(), page: location.pathname, url: 'getUserMedia', constraints: JSON.stringify(c)};
    C.calls.push(rec);
    return gum(c).then(function(s){ rec.status = 'ok'; return s; }, function(e){ rec.status = 'отказ'; rec.err = String(e && (e.name + ': ' + e.message)); throw e; }); }; }
return 'ok';
})()''';

/// Кнопка «Отсканировать QR» на странице (текст кнопки или ссылки).
const _scanFindJs = r'''(function(){
var el = Array.prototype.find.call(document.querySelectorAll('button, a, [role=button]'), function(x){
  return /отскан|сканир|scan|qr/i.test((x.textContent || '') + ' ' + (x.getAttribute('aria-label') || '')); });
if (!el) return '';
window.__capyScan = el; return (el.textContent || el.getAttribute('aria-label') || '?').trim().slice(0, 60);
})()''';

/// Ссылки текущей страницы на разделы Пульса (для обхода).
const _linksJs = r'''(function(){
var out = {};
document.querySelectorAll('a[href]').forEach(function(a){
  try { var u = new URL(a.getAttribute('href'), location.href);
    if (u.host === location.host) out[u.pathname] = (a.textContent || '').trim().slice(0, 40); } catch (e) {}
});
return JSON.stringify(out);
})()''';

/// Перейти в раздел без перезагрузки (перехват остаётся): нажать ссылку на
/// него, если есть, иначе — роутер через history.
String pulseGoJs(String path) => '''(function(){
var p = ${jsonEncode(path)};
var a = Array.prototype.find.call(document.querySelectorAll('a[href]'), function(x){
  try { return new URL(x.getAttribute('href'), location.href).pathname === p; } catch (e) { return false; } });
if (a) { a.click(); return 'click'; }
history.pushState({}, '', p); window.dispatchEvent(new PopStateEvent('popstate', {state: {}})); return 'push';
})()''';

/// Журнал целиком: запросы, пройденные страницы, форма хранилищ и кук
/// (имена и сроки, без значений), все адреса, которые грузила страница.
const _dumpJs = r'''(function(){
var C = window.__capy || {calls: [], pages: []};
function st(s){ var o = {}; try { for (var i = 0; i < s.length; i++) { var k = s.key(i); o[k] = C.shape ? C.shape(s.getItem(k) || '') : '?'; } } catch (e) { o.error = String(e); } return o; }
var res = []; try { res = performance.getEntriesByType('resource').map(function(e){ return e.name; }).filter(function(n){ return !/\.(js|css|png|jpe?g|svg|woff2?|ico)(\?|$)/i.test(n); }); } catch (e) {}
window.__capyOut = JSON.stringify({calls: C.calls, storage: {local: st(localStorage), session: st(sessionStorage)},
  cookie_names: document.cookie.split(';').map(function(c){ return c.split('=')[0].trim(); }).filter(Boolean),
  resources: res.slice(-300), url: location.pathname, ua: navigator.userAgent,
  page_text: (document.body && document.body.innerText || '').slice(0, 1500)});
return String(window.__capyOut.length);
})()''';

class PulseLabScreen extends StatefulWidget {
  final Api api;
  const PulseLabScreen({super.key, required this.api});

  @override
  State<PulseLabScreen> createState() => _PulseLabScreenState();
}

class _PulseLabScreenState extends State<PulseLabScreen> {
  double _progress = 0;
  String? _url;
  bool _busy = false;
  String _status = 'Войди в Пульс как обычно: почта, пароль, код. Пароль видит только сайт МИРЭА.';
  late final WebViewController _web = WebViewController()
    ..setJavaScriptMode(JavaScriptMode.unrestricted)
    ..setNavigationDelegate(
      NavigationDelegate(
        onProgress: (v) {
          if (mounted) setState(() => _progress = v / 100);
        },
        onPageFinished: _loaded,
      ),
    )
    ..loadRequest(Uri.parse('$pulseBase/'));

  // Сколько на самом деле живёт вход (срок в токене может врать, как было в
  // СДО): первый вход и последний раз, когда окно было в Пульсе, — на телефоне.
  Future<void> _loaded(String url) async {
    if (!mounted) return;
    setState(() => _url = url);
    final prefs = await SharedPreferences.getInstance();
    final now = DateTime.now().millisecondsSinceEpoch;
    final first = prefs.getInt(_loginKey), alive = prefs.getInt(_aliveKey);
    if (!onPulse(url)) {
      if (alive != null && mounted && !_busy) {
        setState(() => _status = 'Вход слетел или Пульс переспрашивает. Последний раз был в Пульсе ${pulseAgo(now - alive)} назад, '
            'первый вход — ${pulseAgo(now - (first ?? alive))} назад. Скинь эти цифры Claude.');
      }
      return;
    }
    try {
      await _web.runJavaScript(pulseHookJs);
    } catch (_) {}
    if (first == null) await prefs.setInt(_loginKey, now);
    await prefs.setInt(_aliveKey, now);
    if (mounted && !_busy) {
      setState(() => _status = first == null
          ? 'Ты в Пульсе. Нажми «Собрать», дальше всё само (около 2 минут).'
          : 'Вход жив: с первого входа прошло ${pulseAgo(now - first)}. «Собрать» — снова разведка.');
    }
  }

  Future<Map<String, String>> _links() async {
    try {
      final m = jsonDecode(jsString(await _web.runJavaScriptReturningResult(_linksJs))) as Map;
      return m.map((k, v) => MapEntry('$k', '$v'));
    } catch (_) {
      return {};
    }
  }

  Future<void> _collect() async {
    if (_busy || !onPulse(_url)) return;
    setState(() => _busy = true);
    final started = DateTime.now();
    final queue = <String>[...pulseSeeds];
    final seen = <String>{};
    final pages = <Map<String, Object?>>[];
    try {
      await _web.runJavaScript(pulseHookJs);
      // главная заново: первые запросы после входа прошли до перехвата
      while (queue.isNotEmpty && seen.length < 30) {
        final path = queue.removeAt(0);
        if (seen.contains(path) || pulseSkip.hasMatch(path)) continue;
        seen.add(path);
        if (mounted) setState(() => _status = 'Обхожу Пульс: ${seen.length} — $path');
        String how = '';
        try {
          how = jsString(await _web.runJavaScriptReturningResult(pulseGoJs(path)));
        } catch (_) {}
        await Future.delayed(const Duration(seconds: 4));
        // ушли с Пульса (вход протух) — дальше смысла нет
        if (!onPulse(await _web.currentUrl())) break;
        await _web.runJavaScript(pulseHookJs);
        final links = await _links();
        String scan = '';
        try {
          scan = jsString(await _web.runJavaScriptReturningResult(_scanFindJs));
        } catch (_) {}
        pages.add({'path': path, 'how': how, 'links': links, if (scan.isNotEmpty) 'scan': scan});
        for (final l in links.keys) {
          if (!seen.contains(l) && !queue.contains(l) && !pulseSkip.hasMatch(l)) queue.add(l);
        }
      }
      // пускает ли сайт к своему сканеру: нажать «Отсканировать QR» (сам скан не делаем)
      final withScan = pages.where((p) => p['scan'] != null).toList();
      if (withScan.isNotEmpty) {
        final path = '${withScan.first['path']}';
        if (mounted) setState(() => _status = 'Пробую «${withScan.first['scan']}» — камера спросит разрешение');
        await _web.runJavaScriptReturningResult(pulseGoJs(path));
        await Future.delayed(const Duration(seconds: 3));
        await _web.runJavaScript(pulseHookJs);
        final found = jsString(await _web.runJavaScriptReturningResult(_scanFindJs));
        if (found.isNotEmpty) await _web.runJavaScript('window.__capyScan.click()');
        await Future.delayed(const Duration(seconds: 8));
        pages.add({'path': path, 'scan_clicked': found});
      }
      await _send(pages, started);
    } catch (e) {
      if (mounted) setState(() => _status = 'Не вышло: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _send(List<Map<String, Object?>> pages, DateTime started) async {
    if (mounted) setState(() => _status = 'Собираю журнал…');
    final len = int.tryParse(jsString(await _web.runJavaScriptReturningResult(_dumpJs))) ?? 0;
    final buf = StringBuffer();
    const step = 400000;
    for (var i = 0; i < len; i += step) {
      buf.write(jsString(await _web.runJavaScriptReturningResult('window.__capyOut.slice($i, ${i + step})')));
    }
    final report = Map<String, dynamic>.from(jsonDecode(buf.toString()) as Map);
    final prefs = await SharedPreferences.getInstance();
    final loginAt = prefs.getInt(_loginKey);
    report['pages'] = pages;
    report['login'] = {
      if (loginAt != null) 'age_min': DateTime.now().difference(DateTime.fromMillisecondsSinceEpoch(loginAt)).inMinutes,
      'tour_sec': DateTime.now().difference(started).inSeconds,
    };
    if (mounted) setState(() => _status = 'Отправляю…');
    final r = await widget.api.post('/pulse/lab', report);
    if (mounted) {
      setState(() => _status = r['sent'] == true
          ? 'Готово: ${r['summary']}. Архив пришёл в бота — перешли его Claude.'
          : 'Сервер принял журнал, но в бота не отправил: ${r['summary']}');
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final ready = onPulse(_url) && !_busy;
    return Scaffold(
      backgroundColor: p.bg,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Row(
              children: [
                const BackRow(),
                Expanded(child: Text('Пульс · эксперимент', style: s.body(17, weight: FontWeight.w600))),
              ],
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
              child: Row(
                children: [
                  Expanded(child: Text(_status, style: s.body(13, color: p.muted))),
                  const SizedBox(width: Space.s),
                  FilledButton(
                    key: const Key('pulse:collect'),
                    onPressed: ready ? _collect : null,
                    child: Text(_busy ? '…' : 'Собрать'),
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

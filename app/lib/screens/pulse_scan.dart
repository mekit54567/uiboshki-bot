// Сканер отметки в Пульсе (01.11, Никита: вариант «А» — камера на весь экран,
// капибара выглядывает из-за рамки). Кнопка — кружок над меню, только на
// «Сегодня» (shell.dart). Скан — своей камерой (задняя, лучше камеры сайта),
// отметка — в невидимом окне со своим входом в Пульс (тот же вход, что в
// «Пульс · эксперимент»): сервер в отметке не участвует. Только ссылка
// selfapprove Пульса — и только себя.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import 'pulse_lab.dart' show jsString, pulseBase;

/// QR преподавателя: https://pulse.mirea.ru/lessons/visiting-logs/selfapprove?token=`uuid`.
/// Что-то другое — null (чужие ссылки не открываем).
Uri? pulseSelfApprove(String? raw) {
  final u = Uri.tryParse((raw ?? '').trim());
  if (u == null || u.scheme != 'https' || u.host != Uri.parse(pulseBase).host) return null;
  if (!u.path.endsWith('/selfapprove')) return null;
  final token = u.queryParameters['token'] ?? '';
  return RegExp(r'^[0-9a-fA-F-]{16,64}$').hasMatch(token) ? u : null;
}

enum PulseMark { ok, failed, login, unknown }

/// Итог по тексту страницы и ответам Пульса (gRPC-статус отметки).
PulseMark pulseMarkOf(String text, String url, List<Map> calls) {
  final u = Uri.tryParse(url);
  if (u != null && (u.host != Uri.parse(pulseBase).host || u.path.contains('login'))) return PulseMark.login;
  for (final c in calls) {
    final name = '${c['url']}'.toLowerCase();
    if (!name.contains('approve')) continue;
    final st = '${c['grpc'] ?? ''}';
    if (st == '0' && c['status'] == 200) return PulseMark.ok;
    if (st == '16' || c['status'] == 401) return PulseMark.login;
    if (st.isNotEmpty && st != '0') return PulseMark.failed;
  }
  final t = text.toLowerCase();
  if (RegExp(r'войти|вход в систему|авторизац').hasMatch(t) && !t.contains('отмеч')) return PulseMark.login;
  if (RegExp(r'истек|истёк|недейств|не удалось|ошибк|устарел|не найден').hasMatch(t)) return PulseMark.failed;
  if (RegExp(r'отмечен|успешно|присутств|вы на занятии').hasMatch(t)) return PulseMark.ok;
  return PulseMark.unknown;
}

/// Лёгкий перехват: адрес, HTTP и grpc-status ответов (трейлер gRPC-Web — в теле).
const _markHookJs = r'''(function(){
  if (window.__capyMark) return 'ok';
  var M = window.__capyMark = [];
  function grpc(b){ try { var s = new TextDecoder().decode(b); var m = s.match(/grpc-status:\s*(\d+)/); return m ? m[1] : ''; } catch (e) { return ''; } }
  var of = window.fetch;
  if (of) window.fetch = function(input, init){
    var rec = {url: String((input && input.url) || input)}; M.push(rec);
    return of.apply(this, arguments).then(function(r){
      rec.status = r.status; rec.grpc = r.headers.get('grpc-status') || '';
      r.clone().arrayBuffer().then(function(b){ rec.grpc = rec.grpc || grpc(b); }).catch(function(){});
      return r;
    });
  };
  var X = XMLHttpRequest.prototype, xo = X.open, xs = X.send;
  X.open = function(m, url){ this.__cm = {url: String(url)}; return xo.apply(this, arguments); };
  X.send = function(){
    var rec = this.__cm, xhr = this;
    if (rec) { M.push(rec); xhr.addEventListener('loadend', function(){
      rec.status = xhr.status; rec.grpc = xhr.getResponseHeader('grpc-status') || '';
      try { if (xhr.response instanceof ArrayBuffer) rec.grpc = rec.grpc || grpc(xhr.response); } catch (e) {}
    }); }
    return xs.apply(this, arguments);
  };
  return 'ok';
})()''';

const _readJs = r'''JSON.stringify({text: (document.body ? document.body.innerText : '').slice(0, 1500),
  url: location.href, calls: window.__capyMark || []})''';

class PulseScanScreen extends StatefulWidget {
  const PulseScanScreen({super.key});

  @override
  State<PulseScanScreen> createState() => _PulseScanScreenState();
}

class _PulseScanScreenState extends State<PulseScanScreen> {
  final _cam = MobileScannerController(facing: CameraFacing.back, formats: const [BarcodeFormat.qrCode]);
  WebViewController? _web;
  String _hint = 'Наведи на QR с экрана';
  bool _busy = false;
  String _pageText = '';

  @override
  void dispose() {
    _cam.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture cap) async {
    if (_busy) return;
    final raw = cap.barcodes.map((b) => b.rawValue).whereType<String>().firstOrNull;
    final url = pulseSelfApprove(raw);
    if (url == null) {
      if (raw != null && mounted) setState(() => _hint = 'Это не QR отметки Пульса — наведи на экран преподавателя');
      return;
    }
    setState(() {
      _busy = true;
      _hint = 'Отмечаю в Пульсе…';
    });
    HapticFeedback.mediumImpact();
    await _cam.stop();
    final result = await _mark(url);
    if (!mounted) return;
    if (result == PulseMark.ok) {
      Navigator.of(context).pop(true);
      return;
    }
    setState(() {
      _busy = false;
      _hint = switch (result) {
        PulseMark.login => 'Вход в Пульс слетел — войди заново в «Ещё → Пульс», потом сканируй',
        PulseMark.failed => 'Пульс не принял QR — он уже сменился. Сканируй ещё раз',
        _ => 'Пульс не ответил понятно — проверь отметку в Пульсе.${_pageText.isEmpty ? '' : '\n«$_pageText»'}',
      };
    });
    await _cam.start();
  }

  /// Открыть ссылку в невидимом окне (вход — тот же, что у окна Пульса) и
  /// дождаться понятного ответа до 15 с.
  Future<PulseMark> _mark(Uri url) async {
    final loaded = Completer<void>();
    final web = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted: (_) => _web?.runJavaScript(_markHookJs).catchError((_) {}),
        onPageFinished: (_) {
          _web?.runJavaScript(_markHookJs).catchError((_) {});
          if (!loaded.isCompleted) loaded.complete();
        },
      ));
    setState(() => _web = web);
    await web.loadRequest(url);
    await loaded.future.timeout(const Duration(seconds: 15), onTimeout: () {});
    var last = PulseMark.unknown;
    for (var i = 0; i < 12; i++) {
      await Future<void>.delayed(const Duration(seconds: 1));
      try {
        final m = jsonDecode(jsString(await web.runJavaScriptReturningResult(_readJs))) as Map;
        _pageText = '${m['text'] ?? ''}'.replaceAll(RegExp(r'\s+'), ' ').trim();
        if (_pageText.length > 120) _pageText = '${_pageText.substring(0, 120)}…';
        last = pulseMarkOf('${m['text'] ?? ''}', '${m['url'] ?? ''}', [for (final c in m['calls'] as List? ?? []) c as Map]);
      } catch (_) {
        continue;
      }
      if (last != PulseMark.unknown) break;
    }
    if (mounted) setState(() => _web = null);
    return last;
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final size = MediaQuery.sizeOf(context);
    final box = (size.width * 0.66).clamp(200.0, 320.0);
    final top = size.height * 0.30;
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          Positioned.fill(
            child: MobileScanner(
              controller: _cam,
              onDetect: _onDetect,
              errorBuilder: (ctx, e) => Center(
                child: Padding(
                  padding: const EdgeInsets.all(Space.xl),
                  child: Text(
                    e.errorCode == MobileScannerErrorCode.permissionDenied
                        ? 'Нет доступа к камере. Разреши его в Настройках → Капибара.'
                        : 'Камера не запустилась: ${e.errorCode.name}',
                    textAlign: TextAlign.center,
                    style: s.body(15, color: Colors.white),
                  ),
                ),
              ),
            ),
          ),
          // затемнение вокруг рамки
          Positioned.fill(
            child: CustomPaint(painter: _Mask(Rect.fromLTWH((size.width - box) / 2, top, box, box), p.accent)),
          ),
          // капибара выглядывает из-за верхнего края рамки
          Positioned(
            left: (size.width - 84) / 2,
            top: top - 70,
            child: CapyImage(pose: CapyPose.day, size: 84, color: p.accent),
          ),
          Positioned(
            left: Space.xl,
            right: Space.xl,
            top: top + box + Space.xl,
            child: Column(
              children: [
                Text(
                  _hint,
                  textAlign: TextAlign.center,
                  style: s.body(17, weight: FontWeight.w700, color: Colors.white),
                ),
                const SizedBox(height: Space.s),
                Text(
                  'отметка уйдёт с твоего входа в Пульс',
                  textAlign: TextAlign.center,
                  style: s.body(13, color: Colors.white70),
                ),
                if (_busy) ...[
                  const SizedBox(height: Space.l),
                  CircularProgressIndicator(color: p.accent),
                ],
              ],
            ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(Space.l),
              child: Row(
                children: [
                  _RoundButton(
                    key: const Key('scan:close'),
                    icon: Icons.close_rounded,
                    onTap: () => Navigator.of(context).pop(false),
                  ),
                  const Spacer(),
                  _RoundButton(
                    key: const Key('scan:torch'),
                    icon: Icons.flashlight_on_rounded,
                    onTap: () => _cam.toggleTorch(),
                  ),
                ],
              ),
            ),
          ),
          // невидимое окно отметки: платформенному окну нужен размер, поэтому 1×1 и прозрачно
          if (_web != null)
            Positioned(
              left: 0,
              top: 0,
              width: 1,
              height: 1,
              child: Opacity(opacity: 0.01, child: WebViewWidget(controller: _web!)),
            ),
        ],
      ),
    );
  }
}

class _RoundButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  const _RoundButton({super.key, required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) => Material(
    color: Colors.black54,
    shape: const CircleBorder(),
    child: InkWell(
      customBorder: const CircleBorder(),
      onTap: onTap,
      child: Padding(padding: const EdgeInsets.all(10), child: Icon(icon, color: Colors.white, size: 22)),
    ),
  );
}

/// Тёмная вуаль с вырезом и уголки рамки цветом темы.
class _Mask extends CustomPainter {
  final Rect hole;
  final Color color;
  _Mask(this.hole, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final r = RRect.fromRectAndRadius(hole, const Radius.circular(28));
    canvas.drawPath(
      Path.combine(PathOperation.difference, Path()..addRect(Offset.zero & size), Path()..addRRect(r)),
      Paint()..color = Colors.black.withValues(alpha: 0.6),
    );
    final pen = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 5
      ..strokeCap = StrokeCap.round;
    const k = 46.0;
    final (l, t, rt, b) = (hole.left, hole.top, hole.right, hole.bottom);
    for (final path in [
      Path()..moveTo(l, t + k)..lineTo(l, t + 28)..arcToPoint(Offset(l + 28, t), radius: const Radius.circular(28))..lineTo(l + k, t),
      Path()..moveTo(rt - k, t)..lineTo(rt - 28, t)..arcToPoint(Offset(rt, t + 28), radius: const Radius.circular(28))..lineTo(rt, t + k),
      Path()..moveTo(l, b - k)..lineTo(l, b - 28)..arcToPoint(Offset(l + 28, b), radius: const Radius.circular(28), clockwise: false)..lineTo(l + k, b),
      Path()..moveTo(rt - k, b)..lineTo(rt - 28, b)..arcToPoint(Offset(rt, b - 28), radius: const Radius.circular(28), clockwise: false)..lineTo(rt, b - k),
    ]) {
      canvas.drawPath(path, pen);
    }
  }

  @override
  bool shouldRepaint(_Mask old) => old.hole != hole || old.color != color;
}

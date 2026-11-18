// «Пульс МИРЭА» (18.11, Никита: эксперимент больше не нужен — открыть всем).
// Что даёт Пульс: посещения лекций в «Цели» (как отметил преподаватель) и
// отметка по QR кружком на «Сегодня». Вход — обычной страницей единого входа
// МИРЭА в окне приложения (пароль видит только сайт), потом куки сайта Пульса
// (HttpOnly — каналом uiboshki/cookies) уходят на /pulse/connect с галочкой
// согласия `pulse` (152-ФЗ, как у СДО): сервер хранит вход зашифрованным и
// держит его, как СДО (pulse_accounts.py). Отметку по QR ставит телефон —
// тем же входом в окне, сервер в ней не участвует (pulse_scan.dart).
// Только в приложении: в браузере куку чужого сайта не прочитать.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../api/api.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy_refresh.dart';
import '../widgets/common.dart';
import 'files.dart';
import 'legal.dart';
import 'pulse_lab.dart' show PulseLabScreen, onPulse, pulseBase;
import 'pulse_scan.dart';
import 'sdo_connect.dart' show StatusCard, checkedAgo;
import 'sdo_login.dart' show sdoWebLoginAvailable;

const _cookies = MethodChannel('uiboshki/cookies');

/// Когда телефон последний раз видел себя вошедшим в Пульс (окно входа или
/// разведка): без этого сканер сперва ведёт ко входу.
const pulseLoginKey = 'pulse_login_at';
const _labAliveKey = 'pulse_lab_alive_at';

/// Стенд дизайна (веб-сборка с --dart-define=PULSE_STAND=true) показывает
/// экран и кружок QR, хотя окна входа в браузере нет.
const _stand = bool.fromEnvironment('PULSE_STAND');

/// Пульс есть только в приложении на телефоне (и на стенде).
bool get pulseAvailable => sdoWebLoginAvailable || _stand;

/// Открыт ли Пульс этому человеку (/api/me → pulse; старые серверы — lab).
bool pulseOpen(Map me) => pulseAvailable && (me['pulse'] == true || me['lab'] == true);

/// То же для экранов без /me (лист «Посещения», «Учёба», отступ «Сегодня»):
/// ставит shell.dart по /api/me — при PULSE=0 у всех, кроме старосты, false.
final pulseOpenNow = ValueNotifier<bool>(false);

/// Вошёл ли телефон в Пульс хоть раз (окно сохраняет вход само).
Future<bool> pulseLoggedHere() async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getInt(pulseLoginKey) != null || prefs.getInt(_labAliveKey) != null;
}

/// Что даёт Пульс — экран без входа объясняет, зачем подключаться.
const pulsePerks = [
  (Icons.verified_outlined, 'Посещения лекций в «Цели» — ровно как отметил преподаватель'),
  (Icons.qr_code_scanner_rounded, 'Отметка по QR с «Сегодня»: кружок над меню, без сайта Пульса'),
  (Icons.restore_rounded, 'Если вход слетит, посещения снова считаются по СДО, ничего не пропадёт'),
];

/// Подпись строки «Пульс МИРЭА» в «Ещё» по /pulse/status.
({String text, bool warn}) pulseRowSub(Map? st) => switch ('${st?['state'] ?? ''}') {
  'ok' => (text: 'подключён · посещения и отметка по QR', warn: false),
  'expired' => (text: 'вход устарел · войти заново', warn: true),
  _ => (text: 'посещения лекций и отметка по QR', warn: false),
};

/// Ответ /pulse/connect человеческими словами (null — всё хорошо).
String? pulseConnectProblem(Map r) => switch ('${r['state']}') {
  'ok' => null,
  'blocked' => 'Пульс сейчас не пускает наш сервер. Отметка по QR работает, а для посещений войди ещё раз попозже.',
  'expired' => 'Пульс не принял вход. Войди ещё раз.',
  'empty' => 'Вход не нашёлся — войди в Пульс в окне до конца.',
  'network' => 'Пульс не ответил серверу. Попробуй через пару минут.',
  _ => 'Пульс ответил непонятно (${r['state']}). Попробуй ещё раз.',
};

class PulseScreen extends StatefulWidget {
  final Api api;

  /// Пришёл с кружка QR: после входа сразу открыть сканер.
  final bool thenScan;
  const PulseScreen({super.key, required this.api, this.thenScan = false});

  @override
  State<PulseScreen> createState() => _PulseScreenState();
}

class _PulseScreenState extends State<PulseScreen> {
  Map<String, dynamic>? _st;
  Map? _me;
  String? _error, _loadError;
  bool _busy = false, _agree = false, _consented = false, _here = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await widget.api.get('/pulse/status');
      final c = await widget.api.get('/consent').catchError((_) => const {});
      final me = await widget.api.get('/me').catchError((_) => const {});
      final here = await pulseLoggedHere();
      if (!mounted) return;
      setState(() {
        _st = Map<String, dynamic>.from(r as Map);
        _consented = c is Map && c['pulse'] == true;
        _me = me is Map ? me : null;
        _here = here;
      });
    } on ApiError catch (e) {
      if (mounted) setState(() => _loadError = e.message);
    } catch (e) {
      if (mounted) setState(() => _loadError = errorText(e));
    }
  }

  Future<void> _login() async {
    if (!_agree && !_consented) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final header = await Navigator.of(context)
          .push<String>(MaterialPageRoute(builder: (_) => const PulseLoginPage()));
      if (header == null || !mounted) return;
      final r = await widget.api.post('/pulse/connect', {'cookie': header, 'agree': _agree || _consented});
      if (!mounted) return;
      final problem = pulseConnectProblem(r as Map);
      await _load();
      if (!mounted) return;
      if (problem != null) {
        setState(() => _error = problem);
        if (r['state'] != 'blocked') return;
      } else {
        showToast(context, 'Пульс подключён', kind: ToastKind.done);
      }
      if (widget.thenScan && mounted) await _scan();
    } on ApiError catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _scan() async {
    final ok = await Navigator.of(context)
        .push<bool>(MaterialPageRoute(fullscreenDialog: true, builder: (_) => const PulseScanScreen()));
    if (ok == true && mounted) {
      showToast(context, 'Есть, ты на паре', kind: ToastKind.done);
      if (widget.thenScan) Navigator.of(context).pop();
    }
  }

  Future<void> _disconnect() async {
    final ok = await confirmSheet(
      context,
      title: 'Отключить Пульс?',
      text: 'Капибара забудет вход: посещения снова пойдут по СДО, для отметки по QR надо будет войти заново. Что Пульс уже отметил, останется.',
      action: 'Отключить',
      cancel: 'Оставить',
      danger: true,
    );
    if (!ok) return;
    setState(() => _busy = true);
    try {
      await widget.api.post('/pulse/disconnect');
      await WebViewCookieManager().clearCookies();
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(pulseLoginKey);
      await prefs.remove(_labAliveKey);
      await _load();
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final st = _st;
    return Scaffold(
      body: Backdrop(
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.only(bottom: Space.xxl),
            children: [
              const BackRow(),
              const ScreenTitle(title: 'Пульс МИРЭА', sub: 'посещения и отметка по QR'),
              if (st == null && _loadError == null)
                const Padding(padding: EdgeInsets.all(Space.xxl), child: CapyLoading())
              else if (st == null)
                Notice(
                  title: 'Не загрузилось',
                  text: _loadError!,
                  onRetry: () {
                    setState(() => _loadError = null);
                    _load();
                  },
                )
              else
                ..._body(context, st),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _body(BuildContext context, Map<String, dynamic> st) {
    final s = AppStyle.of(context);
    final p = s.p;
    final state = '${st['state'] ?? 'off'}';
    const pad = EdgeInsets.symmetric(horizontal: Space.l);
    final on = state == 'ok';
    return [
      Padding(
        padding: pad,
        child: switch (state) {
          'ok' => StatusCard(color: p.ok, title: 'Подключён, работает', text: checkedAgo(st['checked_at'] as String?)),
          'expired' => StatusCard(color: p.danger, title: 'Вход устарел', text: 'Пульс сбросил вход — войди заново'),
          _ when _here => StatusCard(
            color: p.warn,
            title: 'Вход только на телефоне',
            text: 'Отметка по QR работает, посещения сервер пока не видит',
          ),
          _ => StatusCard(color: p.muted, title: 'Не подключён', text: 'Посещения пока считаются по баллам\u00a0СДО'),
        },
      ),
      if (on) ...[
        const Section('Что уже работает'),
        Padding(
          padding: pad,
          child: _Perks(items: pulsePerks.take(2).toList()),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
          child: _Primary(
            key: const Key('pulse:scan'),
            icon: Icons.qr_code_scanner_rounded,
            text: 'Отметиться по QR',
            onPressed: _busy ? null : _scan,
          ),
        ),
        if (_error != null) _errorText(context),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
          child: TextButton.icon(
            key: const Key('pulse:off'),
            onPressed: _busy ? null : _disconnect,
            icon: Icon(Icons.link_off_rounded, color: p.danger),
            label: Text(
              'Отключить Пульс',
              style: s.body(15, weight: FontWeight.w600, color: p.danger),
            ),
          ),
        ),
      ] else ...[
        const Section('Что даст вход'),
        Padding(
          padding: pad,
          child: _Perks(items: pulsePerks),
        ),
        const Section('Как подключить'),
        Padding(
          padding: pad,
          child: Tile(
            child: Text(
              'Откроется обычный вход МИРЭА: почта, пароль, код. Войди как всегда — Капибара подключится сама.',
              style: s.body(14),
            ),
          ),
        ),
        if (!_consented)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, 0),
            child: ConsentCheck(
              api: widget.api,
              value: _agree,
              onChanged: (v) => setState(() => _agree = v),
              extra: ', в том числе из Пульса: посещения занятий',
            ),
          ),
        if (_error != null) _errorText(context),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
          child: _Primary(
            key: const Key('pulse:login'),
            text: _busy ? 'Проверяю…' : (state == 'expired' ? 'Войти заново' : 'Войти в Пульс'),
            onPressed: _busy || !(_agree || _consented) ? null : _login,
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.xl, Space.m, Space.xl, 0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.shield_outlined, size: 16, color: p.muted),
              const SizedBox(width: Space.s),
              Expanded(
                child: Text(
                  'Пароль видит только сайт МИРЭА. Вход хранится зашифрованным. Капибара читает посещения, а отмечает '
                  'тебя, только когда ты сам сканируешь QR. Отключить — одной кнопкой.',
                  style: s.body(13, color: p.muted),
                ),
              ),
            ],
          ),
        ),
      ],
      if (_me?['lab'] == true)
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
          child: Center(
            child: TextButton(
              key: const Key('pulse:lab'),
              onPressed: () =>
                  Navigator.of(context).push(MaterialPageRoute(builder: (_) => PulseLabScreen(api: widget.api))),
              child: Text('Разведка Пульса (староста)', style: s.body(13, color: p.muted)),
            ),
          ),
        ),
    ];
  }

  Widget _errorText(BuildContext context) {
    final s = AppStyle.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.xl, Space.m, Space.xl, 0),
      child: Text(_error!, style: s.body(14, color: s.p.danger)),
    );
  }
}

class _Perks extends StatelessWidget {
  final List<(IconData, String)> items;
  const _Perks({required this.items});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Tile(
      child: Column(
        children: [
          for (final (icon, text) in items)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: [
                  Icon(icon, size: 20, color: s.p.accent),
                  const SizedBox(width: Space.m),
                  Expanded(child: Text(text, style: s.body(14))),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _Primary extends StatelessWidget {
  final String text;
  final IconData? icon;
  final VoidCallback? onPressed;
  const _Primary({super.key, required this.text, this.icon, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    final style = FilledButton.styleFrom(
      backgroundColor: p.accent,
      foregroundColor: p.onAccent,
      shape: const StadiumBorder(),
    );
    return SizedBox(
      height: 50,
      child: icon == null
          ? FilledButton(style: style, onPressed: onPressed, child: Text(text))
          : FilledButton.icon(style: style, onPressed: onPressed, icon: Icon(icon), label: Text(text)),
    );
  }
}

/// Вход в Пульс страницей единого входа МИРЭА. Вернёт заголовок Cookie сайта
/// Пульса, когда окно дошло до самого Пульса (null — закрыл экран).
class PulseLoginPage extends StatefulWidget {
  const PulseLoginPage({super.key});

  @override
  State<PulseLoginPage> createState() => _PulseLoginPageState();
}

class _PulseLoginPageState extends State<PulseLoginPage> {
  double _progress = 0;
  bool _done = false;
  late final WebViewController _web = WebViewController()
    ..setJavaScriptMode(JavaScriptMode.unrestricted)
    ..setNavigationDelegate(
      NavigationDelegate(
        onProgress: (v) {
          if (mounted) setState(() => _progress = v / 100);
        },
        onPageFinished: _check,
      ),
    )
    ..loadRequest(Uri.parse('$pulseBase/'));

  /// Пульс сперва открывается со старым входом и только потом уводит на
  /// единый вход — поэтому ждём и смотрим адрес ещё раз.
  Future<void> _check(String url) async {
    if (_done || !onPulse(url)) return;
    await Future.delayed(const Duration(milliseconds: 1500));
    if (_done || !mounted || !onPulse(await _web.currentUrl())) return;
    final header = await _cookies.invokeMethod<String>('header', {'url': pulseBase}) ?? '';
    if (header.isEmpty || _done || !mounted) return;
    _done = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(pulseLoginKey, DateTime.now().millisecondsSinceEpoch);
    if (mounted) Navigator.pop(context, header);
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
                  child: Text('Вход в Пульс МИРЭА', style: s.body(17, weight: FontWeight.w600)),
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

/// Кружок QR на «Сегодня»: телефон уже входил в Пульс — сразу сканер, нет —
/// сперва экран «Пульс МИРЭА» (он после входа сам откроет сканер).
Future<bool?> openPulseScan(BuildContext context, Api api) async {
  if (!await pulseLoggedHere()) {
    if (!context.mounted) return null;
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => PulseScreen(api: api, thenScan: true)));
    return null;
  }
  if (!context.mounted) return null;
  return Navigator.of(context)
      .push<bool>(MaterialPageRoute(fullscreenDialog: true, builder: (_) => const PulseScanScreen()));
}

/// Строка про Пульс под «баллы из СДО» на «Учёбе» (Никита 18.11, к основному
/// варианту) — там же, где посещения. Нажал — экран «Пульс МИРЭА».
class PulseStudyLine extends StatefulWidget {
  final Api api;
  const PulseStudyLine({super.key, required this.api});

  @override
  State<PulseStudyLine> createState() => _PulseStudyLineState();
}

class _PulseStudyLineState extends State<PulseStudyLine> {
  Map? _st;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await widget.api.get('/pulse/status');
      if (mounted) setState(() => _st = r is Map ? r : null);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final state = '${_st?['state'] ?? ''}';
    final muted = s.body(13, color: p.muted);
    final link = s.body(13, weight: FontWeight.w600, color: state == 'expired' ? p.danger : p.accent);
    // тихо: подпись — цветом подписей, ссылкой — только действие
    final spans = switch (state) {
      'ok' => [TextSpan(text: 'посещения из Пульса', style: muted)],
      'expired' => [
        TextSpan(text: 'вход в Пульс устарел · ', style: muted),
        TextSpan(text: 'войти заново', style: link),
      ],
      _ => [TextSpan(text: 'посещения точнее · ', style: muted), TextSpan(text: 'подключить Пульс', style: link)],
    };
    return Semantics(
      button: true,
      child: GestureDetector(
        key: const Key('study:pulse'),
        behavior: HitTestBehavior.opaque,
        onTap: () async {
          tick();
          await Navigator.of(context).push(MaterialPageRoute(builder: (_) => PulseScreen(api: widget.api)));
          _load();
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Text.rich(TextSpan(children: spans)),
        ),
      ),
    );
  }
}

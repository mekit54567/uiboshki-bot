// «Вход в СДО»: свой вход студента (MoodleSession) — баллы, работы и сдача
// файлом. Как лист СДО в WebApp (js/more.js): статус, подключить по шагам,
// делиться заданиями с группой, отключить.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy_refresh.dart';
import '../widgets/common.dart';
import 'files.dart';
import '../api/links.dart';
import 'legal.dart';
import 'sdo_login.dart';

/// Что даёт свой вход — без него экран объясняет, зачем подключаться.
const sdoPerks = [
  (Icons.school_outlined, 'Баллы по каждому предмету и сколько осталось до зачёта или «3»'),
  (Icons.check_circle_outline_rounded, 'Какие работы текущего контроля зачтены, а какие нет'),
  (Icons.upload_rounded, 'Сдача работ прямо отсюда — до 3 файлов за раз'),
  (Icons.notifications_none_rounded, 'Бот напишет, когда появятся новые баллы'),
];

/// Ответ сервера «подключи СДО…» / «вход устарел…» — нужен свой вход.
bool needsSdo(String message) => RegExp(r'подключи|устарел').hasMatch(message);

/// «Проверено 5 мин назад» — checked_at приходит в UTC, как datetime('now') в SQLite.
String checkedAgo(String? at) {
  if (at == null || at.isEmpty) return '';
  final t = DateTime.tryParse('${at.replaceFirst(' ', 'T')}Z');
  if (t == null) return '';
  final min = now().toUtc().difference(t).inMinutes;
  if (min < 1) return 'Проверено только что';
  if (min < 60) return 'Проверено $min мин назад';
  if (min < 48 * 60) return 'Проверено ${(min / 60).round()} ч назад';
  return 'Проверено ${(min / 1440).round()} дн. назад';
}

class SdoConnectScreen extends StatefulWidget {
  final Api api;

  /// Вход страницей СДО (тесты подменяют); webLogin — есть ли он (по умолчанию — телефон, не браузер).
  final SdoWebLogin? sdoLogin;
  final bool? webLogin;
  const SdoConnectScreen({super.key, required this.api, this.sdoLogin, this.webLogin});

  @override
  State<SdoConnectScreen> createState() => _SdoConnectScreenState();
}

class _SdoConnectScreenState extends State<SdoConnectScreen> {
  Map<String, dynamic>? _st;
  String? _error, _loadError;
  bool _busy = false;

  /// На телефоне главный путь — страница входа СДО; вставка куки — запасной.
  bool _manual = false;
  bool get _web => widget.webLogin ?? sdoWebLoginAvailable;

  /// Галочка согласия (152-ФЗ): без неё сервер куку не возьмёт.
  bool _agree = false;
  final _cookie = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _cookie.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final r = await widget.api.get('/sdo/status');
      if (mounted) setState(() => _st = Map<String, dynamic>.from(r));
    } on ApiError catch (e) {
      if (mounted) setState(() => _loadError = e.message);
    } catch (e) {
      if (mounted) setState(() => _loadError = errorText(e));
    }
  }

  /// Запрос, который меняет вход: ответ — новый статус.
  Future<void> _act(Future<dynamic> Function() call) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await call();
      if (r is Map && mounted) setState(() => _st = Map<String, dynamic>.from(r));
    } on ApiError catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _connect() async {
    final v = _cookie.text.trim();
    if (v.isEmpty || !_agree) return;
    tick();
    FocusScope.of(context).unfocus();
    await _act(() => widget.api.post('/sdo/connect', {'cookie': v, 'agree': true}));
    if (_st?['state'] == 'ok' && _error == null) {
      _cookie.clear();
      HapticFeedback.mediumImpact();
    }
  }

  Future<void> _byPage() async {
    if (!_agree) return;
    tick();
    final v = await (widget.sdoLogin ?? systemSdoLogin)(context);
    if (v == null || v.isEmpty || !mounted) return;
    _cookie.text = v;
    await _connect();
  }

  Future<void> _paste() async {
    tick();
    final d = await Clipboard.getData(Clipboard.kTextPlain);
    if (d?.text != null) _cookie.text = d!.text!.trim();
  }

  Future<void> _disconnect() async {
    final ok = await confirmSheet(
      context,
      title: 'Отключить СДО?',
      text: 'Сдавать работы отсюда будет нельзя, пока не подключишь снова.',
      action: 'Отключить',
      cancel: 'Оставить',
      danger: true,
    );
    if (ok) await _act(() => widget.api.post('/sdo/disconnect'));
  }

  Future<void> _share(bool v) async {
    tick();
    await _act(() => widget.api.post('/sdo/share', {'share': v}));
    if (v && _st?['share'] == true && mounted) {
      showToast(context, 'Спасибо! Задания группы появятся в сроках через минуту', kind: ToastKind.done);
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
              const ScreenTitle(title: 'Вход в СДО'),
              if (st == null && _loadError == null)
                Padding(padding: const EdgeInsets.all(Space.xxl), child: const CapyLoading())
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
    final state = st['state'] ?? 'off';
    final shared = st['shared'] == true; // вход старосты из настроек бота — не отключается отсюда
    final pad = const EdgeInsets.symmetric(horizontal: Space.l);
    return [
      Padding(
        padding: pad,
        child: switch (state) {
          'ok' => _StatusCard(
            color: p.ok,
            title: 'Подключено, работает',
            text: shared ? 'Вход старосты из настроек бота' : checkedAgo(st['checked_at'] as String?),
          ),
          'expired' => _StatusCard(
            color: p.danger,
            title: 'Вход устарел',
            text: 'СДО разлогинил сессию — подключи заново',
          ),
          _ => _StatusCard(color: p.muted, title: 'Не подключено', text: 'Сроки группы видны и без этого'),
        },
      ),
      if (state == 'ok') ...[
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.xl, Space.l, Space.xl, 0),
          child: Text(
            'У работ из СДО есть кнопка «Сдать»: выбираешь файл — бот загружает его в нужное задание.',
            style: s.body(14, color: p.muted),
          ),
        ),
        if (st['can_share'] == true) ...[
          const Section('Группа'),
          Padding(
            padding: pad,
            child: Tile(
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Делиться заданиями с группой', style: s.body(15, weight: FontWeight.w600)),
                        const SizedBox(height: 4),
                        Text(
                          'Бот возьмёт из твоего СДО задания и сроки для всей '
                          '${(st['group'] as String?)?.isNotEmpty == true ? st['group'] : 'группы'}. '
                          'Баллы и работы никто не увидит.',
                          style: s.body(13, color: p.muted),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: Space.m),
                  Switch(value: st['share'] == true, activeTrackColor: p.accent, onChanged: _busy ? null : _share),
                ],
              ),
            ),
          ),
        ],
        if (_error != null) _errorText(context),
        if (!shared)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.xl, Space.l, 0),
            child: TextButton.icon(
              onPressed: _busy ? null : _disconnect,
              icon: Icon(Icons.link_off_rounded, color: p.danger),
              label: Text(
                'Отключить СДО',
                style: s.body(15, weight: FontWeight.w600, color: p.danger),
              ),
            ),
          ),
      ] else ...[
        if (state == 'off') ...[
          const Section('Что даст вход'),
          Padding(
            padding: pad,
            child: Tile(
              child: Column(
                children: [
                  for (final (icon, text) in sdoPerks)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: Row(
                        children: [
                          Icon(icon, size: 20, color: p.accent),
                          const SizedBox(width: Space.m),
                          Expanded(child: Text(text, style: s.body(14))),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
        const Section('Как подключить'),
        if (_web && !_manual)
          Padding(
            padding: pad,
            child: Tile(
              child: Text(
                'Откроется обычная страница входа СДО МИРЭА. Войди как всегда — бот подключится сам.',
                style: s.body(14),
              ),
            ),
          )
        else ...[
          Padding(padding: pad, child: const _Steps()),
          _GuideLink(api: widget.api, pad: pad),
        ],
        if (!_web || _manual)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
            child: TextField(
              controller: _cookie,
              autocorrect: false,
              enableSuggestions: false,
              style: s.body(15),
              onSubmitted: (_) => _connect(),
              decoration: InputDecoration(
                hintText: 'Вставь MoodleSession…',
                hintStyle: s.body(15, color: p.muted),
                filled: true,
                fillColor: p.card,
                contentPadding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: 14),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(Radii.chip),
                  borderSide: BorderSide(color: p.line),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(Radii.chip),
                  borderSide: BorderSide(color: p.line),
                ),
                suffixIcon: IconButton(
                  tooltip: 'Вставить',
                  onPressed: _paste,
                  icon: Icon(Icons.content_paste_rounded, color: p.muted, size: 20),
                ),
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, 0),
          child: ConsentCheck(
            api: widget.api,
            value: _agree,
            onChanged: (v) => setState(() => _agree = v),
            extra: ', в том числе из СДО: баллы, посещения, задания',
          ),
        ),
        if (_error != null) _errorText(context),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
          child: SizedBox(
            height: 50,
            child: FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: p.accent,
                foregroundColor: p.onAccent,
                shape: const StadiumBorder(),
              ),
              onPressed: _busy || !_agree ? null : (_web && !_manual ? _byPage : _connect),
              child: Text(
                _busy
                    ? 'Проверяю…'
                    : _web && !_manual
                    ? 'Войти в СДО'
                    : 'Проверить и сохранить',
              ),
            ),
          ),
        ),
        if (_web)
          Center(
            child: TextButton(
              key: const Key('sdo-manual'),
              onPressed: () => setState(() => _manual = !_manual),
              child: Text(
                _manual ? 'Войти страницей СДО' : 'Вставить MoodleSession вручную',
                style: s.body(14, weight: FontWeight.w600, color: p.accent),
              ),
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
                  'Это как «оставаться в системе». Значение сразу шифруется, в переписке и логах не остаётся. '
                  'Отключить — одной кнопкой в любой момент.',
                  style: s.body(13, color: p.muted),
                ),
              ),
            ],
          ),
        ),
        if (state == 'expired')
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
            child: TextButton(
              onPressed: _busy ? null : _disconnect,
              child: Text(
                'Убрать вход',
                style: s.body(15, weight: FontWeight.w600, color: p.danger),
              ),
            ),
          ),
      ],
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

/// Статус входа: точка цвета состояния, заголовок и подпись.
class _StatusCard extends StatelessWidget {
  final Color color;
  final String title, text;
  const _StatusCard({required this.color, required this.title, required this.text});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Tile(
      child: Row(
        children: [
          Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
              boxShadow: [BoxShadow(color: color.withValues(alpha: 0.5), blurRadius: 8)],
            ),
          ),
          const SizedBox(width: Space.l),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: s.body(16, weight: FontWeight.w600)),
                if (text.isNotEmpty) Text(text, style: s.body(13, color: s.p.muted)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Как достать MoodleSession — три шага, как в WebApp.
class _Steps extends StatelessWidget {
  const _Steps();

  static const _steps = [
    ('Открой ', 'online-edu.mirea.ru', ' на компьютере и войди в свой аккаунт'),
    ('F12 → Application → Cookies → строка ', 'MoodleSession', ''),
    ('Скопируй значение и вставь сюда', '', ''),
  ];

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Tile(
      child: Column(
        children: [
          for (var i = 0; i < _steps.length; i++)
            Padding(
              padding: EdgeInsets.only(top: i == 0 ? 0 : Space.m),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 24,
                    height: 24,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(color: p.accent, shape: BoxShape.circle),
                    child: Text(
                      '${i + 1}',
                      style: s.body(13, weight: FontWeight.w700, color: p.onAccent),
                    ),
                  ),
                  const SizedBox(width: Space.m),
                  Expanded(
                    child: Text.rich(
                      TextSpan(
                        style: s.body(14),
                        children: [
                          TextSpan(text: _steps[i].$1),
                          TextSpan(
                            text: _steps[i].$2,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          TextSpan(text: _steps[i].$3),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// «Гайд со скринами — в канале», если пост-гайд уже выпущен (/api/meta).
class _GuideLink extends StatelessWidget {
  final Api api;
  final EdgeInsets pad;
  const _GuideLink({required this.api, required this.pad});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return FutureBuilder<Map<String, String>>(
      future: appLinks(api),
      builder: (context, snap) {
        final url = snap.data?['sdo_guide'] ?? '';
        if (url.isEmpty) return const SizedBox.shrink();
        return Padding(
          padding: pad,
          child: TextButton.icon(
            onPressed: () => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication),
            icon: Icon(Icons.photo_library_outlined, color: s.p.accent),
            label: Text(
              'Гайд со скринами — в канале',
              style: s.body(15, weight: FontWeight.w600, color: s.p.accent),
            ),
          ),
        );
      },
    );
  }
}

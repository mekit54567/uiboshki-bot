// «Безопасность» — устройства со входом, вход без Telegram (VK, Яндекс) и
// коротко, как защищены данные (/api/security, как openSecurity в WebApp).
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/brand_logo.dart';
import '../widgets/common.dart';
import 'files.dart' show BackRow;
import 'legal.dart';

typedef _Data = ({List sessions, Map? identities, Map security});

class SecurityScreen extends StatefulWidget {
  final Api api;

  /// Вышли на этом устройстве — оболочка покажет экран входа.
  final VoidCallback onLogout;
  final VoidCallback? onUnauthorized;

  /// Открыть ссылку привязки в браузере (в тестах — подмена).
  final Future<void> Function(Uri url)? open;
  const SecurityScreen({super.key, required this.api, required this.onLogout, this.onUnauthorized, this.open});

  @override
  State<SecurityScreen> createState() => _SecurityScreenState();
}

class _SecurityScreenState extends State<SecurityScreen> {
  // Вернулись из браузера после «Да, привязать» — список входов обновится сам.
  late final AppLifecycleListener _life;
  int _epoch = 0;

  Api get api => widget.api;

  @override
  void initState() {
    super.initState();
    _life = AppLifecycleListener(onResume: () => setState(() => _epoch++));
  }

  @override
  void dispose() {
    _life.dispose();
    super.dispose();
  }

  Future<_Data> _load() async {
    final r = await Future.wait([
      api.get('/auth/sessions'),
      api.get('/auth/identities').then<Object?>((v) => v, onError: (_) => null),
      api.get('/security').then<Object?>((v) => v, onError: (_) => const {}),
    ]);
    return (
      sessions: (r[0] as Map?)?['items'] as List? ?? const [],
      identities: r[1] is Map ? r[1] as Map : null,
      security: r[2] is Map ? r[2] as Map : const {},
    );
  }

  void _snack(String text) {
    if (mounted) showToast(context, text, kind: ToastKind.error);
  }

  /// Вышли на этом телефоне — закрыть экран и уйти ко входу.
  void _leave() {
    Navigator.of(context).popUntil((r) => r.isFirst);
    widget.onLogout();
  }

  Future<void> _revoke(Map d) async {
    tick();
    try {
      await api.delete('/auth/sessions/${d['id']}');
    } on ApiError catch (e) {
      _snack(e.message);
      return;
    }
    if (d['current'] == true) return _leave();
    setState(() => _epoch++);
  }

  Future<void> _everywhere() async {
    final ok = await confirmSheet(
      context,
      title: 'Выйти везде?',
      text: 'На всех устройствах, и на этом тоже. Войти снова — через бота.',
      action: 'Выйти везде',
      cancel: 'Остаться',
      danger: true,
    );
    if (!ok) return;
    try {
      await api.post('/auth/logout?everywhere=true');
    } on ApiError catch (e) {
      _snack(e.message);
      return;
    }
    _leave();
  }

  Future<void> _erase() async {
    if (await deleteMyData(context, api) && mounted) _leave();
  }

  Future<void> _link(String provider) async {
    tick();
    try {
      final r = await api.post('/auth/$provider/link', {'client': 'app'});
      final url = Uri.parse(r['url'] as String);
      final open = widget.open ?? (u) => launchUrl(u, mode: LaunchMode.externalApplication);
      await open(url);
    } on ApiError catch (e) {
      _snack(e.message);
    }
  }

  Future<void> _unlink(String provider) async {
    tick();
    try {
      await api.delete('/auth/identities/$provider');
    } on ApiError catch (e) {
      _snack(e.message);
      return;
    }
    setState(() => _epoch++);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Backdrop(
      child: SafeArea(
        child: Loader<_Data>(
          key: ValueKey(_epoch),
          load: _load,
          onUnauthorized: widget.onUnauthorized,
          builder: (context, d, _) {
            final s = AppStyle.of(context);
            final p = s.p;
            final ids = d.identities;
            final available = (ids?['available'] as List?) ?? const [];
            final linked = {for (final i in (ids?['items'] as List?) ?? const []) i['provider']};
            return ListView(
              padding: const EdgeInsets.only(bottom: Space.xxl),
              children: [
                const BackRow(),
                const ScreenTitle(title: 'Безопасность'),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: _Summary(security: d.security, devices: d.sessions.length),
                ),
                const Section('Устройства'),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: Tile(
                    padding: EdgeInsets.zero,
                    child: Column(
                      children: [
                        for (var i = 0; i < d.sessions.length; i++) ...[
                          if (i > 0) Divider(height: 1, color: p.line),
                          _ActionRow(
                            icon: Icons.smartphone_outlined,
                            title:
                                '${d.sessions[i]['device'] ?? 'Устройство'}'
                                '${d.sessions[i]['current'] == true ? ' · это' : ''}',
                            sub: 'заходил ${_seen(d.sessions[i]['last_seen'] as String?)}',
                            action: 'Выйти',
                            danger: true,
                            onTap: () => _revoke(d.sessions[i] as Map),
                          ),
                        ],
                        if (d.sessions.isEmpty)
                          Padding(
                            padding: const EdgeInsets.all(Space.l),
                            child: Text('Входов вне Telegram нет', style: s.body(14, color: p.muted)),
                          ),
                      ],
                    ),
                  ),
                ),
                if (d.sessions.length > 1)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, 0),
                    child: TextButton.icon(
                      onPressed: _everywhere,
                      icon: Icon(Icons.logout_rounded, color: p.danger, size: 18),
                      label: Text(
                        'Выйти везде',
                        style: s.body(15, weight: FontWeight.w600, color: p.danger),
                      ),
                    ),
                  ),
                if (available.isNotEmpty) ...[
                  const Section('Вход без Telegram'),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.s),
                    child: Text(
                      'Привяжи VK или Яндекс — войдёшь, даже если Telegram не откроется.',
                      style: s.body(13, color: p.muted),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.l),
                    child: Tile(
                      padding: EdgeInsets.zero,
                      child: Column(
                        children: [
                          for (var i = 0; i < available.length; i++) ...[
                            if (i > 0) Divider(height: 1, color: p.line),
                            linked.contains(available[i]['id'])
                                ? _ActionRow(
                                    icon: Icons.link_rounded,
                                    brand: available[i]['id'] as String,
                                    title: available[i]['name'] as String,
                                    sub: 'привязан',
                                    action: 'Отвязать',
                                    danger: true,
                                    onTap: () => _unlink(available[i]['id'] as String),
                                  )
                                : _ActionRow(
                                    icon: Icons.add_link_rounded,
                                    brand: available[i]['id'] as String,
                                    title: available[i]['name'] as String,
                                    sub: 'не привязан',
                                    action: 'Привязать',
                                    onTap: () => _link(available[i]['id'] as String),
                                  ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ],
                const Section('Как защищены данные'),
                for (final (icon, title, text, meaning) in _facts(d.security))
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
                    child: Tile(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(icon, color: p.accent, size: 22),
                          const SizedBox(width: Space.m),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(title, style: s.body(15, weight: FontWeight.w600)),
                                const SizedBox(height: 2),
                                Text(text, style: s.body(13, color: p.muted)),
                                const SizedBox(height: 4),
                                Text(meaning, style: s.body(13, weight: FontWeight.w600)),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                const Section('Твои данные'),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: _MyData(api: api, onErase: _erase),
                ),
              ],
            );
          },
        ),
      ),
    ),
  );
}

/// «сегодня», «вчера», «8 октября» — время с сервера в UTC.
String _seen(String? at) {
  final t = at == null ? null : DateTime.tryParse('${at.replaceFirst(' ', 'T')}Z')?.toLocal();
  if (t == null) return 'давно';
  final today = now();
  final days = DateTime(today.year, today.month, today.day).difference(DateTime(t.year, t.month, t.day)).inDays;
  if (days <= 0) return 'сегодня';
  if (days == 1) return 'вчера';
  return '${t.day} ${monthsGen[t.month - 1]}';
}

/// Коротко о защите: что сделано и что это значит для тебя — простыми
/// словами, без названий шифров и ключей (владелец, 2.11); цифры с сервера.
List<(IconData, String, String, String)> _facts(Map s) {
  final lim = (s['limits'] as Map?) ?? const {};
  final ai = (lim['ai'] as Map?)?['count'] ?? 15;
  final sub = (lim['submit'] as Map?) ?? const {};
  final minutes = s['link_minutes'] ?? 10;
  return [
    (
      Icons.lock_outline_rounded,
      'Вход в СДО зашифрован',
      '${s['sdo'] == 'ok' ? 'Твой вход подключён. ' : ''}Пароль не хранится — только «оставаться в системе», '
          'и тот зашифрован. Ключ лежит отдельно от базы.',
      'Даже если базу украдут, без ключа вход не прочитать.',
    ),
    (
      Icons.phonelink_lock_outlined,
      'Вход в приложение',
      'Через бота, без пароля. Ключ входа есть только на этом телефоне, на сервере — его отпечаток.',
      'Потерял телефон — выйди на нём кнопкой выше, и ключ перестанет работать.',
    ),
    (
      Icons.download_outlined,
      'Файлы — по коротким ссылкам',
      'Ссылка на скачивание подписана и живёт $minutes минут.',
      'Переслал ссылку — через $minutes минут по ней уже ничего не скачать.',
    ),
    (
      Icons.auto_awesome_outlined,
      'ИИ (Gemini от Google)',
      'Уходит только вопрос, история чата и нужные куски лекций. Имя и вход в СДО — нет.',
      'Google не узнает, кто спрашивал. Но личное в вопросы лучше не писать.',
    ),
    (
      Icons.insights_outlined,
      'Статистика — без содержимого',
      'Только «кто, что открыл и когда». Через ${s['events_days'] ?? 180} дней удаляется сама.',
      'Что ты спрашивал и какие файлы смотрел, никто не видит.',
    ),
    (
      Icons.speed_outlined,
      'Защита от перегруза',
      'Не больше $ai вопросов ИИ в минуту и ${sub['count'] ?? 6} сдач за ${sub['minutes'] ?? 10} минут.',
      'Никто не завалит бота запросами — он не тормозит ни у кого.',
    ),
  ];
}

/// Итог одной зелёной карточкой вместо подписи над заголовком (владелец,
/// 09.10, 14А): главное — с первого взгляда, подробности — ниже.
class _Summary extends StatelessWidget {
  final Map security;
  final int devices;
  const _Summary({required this.security, required this.devices});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final text = [
      security['sdo'] == 'ok' ? 'Вход в СДО зашифрован, пароль не хранится' : 'Пароль от СДО не хранится',
      'ссылки на файлы живут ${security['link_minutes'] ?? 10} минут',
      if (devices > 0) 'входов вне Telegram: $devices',
    ].join(', ');
    return Tile(
      key: const Key('security:summary'),
      color: p.ok.withValues(alpha: p.dark ? 0.16 : 0.12),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(color: p.ok.withValues(alpha: 0.22), shape: BoxShape.circle),
            child: Icon(Icons.verified_user_outlined, color: p.ok, size: 22),
          ),
          const SizedBox(width: Space.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Всё под защитой',
                  style: s.body(16, weight: FontWeight.w700, color: p.ok),
                ),
                const SizedBox(height: 2),
                Text('$text.', style: s.body(13, color: p.muted)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ActionRow extends StatelessWidget {
  final IconData icon;

  /// vk / yandex — фирменный знак вместо значка (brand_logo.dart)
  final String? brand;
  final String title, sub, action;
  final bool danger;
  final VoidCallback onTap;
  const _ActionRow({
    required this.icon,
    required this.title,
    required this.sub,
    required this.action,
    required this.onTap,
    this.danger = false,
    this.brand,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.s, Space.s),
      child: Row(
        children: [
          brand != null && BrandLogo.has(brand!) ? BrandLogo(brand!) : Icon(icon, color: p.muted, size: 20),
          const SizedBox(width: Space.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: s.body(15, weight: FontWeight.w600)),
                Text(sub, style: s.body(12, color: p.muted)),
              ],
            ),
          ),
          TextButton(
            onPressed: onTap,
            child: Text(
              action,
              style: s.body(14, weight: FontWeight.w600, color: danger ? p.danger : p.accent),
            ),
          ),
        ],
      ),
    );
  }
}

/// Политика, согласие (синими ссылками) и «Удалить все мои данные» (152-ФЗ).
class _MyData extends StatefulWidget {
  final Api api;
  final VoidCallback onErase;
  const _MyData({required this.api, required this.onErase});

  @override
  State<_MyData> createState() => _MyDataState();
}

class _MyDataState extends State<_MyData> {
  late final _policy = TapGestureRecognizer()..onTap = () => openLegal(context, widget.api, 'privacy');
  late final _consent = TapGestureRecognizer()..onTap = () => openLegal(context, widget.api, 'consent');

  @override
  void dispose() {
    _policy.dispose();
    _consent.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Tile(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text.rich(
            TextSpan(
              style: s.body(14, color: p.muted),
              children: [
                const TextSpan(text: 'Что храним, сколько и кому передаём — в '),
                TextSpan(
                  text: 'Политике обработки персональных данных',
                  style: TextStyle(color: p.link),
                  recognizer: _policy,
                ),
                const TextSpan(text: '. Твоё '),
                TextSpan(
                  text: 'согласие на обработку персональных данных',
                  style: TextStyle(color: p.link),
                  recognizer: _consent,
                ),
                const TextSpan(text: ' можно отозвать — удалив всё.'),
              ],
            ),
          ),
          const SizedBox(height: Space.s),
          TextButton.icon(
            style: TextButton.styleFrom(padding: EdgeInsets.zero),
            onPressed: widget.onErase,
            icon: Icon(Icons.delete_outline_rounded, color: p.danger, size: 20),
            label: Text('Удалить все мои данные', style: s.body(15, weight: FontWeight.w600, color: p.danger)),
          ),
        ],
      ),
    );
  }
}

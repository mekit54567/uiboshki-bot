// Уведомления нового дизайна (шаг 8, макеты У1 и У2, Никита 11.11).
// У1 — лента: всё, что приходило пушем и в Telegram, по дням, ведёт во
// вкладку; открывается колокольчиком на «Сегодня». У2 — «Что присылать»: три
// набора вместо двадцати тумблеров, тихие часы и куда присылать; «Настроить
// самому» открывает прежний экран целиком (notify.dart). Только при «Новом».
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../app_push.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/common.dart';
import 'files.dart' show BackRow;
import 'more.dart' show notifySummary;
import 'notify.dart' show AppSwitch, NotifyScreen;

/// Тихие часы с сервера: «23:00 – 07:30».
String quietRange(Map data) {
  final q = data['quiet_hours'] is Map ? data['quiet_hours'] as Map : const {};
  return '${q['from'] ?? '23:00'} – ${q['to'] ?? '07:30'}';
}

/// Строка под «Уведомлениями» в «Ещё»: «только важное · тихо с 23:00».
String freshNotifySummary(Map data) {
  if (data['subscribed'] != true) return 'выключены';
  final prefs = (data['prefs'] as Map?) ?? const {};
  final what = switch (data['profile']) {
    'important' => 'только важное',
    'daily' => 'помощь каждый день',
    'custom' => 'своя настройка',
    _ => notifySummary(data), // старый сервер наборов не знает
  };
  if (prefs['quiet'] != true) return what;
  final q = data['quiet_hours'] is Map ? data['quiet_hours'] as Map : const {};
  return '$what · тихо с ${q['from'] ?? '23:00'}';
}

/// Куда ведёт строка ленты: вкладка по имени из пуша (shell.dart: tabByName).
String? inboxAction(String? tab) => switch (tab) {
  'today' => 'Открыть «Сегодня»',
  'week' => 'Открыть «Неделю»',
  'deadlines' => 'Открыть «Сдать»',
  'sdo' || 'study' => 'Открыть «Учёбу»',
  _ => null,
};

/// «Сегодня», «Вчера», «8 октября» — заголовок дня в ленте (at — ISO по Москве).
String inboxDay(String at, DateTime today) {
  final day = at.length >= 10 ? at.substring(0, 10) : at;
  if (day == iso(today)) return 'Сегодня';
  if (day == iso(today.subtract(const Duration(days: 1)))) return 'Вчера';
  final d = DateTime.tryParse(day);
  return d == null ? day : '${d.day} ${monthsGen[d.month - 1]}';
}

/// Колокольчик в шапке «Сегодня»: точка — есть непрочитанное.
class InboxBell extends StatelessWidget {
  final int unread;
  final VoidCallback onTap;
  const InboxBell({super.key, required this.unread, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    return Semantics(
      button: true,
      label: unread > 0 ? 'Уведомления, новых: $unread' : 'Уведомления',
      excludeSemantics: true,
      child: GestureDetector(
        key: const Key('today:bell'),
        behavior: HitTestBehavior.opaque,
        onTap: () {
          tick();
          onTap();
        },
        child: SizedBox(
          width: 44,
          height: 44,
          child: Stack(
            alignment: Alignment.center,
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: p.edge),
                ),
                child: Icon(Icons.notifications_none_rounded, size: 20, color: p.text),
              ),
              if (unread > 0)
                Positioned(
                  key: const Key('today:bell:dot'),
                  top: 6,
                  right: 6,
                  child: Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      color: p.accent,
                      shape: BoxShape.circle,
                      border: Border.all(color: p.bg, width: 2),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// У1: лента уведомлений. Открыл — всё прочитано.
class InboxScreen extends StatelessWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const InboxScreen({super.key, required this.api, this.onUnauthorized});

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Backdrop(
      child: SafeArea(
        child: Loader<Map<String, dynamic>>(
          load: () async {
            final d = Map<String, dynamic>.from(await api.get('/inbox'));
            if ((d['unread'] as int? ?? 0) > 0) {
              api.post('/inbox/read', const {}).then<void>((_) {}, onError: (_) {}); // точка погаснет
            }
            return d;
          },
          onUnauthorized: onUnauthorized,
          builder: (context, d, reload) => _InboxBody(api: api, data: d, onUnauthorized: onUnauthorized),
        ),
      ),
    ),
  );
}

class _InboxBody extends StatelessWidget {
  final Api api;
  final Map<String, dynamic> data;
  final VoidCallback? onUnauthorized;
  const _InboxBody({required this.api, required this.data, this.onUnauthorized});

  void _open(BuildContext context, String? tab) {
    if (inboxAction(tab) == null) return;
    tick();
    AppPush.tab.value = tab; // оболочка закроет экраны поверх и откроет вкладку, как у пуша
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final items = [for (final i in (data['items'] as List? ?? const [])) Map<String, dynamic>.from(i as Map)];
    final today = now();
    final days = <String, List<Map<String, dynamic>>>{};
    for (final i in items) {
      days.putIfAbsent(inboxDay('${i['at'] ?? ''}', today), () => []).add(i);
    }
    return ListView(
      key: const ValueKey('inbox'),
      padding: const EdgeInsets.only(bottom: Space.xxl),
      children: [
        Row(
          children: [
            const BackRow(),
            const Spacer(),
            Padding(
              padding: const EdgeInsets.only(right: Space.l),
              child: FreshPill(
                key: const Key('inbox:settings'),
                icon: Icons.tune_rounded,
                text: 'Настроить',
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => NotifyHome(api: api, onUnauthorized: onUnauthorized),
                  ),
                ),
              ),
            ),
          ],
        ),
        const ScreenTitle(title: 'Уведомления'),
        if (items.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: Space.xl),
            child: FreshEmpty(
              key: const Key('inbox:empty'),
              pose: CapyPose.day,
              title: 'Пока пусто',
              text:
                  'Здесь будет всё, что пришло пушем или в Telegram: сроки, баллы, новые задания. '
                  'Хранится ${data['keep_days'] ?? 30}\u00A0дней.',
            ),
          ),
        for (final MapEntry(key: day, value: list) in days.entries) ...[
          Section(day),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: Tile(
              padding: EdgeInsets.zero,
              radius: Radii.card,
              child: Column(
                children: [
                  for (final (k, i) in list.indexed) ...[
                    if (k > 0) Divider(height: 1, color: p.line),
                    _InboxRow(item: i, onTap: () => _open(context, i['tab'] as String?)),
                  ],
                ],
              ),
            ),
          ),
        ],
        if (items.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.xl, Space.l, Space.xl, 0),
            child: Text(
              data['quiet'] == true
                  ? 'Ночью в тихие часы уведомления не приходят, а ждут здесь. Лента хранится ${data['keep_days'] ?? 30}\u00A0дней.'
                  : 'Лента хранится ${data['keep_days'] ?? 30}\u00A0дней.',
              style: s.body(13, color: p.muted),
            ),
          ),
      ],
    );
  }
}

class _InboxRow extends StatelessWidget {
  final Map<String, dynamic> item;
  final VoidCallback onTap;
  const _InboxRow({required this.item, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final at = '${item['at'] ?? ''}';
    final time = at.length >= 16 ? at.substring(11, 16) : '';
    final action = inboxAction(item['tab'] as String?);
    final body = '${item['body'] ?? ''}'.trim();
    return InkWell(
      key: Key('inbox:${item['id']}'),
      onTap: action == null ? null : onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.m, Space.m, Space.l, Space.m),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 7),
              child: Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: item['read'] == true ? Colors.transparent : p.accent,
                  shape: BoxShape.circle,
                ),
              ),
            ),
            const SizedBox(width: Space.s),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${item['title'] ?? ''}', style: s.body(15, weight: FontWeight.w700)),
                  if (body.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      body,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: s.body(13, color: p.muted),
                    ),
                  ],
                  if (action != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      action,
                      style: s.body(13, weight: FontWeight.w700, color: p.accent),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: Space.s),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(time, style: s.body(12.5, color: p.muted)),
                if (item['quiet'] == true)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Icon(Icons.bedtime_outlined, size: 14, color: p.muted, semanticLabel: 'в тихие часы'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// У2: «Что присылать».
class NotifyHome extends StatelessWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const NotifyHome({super.key, required this.api, this.onUnauthorized});

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Backdrop(
      child: SafeArea(
        child: Loader<Map<String, dynamic>>(
          load: () async => Map<String, dynamic>.from(await api.get('/notify')),
          onUnauthorized: onUnauthorized,
          builder: (context, d, reload) =>
              _NotifyHomeBody(api: api, initial: d, reload: reload, onUnauthorized: onUnauthorized),
        ),
      ),
    ),
  );
}

class _NotifyHomeBody extends StatefulWidget {
  final Api api;
  final Map<String, dynamic> initial;
  final Future<void> Function() reload;
  final VoidCallback? onUnauthorized;
  const _NotifyHomeBody({required this.api, required this.initial, required this.reload, this.onUnauthorized});

  @override
  State<_NotifyHomeBody> createState() => _NotifyHomeBodyState();
}

class _NotifyHomeBodyState extends State<_NotifyHomeBody> {
  late Map<String, dynamic> _s = widget.initial;
  Future<void> _queue = Future.value();

  @override
  void didUpdateWidget(_NotifyHomeBody old) {
    super.didUpdateWidget(old);
    if (old.initial != widget.initial) _s = widget.initial;
  }

  Map<String, dynamic> get _prefs => Map<String, dynamic>.from(_s['prefs'] as Map? ?? const {});

  /// Меняем у себя сразу, запросы — по очереди, ответ берём от сервера.
  void _save(Map<String, dynamic> body, Map<String, dynamic> optimistic) {
    tick();
    setState(() {
      _s = {
        ..._s,
        ...optimistic,
        'prefs': {..._prefs, ...?(optimistic['prefs'] as Map<String, dynamic>?)},
      };
    });
    _queue = _queue.then((_) async {
      try {
        final fresh = await widget.api.post('/notify', body);
        if (fresh is Map && mounted) setState(() => _s = Map<String, dynamic>.from(fresh));
      } catch (e) {
        if (mounted) showToast(context, 'Не сохранилось: ${errorText(e)}', kind: ToastKind.error);
        await widget.reload();
      }
    });
  }

  void _pick(String profile) {
    if (_s['profile'] == profile && _s['subscribed'] == true) return;
    _save({'profile': profile}, {'profile': profile, 'subscribed': true});
  }

  Future<void> _custom() async {
    tick();
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => NotifyScreen(api: widget.api, onUnauthorized: widget.onUnauthorized),
      ),
    );
    if (mounted) await widget.reload(); // там могли поменять что угодно
  }

  Future<void> _where() async {
    final copy = _prefs['tg_copy'] != false;
    final got = await appSheet<bool>(context, (ctx) => _WhereSheet(copy: copy));
    if (got == null || got == copy || !mounted) return;
    _save(
      {
        'prefs': {'tg_copy': got},
      },
      {
        'prefs': {'tg_copy': got},
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final on = _s['subscribed'] == true;
    final profile = on ? '${_s['profile'] ?? ''}' : '';
    final quiet = _prefs['quiet'] == true;
    final hasQuiet = _prefs.containsKey('quiet');
    return ListView(
      key: const ValueKey('notify:home'),
      padding: const EdgeInsets.only(bottom: Space.xxl),
      children: [
        const BackRow(),
        const ScreenTitle(title: 'Что присылать'),
        if (!on)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.m),
            child: Text(
              'Сейчас уведомления выключены. Выбери, что присылать, и они включатся.',
              style: s.body(14, color: p.muted),
            ),
          ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _Choice(
                key: const Key('notify:profile:important'),
                title: 'Только важное',
                sub: 'Сроки, новые задания, баллы. Около\u00A03\u00A0в\u00A0день',
                on: profile == 'important',
                onTap: () => _pick('important'),
              ),
              const SizedBox(height: Space.s),
              _Choice(
                key: const Key('notify:profile:daily'),
                title: 'Помощь каждый день',
                sub: 'Плюс утро, пары и обзор недели. Около\u00A08\u00A0в\u00A0день',
                on: profile == 'daily',
                onTap: () => _pick('daily'),
              ),
              const SizedBox(height: Space.s),
              _Choice(
                key: const Key('notify:profile:custom'),
                title: 'Настроить самому',
                sub: profile == 'custom' ? 'Сейчас своя настройка. Каждый вид отдельно' : 'Каждый вид отдельно',
                on: profile == 'custom',
                chevron: true,
                onTap: _custom,
              ),
            ],
          ),
        ),
        const SizedBox(height: Space.l),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l),
          child: Tile(
            padding: EdgeInsets.zero,
            radius: Radii.card,
            child: Column(
              children: [
                if (hasQuiet) ...[
                  _Line(
                    key: const Key('notify:quiet'),
                    icon: Icons.bedtime_outlined,
                    title: 'Тихие часы',
                    sub: '${quietRange(_s)}, по Москве',
                    trailing: AppSwitch(
                      value: quiet,
                      onChanged: () => _save(
                        {
                          'prefs': {'quiet': !quiet},
                        },
                        {
                          'prefs': {'quiet': !quiet},
                        },
                      ),
                    ),
                  ),
                  Divider(height: 1, color: p.line),
                ],
                _Line(
                  key: const Key('notify:where'),
                  icon: Icons.notifications_none_rounded,
                  title: 'Куда присылать',
                  sub: _prefs['tg_copy'] != false ? 'Пуш и Telegram' : 'Пуш. Telegram, если пуш не\u00A0дошёл',
                  onTap: _where,
                ),
              ],
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.xl, Space.m, Space.xl, 0),
          child: Text(
            hasQuiet
                ? 'Всё время в приложении московское. Срочное про тест, который закрывается ночью, придёт и в тихие часы.'
                : 'Всё время в приложении московское.',
            style: s.body(13, color: p.muted),
          ),
        ),
      ],
    );
  }
}

/// Карточка выбора: название, пояснение, галочка (или стрелка).
class _Choice extends StatelessWidget {
  final String title, sub;
  final bool on, chevron;
  final VoidCallback onTap;
  const _Choice({
    super.key,
    required this.title,
    required this.sub,
    required this.on,
    required this.onTap,
    this.chevron = false,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Semantics(
      button: true,
      selected: on,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          // рамка выбранной толще на 1 — отступ меньше на 1, текст не прыгает
          padding: EdgeInsets.all(Space.l - (on ? 1 : 0)),
          decoration: BoxDecoration(
            color: p.card,
            borderRadius: BorderRadius.circular(Radii.tile),
            border: Border.all(color: on ? p.accent : p.line, width: on ? 2 : 1),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: s.body(16, weight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(sub, style: s.body(13.5, color: p.muted)),
                  ],
                ),
              ),
              const SizedBox(width: Space.s),
              if (on && !chevron)
                Icon(Icons.check_circle_rounded, color: p.accent)
              else if (chevron)
                Icon(Icons.chevron_right_rounded, color: on ? p.accent : p.muted),
            ],
          ),
        ),
      ),
    );
  }
}

/// Строка в карточке: значок, название, пояснение, справа — выключатель или стрелка.
class _Line extends StatelessWidget {
  final IconData icon;
  final String title, sub;
  final Widget? trailing;
  final VoidCallback? onTap;
  const _Line({super.key, required this.icon, required this.title, required this.sub, this.trailing, this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return InkWell(
      onTap: onTap == null
          ? null
          : () {
              tick();
              onTap!();
            },
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 60),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.m, Space.s),
          child: Row(
            children: [
              Icon(icon, size: 22, color: p.accent),
              const SizedBox(width: Space.m),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: s.body(15, weight: FontWeight.w700)),
                    Text(sub, style: s.body(13, color: p.muted)),
                  ],
                ),
              ),
              ?trailing,
              if (trailing == null && onTap != null) Icon(Icons.chevron_right_rounded, color: p.muted),
            ],
          ),
        ),
      ),
    );
  }
}

/// «Куда присылать»: пуш и Telegram или только пуш (Telegram — если пуш не дошёл).
class _WhereSheet extends StatelessWidget {
  final bool copy;
  const _WhereSheet({required this.copy});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    Widget option(bool v, String title, String sub) => ListTile(
      key: Key('notify:where:${v ? 'both' : 'push'}'),
      contentPadding: const EdgeInsets.symmetric(horizontal: Space.xl),
      title: Text(title, style: s.body(15, weight: FontWeight.w700)),
      subtitle: Text(sub, style: s.body(13, color: p.muted)),
      trailing: Icon(
        v == copy ? Icons.check_circle_rounded : Icons.radio_button_unchecked_rounded,
        color: v == copy ? p.accent : p.muted,
      ),
      onTap: () {
        tick();
        Navigator.pop(context, v);
      },
    );
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.s),
            child: Text('Куда присылать', style: s.title(24)),
          ),
          option(true, 'Пуш и Telegram', 'Одно и то же приходит в оба места'),
          option(false, 'Только пуш', 'Telegram — только если пуш не\u00A0дошёл'),
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.xl, Space.s, Space.xl, Space.l),
            child: Text('Пуши на этом телефоне включаются в «Настроить самому».', style: s.body(13, color: p.muted)),
          ),
        ],
      ),
    );
  }
}

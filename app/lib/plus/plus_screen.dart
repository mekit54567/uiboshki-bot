// Экран «Капибара+» (Ещё → Капибара+) и лист «Позвать друга».
// Подписка оплачивается только на сайте (/plus по личной ссылке pay_url) —
// в приложении ни покупок, ни кассы. На iPhone экрана нет вовсе: сервер на
// X-App: ios отвечает {"hidden": true} (правила App Store вне США).
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../achievements/catalog.dart';
import '../achievements/ui.dart' show RankBadge;
import '../api/api.dart';
import '../api/models.dart' show monthsGen, plural;
import '../screens/files.dart' show BackRow;
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';
import 'donate.dart';
import 'plus.dart';

/// Ссылки наружу и «Поделиться» — тесты подменяют.
class PlusLinks {
  PlusLinks._();

  static Future<bool> Function(Uri) open = (u) => launchUrl(u, mode: LaunchMode.externalApplication);

  static Future<void> Function(String text, Rect? origin) share = (text, origin) async {
    await SharePlus.instance.share(ShareParams(text: text, sharePositionOrigin: origin));
  };
}

final _shown = Expando<bool>();

/// Показывать ли «Капибару+» в «Ещё»: сервер сказал hidden:false. Ответ
/// помнится на запуск; не ответил — плитки нет (спросим в следующий раз).
Future<bool> plusShown(Api api) async {
  if (!PlusBonus.allowed) return false;
  final known = _shown[api];
  if (known != null) return known;
  try {
    final r = await api.get('/plus');
    return _shown[api] = r is Map && r['hidden'] == false;
  } catch (_) {
    return false;
  }
}

/// «до 14 ноября» из «2026-11-14».
String plusUntil(String? iso) {
  final d = DateTime.tryParse(iso ?? '');
  if (d == null) return '';
  final year = d.year != now().year ? ' ${d.year}' : '';
  return '${d.day} ${monthsGen[d.month - 1]}$year';
}

String _days(int n) => '$n ${plural(n, 'день', 'дня', 'дней')}';

/// Что даёт подписка — как PERKS на странице оплаты (webapp/routes/billing.py).
const plusPerks = [
  (Icons.auto_awesome_outlined, 'ИИ сверх пробы', 'до 100 вопросов в день для любой группы МИРЭА'),
  (Icons.palette_outlined, 'Иконки и наряды капибары', 'те, что «по подписке», в «Оформлении»'),
  (Icons.workspace_premium_outlined, 'Значок «друг Капибары»', 'в профиле'),
  (Icons.upcoming_outlined, 'Дальше', 'ответы на экзаменационные билеты, «Пульс группы», «Архив потока»'),
];

/// Что даёт безлимит (/grant … unlimited): ИИ без дневных лимитов — до дня или навсегда.
List<(IconData, String, String)> unlimitedPerks(String? until) => [
  (
    Icons.auto_awesome_outlined,
    'ИИ без ограничений',
    until == null ? 'без дневных лимитов, навсегда' : 'без дневных лимитов до ${plusUntil(until)}',
  ),
  ...plusPerks.skip(1),
];

class PlusScreen extends StatelessWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const PlusScreen({super.key, required this.api, this.onUnauthorized});

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Backdrop(
      child: SafeArea(
        child: Loader<Map<String, dynamic>>(
          load: () async => Map<String, dynamic>.from(await api.get('/plus') as Map),
          onUnauthorized: onUnauthorized,
          builder: (context, d, _) => _PlusBody(api: api, d: d),
        ),
      ),
    ),
  );
}

class _PlusBody extends StatelessWidget {
  final Api api;
  final Map<String, dynamic> d;
  const _PlusBody({required this.api, required this.d});

  Future<void> _open(BuildContext context, String url) async {
    tick();
    final toast = Overlay.of(context, rootOverlay: true);
    var ok = false;
    try {
      ok = await PlusLinks.open(Uri.parse(url));
    } catch (_) {}
    if (!ok) toastOn(toast, 'Не открылось — попробуй ещё раз', kind: ToastKind.error);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    if (d['hidden'] != false) {
      return ListView(
        children: const [
          BackRow(),
          ScreenTitle(title: 'Капибара+'),
        ],
      );
    }
    final active = d['active'] == true;
    final gift = d['paid_until'] == null && d['gift'] is String;
    final unlimited = d['unlimited'] == true;
    final founder = d['founder'] == true;
    final prices = [for (final x in d['prices'] as List? ?? const []) Map<String, dynamic>.from(x as Map)];
    final payUrl = '${d['pay_url'] ?? ''}';
    final offerUrl = '${d['offer_url'] ?? ''}';
    final invite = Map<String, dynamic>.from(d['invite'] as Map? ?? const {});
    final ranks = Map<String, dynamic>.from(invite['ranks'] as Map? ?? const {});
    final unlimitedUntil = d['unlimited_until'] is String ? d['unlimited_until'] as String : null;
    final perks = unlimited ? unlimitedPerks(unlimitedUntil) : plusPerks;
    final founderPrice = prices.where((x) => x['founder'] == true).map((x) => x['price']).firstOrNull;
    return ListView(
      padding: const EdgeInsets.only(bottom: Space.xxl),
      children: [
        const BackRow(),
        const ScreenTitle(title: 'Капибара+', sub: 'подписка на Капибару'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l),
          child: Tile(
            key: const Key('plus:state'),
            radius: Radii.card,
            child: Row(
              children: [
                Icon(
                  active ? Icons.verified_rounded : Icons.workspace_premium_outlined,
                  color: active ? p.ok : p.accent,
                  size: 30,
                ),
                const SizedBox(width: Space.m),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        unlimited
                            ? (d['unlimited_until'] is String
                                  ? 'У тебя безлимит до ${plusUntil(d['unlimited_until'] as String?)}'
                                  : 'У тебя безлимит навсегда')
                            : gift
                            ? 'Подарок группе до ${plusUntil(d['gift'] as String?)}'
                            : active
                            ? 'Действует до ${plusUntil(d['until'] as String?)}'
                            : 'Подписки нет',
                        style: s.body(17, weight: FontWeight.w600),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        unlimited
                            ? 'ИИ без дневных лимитов, платить не нужно'
                            : gift
                            ? 'Платить не нужно — всё уже включено'
                            : active
                            ? 'Оплата добавит дни к этому сроку'
                            : 'Всё главное работает и без неё — она для тех, кому нужно больше',
                        style: s.body(13, color: p.muted),
                      ),
                      if (founder && !unlimited) ...[
                        const SizedBox(height: Space.s),
                        Row(
                          children: [
                            const _Tag('Основатель'),
                            if (founderPrice != null) ...[
                              const SizedBox(width: Space.s),
                              Expanded(
                                child: Text(
                                  'месяц для тебя — $founderPrice ₽, навсегда',
                                  style: s.body(13, color: p.muted),
                                ),
                              ),
                            ],
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const Section('Что даёт'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l),
          child: Tile(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                for (var i = 0; i < perks.length; i++) ...[
                  if (i > 0) Divider(height: 1, color: p.line),
                  _Row(icon: perks[i].$1, title: perks[i].$2, sub: perks[i].$3),
                ],
              ],
            ),
          ),
        ),
        // безлимиту цены и оплата ни к чему (робот 18.10)
        if (!unlimited && prices.isNotEmpty) ...[
          Section(prices.any((x) => x['founder'] == true) ? 'Цены первых пользователей' : 'Цены'),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: Tile(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  for (var i = 0; i < prices.length; i++) ...[
                    if (i > 0) Divider(height: 1, color: p.line),
                    _PriceRow(price: prices[i]),
                  ],
                ],
              ),
            ),
          ),
        ],
        if (!unlimited) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.l, 0),
            child: payUrl.isEmpty
                ? Tile(
                    key: const Key('plus:soon'),
                    child: Row(
                      children: [
                        Icon(Icons.schedule_rounded, color: p.muted),
                        const SizedBox(width: Space.m),
                        Expanded(
                          child: Text(
                            'Оплата скоро заработает. Бонусные дни за ранги и друзей уже начисляются.',
                            style: s.body(14, color: p.muted),
                          ),
                        ),
                      ],
                    ),
                  )
                : FilledButton.icon(
                    key: const Key('plus:pay'),
                    style: FilledButton.styleFrom(
                      backgroundColor: p.accent,
                      foregroundColor: p.onAccent,
                      minimumSize: const Size.fromHeight(52),
                      shape: const StadiumBorder(),
                    ),
                    onPressed: () => _open(context, payUrl),
                    icon: const Icon(Icons.open_in_new_rounded, size: 20),
                    label: Text(
                      'Оплатить на сайте',
                      style: s.body(16, weight: FontWeight.w600, color: p.onAccent),
                    ),
                  ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.xl, Space.m, Space.xl, 0),
            child: Text(
              'Без автосписаний: каждый срок оплачивается отдельно. Июль и август в срок не считаются.',
              style: s.body(13, color: p.muted),
            ),
          ),
          if (offerUrl.isNotEmpty)
            Align(
              alignment: Alignment.centerLeft,
              child: Padding(
                padding: const EdgeInsets.only(left: Space.m),
                child: TextButton(
                  key: const Key('plus:offer'),
                  onPressed: () => _open(context, offerUrl),
                  child: Text(
                    'Оферта',
                    style: s.body(14, weight: FontWeight.w600, color: p.accent),
                  ),
                ),
              ),
            ),
        ],
        const Section('Позови друга'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l),
          child: _InviteCard(api: api, invite: invite),
        ),
        const Section('Поддержать проект'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l),
          child: Tile(
            key: const Key('plus:donate'),
            onTap: () => showDonateSheet(context, api),
            child: Row(
              children: [
                Icon(Icons.favorite_border_rounded, color: p.accent),
                const SizedBox(width: Space.m),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Сказать спасибо рублём', style: s.body(15, weight: FontWeight.w600)),
                      Text(donateNote, style: s.body(13, color: p.muted)),
                    ],
                  ),
                ),
                Icon(Icons.chevron_right_rounded, color: p.muted),
              ],
            ),
          ),
        ),
        if (ranks.isNotEmpty) ...[
          const Section('Бонусы за ранги ачивок'),
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.s),
            child: Text(
              'Открой все ачивки ранга на телефоне — дни подписки придут сами.',
              style: s.body(13, color: p.muted),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: Tile(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  for (final r in Rank.values)
                    if (ranks[r.name] is Map) ...[
                      if (r != Rank.dawn) Divider(height: 1, color: p.line),
                      _RankRow(rank: r, info: Map<String, dynamic>.from(ranks[r.name] as Map)),
                    ],
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _Tag extends StatelessWidget {
  final String text;
  const _Tag(this.text);

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.s, vertical: 2),
      decoration: BoxDecoration(color: s.p.accent, borderRadius: BorderRadius.circular(99)),
      child: Text(
        text,
        style: s.body(12, weight: FontWeight.w600, color: s.p.onAccent),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final IconData icon;
  final String title, sub;
  const _Row({required this.icon, required this.title, required this.sub});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
      child: Row(
        children: [
          Icon(icon, color: s.p.accent),
          const SizedBox(width: Space.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: s.body(15, weight: FontWeight.w600)),
                Text(sub, style: s.body(13, color: s.p.muted)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PriceRow extends StatelessWidget {
  final Map<String, dynamic> price;
  const _PriceRow({required this.price});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final now = price['price'], full = price['full'];
    final cut = now is num && full is num && now < full;
    final days = price['days'] is int ? price['days'] as int : 0;
    return Padding(
      key: Key('plus:price:${price['plan']}'),
      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${price['title'] ?? ''}', style: s.body(15, weight: FontWeight.w600)),
                Wrap(
                  spacing: Space.s,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    if (days > 0) Text(_days(days), style: s.body(13, color: p.muted)),
                    if (price['founder'] == true) const _Tag('Основатель'),
                  ],
                ),
              ],
            ),
          ),
          if (cut) ...[
            Text(
              '$full ₽',
              style: s.body(14, color: p.muted).copyWith(decoration: TextDecoration.lineThrough),
            ),
            const SizedBox(width: Space.s),
          ],
          Text('$now ₽', style: s.body(18, weight: FontWeight.w700)),
        ],
      ),
    );
  }
}

class _RankRow extends StatelessWidget {
  final Rank rank;
  final Map<String, dynamic> info;
  const _RankRow({required this.rank, required this.info});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final days = info['days'] is int ? info['days'] as int : 0;
    final need = info['need_days'] is int ? info['need_days'] as int : 0;
    final claimed = info['claimed'] == true;
    return Padding(
      key: Key('plus:rank:${rank.name}'),
      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
      child: Row(
        children: [
          RankBadge(rank: rank, size: 34),
          const SizedBox(width: Space.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${rank.title} · +${_days(days)}', style: s.body(15, weight: FontWeight.w600)),
                Text(
                  claimed
                      ? 'получено'
                      : (need > 1
                            ? 'все ачивки ранга и $need ${plural(need, 'день', 'дня', 'дней')} с заходами'
                            : 'все ачивки ранга'),
                  style: s.body(13, color: claimed ? p.ok : p.muted),
                ),
              ],
            ),
          ),
          if (claimed) Icon(Icons.check_circle_rounded, color: p.ok),
        ],
      ),
    );
  }
}

class _InviteCard extends StatelessWidget {
  final Api api;
  final Map<String, dynamic> invite;
  const _InviteCard({required this.api, required this.invite});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final came = invite['came'] is int ? invite['came'] as int : 0;
    final rewarded = invite['rewarded'] is int ? invite['rewarded'] as int : 0;
    final bonus = invite['bonus_days'] is int ? invite['bonus_days'] as int : 0;
    final need = invite['friend_days'] is int ? invite['friend_days'] as int : 0;
    return Tile(
      key: const Key('plus:invite'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (bonus > 0)
            Text(
              '+${_days(bonus)} обоим, когда друг попользуется Капибарой $need ${plural(need, 'день', 'дня', 'дней')}',
              style: s.body(15, weight: FontWeight.w600),
            ),
          const SizedBox(height: 4),
          Text(
            came == 0 ? 'По твоей ссылке пока никто не пришёл' : 'Пришло по ссылке: $came · засчитано: $rewarded',
            style: s.body(13, color: p.muted),
          ),
          const SizedBox(height: Space.m),
          FilledButton.icon(
            key: const Key('plus:invite:go'),
            style: FilledButton.styleFrom(
              backgroundColor: p.accent,
              foregroundColor: p.onAccent,
              minimumSize: const Size.fromHeight(46),
              shape: const StadiumBorder(),
            ),
            onPressed: () {
              tick();
              showInviteSheet(context, api);
            },
            icon: const Icon(Icons.group_add_outlined, size: 20),
            label: Text(
              'Позвать друга',
              style: s.body(15, weight: FontWeight.w600, color: p.onAccent),
            ),
          ),
        ],
      ),
    );
  }
}

// ── «Позвать друга»: готовое сообщение, а не голая ссылка ───────────────

/// Лист «Позвать»: в Telegram (t.me/share — Telegram сам предложит чат),
/// системное «Поделиться…», «Скопировать». Работает везде, и на iPhone —
/// там без строк про дни подписки (их и не присылает сервер).
Future<void> showInviteSheet(BuildContext context, Api api) async {
  final toast = Overlay.of(context, rootOverlay: true);
  Map<String, dynamic> d;
  try {
    d = Map<String, dynamic>.from(await api.get('/invite') as Map);
    if ('${d['link'] ?? ''}'.isEmpty) throw ApiError('Не получилось взять ссылку — попробуй позже');
  } catch (e) {
    toastOn(toast, errorText(e), kind: ToastKind.error);
    return;
  }
  if (!context.mounted) return;
  await appSheet<void>(context, (_) => InviteSheet(data: d));
}

class InviteSheet extends StatelessWidget {
  final Map<String, dynamic> data;
  const InviteSheet({super.key, required this.data});

  String get _link => '${data['link'] ?? ''}';
  String get _message {
    final text = '${data['share_text'] ?? ''}'.trim();
    return text.isEmpty ? _link : '$text\n$_link';
  }

  Future<void> _telegram(BuildContext context) async {
    final tg = '${data['tg_share'] ?? ''}';
    final toast = Overlay.of(context, rootOverlay: true);
    Navigator.pop(context);
    var ok = false;
    try {
      if (tg.isNotEmpty) ok = await PlusLinks.open(Uri.parse(tg));
    } catch (_) {}
    if (!ok) await _copyTo(toast, _message, 'Telegram не открылся — сообщение скопировано, вставь его в чат');
  }

  Future<void> _share(BuildContext context, Rect? origin) async {
    final toast = Overlay.of(context, rootOverlay: true);
    final msg = _message;
    Navigator.pop(context);
    try {
      await PlusLinks.share(msg, origin);
    } catch (_) {
      await _copyTo(toast, msg, 'Не вышло поделиться — сообщение скопировано');
    }
  }

  Future<void> _copy(BuildContext context) async {
    final toast = Overlay.of(context, rootOverlay: true);
    Navigator.pop(context);
    await _copyTo(toast, _message, 'Скопировано — вставь в чат другу');
  }

  static Future<void> _copyTo(OverlayState toast, String text, String done) async {
    try {
      await Clipboard.setData(ClipboardData(text: text));
    } catch (_) {
      toastOn(toast, 'Не удалось скопировать — попробуй ещё раз.', kind: ToastKind.error);
      return;
    }
    toastOn(toast, done, kind: ToastKind.done);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final bonus = data['bonus_days'] is int ? data['bonus_days'] as int : 0;
    final need = data['friend_days'] is int ? data['friend_days'] as int : 0;
    final shareKey = GlobalKey();
    Rect? origin() {
      final box = shareKey.currentContext?.findRenderObject();
      if (box is! RenderBox || !box.hasSize) return null;
      return box.localToGlobal(Offset.zero) & box.size;
    }

    ButtonStyle outlined() => OutlinedButton.styleFrom(
      foregroundColor: p.text,
      side: BorderSide(color: p.line),
      minimumSize: const Size.fromHeight(50),
      shape: const StadiumBorder(),
    );
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Позвать друга', style: s.title(24)),
            const SizedBox(height: Space.s),
            Text('Друг получит готовое сообщение с твоей ссылкой:', style: s.body(15, color: p.muted)),
            const SizedBox(height: Space.m),
            Tile(
              key: const Key('invite:preview'),
              child: Text(_message, style: s.body(14).copyWith(height: 1.4)),
            ),
            if (bonus > 0 && PlusBonus.allowed) ...[
              const SizedBox(height: Space.s),
              Text(
                '+${_days(bonus)} Капибары+ вам обоим, когда друг попользуется $need ${plural(need, 'день', 'дня', 'дней')}',
                key: const Key('invite:bonus'),
                style: s.body(13, color: p.muted),
              ),
            ],
            const SizedBox(height: Space.xl),
            FilledButton.icon(
              key: const Key('invite:tg'),
              style: FilledButton.styleFrom(
                backgroundColor: p.accent,
                foregroundColor: p.onAccent,
                minimumSize: const Size.fromHeight(50),
                shape: const StadiumBorder(),
              ),
              onPressed: () {
                tick();
                _telegram(context);
              },
              icon: const Icon(Icons.send_rounded, size: 20),
              label: Text(
                'Отправить в Telegram',
                style: s.body(16, weight: FontWeight.w600, color: p.onAccent),
              ),
            ),
            const SizedBox(height: Space.s),
            OutlinedButton.icon(
              key: const Key('invite:share'),
              style: outlined(),
              onPressed: () {
                tick();
                _share(context, origin());
              },
              icon: Icon(Icons.ios_share_rounded, size: 20, key: shareKey),
              label: Text('Поделиться…', style: s.body(16, weight: FontWeight.w600)),
            ),
            const SizedBox(height: Space.s),
            OutlinedButton.icon(
              key: const Key('invite:copy'),
              style: outlined(),
              onPressed: () {
                tick();
                _copy(context);
              },
              icon: const Icon(Icons.copy_rounded, size: 20),
              label: Text('Скопировать', style: s.body(16, weight: FontWeight.w600)),
            ),
          ],
        ),
      ),
    );
  }
}

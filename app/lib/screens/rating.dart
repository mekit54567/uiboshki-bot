// «Рейтинг» (5.100.3, Никита 18.10): прежде всего место группы — в своём
// институте и во всём университете; люди своей группы — только те, кто сам
// согласился, под своим ником. Опыт считает сервер (xp.py) по тому, что видно
// в СДО, — галочка «сделал» от руки его не даёт.
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';
import 'files.dart' show BackRow;
import 'notify.dart' show AppSwitch;

class RatingScreen extends StatefulWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const RatingScreen({super.key, required this.api, this.onUnauthorized});

  @override
  State<RatingScreen> createState() => _RatingScreenState();
}

class _RatingScreenState extends State<RatingScreen> {
  int _epoch = 0;

  Api get api => widget.api;

  Future<void> _save(Map<String, Object?> body) async {
    tick();
    try {
      await api.put('/rating/me', body);
    } on ApiError catch (e) {
      if (mounted) showToast(context, e.message, kind: ToastKind.error);
      return;
    }
    if (mounted) setState(() => _epoch++);
  }

  Future<void> _nick(Map me) async {
    final v = await inputSheet(
      context,
      title: 'Ник в рейтинге',
      text:
          'Его видит только твоя группа, и только если ты включишь «Показывать меня». '
          'Пустое поле — имя и первая буква фамилии.',
      hint: me['nick'] as String? ?? '',
      initial: me['custom_nick'] == true ? me['nick'] as String? ?? '' : '',
    );
    if (v != null) await _save({'nick': v});
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Backdrop(
      child: SafeArea(
        child: Loader<Map<String, dynamic>>(
          key: ValueKey(_epoch),
          load: () async => Map<String, dynamic>.from(await api.get('/rating')),
          onUnauthorized: widget.onUnauthorized,
          builder: (context, d, _) {
            final group = Map<String, dynamic>.from(d['group'] as Map? ?? const {});
            final me = Map<String, dynamic>.from(d['me'] as Map? ?? const {});
            final inst = (d['institute_top'] as List?) ?? const [];
            final all = (d['university_top'] as List?) ?? const [];
            final people = (d['people'] as List?) ?? const [];
            final rules = Map<String, dynamic>.from(d['rules'] as Map? ?? const {});
            return ListView(
              padding: const EdgeInsets.only(bottom: Space.xxl),
              children: [
                const BackRow(),
                ScreenTitle(title: 'Рейтинг', sub: group['name'] as String?),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: _GroupCard(group: group),
                ),
                if (inst.isNotEmpty) ...[
                  Section(
                    (group['institute_name'] as String?)?.isNotEmpty == true
                        ? group['institute_name'] as String
                        : 'Институт',
                  ),
                  _Board(rows: inst, placeKey: 'place_inst'),
                ],
                if (all.isNotEmpty) ...[const Section('Весь университет'), _Board(rows: all, placeKey: 'place')],
                const Section('Моя группа'),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: _People(
                    people: people,
                    me: me,
                    onShow: () => _save({'show': me['show'] != true}),
                    onNick: () => _nick(me),
                  ),
                ),
                const Section('Мой опыт'),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: _MyXp(me: me),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(Space.xl, Space.m, Space.xl, 0),
                  child: Text(
                    _rulesText(rules),
                    style: AppStyle.of(context).body(13, color: AppStyle.of(context).p.muted),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    ),
  );
}

String _rulesText(Map r) {
  final n = (r['min_people'] as num?)?.toInt() ?? 3;
  return 'Опыт — за то, что видно в СДО: ${r['brs'] ?? 1} за каждый балл БРС, ${r['submit'] ?? 15} '
      'за сданную работу и ещё ${r['early'] ?? 10}, если сдал за сутки до срока; от ${r['ach_min'] ?? 3} до ${r['ach_max'] ?? 25} за '
      'ачивку (чем выше ранг, тем больше) и ${r['file'] ?? 2} за файл, который ты выложил группе. Галочка «сделал» опыта не даёт. '
      'Опыт группы — сумма опыта её людей; в рейтинг группа попадает, когда опыт есть хотя бы у $n '
      '${plural(n, 'человека', 'человек', 'человек')}.';
}

String _xp(Object? v) => '${(v as num?)?.toInt() ?? 0}';

/// Место группы: в институте и во всём вузе — двумя крупными цифрами.
class _GroupCard extends StatelessWidget {
  final Map<String, dynamic> group;
  const _GroupCard({required this.group});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final place = group['place'] as int?;
    final need = (group['need'] as num?)?.toInt() ?? 0;
    if (place == null) {
      return Tile(
        key: const Key('rating:wait'),
        child: Row(
          children: [
            Icon(Icons.hourglass_empty_rounded, color: p.muted),
            const SizedBox(width: Space.m),
            Expanded(
              child: Text(
                need > 0
                    ? 'Группа попадёт в рейтинг, когда опыт появится ещё у $need '
                          '${plural(need, 'человека', 'человек', 'человек')}. Опыт дают сданные работы и баллы БРС.'
                    : 'Рейтинг пересчитывается раз в несколько минут — загляни чуть позже.',
                style: s.body(14, color: p.muted),
              ),
            ),
          ],
        ),
      );
    }
    Widget cell(String key, Object? value, Object? of, String where) => Expanded(
      child: Column(
        key: Key(key),
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value == null ? '—' : '$value', style: s.number(40)),
          const SizedBox(height: 6),
          Text(where, style: s.body(13.5, weight: FontWeight.w600)),
          if (of != null)
            Text(
              'из $of ${plural((of as num).toInt(), 'группы', 'групп', 'групп')}',
              style: s.body(13, color: p.muted),
            ),
        ],
      ),
    );
    return Tile(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if ((group['institute'] as String?)?.isNotEmpty == true) ...[
                cell('rating:inst', group['place_inst'], group['groups_inst'], 'место в ${group['institute']}'),
                const SizedBox(width: Space.l),
              ],
              cell('rating:all', place, group['groups_all'], 'место в университете'),
            ],
          ),
          const SizedBox(height: Space.m),
          Divider(height: 1, color: p.line),
          const SizedBox(height: Space.m),
          Text(
            'У группы ${_xp(group['xp'])} опыта · с опытом ${group['people'] ?? 0} '
            '${plural((group['people'] as num?)?.toInt() ?? 0, 'человек', 'человека', 'человек')}',
            style: s.body(14, color: p.muted),
          ),
        ],
      ),
    );
  }
}

/// Топ групп: место, название, опыт; своя группа — акцентом.
class _Board extends StatelessWidget {
  final List rows;
  final String placeKey;
  const _Board({required this.rows, required this.placeKey});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: Tile(
        padding: EdgeInsets.zero,
        child: Column(
          children: [
            for (var i = 0; i < rows.length; i++) ...[
              if (i > 0) Divider(height: 1, color: p.line),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                child: Row(
                  children: [
                    SizedBox(
                      width: 32,
                      child: Text(
                        '${rows[i][placeKey] ?? ''}',
                        style: s.number(17, color: rows[i]['mine'] == true ? p.accent : p.muted),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        rows[i]['name'] as String? ?? '',
                        style: s.body(
                          15,
                          weight: rows[i]['mine'] == true ? FontWeight.w700 : FontWeight.w500,
                          color: rows[i]['mine'] == true ? p.accent : p.text,
                        ),
                      ),
                    ),
                    Text(_xp(rows[i]['xp']), style: s.number(15, color: p.muted)),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Люди своей группы (кто согласился) и свои настройки: показывать ли меня, ник.
class _People extends StatelessWidget {
  final List people;
  final Map me;
  final VoidCallback onShow, onNick;
  const _People({required this.people, required this.me, required this.onShow, required this.onNick});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final show = me['show'] == true;
    return Tile(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.s, Space.m),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Показывать меня группе', style: s.body(15, weight: FontWeight.w600)),
                      Text(
                        show
                            ? 'группа видит твой ник и опыт (он считается из баллов СДО и сдач)'
                            : 'включишь — группа увидит твой ник и опыт (он считается из баллов СДО и сдач)',
                        style: s.body(12.5, color: p.muted),
                      ),
                    ],
                  ),
                ),
                AppSwitch(key: const Key('rating:show'), value: show, onChanged: onShow),
              ],
            ),
          ),
          Divider(height: 1, color: p.line),
          InkWell(
            key: const Key('rating:nick'),
            onTap: () {
              tick();
              onNick();
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
              child: Row(
                children: [
                  Text('Ник', style: s.body(15, weight: FontWeight.w600)),
                  const SizedBox(width: Space.m),
                  Expanded(
                    child: Text(
                      me['nick'] as String? ?? '',
                      textAlign: TextAlign.end,
                      overflow: TextOverflow.ellipsis,
                      style: s.body(15, color: p.muted),
                    ),
                  ),
                  Icon(Icons.chevron_right_rounded, color: p.muted),
                ],
              ),
            ),
          ),
          for (final r in people) ...[
            Divider(height: 1, color: p.line),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
              child: Row(
                children: [
                  Expanded(
                    child: Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                            text: r['nick'] as String? ?? '',
                            style: s.body(15, weight: r['me'] == true ? FontWeight.w700 : FontWeight.w500),
                          ),
                          if (r['me'] == true && r['hidden'] == true)
                            TextSpan(
                              text: '  · видишь только ты',
                              style: s.body(12.5, color: p.muted),
                            ),
                        ],
                      ),
                    ),
                  ),
                  Text(_xp(r['xp']), style: s.number(15, color: p.muted)),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Свой опыт по частям: за что сколько.
class _MyXp extends StatelessWidget {
  final Map me;
  const _MyXp({required this.me});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    const parts = [
      ('brs', 'Баллы БРС'),
      ('submit', 'Сданные работы'),
      ('early', 'Сдано заранее'),
      ('ach', 'Ачивки'),
      ('file', 'Файлы для группы'),
    ];
    Widget row(String title, Object? v, {bool total = false}) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
      child: Row(
        children: [
          Expanded(
            child: Text(title, style: s.body(15, weight: total ? FontWeight.w700 : FontWeight.w400)),
          ),
          Text(
            _xp(v),
            style: total ? s.number(20, color: p.accent) : s.number(15, color: p.muted),
          ),
        ],
      ),
    );
    return Tile(
      key: const Key('rating:mine'),
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          for (final (k, t) in parts) ...[row(t, me[k]), Divider(height: 1, color: p.line)],
          row('Всего', me['total'], total: true),
        ],
      ),
    );
  }
}

/// Строка «Рейтинг» в «Ещё»: место группы одной фразой.
class RatingRow extends StatefulWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const RatingRow({super.key, required this.api, this.onUnauthorized});

  static String line(Object? data) {
    final g = data is Map ? data['group'] : null;
    if (g is! Map || g['place'] == null) return 'места групп в институте и вузе';
    final all = '${g['place']} место в вузе';
    final inst = g['institute'] as String?;
    return inst != null && inst.isNotEmpty && g['place_inst'] != null
        ? '${g['place_inst']} место в $inst · ${g['place']} в вузе'
        : all;
  }

  @override
  State<RatingRow> createState() => _RatingRowState();
}

class _RatingRowState extends State<RatingRow> {
  // одна загрузка на экран «Ещё», а не на каждую перестройку
  late Future<dynamic> _data = _load();

  Future<dynamic> _load() => widget.api.get('/rating').then<dynamic>((v) => v, onError: (_) => null);

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return FutureBuilder<dynamic>(
      future: _data,
      builder: (context, snap) => Tile(
        key: const Key('more:rating'),
        onTap: () async {
          await Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => RatingScreen(api: widget.api, onUnauthorized: widget.onUnauthorized),
            ),
          );
          if (mounted) setState(() => _data = _load());
        },
        child: Row(
          children: [
            Icon(Icons.leaderboard_outlined, color: p.accent),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Рейтинг', style: s.body(15, weight: FontWeight.w700)),
                  Text(RatingRow.line(snap.data), style: s.body(13, color: p.muted)),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded, color: p.muted),
          ],
        ),
      ),
    );
  }
}

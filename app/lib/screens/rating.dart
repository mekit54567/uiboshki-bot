// «Рейтинг» (5.100.3, Никита 18.10): прежде всего место группы — в своём
// институте и во всём университете; люди своей группы — только те, кто сам
// согласился, под своим ником. Опыт считает сервер (xp.py) по тому, что видно
// в СДО, — галочка «сделал» от руки его не даёт. 5.100.5 (Никита: «мб
// диаграммки»): как росла группа по неделям, из чего её опыт, и группа по
// нажатию — её люди, кто разрешил (своей группе — «группе», всем — «всем»).
// «Показывать меня всем» — распространение (ст. 10.1 152-ФЗ, ревью 18.10):
// включается только через лист с отдельным согласием, а чужие видят свой ник
// человека или «Капибара №…», не имя.
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';
import '../widgets/trend_chart.dart';
import 'files.dart' show BackRow;
import 'legal.dart' show LegalLink, openLegal;
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
          'Можно: 2–24 знака — буквы, цифры, пробел, точка, дефис и _. Слово «капибара» в своём '
          'нике тоже можно: «Капибара на паре».\n'
          'Нельзя: мат и оскорбления, а ещё выдавать себя за сервис, МИРЭА или старост — «Капибара», '
          '«Капибара МИРЭА», «Админ», «Поддержка», «Староста».\n'
          'Ник видит твоя группа, если включишь «Показывать меня группе», и все — если «Показывать '
          'меня всем». Пустое поле — имя и первая буква фамилии: так тебя видит только группа, '
          'остальные — «Капибара №…».',
      hint: me['nick'] as String? ?? '',
      initial: me['custom_nick'] == true ? me['nick'] as String? ?? '' : '',
    );
    if (v != null) await _save({'nick': v});
  }

  /// Включить «всем» — только через лист отдельного согласия; выключить — сразу.
  Future<void> _showAll(Map me) async {
    if (me['show_all'] == true) return _save({'show_all': false});
    tick();
    final Map doc;
    try {
      doc = Map<String, dynamic>.from(await api.get('/legal/rating_all') as Map);
    } on ApiError catch (e) {
      if (mounted) showToast(context, e.message, kind: ToastKind.error);
      return;
    }
    if (!mounted) return;
    final version = await appSheet<String>(
      context,
      (_) => ShowAllSheet(api: api, doc: doc, seenAs: me['public_nick'] as String?),
    );
    if (version != null) await _save({'show_all': true, 'consent': version});
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
                ..._groupCharts(group),
                if (inst.isNotEmpty) ...[
                  Section(
                    (group['institute_name'] as String?)?.isNotEmpty == true
                        ? group['institute_name'] as String
                        : 'Институт',
                  ),
                  _Board(rows: inst, placeKey: 'place_inst', api: api, onUnauthorized: widget.onUnauthorized),
                ],
                if (all.isNotEmpty) ...[
                  const Section('Весь университет'),
                  _Board(rows: all, placeKey: 'place', api: api, onUnauthorized: widget.onUnauthorized),
                ],
                const Section('Моя группа'),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: _People(
                    people: people,
                    me: me,
                    onShow: () => _save({'show': me['show'] != true}),
                    onShowAll: () => _showAll(me),
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

const _partNames = [
  ('brs', 'Баллы БРС'),
  ('submit', 'Сданные работы'),
  ('early', 'Сдано заранее'),
  ('ach', 'Ачивки'),
  ('file', 'Файлы для группы'),
];

List<(String, num)> _parts(Object? m) => [for (final (k, t) in _partNames) (t, (m is Map ? m[k] as num? : null) ?? 0)];

/// Под карточкой мест: «Как росла группа» (график по неделям) и «Из чего
/// опыт группы» (полосы) — пока у группы нет опыта, их нет.
List<Widget> _groupCharts(Map<String, dynamic> group) {
  final history = (group['history'] as List?) ?? const [];
  if (((group['xp'] as num?) ?? 0) <= 0) return const [];
  return [
    if (history.length > 1) ...[
      const Section('Как росла группа'),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l),
        child: _Growth(group: group, history: history),
      ),
    ],
    const Section('Из чего опыт группы'),
    Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: Tile(
        key: const Key('rating:parts'),
        padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, Space.s),
        child: PartsBars(parts: _parts(group['parts'])),
      ),
    ),
  ];
}

/// Опыт группы или её место по неделям — переключатель над одним графиком
/// (две величины разного масштаба на одной оси не рисуем).
class _Growth extends StatefulWidget {
  final Map<String, dynamic> group;
  final List history;
  const _Growth({required this.group, required this.history});

  @override
  State<_Growth> createState() => _GrowthState();
}

class _GrowthState extends State<_Growth> {
  /// Что на графике: 'xp' — опыт, 'place_inst' — место в институте,
  /// 'place' — место среди всех групп вуза (Никита 18.10).
  String _mode = 'xp';

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final inst = widget.group['institute'] as String? ?? '';
    final h = widget.history.cast<Map>();
    bool has(String k) => h.any((w) => w[k] != null);
    final modes = [
      ('xp', 'Опыт', ''),
      if (inst.isNotEmpty && has('place_inst')) ('place_inst', 'В $inst', 'в $inst'),
      if (has('place')) ('place', 'В вузе', 'в вузе'),
    ];
    final mode = modes.any((m) => m.$1 == _mode) ? _mode : 'xp';
    final where = modes.firstWhere((m) => m.$1 == mode).$3;
    final place = mode != 'xp';
    Widget chip(String text, bool on, VoidCallback tap, Key k) => GestureDetector(
      key: k,
      onTap: () {
        tick();
        tap();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: on ? p.accent : Colors.transparent,
          borderRadius: BorderRadius.circular(Radii.chip),
          border: Border.all(color: on ? p.accent : p.line),
        ),
        child: Text(
          text,
          style: s.body(13, weight: FontWeight.w600, color: on ? p.onAccent : p.muted),
        ),
      ),
    );
    return Tile(
      key: const Key('rating:growth'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (modes.length > 1) ...[
            Wrap(
              spacing: Space.s,
              runSpacing: Space.s,
              children: [
                for (final (k, title, _) in modes)
                  chip(
                    title,
                    mode == k,
                    () => setState(() => _mode = k),
                    Key(
                      k == 'xp'
                          ? 'rating:growth:xp'
                          : k == 'place'
                          ? 'rating:growth:place_all'
                          : 'rating:growth:place',
                    ),
                  ),
              ],
            ),
            const SizedBox(height: Space.m),
          ],
          TrendChart(
            key: ValueKey(mode),
            values: [for (final w in h) place ? w[mode] as num? : (w['xp'] as num?) ?? 0],
            labels: [for (final w in h) '${w['week'] ?? ''}'],
            invert: place,
            format: (v) => place ? '${v.toInt()} место $where' : '${v.toInt()} опыта',
          ),
        ],
      ),
    );
  }
}

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
  final Api api;
  final VoidCallback? onUnauthorized;
  const _Board({required this.rows, required this.placeKey, required this.api, this.onUnauthorized});

  void _open(BuildContext context, Map row) {
    final id = row['id'] as int?;
    if (id == null) return;
    tick();
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) =>
            GroupRatingScreen(api: api, id: id, name: row['name'] as String? ?? '', onUnauthorized: onUnauthorized),
      ),
    );
  }

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
              InkWell(
                key: Key('rating:group:${rows[i]['id']}:$placeKey'),
                onTap: () => _open(context, rows[i] as Map),
                child: Padding(
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
                      const SizedBox(width: 4),
                      Icon(Icons.chevron_right_rounded, size: 18, color: p.muted),
                    ],
                  ),
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
  final VoidCallback onShow, onShowAll, onNick;
  const _People({
    required this.people,
    required this.me,
    required this.onShow,
    required this.onShowAll,
    required this.onNick,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final show = me['show'] == true;
    final all = me['show_all'] == true;
    Widget toggle(String title, String sub, bool on, VoidCallback tap, Key k) => Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.s, Space.m),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: s.body(15, weight: FontWeight.w600)),
                Text(sub, style: s.body(12.5, color: p.muted)),
              ],
            ),
          ),
          AppSwitch(key: k, value: on, onChanged: tap),
        ],
      ),
    );
    return Tile(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          toggle(
            'Показывать меня группе',
            show
                ? 'группа видит твой ник и опыт (он считается из баллов СДО и сдач)'
                : 'включишь — группа увидит твой ник и опыт (он считается из баллов СДО и сдач)',
            show,
            onShow,
            const Key('rating:show'),
          ),
          Divider(height: 1, color: p.line),
          toggle(
            'Показывать меня всем',
            all
                ? 'все пользователи Капибары видят тебя как «${me['public_nick'] ?? 'Капибара №…'}» и твой опыт'
                : 'по отдельному согласию: все увидят твой ник (или «Капибара №…», не имя) и опыт',
            all,
            onShowAll,
            const Key('rating:show_all'),
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

/// Свой опыт по частям: за что сколько — полосами, внизу итог.
class _MyXp extends StatelessWidget {
  final Map me;
  const _MyXp({required this.me});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Tile(
      key: const Key('rating:mine'),
      padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, Space.m),
      child: Column(
        children: [
          PartsBars(parts: _parts(me)),
          const SizedBox(height: Space.s),
          Divider(height: 1, color: p.line),
          const SizedBox(height: Space.m),
          Row(
            children: [
              Expanded(
                child: Text('Всего', style: s.body(15, weight: FontWeight.w700)),
              ),
              Text(_xp(me['total']), style: s.number(20, color: p.accent)),
            ],
          ),
        ],
      ),
    );
  }
}

/// Группа из рейтинга по нажатию: места, как росла, из чего опыт и её люди —
/// только кто разрешил (своей группе — «группе» или «всем», чужим — «всем»).
class GroupRatingScreen extends StatelessWidget {
  final Api api;
  final int id;
  final String name;
  final VoidCallback? onUnauthorized;
  const GroupRatingScreen({super.key, required this.api, required this.id, required this.name, this.onUnauthorized});

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Backdrop(
      child: SafeArea(
        child: Loader<Map<String, dynamic>>(
          load: () async => Map<String, dynamic>.from(await api.get('/rating/group/$id')),
          onUnauthorized: onUnauthorized,
          builder: (context, g, _) {
            final s = AppStyle.of(context);
            final p = s.p;
            final people = (g['people_list'] as List?) ?? const [];
            final hidden = (g['hidden'] as num?)?.toInt() ?? 0;
            final member = g['member'] == true;
            final inst = g['institute_name'] as String? ?? '';
            return ListView(
              padding: const EdgeInsets.only(bottom: Space.xxl),
              children: [
                const BackRow(),
                ScreenTitle(title: g['name'] as String? ?? name, sub: inst.isEmpty ? null : inst),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: _GroupCard(group: g),
                ),
                ..._groupCharts(g),
                const Section('Люди'),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: Tile(
                    key: const Key('rating:group:people'),
                    padding: EdgeInsets.zero,
                    child: Column(
                      children: [
                        for (var i = 0; i < people.length; i++) ...[
                          if (i > 0) Divider(height: 1, color: p.line),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    people[i]['nick'] as String? ?? '',
                                    style: s.body(
                                      15,
                                      weight: people[i]['me'] == true ? FontWeight.w700 : FontWeight.w500,
                                    ),
                                  ),
                                ),
                                Text(_xp(people[i]['xp']), style: s.number(15, color: p.muted)),
                              ],
                            ),
                          ),
                        ],
                        if (people.isNotEmpty && hidden > 0) Divider(height: 1, color: p.line),
                        if (people.isEmpty || hidden > 0)
                          Padding(
                            padding: const EdgeInsets.all(Space.l),
                            child: Text(
                              people.isEmpty
                                  ? (member
                                        ? 'Пока никто не включил «Показывать меня группе».'
                                        : 'Пока никто из группы не включил «Показывать меня всем».')
                                  : 'Ещё $hidden ${plural(hidden, 'человек', 'человека', 'человек')} с опытом '
                                        'не показывают себя.',
                              style: s.body(14, color: p.muted),
                            ),
                          ),
                      ],
                    ),
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

/// Отдельное согласие на показ всем (ст. 10.1): на листе — общая
/// формулировка, что показываем, где и кому (разделы с sheet из
/// /legal/rating_all) и как тебя увидят; оператор, срок и остальное — в
/// полном тексте по ссылке (Никита 18.10: «запрятать»). Галочка по умолчанию
/// не стоит, «Включить» без неё неактивна. Возвращает версию текста.
class ShowAllSheet extends StatefulWidget {
  final Api api;
  final Map doc;
  final String? seenAs;
  const ShowAllSheet({super.key, required this.api, required this.doc, this.seenAs});

  @override
  State<ShowAllSheet> createState() => _ShowAllSheetState();
}

class _ShowAllSheetState extends State<ShowAllSheet> {
  bool _agree = false;
  late final _full = TapGestureRecognizer()..onTap = () => openLegal(context, widget.api, 'rating_all');

  @override
  void dispose() {
    _full.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final d = widget.doc;
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.85),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Flexible(
              child: ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.m),
                children: [
                  Text(d['title'] as String? ?? '', style: s.title(24)),
                  const SizedBox(height: Space.xs),
                  Text('Версия ${d['version']} от ${d['date']}', style: s.body(12.5, color: p.muted)),
                  const SizedBox(height: Space.m),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                    decoration: BoxDecoration(color: p.card, borderRadius: BorderRadius.circular(Radii.chip)),
                    child: Text.rich(
                      TextSpan(
                        style: s.body(14, color: p.muted),
                        children: [
                          const TextSpan(text: 'Все увидят тебя как '),
                          TextSpan(
                            text: widget.seenAs ?? 'Капибара №…',
                            style: s.body(14, weight: FontWeight.w700),
                          ),
                          if (widget.seenAs == null) const TextSpan(text: ' — номер случайный, дадим при включении'),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: Space.m),
                  Text((d['lead_short'] ?? d['lead']) as String? ?? '', style: s.body(14)),
                  for (final sec in (d['sections'] as List? ?? const []))
                    if (sec['sheet'] == true || d['lead_short'] == null) ...[
                      const SizedBox(height: Space.m),
                      Text(
                        sec['title'] as String,
                        style: s.body(13, weight: FontWeight.w700, color: p.muted),
                      ),
                      const SizedBox(height: Space.xs),
                      for (final b in (sec['blocks'] as List))
                        if (b['ul'] != null)
                          for (final item in (b['ul'] as List))
                            Padding(
                              padding: const EdgeInsets.only(bottom: Space.xs),
                              child: Text('• $item', style: s.body(14)),
                            )
                        else
                          Padding(
                            padding: const EdgeInsets.only(bottom: Space.xs),
                            child: Text(b['p'] as String, style: s.body(14)),
                          ),
                    ],
                  if (d['lead_short'] != null) ...[
                    const SizedBox(height: Space.s),
                    InkWell(
                      key: const Key('rating:all:full'),
                      onTap: () => openLegal(context, widget.api, 'rating_all'),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: Space.xs),
                        child: Text(
                          'Полный текст согласия — кто оператор, срок, как отозвать',
                          style: s.body(14, color: p.link),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.xl, Space.s, Space.xl, Space.l),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Semantics(
                    checked: _agree,
                    child: InkWell(
                      key: const Key('rating:all:agree'),
                      borderRadius: BorderRadius.circular(Radii.chip),
                      onTap: () {
                        tick();
                        setState(() => _agree = !_agree);
                      },
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: Space.s),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            AnimatedContainer(
                              duration: const Duration(milliseconds: 150),
                              width: 22,
                              height: 22,
                              decoration: BoxDecoration(
                                color: _agree ? p.accent : Colors.transparent,
                                borderRadius: BorderRadius.circular(7),
                                border: Border.all(color: _agree ? p.accent : p.muted, width: 2),
                              ),
                              child: _agree ? Icon(Icons.check_rounded, size: 16, color: p.onAccent) : null,
                            ),
                            const SizedBox(width: Space.m),
                            Expanded(
                              child: Text.rich(
                                TextSpan(
                                  style: s.body(14),
                                  children: [
                                    const TextSpan(text: 'Даю '),
                                    TextSpan(
                                      text: 'согласие на показ ника и опыта всем пользователям Капибары',
                                      style: TextStyle(color: p.link),
                                      recognizer: _full,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: Space.m),
                  FilledButton(
                    key: const Key('rating:all:on'),
                    style: FilledButton.styleFrom(
                      backgroundColor: p.accent,
                      foregroundColor: p.onAccent,
                      minimumSize: const Size.fromHeight(50),
                      shape: const StadiumBorder(),
                    ),
                    onPressed: _agree ? () => Navigator.pop(context, '${d['version']}') : null,
                    child: Text(
                      'Включить',
                      style: s.body(16, weight: FontWeight.w600, color: p.onAccent),
                    ),
                  ),
                  TextButton(
                    style: TextButton.styleFrom(minimumSize: const Size.fromHeight(46)),
                    onPressed: () => Navigator.pop(context),
                    child: Text('Отмена', style: s.body(15, color: p.muted)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

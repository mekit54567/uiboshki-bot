// «Рейтинг» нового дизайна (шаг 7, макет «Итог: сначала твой личный
// рейтинг», Никита 11.11): экран открывается на «Я» — твоё место среди людей
// группы, института и вуза; «Группы» — места групп, как раньше. Ник,
// видимость и из чего опыт — в листе «Мой опыт» по кнопке сверху. Чужие ники —
// по тем же согласиям, что и в группе (сервер, xp._seen_as).
part of 'rating.dart';

/// 2940 → «2 940» (неразрывный пробел: число не рвётся по строкам).
String _n(Object? v) {
  final n = (v as num?)?.toInt() ?? 0;
  final d = n.abs().toString();
  final b = StringBuffer(n < 0 ? '-' : '');
  for (var i = 0; i < d.length; i++) {
    if (i > 0 && (d.length - i) % 3 == 0) b.write('\u00A0');
    b.write(d[i]);
  }
  return b.toString();
}

String _people(int n) => '${_n(n)}\u00A0${plural(n, 'человек', 'человека', 'человек')}';

/// «До 3 места 26 опыта: это две работы, сданные заранее» — сколько не
/// хватает до места выше, переведённое в понятные дела (правила — с сервера).
String ratingUpHint(Map scope, Map rules) {
  final place = (scope['place'] as num?)?.toInt();
  final up = (scope['up'] as num?)?.toInt();
  if (place == null) return 'Место появится с первым опытом: за баллы БРС и сданные работы.';
  if (place == 1) return (scope['of'] as num? ?? 0) > 1 ? 'Ты на первом месте.' : 'Пока опыт здесь только у тебя.';
  if (up == null || up <= 0) return '';
  final head = 'До ${place - 1}\u00A0места ${_n(up)} опыта';
  final brs = (rules['brs'] as num?)?.toInt() ?? 1;
  final submit = (rules['submit'] as num?)?.toInt() ?? 15;
  final early = (rules['early'] as num?)?.toInt() ?? 10;
  final points = (up / (brs < 1 ? 1 : brs)).ceil();
  if (points <= 5) return '$head: это $points ${plural(points, 'балл', 'балла', 'баллов')} БРС';
  if (up <= submit) return '$head: это одна сданная работа';
  if (up <= submit + early) return '$head: это одна работа, сданная заранее';
  final k = (up / (submit + early)).ceil();
  if (k > 9) return head;
  return '$head: это $k ${plural(k, 'работа, сданная', 'работы, сданные', 'работ, сданных')} заранее';
}

class _FreshRating extends StatelessWidget {
  final Map<String, dynamic> d;
  final _RatingScreenState st;
  const _FreshRating({required this.d, required this.st});

  @override
  Widget build(BuildContext context) {
    final me = Map<String, dynamic>.from(d['me'] as Map? ?? const {});
    final rules = Map<String, dynamic>.from(d['rules'] as Map? ?? const {});
    return ListView(
      key: const ValueKey('rating:fresh'),
      padding: const EdgeInsets.only(bottom: Space.xxl),
      children: [
        Row(
          children: [
            const BackRow(),
            const Spacer(),
            Padding(
              padding: const EdgeInsets.only(right: Space.l),
              child: _Pill(
                key: const Key('rating:mine:open'),
                icon: Icons.person_outline_rounded,
                text: 'Мой опыт',
                onTap: () => _openMine(context, st, me, rules),
              ),
            ),
          ],
        ),
        const ScreenTitle(title: 'Рейтинг', sub: 'активность в Капибаре, не успеваемость'),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
          child: _Tabs(
            key: const Key('rating:view'),
            labels: const ['Я', 'Группы'],
            on: st._view,
            accent: true,
            onPick: (i) => st._set(() => st._view = i),
          ),
        ),
        if (st._view == 0) ..._meView(context, me, rules) else ..._groupsView(context, me),
      ],
    );
  }

  List<Widget> _meView(BuildContext context, Map me, Map rules) {
    final ranks = d['ranks'] is Map ? d['ranks'] as Map : const {};
    final group = d['group'] as Map? ?? const {};
    final inst = group['institute'] as String? ?? '';
    final scopes = [
      ('group', 'Группа', 'Ты в группе'),
      if (ranks['inst'] is Map) ('inst', 'Институт', inst.isEmpty ? 'Ты в институте' : 'Ты в $inst'),
      ('all', 'Вуз', 'Ты в вузе'),
    ];
    final at = scopes.indexWhere((x) => x.$1 == st._scope);
    final i = at < 0 ? 0 : at;
    final (key, _, eyebrow) = scopes[i];
    final scope = ranks[key] is Map ? ranks[key] as Map : const {};
    return [
      _pad(_MeCard(scope: scope, me: me, rules: rules, eyebrow: eyebrow, vuz: key == 'all')),
      const SizedBox(height: Space.m),
      _pad(
        _Tabs(
          key: const Key('rating:scope'),
          labels: [for (final x in scopes) x.$2],
          on: i,
          onPick: (j) => st._set(() {
            st._scope = scopes[j].$1;
            st._expanded = false;
          }),
        ),
      ),
      const SizedBox(height: Space.m),
      _pad(
        _PeopleList(
          key: ValueKey('rating:people:$key'),
          rows: [for (final r in (scope['rows'] as List? ?? const [])) r as Map],
          me: me,
          scope: key,
          collapse: key == 'group' && !st._expanded,
          onExpand: () => st._set(() => st._expanded = true),
        ),
      ),
    ];
  }

  List<Widget> _groupsView(BuildContext context, Map me) {
    final group = Map<String, dynamic>.from(d['group'] as Map? ?? const {});
    final hasInst = (group['institute'] as String?)?.isNotEmpty == true;
    final tabs = [
      if (hasInst) ('inst', 'Институт', 'institute_top', 'place_inst'),
      ('all', 'Вуз', 'university_top', 'place'),
    ];
    final i = st._groupsTab.clamp(0, tabs.length - 1);
    final (_, _, listKey, placeKey) = tabs[i];
    final top = [for (final r in (d[listKey] as List? ?? const [])) r as Map];
    return [
      _pad(
        group['place'] == null
            ? _GroupCard(group: group)
            : _GroupsCard(group: group, mine: (me['total'] as num?)?.toInt() ?? 0),
      ),
      if (top.isNotEmpty) ...[
        const SizedBox(height: Space.m),
        if (tabs.length > 1) ...[
          _pad(
            _Tabs(
              key: const Key('rating:groups:scope'),
              labels: [for (final t in tabs) t.$2],
              on: i,
              onPick: (j) => st._set(() => st._groupsTab = j),
            ),
          ),
          const SizedBox(height: Space.m),
        ],
        _pad(
          _GroupList(
            rows: top,
            group: group,
            placeKey: placeKey,
            of: (group[placeKey == 'place' ? 'groups_all' : 'groups_inst'] as num?)?.toInt() ?? top.length,
            api: st.api,
            onUnauthorized: st.widget.onUnauthorized,
          ),
        ),
      ],
    ];
  }
}

Widget _pad(Widget child) => Padding(
  padding: const EdgeInsets.symmetric(horizontal: Space.l),
  child: child,
);

/// Кнопка-капсула в шапке («Мой опыт»), как «Спросить Kapi» у предмета.
class _Pill extends StatelessWidget {
  final IconData icon;
  final String text;
  final VoidCallback onTap;
  const _Pill({super.key, required this.icon, required this.text, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Semantics(
      button: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          tick();
          onTap();
        },
        child: Container(
          height: 36,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: p.edge),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 17, color: p.accent),
              const SizedBox(width: 6),
              Text(text, style: s.body(13.5, weight: FontWeight.w600)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Переключатель-капсула: [accent] — главный («Я | Группы», как «По срокам |
/// По предметам» в «Сдать»), иначе тёмный — вкладки внутри (как цель 3/4/5).
class _Tabs extends StatelessWidget {
  final List<String> labels;
  final int on;
  final bool accent;
  final ValueChanged<int> onPick;
  const _Tabs({super.key, required this.labels, required this.on, required this.onPick, this.accent = false});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final fill = accent ? p.accent : p.text;
    final ink = accent ? p.onAccent : p.bg;
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: accent ? p.line : p.card,
        borderRadius: BorderRadius.circular(Radii.pill),
        border: accent ? null : Border.all(color: p.line),
      ),
      child: Row(
        children: [
          for (var i = 0; i < labels.length; i++)
            Expanded(
              child: Semantics(
                button: true,
                selected: i == on,
                child: GestureDetector(
                  key: Key('${(key as ValueKey?)?.value ?? 'tabs'}:$i'),
                  behavior: HitTestBehavior.opaque,
                  onTap: () {
                    if (i == on) return;
                    tick();
                    onPick(i);
                  },
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    curve: Curves.easeOutCubic,
                    alignment: Alignment.center,
                    padding: EdgeInsets.symmetric(horizontal: Space.s, vertical: accent ? 9 : 8),
                    decoration: BoxDecoration(
                      color: i == on ? fill : fill.withValues(alpha: 0),
                      borderRadius: BorderRadius.circular(Radii.pill),
                    ),
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text(
                        labels[i],
                        maxLines: 1,
                        style: s.body(accent ? 14.5 : 14, weight: FontWeight.w600, color: i == on ? ink : p.muted),
                      ),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Сводка: подписи сверху в одну линию, слева крупное место «4 место из 14»,
/// справа второе число и строка под ним, внизу — пояснение.
class _Summary extends StatelessWidget {
  final String eyebrow, sideEyebrow, sideValue;
  final int? place;
  final String placeText, footer;
  final String? sideSub;
  final Color? sideSubColor;
  final Key? sideKey;
  const _Summary({
    super.key,
    required this.eyebrow,
    required this.place,
    required this.placeText,
    required this.sideEyebrow,
    required this.sideValue,
    this.sideSub,
    this.sideSubColor,
    this.sideKey,
    required this.footer,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Tile(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(eyebrow, maxLines: 1, overflow: TextOverflow.ellipsis, style: s.eyebrow()),
              ),
              const SizedBox(width: Space.m),
              Text(sideEyebrow, style: s.eyebrow()),
            ],
          ),
          const SizedBox(height: Space.s),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.bottomLeft,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.baseline,
                    textBaseline: TextBaseline.alphabetic,
                    children: [
                      Text(place == null ? '—' : '$place', style: s.number(54)),
                      const SizedBox(width: Space.s),
                      Text(placeText, style: s.body(15, color: p.muted)),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: Space.m),
              Column(
                key: sideKey,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(sideValue, style: s.number(30)),
                  if (sideSub != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      sideSub!,
                      style: s.body(13, weight: FontWeight.w600, color: sideSubColor ?? p.muted),
                    ),
                  ],
                ],
              ),
            ],
          ),
          if (footer.isNotEmpty) ...[const SizedBox(height: Space.m), Text(footer, style: s.body(14, color: p.muted))],
        ],
      ),
    );
  }
}

/// «Я»: «Ты в группе 4 место из 14 · опыт 412 · +38 за неделю» и «До 3 места …».
class _MeCard extends StatelessWidget {
  final Map scope, me, rules;
  final String eyebrow;

  /// Вкладка «Вуз»: справа «выше 89%» вместо «+N за неделю».
  final bool vuz;
  const _MeCard({required this.scope, required this.me, required this.rules, required this.eyebrow, required this.vuz});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    final place = (scope['place'] as num?)?.toInt();
    final week = (me['week'] as num?)?.toInt() ?? 0;
    final above = (scope['above'] as num?)?.toInt();
    final top = vuz && above != null;
    return _Summary(
      key: const Key('rating:me'),
      eyebrow: eyebrow,
      place: place,
      placeText: place == null ? 'пока без опыта' : 'место из ${_n(scope['of'])}',
      sideEyebrow: 'Опыт',
      sideValue: _n(me['total']),
      sideKey: const Key('rating:me:side'),
      sideSub: top
          ? 'выше $above%'
          : week > 0
          ? '+${_n(week)} за\u00A0неделю'
          : null,
      sideSubColor: top ? p.muted : p.ok,
      footer: ratingUpHint(scope, rules),
    );
  }
}

/// Кружок с местом: обычный — обводкой, свой — залит акцентом; скрытый и
/// пропуск — пунктиром с точкой.
class _Place extends StatelessWidget {
  final int? place;
  final bool me, dotted;
  const _Place({this.place, this.me = false, this.dotted = false});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    if (dotted || place == null) {
      return SizedBox(width: 32, height: 32, child: CustomPaint(painter: _DotRing(p.muted)));
    }
    final t = '$place';
    return Container(
      constraints: const BoxConstraints(minWidth: 32),
      height: 32,
      padding: EdgeInsets.symmetric(horizontal: t.length > 2 ? 5 : 0),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: me ? p.accent : null,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: me ? p.accent : p.muted.withValues(alpha: 0.55), width: 1.2),
      ),
      child: Text(
        t,
        style: s.number(t.length > 3 ? 12.5 : (t.length > 2 ? 14 : 15.5), color: me ? p.onAccent : p.text),
      ),
    );
  }
}

class _DotRing extends CustomPainter {
  final Color color;
  _DotRing(this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2 - 1;
    final dot = Paint()..color = color.withValues(alpha: 0.7);
    const n = 16;
    for (var i = 0; i < n; i++) {
      final a = 2 * math.pi * i / n;
      canvas.drawCircle(c + Offset(math.cos(a), math.sin(a)) * r, 1, dot);
    }
    canvas.drawCircle(c, 1.6, dot);
  }

  @override
  bool shouldRepaint(_DotRing old) => old.color != color;
}

/// Строка списка: кружок с местом, ник и подпись, справа опыт.
class _Line extends StatelessWidget {
  final Widget lead;
  final String title;
  final String? sub, xp;
  final bool me, quiet;
  final VoidCallback? onTap;
  const _Line({
    super.key,
    required this.lead,
    required this.title,
    this.sub,
    this.xp,
    this.me = false,
    this.quiet = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final body = Container(
      color: me ? p.accent.withValues(alpha: p.dark ? 0.16 : 0.09) : null,
      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: 11),
      constraints: const BoxConstraints(minHeight: 58),
      child: Row(
        children: [
          lead,
          const SizedBox(width: Space.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  maxLines: quiet ? 2 : 1,
                  overflow: TextOverflow.ellipsis,
                  style: quiet ? s.body(14, color: p.muted) : s.body(15, weight: FontWeight.w600),
                ),
                if (sub != null && sub!.isNotEmpty)
                  Text(
                    sub!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: s.body(12.5, color: p.muted),
                  ),
              ],
            ),
          ),
          if (xp != null) ...[const SizedBox(width: Space.s), Text(xp!, style: s.number(16))],
          if (onTap != null) ...[const SizedBox(width: 2), Icon(Icons.chevron_right_rounded, size: 18, color: p.muted)],
        ],
      ),
    );
    return onTap == null
        ? body
        : InkWell(
            onTap: () {
              tick();
              onTap!();
            },
            child: body,
          );
  }
}

/// Список одной вкладки «Я»: в группе — все (хвост сворачивается в «ещё N
/// человек»), в институте и вузе — верх и соседи с пропусками.
class _PeopleList extends StatelessWidget {
  final List<Map> rows;
  final Map me;
  final String scope;
  final bool collapse;
  final VoidCallback onExpand;
  const _PeopleList({
    super.key,
    required this.rows,
    required this.me,
    required this.scope,
    required this.collapse,
    required this.onExpand,
  });

  String _meSub(Map r) {
    if (r['seen'] == true) return 'это ты';
    if (scope != 'group' && me['show'] == true) return 'это ты · видят только свои';
    return 'это ты · другим не видно';
  }

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    if (rows.isEmpty) {
      return Tile(
        child: Text(
          'Здесь пока никого с опытом. Он появится за баллы БРС и сданные работы.',
          style: AppStyle.of(context).body(14, color: p.muted),
        ),
      );
    }
    final mine = rows.indexWhere((r) => r['me'] == true);
    var cut = rows.length;
    if (collapse && rows.length > 8) {
      cut = math.max(5, mine + 2);
      if (cut >= rows.length - 1) cut = rows.length;
    }
    final rest = rows.skip(cut).toList();
    final hidden = rest.where((r) => r['hidden'] == true).length;
    final shown = rows.take(cut).toList();
    final items = <Widget>[
      for (final (i, r) in shown.indexed)
        if (r['gap'] != null)
          _Line(
            lead: const _Place(dotted: true),
            title: i == shown.length - 1
                ? 'ещё ${_people((r['gap'] as num).toInt())}'
                : 'дальше ${_people((r['gap'] as num).toInt())}',
            quiet: true,
          )
        else if (r['hidden'] == true)
          _Line(
            key: Key('rating:hidden:${r['place']}'),
            lead: const _Place(dotted: true),
            title: '${r['place']}\u00A0место не показывает себя',
            quiet: true,
          )
        else
          _Line(
            key: Key(r['me'] == true ? 'rating:row:me' : 'rating:row:${r['place']}'),
            lead: _Place(place: (r['place'] as num?)?.toInt(), me: r['me'] == true),
            title: r['nick'] as String? ?? '',
            sub: r['me'] == true ? _meSub(r) : r['group'] as String?,
            xp: _n(r['xp']),
            me: r['me'] == true,
          ),
      if (rest.isNotEmpty)
        _Line(
          key: const Key('rating:more'),
          lead: const _Place(dotted: true),
          title: hidden == 0
              ? 'ещё ${_people(rest.length)}'
              : 'ещё ${_people(rest.length)}, из них $hidden ${plural(hidden, 'скрыт', 'скрыты', 'скрыты')}',
          quiet: true,
          onTap: onExpand,
        ),
    ];
    return Tile(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          for (var i = 0; i < items.length; i++) ...[if (i > 0) Divider(height: 1, color: p.line), items[i]],
        ],
      ),
    );
  }
}

/// «Группы»: место своей группы в институте и вузе, опыт, до места выше и
/// твой вклад.
class _GroupsCard extends StatelessWidget {
  final Map group;
  final int mine;
  const _GroupsCard({required this.group, required this.mine});

  @override
  Widget build(BuildContext context) {
    final inst = group['institute'] as String? ?? '';
    final name = group['name'] as String? ?? '';
    final hasInst = inst.isNotEmpty && group['place_inst'] != null;
    final xp = (group['xp'] as num?)?.toInt() ?? 0;
    final up = (hasInst ? group['up_inst'] : group['up_all']) as num?;
    final place = ((hasInst ? group['place_inst'] : group['place']) as num?)?.toInt();
    final share = xp > 0 && mine > 0 ? (mine * 100 / xp).round() : 0;
    return _Summary(
      key: const Key('rating:groups:card'),
      eyebrow: hasInst ? '$name в $inst' : '$name в вузе',
      place: place,
      placeText: 'место из ${_n(group[hasInst ? 'groups_inst' : 'groups_all'])}',
      sideEyebrow: hasInst ? 'В вузе' : 'Опыт',
      sideValue: hasInst ? '${group['place'] ?? '—'}' : _n(xp),
      sideSub: hasInst ? 'из ${_n(group['groups_all'])}' : null,
      sideKey: const Key('rating:groups:all'),
      footer: [
        if (hasInst) 'У группы ${_n(xp)} опыта',
        if (up != null && place != null && place > 1) 'до ${place - 1}\u00A0места ${_n(up)}',
        if (share > 0) 'твой вклад $share%',
      ].join(' · '),
    );
  }
}

/// Верх групп института или вуза; своя группа ниже верха — после пропуска.
class _GroupList extends StatelessWidget {
  final List<Map> rows;
  final Map group;
  final String placeKey;
  final int of;
  final Api api;
  final VoidCallback? onUnauthorized;
  const _GroupList({
    required this.rows,
    required this.group,
    required this.placeKey,
    required this.of,
    required this.api,
    this.onUnauthorized,
  });

  void _open(BuildContext context, Map row) {
    final id = row['id'] as int?;
    if (id == null) return;
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) =>
            GroupRatingScreen(api: api, id: id, name: row['name'] as String? ?? '', onUnauthorized: onUnauthorized),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    String groups(int n) => '${_n(n)}\u00A0${plural(n, 'группа', 'группы', 'групп')}';
    Widget row(Map r) => _Line(
      key: Key('rating:group:${r['id']}:$placeKey'),
      lead: _Place(place: (r[placeKey] as num?)?.toInt(), me: r['mine'] == true),
      title: r['name'] as String? ?? '',
      sub: r['mine'] == true ? 'твоя группа' : null,
      xp: _n(r['xp']),
      me: r['mine'] == true,
      onTap: () => _open(context, r),
    );
    final last = rows.isEmpty ? 0 : (rows.last[placeKey] as num?)?.toInt() ?? rows.length;
    final minePlace = (group[placeKey] as num?)?.toInt();
    final below = minePlace != null && minePlace > last && !rows.any((r) => r['mine'] == true);
    final items = <Widget>[
      for (final r in rows) row(r),
      if (below) ...[
        if (minePlace - last > 1)
          _Line(lead: const _Place(dotted: true), title: 'дальше ${groups(minePlace - last - 1)}', quiet: true),
        row({...group, 'mine': true}),
      ],
      if ((below ? minePlace : last) < of)
        _Line(lead: const _Place(dotted: true), title: 'ещё ${groups(of - (below ? minePlace : last))}', quiet: true),
    ];
    return Tile(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          for (var i = 0; i < items.length; i++) ...[if (i > 0) Divider(height: 1, color: p.line), items[i]],
        ],
      ),
    );
  }
}

/// Полосы «из чего опыт» в одну строку: название, полоса, число.
class _Bars extends StatelessWidget {
  final List<(String, num)> parts;
  const _Bars({required this.parts});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final top = parts.fold<num>(0, (m, e) => e.$2 > m ? e.$2 : m);
    return Column(
      children: [
        for (final (title, v) in parts)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 7),
            child: Row(
              children: [
                SizedBox(
                  width: 138,
                  child: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: s.body(13.5)),
                ),
                Expanded(
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(3),
                    child: SizedBox(
                      height: 6,
                      child: Stack(
                        children: [
                          Positioned.fill(child: ColoredBox(color: p.line)),
                          FractionallySizedBox(
                            widthFactor: top > 0 ? (v / top).clamp(0, 1).toDouble() : 0,
                            child: DecoratedBox(
                              decoration: BoxDecoration(color: p.accent, borderRadius: BorderRadius.circular(3)),
                              child: const SizedBox.expand(),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                SizedBox(
                  width: 56,
                  child: Text(_n(v), textAlign: TextAlign.end, style: s.number(15)),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

/// Лист «Мой опыт»: итог, из чего он, ник и кто меня видит, правила.
Future<void> _openMine(BuildContext context, _RatingScreenState st, Map me, Map rules) {
  final p = AppStyle.of(context).p;
  return showModalBottomSheet<void>(
    context: context,
    useSafeArea: true,
    backgroundColor: p.bg,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (_) => _FreshMine(
      me: me,
      rules: rules,
      onShow: (m) => st._save({'show': m['show'] != true}),
      onShowAll: st._showAll,
      onNick: st._nick,
      reload: st._me,
    ),
  );
}

class _FreshMine extends StatefulWidget {
  final Map me, rules;
  final Future<bool> Function(Map me) onShow, onShowAll, onNick;

  /// Свежий `me` с сервера после правки (null — не вышло, остаётся прежний).
  final Future<Map?> Function() reload;
  const _FreshMine({
    required this.me,
    required this.rules,
    required this.onShow,
    required this.onShowAll,
    required this.onNick,
    required this.reload,
  });

  @override
  State<_FreshMine> createState() => _FreshMineState();
}

class _FreshMineState extends State<_FreshMine> {
  late Map _me = widget.me;
  bool _rules = false;

  /// Правка: переключатель щёлкает сразу ([now]), не вышло — обратно.
  Future<void> _run(Future<bool> Function(Map) f, [Map? now]) async {
    final was = _me;
    if (now != null) setState(() => _me = {...was, ...now});
    final ok = await f(was);
    if (!mounted) return;
    if (!ok) {
      setState(() => _me = was);
      return;
    }
    final fresh = await widget.reload();
    if (fresh != null && mounted) setState(() => _me = fresh);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final show = _me['show'] == true;
    final all = _me['show_all'] == true;
    Widget toggle(String title, String sub, bool on, VoidCallback tap, Key k) => Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: s.body(15, weight: FontWeight.w600)),
                const SizedBox(height: 2),
                Text(sub, style: s.body(12.5, color: p.muted)),
              ],
            ),
          ),
          const SizedBox(width: Space.s),
          AppSwitch(key: k, value: on, onChanged: tap),
        ],
      ),
    );
    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.88),
      child: SingleChildScrollView(
        key: const Key('rating:mine'),
        padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.xl),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Мой опыт', style: s.title(26)),
                        const SizedBox(height: 2),
                        Text('видишь только ты', style: s.body(13, color: p.muted)),
                      ],
                    ),
                  ),
                  Text(_n(_me['total']), key: const Key('rating:mine:total'), style: s.number(44)),
                ],
              ),
            ),
            const SizedBox(height: Space.m),
            Tile(
              padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, Space.s),
              child: _Bars(parts: _parts(_me)),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.xs, Space.xl, Space.xs, Space.s),
              child: Text('Кто меня видит', style: s.eyebrow()),
            ),
            Tile(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  InkWell(
                    key: const Key('rating:nick'),
                    onTap: () {
                      tick();
                      _run(widget.onNick);
                    },
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, Space.m),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('Ник', style: s.body(15, weight: FontWeight.w600)),
                                const SizedBox(height: 2),
                                Text(
                                  _me['nick'] as String? ?? '',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: s.body(13, color: p.muted),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: Space.s),
                          Text(
                            'Изменить',
                            style: s.body(14, weight: FontWeight.w600, color: p.accent),
                          ),
                        ],
                      ),
                    ),
                  ),
                  Divider(height: 1, color: p.line),
                  toggle(
                    'Показывать меня группе',
                    show ? 'группа видит твой ник и опыт' : 'сейчас группа тебя не видит',
                    show,
                    () => _run(widget.onShow, {'show': !show}),
                    const Key('rating:show'),
                  ),
                  Divider(height: 1, color: p.line),
                  toggle(
                    'Показывать меня всем',
                    all ? 'все видят тебя как «${_me['public_nick'] ?? 'Капибара №…'}»' : 'по отдельному согласию',
                    all,
                    () => _run(widget.onShowAll, all ? {'show_all': false} : null),
                    const Key('rating:show_all'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: Space.m),
            Tile(
              key: const Key('rating:rules'),
              padding: EdgeInsets.zero,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  InkWell(
                    onTap: () {
                      tick();
                      setState(() => _rules = !_rules);
                    },
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text('Как считается опыт', style: s.body(15, weight: FontWeight.w600)),
                          ),
                          AnimatedRotation(
                            turns: _rules ? 0.25 : 0,
                            duration: const Duration(milliseconds: 200),
                            child: Icon(Icons.chevron_right_rounded, color: p.muted),
                          ),
                        ],
                      ),
                    ),
                  ),
                  AnimatedSize(
                    duration: const Duration(milliseconds: 220),
                    curve: Curves.easeOutCubic,
                    alignment: Alignment.topCenter,
                    child: _rules
                        ? Padding(
                            padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.l),
                            child: Text(
                              _rulesText(widget.rules),
                              key: const Key('rating:rules:text'),
                              style: s.body(14, color: p.muted),
                            ),
                          )
                        : const SizedBox(width: double.infinity),
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

/// Экран группы в новом виде: места, как росла, из чего опыт, люди.
class _FreshGroup extends StatelessWidget {
  final Map<String, dynamic> g;
  final String name;
  const _FreshGroup({required this.g, required this.name});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final people = [for (final r in (g['people_list'] as List? ?? const [])) r as Map];
    final hidden = (g['hidden'] as num?)?.toInt() ?? 0;
    final member = g['member'] == true;
    final inst = g['institute'] as String? ?? '';
    final history = (g['history'] as List?) ?? const [];
    final places = [
      if (inst.isNotEmpty && g['place_inst'] != null) '${g['place_inst']}\u00A0место в $inst',
      if (g['place'] != null) '${g['place']}\u00A0в\u00A0вузе',
    ].join(' · ');
    final hasXp = ((g['xp'] as num?) ?? 0) > 0;
    final items = <Widget>[
      for (final r in people)
        _Line(
          lead: Icon(
            r['me'] == true ? Icons.person_rounded : Icons.person_outline_rounded,
            size: 22,
            color: r['me'] == true ? p.accent : p.muted,
          ),
          title: r['nick'] as String? ?? '',
          sub: r['me'] == true ? 'это ты' : null,
          xp: _n(r['xp']),
          me: r['me'] == true,
        ),
      if (people.isEmpty || hidden > 0)
        _Line(
          key: const Key('rating:group:hidden'),
          lead: const _Place(dotted: true),
          title: people.isEmpty
              ? (member ? 'Пока никто не показывает себя группе' : 'Пока никто не показывает себя всем')
              : 'ещё ${_people(hidden)} не показывают себя',
          quiet: true,
        ),
    ];
    return ListView(
      key: const ValueKey('rating:group:fresh'),
      padding: const EdgeInsets.only(bottom: Space.xxl),
      children: [
        const BackRow(),
        ScreenTitle(title: g['name'] as String? ?? name, sub: places.isEmpty ? null : places),
        if (g['place'] == null) _pad(_GroupCard(group: g)),
        if (hasXp && history.length > 1) ...[
          const Section('Как росла группа'),
          _pad(_Growth(group: g, history: history)),
        ],
        if (hasXp) ...[
          const Section('Из чего опыт группы'),
          _pad(
            Tile(
              key: const Key('rating:parts'),
              padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, Space.s),
              child: _Bars(parts: _parts(g['parts'])),
            ),
          ),
        ],
        const Section('Люди'),
        _pad(
          Tile(
            key: const Key('rating:group:people'),
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                for (var i = 0; i < items.length; i++) ...[if (i > 0) Divider(height: 1, color: p.line), items[i]],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

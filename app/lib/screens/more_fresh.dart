// «Ещё» нового дизайна (макет Е3, Никита 11.11) — только при «Новом» в
// «Оформлении» ([AppStyle.fresh]); прежний экран не меняется.
// Короткий: сверху имя, группа и курс, ачивки и рейтинг одной карточкой на
// виду; ниже три раздела строками — «Моя учёба», «Настройки», «Ещё»;
// «Сообщество» и «О Капибаре» открывают листы с пунктами. Баллов БРС здесь
// больше нет — они на «Учёбе» (карточка автоматов).
part of 'more.dart';

/// «3 курс» по году поступления в конце названия группы (…-24 — поступили в
/// 2024-м); учебный год — с сентября. Не похоже на год или вышло не 1–6 — null.
String? courseOfGroup(String name, DateTime at) {
  final m = RegExp(r'-(\d{2})$').firstMatch(name.trim());
  if (m == null) return null;
  final start = at.month >= 9 ? at.year : at.year - 1;
  final n = start - (2000 + int.parse(m[1]!)) + 1;
  return n >= 1 && n <= 6 ? '$n курс' : null;
}

/// Что включено в «Уведомлениях» — одной строкой под пунктом (ответ /notify).
String notifySummary(Map data) {
  if (data['subscribed'] != true) return 'выключены';
  final prefs = (data['prefs'] as Map?) ?? const {};
  const names = {
    'morning': 'утро',
    'lessons': 'перед парой',
    'deadlines': 'дедлайны',
    'weekly': 'обзор недели',
    'grades': 'новые баллы',
    'new_tasks': 'новые задания',
    'evening': 'вечер',
  };
  final known = [
    for (final k in names.keys)
      if (prefs.containsKey(k)) k,
  ];
  final on = [
    for (final k in known)
      if (prefs[k] == true) names[k]!,
  ];
  if (on.isEmpty) return 'ничего не включено';
  if (on.length == known.length) return 'включены все';
  if (on.length <= 2) return on.join(', ');
  return '${on.take(2).join(', ')} и ещё ${on.length - 2}';
}

/// «Тетрадь, книжный шрифт» — что сейчас в «Оформлении».
String lookSummary(AppStyle s) {
  final theme = !s.p.dark ? 'Тетрадь' : (s.look.freshDepth ? 'Глубина' : 'Ночная тетрадь');
  return '$theme, ${s.font == FontChoice.book ? 'книжный' : 'строгий'} шрифт';
}

class _FreshMore extends StatefulWidget {
  final MoreScreen screen;

  /// Ответ /me: пришёл новый (потянул экран вниз) — остальное тоже заново.
  final Map<String, dynamic> me;
  const _FreshMore({required this.screen, required this.me});

  @override
  State<_FreshMore> createState() => _FreshMoreState();
}

class _FreshMoreState extends State<_FreshMore> {
  Map<String, String> _links = const {};
  bool _plus = false, _donate = false;
  Map<String, dynamic>? _notify;
  Object? _rating;
  List<String> _optPending = const [];
  Map<String, bool> _optAnswers = const {};

  Api get _api => widget.screen.api;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(_FreshMore old) {
    super.didUpdateWidget(old);
    if (!identical(old.me, widget.me)) _load();
  }

  // каждая часть сама по себе: что-то не ответило — остальной экран работает
  void _load() {
    appLinks(_api).then((l) => _set(() => _links = l), onError: (_) {});
    // «Капибара+» и «Поддержать» — только если сервер их показывает (на iPhone — нет)
    plusShown(_api).then((v) => _set(() => _plus = v), onError: (_) {});
    donateShown(_api).then((v) => _set(() => _donate = v), onError: (_) {});
    _loadRating();
    _loadNotify();
    _loadOptional();
  }

  void _set(VoidCallback f) {
    if (mounted) setState(f);
  }

  Future<void> _loadRating() => _api.get('/rating').then((v) => _set(() => _rating = v), onError: (_) {});

  Future<void> _loadNotify() => _api
      .get('/notify')
      .then((v) => _set(() => _notify = v is Map ? Map<String, dynamic>.from(v) : null), onError: (_) {});

  Future<void> _loadOptional() => _api
      .get('/optional')
      .then(
        (r) => _set(() {
          _optPending = [for (final x in (r['pending'] as List? ?? const [])) x as String];
          _optAnswers = {
            for (final e in ((r['answers'] as Map?) ?? const {}).entries) e.key as String: e.value == true,
          };
        }),
        onError: (_) {},
      );

  Future<void> _push(Widget screen) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));

  List<String> get _optSubjects => [..._optPending, ..._optAnswers.keys.where((k) => !_optPending.contains(k))];

  /// «Военная кафедра: не хожу»; ещё не ответил — «ходишь?».
  String _optLine(List<String> subjects) {
    final first = subjects.first;
    final state = _optPending.contains(first) ? 'ходишь?' : (_optAnswers[first]! ? 'хожу' : 'не хожу');
    return '$first: $state${subjects.length > 1 ? ' · ещё ${subjects.length - 1}' : ''}';
  }

  /// Лист нового вида: заголовок и карточки-списки на цвете экрана. Пункт
  /// листа сначала закрывает лист, потом делает своё (`go`).
  Future<void> _sheet(String title, List<Widget> Function(VoidCallback Function(VoidCallback) go) items) {
    final s = AppStyle.of(context);
    return showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: s.p.bg,
      builder: (ctx) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.l),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(title, style: s.title(22)),
              const SizedBox(height: Space.m),
              ...items(
                (f) => () {
                  Navigator.pop(ctx);
                  f();
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _community() {
    final news = MoreScreen._links(_links);
    final channel = (_links['channel'] ?? '').isNotEmpty, contact = (_links['contact'] ?? '').isNotEmpty;
    _sheet(
      'Сообщество',
      (go) => [
        _FreshList(
          inset: false,
          children: [
            _FreshRow(
              key: const Key('more:invite'),
              icon: Icons.person_add_alt_outlined,
              title: 'Позвать',
              sub: 'готовое сообщение другу или в чат группы',
              onTap: go(() => showInviteSheet(context, _api)),
            ),
            if (news.isNotEmpty)
              _FreshRow(
                key: const Key('more:links'),
                icon: Icons.chat_bubble_outline_rounded,
                title: 'Новости и связь',
                sub: channel && contact
                    ? 'канал Капибары и «Написать нам»'
                    : (channel ? 'канал Капибары' : '«Написать нам»'),
                onTap: go(() => showLinksSheet(context, news)),
              ),
          ],
        ),
      ],
    );
  }

  void _about() {
    final screen = widget.screen;
    final p = AppStyle.of(context).p;
    _sheet(
      'О Капибаре',
      (go) => [
        _FreshList(
          inset: false,
          children: [
            if (screen.onTour != null)
              _FreshRow(
                key: const Key('more:tour'),
                icon: Icons.lightbulb_outline_rounded,
                title: 'Как пользоваться',
                sub: 'короткий тур: что где и какие есть жесты',
                onTap: go(screen.onTour!),
              ),
            _FreshRow(
              key: const Key('more:places'),
              icon: Icons.devices_other_outlined,
              title: 'Капибара в других местах',
              sub: 'Telegram-бот, браузер и компьютер',
              onTap: go(() async {
                final l = await appLinks(_api);
                if (mounted) showLinksSheet(context, MoreScreen.places(l), title: 'Капибара в других местах');
              }),
            ),
          ],
        ),
        // на iPhone сервер их не показывает — и в листе их нет (App Store 3.1.1)
        if (_plus || _donate) ...[
          const SizedBox(height: Space.m),
          _FreshList(
            inset: false,
            children: [
              if (_plus)
                _FreshRow(
                  key: const Key('more:plus'),
                  icon: Icons.star_outline_rounded,
                  title: 'Капибара+',
                  onTap: go(() => _push(PlusScreen(api: _api, onUnauthorized: screen.onUnauthorized))),
                ),
              if (_donate) ...[
                _FreshRow(
                  key: const Key('more:donate'),
                  icon: Icons.favorite_border_rounded,
                  title: 'Поддержать проект',
                  sub: 'разово, сумма на выбор',
                  onTap: go(() => showDonateSheet(context, _api)),
                ),
                _FreshRow(
                  key: const Key('more:roadmap'),
                  icon: Icons.push_pin_outlined,
                  title: 'Роадмап',
                  sub: 'что дальше, для тех, кто поддержал',
                  onTap: go(() => showRoadmapSheet(context, _api)),
                ),
              ],
            ],
          ),
        ],
        const SizedBox(height: Space.m),
        // магазины (App Store 5.2.1): не выдавать себя за приложение института
        Text(unofficialNote, style: AppStyle.of(context).body(13, color: p.muted)),
      ],
    );
  }

  Future<void> _optional() async {
    await _sheet(
      'Предметы по выбору',
      (_) => [_Optional(api: _api, sheet: true, initial: (pending: _optPending, answers: _optAnswers))],
    );
    _loadOptional();
  }

  Future<void> _logout() async {
    final ok = await confirmSheet(
      context,
      title: 'Выйти?',
      text: 'На этом устройстве. Войти снова — через бота.',
      action: 'Выйти',
      cancel: 'Остаться',
      danger: true,
    );
    if (ok) widget.screen.onLogout();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final screen = widget.screen;
    final me = widget.me;
    final first = '${me['first_name'] ?? ''}'.trim();
    final user = '${me['username'] ?? ''}'.trim();
    final name = first.isNotEmpty ? first : (user.isNotEmpty ? '@$user' : 'Ещё');
    final g = me['group'];
    final group = g is Map ? '${g['name'] ?? ''}' : '';
    final course = courseOfGroup(group, now());
    final subjects = _optSubjects;
    return ListView(
      key: const ValueKey('more:fresh'),
      padding: const EdgeInsets.only(bottom: 120),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.l, Space.l, Space.m, Space.m),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    FitWords(name, style: s.title(30), maxLines: 2),
                    const SizedBox(height: 6),
                    Text(
                      group.isEmpty ? 'группа не выбрана' : [group, ?course].join(' · '),
                      style: s.body(13, color: p.muted),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: Space.s),
              CapyImage(pose: CapyPose.joy, size: 62, color: p.text),
            ],
          ),
        ),
        _FreshList(
          children: [
            const AchievementsLine(),
            _FreshRating(
              data: _rating,
              group: group,
              onTap: () async {
                await _push(RatingScreen(api: _api, onUnauthorized: screen.onUnauthorized));
                _loadRating();
              },
            ),
          ],
        ),
        const Section('Моя учёба'),
        _FreshList(
          children: [
            _FreshRow(
              key: const Key('more:group'),
              icon: Icons.group_outlined,
              title: 'Сменить мою группу',
              sub: group.isEmpty ? 'группа не выбрана' : 'сейчас $group',
              onTap: screen.onGroup,
            ),
            if (g is Map && g['own'] != true) _AdminRequest(api: _api, fresh: true),
            if (subjects.isNotEmpty)
              _FreshRow(
                key: const Key('more:optional'),
                icon: Icons.school_outlined,
                title: 'Предметы по выбору',
                sub: _optLine(subjects),
                subColor: _optPending.isNotEmpty ? p.accent : null,
                onTap: _optional,
              ),
            _FreshRow(
              key: const Key('more:calendar'),
              icon: Icons.event_available_outlined,
              title: 'Добавить в календарь телефона',
              onTap: () => screen._calendarSheet(context),
            ),
            // экспериментальный вход в Пульс (31.10) — только старосте и только в приложении
            if (me['lab'] == true && sdoWebLoginAvailable)
              _FreshRow(
                key: const Key('more:pulse'),
                icon: Icons.science_outlined,
                title: 'Пульс · эксперимент',
                sub: 'вход в Пульс МИРЭА и разведка, что он отдаёт',
                onTap: () => _push(PulseLabScreen(api: _api)),
              ),
          ],
        ),
        const Section('Настройки'),
        _FreshList(
          children: [
            _FreshRow(
              key: const Key('more:notify'),
              icon: Icons.notifications_none_rounded,
              title: 'Уведомления',
              sub: _notify == null ? null : notifySummary(_notify!),
              onTap: () async {
                await _push(NotifyScreen(api: _api, onUnauthorized: screen.onUnauthorized));
                _loadNotify();
              },
            ),
            _FreshRow(
              key: const Key('more:theme'),
              icon: Icons.palette_outlined,
              title: 'Оформление',
              sub: lookSummary(s),
              onTap: () => screen._themeSheet(context),
            ),
            _FreshRow(
              key: const Key('more:security'),
              icon: Icons.shield_outlined,
              title: 'Безопасность и мои данные',
              onTap: () =>
                  _push(SecurityScreen(api: _api, onLogout: screen.onLogout, onUnauthorized: screen.onUnauthorized)),
            ),
          ],
        ),
        const Section('Ещё'),
        _FreshList(
          children: [
            _FreshRow(
              key: const Key('more:community'),
              icon: Icons.person_add_alt_outlined,
              title: 'Сообщество',
              sub: MoreScreen._links(_links).isEmpty ? 'позвать друга или группу' : 'позвать друга, новости и связь',
              onTap: _community,
            ),
            _FreshRow(
              key: const Key('more:about'),
              icon: Icons.lightbulb_outline_rounded,
              title: 'О Капибаре',
              sub: _plus || _donate
                  ? 'как пользоваться, другие устройства, поддержка'
                  : 'как пользоваться и другие устройства',
              onTap: _about,
            ),
          ],
        ),
        const SizedBox(height: Space.m),
        _FreshList(
          children: [
            _FreshRow(
              key: const Key('more:logout'),
              icon: Icons.logout_rounded,
              title: 'Выйти',
              danger: true,
              onTap: _logout,
            ),
          ],
        ),
      ],
    );
  }
}

/// Карточка-список: строки через тонкую линию.
class _FreshList extends StatelessWidget {
  final List<Widget> children;

  /// Отступы по бокам экрана; в листе их уже дал сам лист.
  final bool inset;
  const _FreshList({required this.children, this.inset = true});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: inset ? Space.l : 0),
      child: Tile(
        padding: EdgeInsets.zero,
        radius: Radii.card,
        child: Column(
          children: [
            for (final (i, c) in children.indexed) ...[if (i > 0) Divider(height: 1, color: p.line), c],
          ],
        ),
      ),
    );
  }
}

/// Строка списка: значок в мягком квадрате, название, пояснение и стрелка.
class _FreshRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? sub;
  final Color? subColor;

  /// null — строка не нажимается (запрос уже отправлен).
  final VoidCallback? onTap;

  /// «Выйти» — красным и без стрелки.
  final bool danger;
  const _FreshRow({
    super.key,
    required this.icon,
    required this.title,
    this.sub,
    this.subColor,
    required this.onTap,
    this.danger = false,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final tone = danger ? p.danger : p.accent;
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
          padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: tone.withValues(alpha: danger ? 0.12 : 0.14),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, size: 20, color: tone),
              ),
              const SizedBox(width: Space.m),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: s.body(15, weight: FontWeight.w700, color: danger ? p.danger : null),
                    ),
                    if (sub != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        sub!,
                        style: s.body(
                          13,
                          weight: subColor == null ? FontWeight.w400 : FontWeight.w600,
                          color: subColor ?? p.muted,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (onTap != null && !danger) ...[
                const SizedBox(width: Space.xs),
                Icon(Icons.chevron_right_rounded, color: p.muted),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// «Рейтинг»: место группы кружком и фразой (в институте, иначе в вузе).
class _FreshRating extends StatelessWidget {
  final Object? data;

  /// Название группы из профиля — пока рейтинг не ответил.
  final String group;
  final VoidCallback onTap;
  const _FreshRating({required this.data, required this.group, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final d = data;
    final g = d is Map ? d['group'] : null;
    final inst = g is Map ? g['place_inst'] : null;
    final place = inst ?? (g is Map ? g['place'] : null);
    final name = g is Map && '${g['name'] ?? ''}'.isNotEmpty ? '${g['name']}' : group;
    final line = place == null
        ? 'места групп в институте и вузе'
        : '$name на $place месте ${inst != null ? 'в институте' : 'в вузе'}';
    return InkWell(
      key: const Key('more:rating'),
      onTap: () {
        tick();
        onTap();
      },
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
        child: Row(
          children: [
            Container(
              width: 52,
              height: 52,
              padding: const EdgeInsets.all(6),
              alignment: Alignment.center,
              decoration: BoxDecoration(color: p.accent.withValues(alpha: 0.14), shape: BoxShape.circle),
              child: place == null
                  ? Icon(Icons.leaderboard_outlined, color: p.accent)
                  : FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text('$place', style: s.number(24, color: p.accent)),
                    ),
            ),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Рейтинг', style: s.body(17, weight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text(line, style: s.body(13, color: p.muted)),
                ],
              ),
            ),
            const SizedBox(width: Space.s),
            Icon(Icons.chevron_right_rounded, color: p.muted),
          ],
        ),
      ),
    );
  }
}

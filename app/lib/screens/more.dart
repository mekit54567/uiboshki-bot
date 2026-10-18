// «Ещё» (дизайн 23Б, владелец 09.10): сверху кто я и группа, под ними баллы
// БРС одной цифрой и одной фразой (нажал — «Учёба»), ниже настройки плитками
// по две; действия с пояснениями — строками под плитками.
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../achievements/ui.dart';
import '../api/api.dart';
import '../api/links.dart';
import '../api/models.dart';
import '../plus/donate.dart';
import '../plus/plus_screen.dart';
import '../theme/app_theme.dart';
import '../theme/look.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';
import '../widgets/goal_card.dart';
import 'look_screen.dart';
import 'notify.dart';
import 'rating.dart';
import 'sdo_connect.dart';
import 'security.dart';
import 'study.dart';

class MoreScreen extends StatelessWidget {
  final Api api;
  final ValueChanged<FontChoice> onFont;

  /// Тема: как в телефоне, светлая или тёмная (main.dart запоминает).
  final ValueChanged<ThemeChoice>? onTheme;

  /// «Оформление» (5.79) — темы, бумага, вид пар и прочее (main.dart запоминает).
  final ValueChanged<Look>? onLook;
  final VoidCallback onLogout;
  final VoidCallback? onUnauthorized;

  /// «Группа» → выбрать другую (оболочка перестроит экраны).
  final VoidCallback? onGroup;

  /// Карточка баллов → вкладка «Учёба» (её переключает оболочка).
  final VoidCallback? onStudy;

  /// Подключил СДО отсюда — оболочка перезагрузит «Учёбу» (иначе там висит
  /// «Подключить СДО», пока не потянешь экран).
  final VoidCallback? onSdo;

  /// «Как пользоваться» — тур по приложению ещё раз (оболочка).
  final VoidCallback? onTour;
  const MoreScreen({
    super.key,
    required this.api,
    required this.onFont,
    this.onTheme,
    this.onLook,
    required this.onLogout,
    this.onUnauthorized,
    this.onGroup,
    this.onStudy,
    this.onSdo,
    this.onTour,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Loader<Map<String, dynamic>>(
      load: () async => Map<String, dynamic>.from(await api.get('/me')),
      onUnauthorized: onUnauthorized,
      builder: (context, me, _) => ListView(
        padding: const EdgeInsets.only(bottom: 120),
        children: [
          _Profile(me: me),
          // баллы грузятся сами по себе: СДО не отвечает — остальной экран работает
          _PointsCard(api: api, me: me, onOpen: onStudy, onSdo: onSdo),
          const SizedBox(height: Space.m),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: Space.l),
            child: AchievementsRow(),
          ),
          const SizedBox(height: Space.s),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: RatingRow(api: api, onUnauthorized: onUnauthorized),
          ),
          const SizedBox(height: Space.m),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: FutureBuilder<List<Object>>(
              // «Капибара+» — только если сервер её показывает (на iPhone — нет)
              future: Future.wait<Object>([appLinks(api).catchError((_) => <String, String>{}), plusShown(api)]),
              builder: (context, snap) {
                final links = _links(snap.data?[0] as Map<String, String>? ?? const {});
                final plus = snap.data?[1] == true;
                return _TileGrid(
                  items: [
                    _TileItem(
                      key: const Key('more:notify'),
                      icon: Icons.notifications_none_rounded,
                      title: 'Уведомления',
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => NotifyScreen(api: api, onUnauthorized: onUnauthorized),
                        ),
                      ),
                    ),
                    _TileItem(
                      key: const Key('more:theme'),
                      icon: Icons.palette_outlined,
                      title: s.design2 ? 'Оформление' : 'Тема и шрифт',
                      onTap: () => _themeSheet(context),
                    ),
                    _TileItem(
                      key: const Key('more:security'),
                      icon: Icons.shield_outlined,
                      title: 'Безопасность',
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => SecurityScreen(api: api, onLogout: onLogout, onUnauthorized: onUnauthorized),
                        ),
                      ),
                    ),
                    _TileItem(
                      key: const Key('more:calendar'),
                      icon: Icons.event_available_outlined,
                      title: 'Календарь',
                      onTap: () => _calendarSheet(context),
                    ),
                    _TileItem(
                      key: const Key('more:group'),
                      icon: Icons.swap_horiz_rounded,
                      title: 'Группа',
                      onTap: onGroup,
                    ),
                    // «Новости и связь» — если сервер знает ссылки (/api/meta → links)
                    if (links.isNotEmpty)
                      _TileItem(
                        key: const Key('more:links'),
                        icon: Icons.forum_outlined,
                        title: 'Новости и связь',
                        onTap: () => showLinksSheet(context, links),
                      ),
                    if (plus)
                      _TileItem(
                        key: const Key('more:plus'),
                        icon: Icons.workspace_premium_outlined,
                        title: 'Капибара+',
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => PlusScreen(api: api, onUnauthorized: onUnauthorized),
                          ),
                        ),
                      ),
                  ],
                );
              },
            ),
          ),
          _Optional(api: api),
          const SizedBox(height: Space.m),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: Tile(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  if (onTour != null) ...[
                    _MenuRow(
                      icon: Icons.lightbulb_outline_rounded,
                      title: 'Как пользоваться',
                      sub: 'короткий тур: что где и какие есть жесты',
                      onTap: onTour,
                    ),
                    Divider(height: 1, color: p.line),
                  ],
                  _MenuRow(
                    icon: Icons.devices_other_outlined,
                    title: 'Капибара в других местах',
                    sub: 'Telegram-бот, браузер и компьютер',
                    onTap: () async {
                      final l = await appLinks(api);
                      if (context.mounted) showLinksSheet(context, places(l), title: 'Капибара в других местах');
                    },
                  ),
                  Divider(height: 1, color: p.line),
                  _MenuRow(
                    icon: Icons.group_add_outlined,
                    title: 'Позвать',
                    sub: 'готовое сообщение со ссылкой — другу или в чат группы',
                    onTap: () => showInviteSheet(context, api),
                  ),
                  // «Поддержать проект» — строкой, не плиткой (Никита 18.10: без перегруза); на iPhone — нет
                  FutureBuilder<bool>(
                    future: donateShown(api),
                    builder: (context, snap) => snap.data != true
                        ? const SizedBox.shrink()
                        : Column(
                            children: [
                              Divider(height: 1, color: p.line),
                              KeyedSubtree(
                                key: const Key('more:donate'),
                                child: _MenuRow(
                                  icon: Icons.favorite_border_rounded,
                                  title: 'Поддержать проект',
                                  sub: 'разово, сумма на выбор',
                                  onTap: () => showDonateSheet(context, api),
                                ),
                              ),
                            ],
                          ),
                  ),
                  if (me['group'] != null && me['group']['own'] != true) ...[
                    Divider(height: 1, color: p.line),
                    _AdminRequest(api: api),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: Space.s),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: Tile(
              onTap: () async {
                final ok = await confirmSheet(
                  context,
                  title: 'Выйти?',
                  text: 'На этом устройстве. Войти снова — через бота.',
                  action: 'Выйти',
                  cancel: 'Остаться',
                  danger: true,
                );
                if (ok) onLogout();
              },
              child: Row(
                children: [
                  Icon(Icons.logout_rounded, color: p.danger),
                  const SizedBox(width: Space.m),
                  Text(
                    'Выйти',
                    style: s.body(15, weight: FontWeight.w600, color: p.danger),
                  ),
                ],
              ),
            ),
          ),
          // магазины (App Store 5.2.1): не выдавать себя за приложение института
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.xl, Space.l, Space.xl, 0),
            child: Text(
              unofficialNote,
              textAlign: TextAlign.center,
              style: s.body(12, color: p.muted),
            ),
          ),
        ],
      ),
    );
  }

  /// Ссылки «Новости и связь»: канал бота и «Написать нам» — что задал сервер.
  static List<(IconData, String, String, String, String)> _links(Map<String, String> l) => [
    if ((l['channel'] ?? '').isNotEmpty)
      (
        Icons.campaign_outlined,
        'Канал бота',
        'Новости, как всё устроено и что нового',
        'Открыть канал',
        _url(l['channel']!),
      ),
    if ((l['contact'] ?? '').isNotEmpty)
      (
        Icons.chat_bubble_outline_rounded,
        'Написать нам',
        'Идея, ошибка или вопрос — ответим',
        'Написать',
        _url(l['contact']!),
      ),
  ];

  /// «Капибара в других местах» (5.97): бот, браузер и компьютер, канал —
  /// без слов о цене (правило Apple 3.1.1). С iPhone бот открывается со
  /// start=ios — приветствие без строк об оплате (handlers/start.py).
  @visibleForTesting
  static List<(IconData, String, String, String, String)> places(
    Map<String, String> l, {
    bool? ios,
    bool web = kIsWeb,
  }) {
    final bot = l['bot'] ?? '';
    final fromIos = ios ?? (!web && defaultTargetPlatform == TargetPlatform.iOS);
    return [
      if (bot.isNotEmpty)
        (
          Icons.send_outlined,
          'Telegram-бот',
          'Расписание в чате, напоминания до пары и приложение прямо в Telegram',
          'Открыть',
          fromIos ? '$bot?start=ios' : bot,
        ),
      if (!web)
        (
          Icons.laptop_mac_outlined,
          'В браузере и на компьютере',
          'uiboshki.ru/app — тот же вход, можно поставить на экран «Домой»',
          'Открыть',
          '$_origin/app',
        ),
      if ((l['news'] ?? '').isNotEmpty)
        (Icons.campaign_outlined, 'Канал Капибары', 'Новости и обновления', 'Открыть', _url(l['news']!)),
    ];
  }

  /// «@имя» → https://t.me/имя
  static String _url(String v) => v.startsWith('@') ? 'https://t.me/${v.substring(1)}' : v;

  /// «Тема и шрифт» — лист: шрифт и тема (как в телефоне, светлая, тёмная).
  /// С новым дизайном (5.79) — экран «Оформление»; сервер выключил — старый лист.
  Future<void> _themeSheet(BuildContext context) => AppStyle.of(context).design2
      ? Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => LookScreen(onFont: onFont, onTheme: onTheme, onLook: onLook),
          ),
        )
      : appSheet<void>(context, (_) => _ThemeSheet(onFont: onFont, onTheme: onTheme));

  /// Адрес сервера для ссылок наружу (на стенде base пустой — тот же сайт).
  static String get _origin => Api.base.isEmpty ? Uri.base.origin : Api.base;

  /// Открыть ссылку в системе (календарь по webcal://); тесты подменяют.
  @visibleForTesting
  static Future<bool> Function(Uri) openUrl = (u) => launchUrl(u, mode: LaunchMode.externalApplication);

  /// Подписка на расписание и дедлайны в календаре телефона (как /calendar в
  /// боте): лист с двумя кнопками. «Добавить в календарь» сразу открывает
  /// окно подписки (webcal:// — на iPhone «Подписаться на календарь»), не
  /// вышло — ссылка копируется; «Скопировать ссылку» — для других телефонов.
  Future<void> _calendarSheet(BuildContext context) => appSheet<void>(
    context,
    (ctx) => SheetFrame(
      title: 'Календарь',
      text: 'Пары и сроки появятся в календаре телефона и будут обновляться сами.',
      action: 'Добавить в календарь',
      cancel: 'Скопировать ссылку',
      onAction: () async {
        Navigator.pop(ctx);
        await _subscribe(context);
      },
      onCancel: () async {
        Navigator.pop(ctx);
        await _subscribe(context, copy: true);
      },
    ),
  );

  Future<void> _subscribe(BuildContext context, {bool copy = false}) async {
    final toast = Overlay.of(context, rootOverlay: true);
    String path;
    try {
      path = '${(await api.get('/calendar/link'))['ics_path'] ?? ''}';
      if (path.isEmpty) throw ApiError('нет ссылки');
    } catch (e) {
      toastOn(
        toast,
        e is ApiError && e.message == 'нет ссылки' ? 'Не получилось взять ссылку — попробуй позже' : errorText(e),
        kind: ToastKind.error,
      );
      return;
    }
    final https = '$_origin$path';
    if (!copy) {
      final host = https.replaceFirst(RegExp(r'^https?://'), '');
      var opened = false;
      try {
        opened = await openUrl(Uri.parse('webcal://$host'));
      } catch (_) {}
      if (opened) return;
    }
    try {
      await Clipboard.setData(ClipboardData(text: https));
    } catch (_) {
      toastOn(toast, 'Не удалось скопировать — попробуй ещё раз.', kind: ToastKind.error);
      return;
    }
    toastOn(
      toast,
      copy
          ? 'Ссылка скопирована — в календаре: «Добавить подписку» и вставь её'
          : 'Календарь не открылся — ссылка скопирована, добавь подписку в календаре',
      kind: ToastKind.done,
    );
  }
}

/// Шапка: кружок с первой буквой имени, имя и группа — без подписи над ними
/// (владелец: «профиль и настройки» курсивом смотрелись странно).
class _Profile extends StatelessWidget {
  final Map<String, dynamic> me;
  const _Profile({required this.me});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final first = '${me['first_name'] ?? ''}'.trim();
    final user = '${me['username'] ?? ''}'.trim();
    final name = first.isNotEmpty ? first : (user.isNotEmpty ? '@$user' : 'Ещё');
    final letter = first.isNotEmpty ? first.characters.first.toUpperCase() : '';
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.xl, Space.l, Space.xl, Space.l),
      child: Row(
        children: [
          ExcludeSemantics(
            child: Container(
              width: 52,
              height: 52,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: p.accent, shape: BoxShape.circle),
              child: letter.isEmpty
                  ? Icon(Icons.person_rounded, color: p.onAccent)
                  : Text(
                      letter,
                      textScaler: TextScaler.noScaling,
                      style: s.body(22, weight: FontWeight.w800, color: p.onAccent).copyWith(height: 1),
                    ),
            ),
          ),
          const SizedBox(width: Space.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: s.name(22)),
                const SizedBox(height: 2),
                Text('${me['group']?['name'] ?? 'группа не выбрана'}', style: s.body(14, color: p.muted)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Баллы БРС одной фразой: средний балл по журналам, на сколько предметов уже
/// хватает первой отметки («3» у экзамена, зачёт у зачёта; порог — свой у
/// курса) и где баллов меньше всего.
class PointsSummary {
  /// Предметов в журнале; из них с отметками — rated, первая уже есть — reached.
  final int total, rated, reached, average;

  /// Где баллов меньше всего (null — предмет один, сравнивать не с чем).
  final Course? lowest;

  /// Какие первые отметки встречаются: «3», зачёт.
  final List<String> firsts;

  /// Баллов нет нигде (начало семестра, журналы пустые).
  final bool blank;

  const PointsSummary._(this.total, this.rated, this.reached, this.average, this.lowest, this.firsts, this.blank);

  factory PointsSummary.of(List<Course> courses) {
    if (courses.isEmpty) return const PointsSummary._(0, 0, 0, 0, null, [], true);
    var rated = 0, reached = 0;
    final firsts = <String>[];
    for (final c in courses) {
      if (c.marks.isEmpty) continue;
      final first = c.marks.reduce((a, b) => b.at < a.at ? b : a);
      rated++;
      if (c.score >= first.at) reached++;
      if (!firsts.contains(first.label)) firsts.add(first.label);
    }
    firsts.sort((a, b) => (a == 'зачёт' ? 1 : 0) - (b == 'зачёт' ? 1 : 0)); // «3» раньше зачёта
    final sum = courses.fold<num>(0, (acc, c) => acc + c.score);
    final lowest = courses.reduce((a, b) => b.score < a.score ? b : a);
    return PointsSummary._(
      courses.length,
      rated,
      reached,
      (sum / courses.length).round(),
      courses.length > 1 ? lowest : null,
      firsts,
      courses.every((c) => c.score <= 0),
    );
  }

  /// Фраза кусками: (текст, жирный).
  List<(String, bool)> get parts {
    if (total == 0) return const [('Пока пусто — преподаватели ещё не завели журналы.', false)];
    String of(int n) => plural(n, 'предмета', 'предметов', 'предметов'); // «из 21 предмета»
    if (blank) {
      return [(total > 1 ? 'Баллов пока нет — ни в одном из $total ${of(total)}.' : 'Баллов пока нет.', false)];
    }
    final mark = firsts.map(markWord).join(' или ');
    return [
      if (rated > 0 && reached == 0) ('На $mark пока не хватает ни в одном из $rated ${of(rated)}.', false),
      if (reached > 0) ...[('На $mark хватает в ', false), ('$reached из $rated', true), (' ${of(rated)}.', false)],
      if (lowest != null) ...[
        (' Меньше всего — ', false),
        (lowest!.title, true),
        (', ${fmtNum(lowest!.score)}.', false),
      ],
    ];
  }

  String get sentence => parts.map((x) => x.$1).join().trim();
}

typedef _Points = ({List<Course> courses, String? problem});

/// «Баллы БРС, в среднем»: большая цифра и одна фраза. Без своего входа в СДО —
/// «Подключи СДО», ведёт на вход. Не загрузилось — тихая строка, экран живёт.
class _PointsCard extends StatefulWidget {
  final Api api;

  /// Ответ /me: пришёл новый (потянул экран вниз) — баллы тоже заново.
  final Object me;
  final VoidCallback? onOpen, onSdo;
  const _PointsCard({required this.api, required this.me, this.onOpen, this.onSdo});

  @override
  State<_PointsCard> createState() => _PointsCardState();
}

class _PointsCardState extends State<_PointsCard> {
  _Points? _d;
  bool _failed = false, _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(_PointsCard old) {
    super.didUpdateWidget(old);
    // при первом запуске /me приходит дважды (запас, потом сеть) — баллы уже грузятся
    if (!identical(old.me, widget.me) && !_busy) _load(cache: false);
  }

  Future<_Points> _fetch() async {
    try {
      final j = await widget.api.get('/sdo/grades');
      return (courses: [for (final c in j['courses'] as List) Course.fromJson(c)], problem: null);
    } on ApiError catch (e) {
      return (courses: <Course>[], problem: e.message);
    }
  }

  Future<void> _load({bool cache = true}) async {
    _busy = true;
    try {
      if (cache) {
        final c = await Api.fromCache(_fetch);
        if (c != null && mounted && _d == null) setState(() => _d = c);
      }
      final d = await _fetch();
      if (mounted) {
        setState(() {
          _d = d;
          _failed = false;
        });
      }
    } catch (_) {
      // нет сети и запаса — тихая строка «не загрузились» (если прошлых баллов нет);
      // вход в бота устарел — это решит загрузка /me
      if (mounted) setState(() => _failed = _d == null);
    } finally {
      _busy = false;
    }
  }

  Future<void> _connect() async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => SdoConnectScreen(api: widget.api)));
    widget.onSdo?.call();
    if (mounted) await _load(cache: false);
  }

  @override
  Widget build(BuildContext context) {
    final d = _d;
    if (d == null && _failed) {
      return _Quiet(text: 'Баллы не загрузились — нажми, чтобы попробовать ещё раз', onTap: () => _load(cache: false));
    }
    if (d != null && d.problem != null) {
      if (needsSdo(d.problem!)) {
        final expired = d.problem!.contains('устарел');
        return _Quiet(
          key: const Key('more:sdo'),
          icon: Icons.school_outlined,
          title: expired ? 'Вход в СДО устарел — подключи заново' : 'Подключи СДО — тут будут баллы',
          text: 'Баллы БРС по каждому предмету и сколько до зачёта или «3»',
          onTap: _connect,
        );
      }
      return _Quiet(text: 'Баллы не видны: ${d.problem}', onTap: () => _load(cache: false));
    }
    return _PointsBody(sum: d == null ? null : PointsSummary.of(d.courses), onTap: widget.onOpen);
  }
}

class _PointsBody extends StatelessWidget {
  /// null — ещё считаем.
  final PointsSummary? sum;
  final VoidCallback? onTap;
  const _PointsBody({required this.sum, this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final sum = this.sum;
    final words = Text.rich(
      TextSpan(
        children: sum == null
            ? [
                TextSpan(
                  text: 'Считаю баллы…',
                  style: TextStyle(color: p.muted),
                ),
              ]
            : [
                for (final (text, bold) in sum.parts)
                  TextSpan(
                    text: text,
                    style: bold ? const TextStyle(fontWeight: FontWeight.w700) : null,
                  ),
              ],
      ),
      style: s.body(14).copyWith(height: 1.45),
    );
    final number = sum == null || sum.total == 0 ? null : Text('${sum.average}', style: s.number(44));
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: Tile(
        key: const Key('more:points'),
        radius: Radii.card,
        onTap: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('Баллы БРС, в среднем', style: s.body(13, color: p.muted)),
                ),
                if (onTap != null) Icon(Icons.chevron_right_rounded, size: 20, color: p.muted),
              ],
            ),
            const SizedBox(height: Space.s),
            if (number == null)
              words
            else
              // цифра слева, фраза справа; узко или крупный шрифт — фраза под цифрой
              LayoutBuilder(
                builder: (context, box) => box.maxWidth / MediaQuery.textScalerOf(context).scale(1) >= 280
                    ? Row(
                        children: [
                          number,
                          const SizedBox(width: Space.l),
                          Expanded(child: words),
                        ],
                      )
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          number,
                          const SizedBox(height: Space.s),
                          words,
                        ],
                      ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Карточка-строка вместо баллов: «Подключи СДО» или тихая подсказка.
class _Quiet extends StatelessWidget {
  final IconData icon;
  final String? title;
  final String text;
  final VoidCallback onTap;
  const _Quiet({super.key, this.icon = Icons.cloud_off_rounded, this.title, required this.text, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.l),
      child: Tile(
        radius: title == null ? Radii.tile : Radii.card,
        onTap: onTap,
        child: Row(
          children: [
            if (title == null) Icon(icon, size: 20, color: p.muted) else _IconBox(icon: icon),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (title != null) Text(title!, style: s.body(16, weight: FontWeight.w600)),
                  Text(text, style: s.body(13, color: p.muted)),
                ],
              ),
            ),
            if (title != null) Icon(Icons.chevron_right_rounded, color: p.muted),
          ],
        ),
      ),
    );
  }
}

/// Значок в мягком квадрате цвета акцента — у плиток настроек.
class _IconBox extends StatelessWidget {
  final IconData icon;
  const _IconBox({required this.icon});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    return Container(
      width: 34,
      height: 34,
      decoration: BoxDecoration(color: p.accent.withValues(alpha: 0.16), borderRadius: BorderRadius.circular(11)),
      child: Icon(icon, size: 19, color: p.accent),
    );
  }
}

class _TileItem {
  final Key key;
  final IconData icon;
  final String title;
  final VoidCallback? onTap;
  const _TileItem({required this.key, required this.icon, required this.title, required this.onTap});
}

/// Настройки плитками по две; нечётная последняя — во всю ширину строкой.
class _TileGrid extends StatelessWidget {
  final List<_TileItem> items;
  const _TileGrid({required this.items});

  static const _gap = Space.s;

  /// Один размер надписей на всю сетку: самое длинное слово («Безопасность»,
  /// «Уведомления») влезает в половину строки целиком, не рвётся на «…ни/я»
  /// на узком экране с крупным шрифтом — и плитки не разнобой по размеру.
  TextStyle _fit(BuildContext context, TextStyle style, double width) {
    final scaler = MediaQuery.textScalerOf(context);
    var widest = 0.0;
    for (final it in items) {
      for (final w in it.title.split(' ')) {
        final tp = TextPainter(
          text: TextSpan(text: w, style: style),
          textScaler: scaler,
          textDirection: Directionality.of(context),
        )..layout();
        if (tp.width > widest) widest = tp.width;
        tp.dispose();
      }
    }
    return widest <= width ? style : style.copyWith(fontSize: style.fontSize! * width / widest * 0.98);
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, box) {
      // Text добавляет к стилю тему (интервал букв) — меряем тем же, что рисуем
      final base = DefaultTextStyle.of(context).style.merge(AppStyle.of(context).body(15, weight: FontWeight.w600));
      final style = _fit(context, base, (box.maxWidth - _gap) / 2 - 2 * Space.m - 2);
      return Column(
        children: [
          for (var i = 0; i < items.length; i += 2)
            Padding(
              padding: EdgeInsets.only(top: i == 0 ? 0 : _gap),
              child: i + 1 < items.length
                  ? IntrinsicHeight(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(
                            child: _SettingTile(item: items[i], style: style),
                          ),
                          const SizedBox(width: _gap),
                          Expanded(
                            child: _SettingTile(item: items[i + 1], style: style),
                          ),
                        ],
                      ),
                    )
                  : _SettingTile(item: items[i], style: style, wide: true),
            ),
        ],
      );
    },
  );
}

class _SettingTile extends StatelessWidget {
  final _TileItem item;
  final TextStyle style;

  /// Во всю ширину — строкой: значок слева, название справа.
  final bool wide;
  const _SettingTile({required this.item, required this.style, this.wide = false});

  @override
  Widget build(BuildContext context) => Tile(
    key: item.key,
    onTap: item.onTap,
    padding: const EdgeInsets.all(Space.m),
    child: wide
        ? Row(
            children: [
              _IconBox(icon: item.icon),
              const SizedBox(width: Space.m),
              Expanded(child: Text(item.title, style: style)),
            ],
          )
        : Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _IconBox(icon: item.icon),
              const SizedBox(height: Space.s + 2),
              Text(item.title, style: style),
            ],
          ),
  );
}

/// Лист «Тема и шрифт»: шрифт — «Книжный» или «Строгий»; тема — как в
/// телефоне (по умолчанию), светлая «Тетрадь» или тёмная «Глубина».
class _ThemeSheet extends StatelessWidget {
  final ValueChanged<FontChoice> onFont;
  final ValueChanged<ThemeChoice>? onTheme;
  const _ThemeSheet({required this.onFont, this.onTheme});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.l),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Тема и шрифт', style: s.title(22)),
            const SizedBox(height: Space.m),
            Row(
              children: [
                for (final f in const [FontChoice.book, FontChoice.strict]) ...[
                  if (f != FontChoice.book) const SizedBox(width: Space.s),
                  Expanded(
                    child: _FontCard(choice: f, selected: s.font == f, onTap: () => onFont(f)),
                  ),
                ],
              ],
            ),
            const SizedBox(height: Space.s),
            Tile(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  for (final t in const [ThemeChoice.system, ThemeChoice.light, ThemeChoice.dark]) ...[
                    if (t != ThemeChoice.system) Divider(height: 1, color: p.line),
                    _ThemeRow(choice: t, selected: s.theme == t, onTap: onTheme == null ? null : () => onTheme!(t)),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MenuRow extends StatelessWidget {
  final IconData icon;
  final String title, sub;

  /// null — строка не нажимается (запрос уже отправлен).
  final VoidCallback? onTap;
  const _MenuRow({required this.icon, required this.title, required this.sub, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return InkWell(
      onTap: onTap == null
          ? null
          : () {
              tick();
              onTap!();
            },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
        child: Row(
          children: [
            Icon(icon, color: s.p.accent),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: s.body(16, weight: FontWeight.w600)),
                  Text(sub, style: s.body(13, color: s.p.muted)),
                ],
              ),
            ),
            if (onTap != null) Icon(Icons.chevron_right_rounded, color: s.p.muted),
          ],
        ),
      ),
    );
  }
}

/// Предметы по выбору (военная кафедра): «хожу» — пары в расписании, «не хожу» —
/// скрыты (optional_subjects.py). Нет таких в расписании группы — блока нет.
class _Optional extends StatefulWidget {
  final Api api;
  const _Optional({required this.api});

  @override
  State<_Optional> createState() => _OptionalState();
}

class _OptionalState extends State<_Optional> {
  List<String> _pending = [];
  Map<String, bool> _answers = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await widget.api.get('/optional');
      if (!mounted) return;
      setState(() {
        _pending = [for (final x in (r['pending'] as List? ?? const [])) x as String];
        _answers = {for (final e in ((r['answers'] as Map?) ?? const {}).entries) e.key as String: e.value == true};
      });
    } catch (_) {}
  }

  Future<void> _answer(String subject, bool attend) async {
    tick();
    final toast = Overlay.of(context, rootOverlay: true);
    try {
      await widget.api.post('/optional', {'subject': subject, 'attend': attend});
    } on ApiError catch (e) {
      toastOn(toast, 'Не сохранилось: ${e.message}', kind: ToastKind.error);
      return;
    }
    if (!mounted) return;
    setState(() {
      _pending.remove(subject);
      _answers[subject] = attend;
    });
    showToast(
      context,
      attend ? 'Пары «$subject» будут в расписании' : 'Убрал «$subject» из расписания',
      kind: ToastKind.done,
    );
  }

  @override
  Widget build(BuildContext context) {
    final subjects = [..._pending, ..._answers.keys.where((k) => !_pending.contains(k))];
    if (subjects.isEmpty) return const SizedBox.shrink();
    final s = AppStyle.of(context);
    final p = s.p;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Section('Предметы по выбору'),
        for (final subj in subjects)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
            child: Tile(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.military_tech_outlined, color: p.accent),
                      const SizedBox(width: Space.m),
                      Expanded(
                        child: Text(subj, style: s.body(16, weight: FontWeight.w600)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _pending.contains(subj)
                        ? 'Ходишь? Если нет — уберу эти пары из твоего расписания.'
                        : (_answers[subj]! ? 'Хожу — пары в расписании' : 'Не хожу — пары скрыты'),
                    style: s.body(13, color: p.muted),
                  ),
                  const SizedBox(height: Space.m),
                  Row(
                    children: [
                      for (final attend in [true, false]) ...[
                        if (!attend) const SizedBox(width: Space.s),
                        Expanded(
                          child: _Choice(
                            text: attend ? 'Хожу' : 'Не хожу',
                            on: _answers[subj] == attend,
                            onTap: () => _answer(subj, attend),
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class _Choice extends StatelessWidget {
  final String text;
  final bool on;
  final VoidCallback onTap;
  const _Choice({required this.text, required this.on, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final r = BorderRadius.circular(Radii.chip);
    return Material(
      color: on ? p.accent : p.line,
      borderRadius: r,
      child: InkWell(
        borderRadius: r,
        onTap: on ? null : onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: Space.m),
          child: Text(
            text,
            textAlign: TextAlign.center,
            style: s.body(15, weight: FontWeight.w600, color: on ? p.onAccent : p.text),
          ),
        ),
      ),
    );
  }
}

/// Строка темы: значок, название и какая палитра; выбранная — с галочкой.
class _ThemeRow extends StatelessWidget {
  final ThemeChoice choice;
  final bool selected;
  final VoidCallback? onTap;
  const _ThemeRow({required this.choice, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final (icon, title, sub) = switch (choice) {
      ThemeChoice.system => (
        Icons.brightness_auto_outlined,
        'Как в телефоне',
        p.dark ? 'сейчас тёмная «Глубина»' : 'сейчас светлая «Тетрадь»',
      ),
      ThemeChoice.sunset => (Icons.wb_twilight_outlined, 'По закату', 'тёмная с заката до восхода'),
      ThemeChoice.light => (Icons.light_mode_outlined, 'Светлая', '«Тетрадь»'),
      ThemeChoice.dark => (Icons.dark_mode_outlined, 'Тёмная', '«Глубина»'),
    };
    return Semantics(
      selected: selected,
      button: true,
      child: InkWell(
        key: Key('theme:${choice.name}'),
        onTap: onTap == null
            ? null
            : () {
                tick();
                onTap!();
              },
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
          child: Row(
            children: [
              Icon(icon, color: p.accent),
              const SizedBox(width: Space.m),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: s.body(16, weight: FontWeight.w600)),
                    Text(sub, style: s.body(13, color: p.muted)),
                  ],
                ),
              ),
              AnimatedOpacity(
                opacity: selected ? 1 : 0,
                duration: const Duration(milliseconds: 180),
                child: Icon(Icons.check_circle_rounded, color: p.accent),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FontCard extends StatelessWidget {
  final FontChoice choice;
  final bool selected;
  final VoidCallback onTap;
  const _FontCard({required this.choice, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final book = choice == FontChoice.book;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 220),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Radii.tile),
        border: Border.all(color: selected ? p.accent : Colors.transparent, width: 2),
      ),
      child: Tile(
        onTap: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Аа 73',
              style: TextStyle(
                fontFamily: book ? 'SourceSerif' : 'Onest',
                fontSize: 30,
                fontWeight: book ? FontWeight.w500 : FontWeight.w800,
                color: p.text,
              ),
            ),
            const SizedBox(height: 4),
            Text(book ? 'Книжный' : 'Строгий', style: s.body(14, weight: FontWeight.w600)),
            Text(book ? 'с засечками' : 'ровный, Onest', style: s.body(12, color: p.muted)),
          ],
        ),
      ),
    );
  }
}

/// «Я староста этой группы» — запрос владельцу бота (одобрит — можно вести
/// общие сроки, ДЗ и заметки группы). Строкой под плитками: действие с пояснением.
class _AdminRequest extends StatefulWidget {
  final Api api;
  const _AdminRequest({required this.api});

  @override
  State<_AdminRequest> createState() => _AdminRequestState();
}

class _AdminRequestState extends State<_AdminRequest> {
  String? _note;

  @override
  Widget build(BuildContext context) => _MenuRow(
    icon: Icons.verified_user_outlined,
    title: 'Я староста этой группы',
    sub: _note ?? 'спрошу владельца бота — сможешь вести общие сроки и ДЗ',
    onTap: _note != null
        ? null
        : () async {
            try {
              await widget.api.post('/me/group/admin');
              setState(() => _note = 'Запрос отправлен — ответ придёт в бота.');
            } on ApiError catch (e) {
              setState(() => _note = e.message);
            }
          },
  );
}

/// Лист «Новости и связь»: что за ссылка — и кнопка «Перейти», решает человек.
Future<void> showLinksSheet(
  BuildContext context,
  List<(IconData, String, String, String, String)> links, {
  String title = 'Новости и связь',
}) {
  final s = AppStyle.of(context);
  final p = s.p;
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: p.cardSolid,
    showDragHandle: true,
    // прокрутка — на маленьком экране три строки «других мест» не влезали
    builder: (ctx) => SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(title, style: s.title(22)),
            const SizedBox(height: Space.m),
            for (final (icon, title, sub, button, url) in links)
              Padding(
                padding: const EdgeInsets.only(bottom: Space.s),
                child: Tile(
                  child: Row(
                    children: [
                      Icon(icon, color: p.accent),
                      const SizedBox(width: Space.m),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(title, style: s.body(16, weight: FontWeight.w600)),
                            Text(sub, style: s.body(13, color: p.muted)),
                          ],
                        ),
                      ),
                      const SizedBox(width: Space.s),
                      FilledButton(
                        key: Key('go:$title'),
                        style: FilledButton.styleFrom(
                          backgroundColor: p.accent,
                          foregroundColor: p.onAccent,
                          shape: const StadiumBorder(),
                        ),
                        onPressed: () {
                          tick();
                          launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
                        },
                        child: Text(button),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}

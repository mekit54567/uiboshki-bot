// Оболочка: пять вкладок и меню-капсула; при первом запуске — короткий тур
// по приложению (tour.dart).
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../achievements/store.dart';
import '../achievements/ui.dart';
import '../api/api.dart';
import '../api/links.dart';
import '../api/models.dart';
import '../theme/app_icon.dart';
import '../theme/app_theme.dart';
import '../theme/look.dart';
import '../theme/tokens.dart';
import '../widgets/capsule_tabbar.dart';
import '../widget_data.dart';
import '../widgets/common.dart';
import 'deadlines.dart';
import 'group_pick.dart';
import 'legal.dart';
import 'more.dart';
import 'study.dart';
import 'today.dart';
import 'tour.dart';
import 'week.dart';

const tabs = [
  TabItem(Icons.schedule_rounded, 'Сегодня'),
  TabItem(Icons.calendar_today_rounded, 'Неделя'),
  TabItem(Icons.bookmark_border_rounded, 'Сдать'),
  TabItem(Icons.school_outlined, 'Учёба'),
  TabItem(Icons.more_horiz_rounded, 'Ещё'),
];

/// Вкладка по имени из ссылки пуша (`/app?tab=deadlines`, delivery.py).
int tabByName(String? name) => switch (name) {
  'week' => 1,
  'deadlines' => 2,
  'sdo' || 'study' => 3,
  'more' => 4,
  _ => 0,
};

class Shell extends StatefulWidget {
  final Api api;
  final ValueChanged<FontChoice> onFont;
  final ValueChanged<ThemeChoice>? onTheme;

  /// «Оформление» (5.79): main.dart запоминает выбор.
  final ValueChanged<Look>? onLook;
  final VoidCallback onLogout, onUnauthorized;
  final int initialTab;
  const Shell({
    super.key,
    required this.api,
    required this.onFont,
    this.onTheme,
    this.onLook,
    required this.onLogout,
    required this.onUnauthorized,
    this.initialTab = 0,
  });

  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> with WidgetsBindingObserver {
  late int _index = widget.initialTab;

  /// Сменилась группа — номер растёт, экраны строятся заново со своими данными.
  int _epoch = 0;

  // СДО подключили из «Ещё» — «Учёба» строится заново
  int _sdo = 0;

  /// Сменили шрифт или тему, пока вкладка была скрыта: на iPhone такая
  /// вкладка оставалась со старым шрифтом (Onest не уходил обратно, владелец
  /// 09.10, 3.7). Скрытые вкладки строятся заново, когда их открывают.
  final _gen = List<int>.filled(tabs.length, 0);
  final _stale = <int>{};
  (FontChoice, bool)? _style;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final s = AppStyle.of(context);
    final cur = (s.font, s.p.dark);
    if (_style != null && _style != cur) {
      for (var i = 0; i < tabs.length; i++) {
        if (i != _index) _stale.add(i);
      }
    }
    _style = cur;
  }

  void _open(int i) => setState(() {
    if (_stale.remove(i)) _gen[i]++;
    _index = i;
    _barHidden = false; // сменил вкладку — меню на месте
    _drift = 0;
  });

  // Меню при прокрутке (новый дизайн, Никита 12.10, вариант Г): капсула
  // уезжает вниз только в длинном списке («Неделя», «Сдано»), пока человек
  // пальцем листает дальше, и возвращается, когда чуть листнул назад, дошёл
  // до конца или начала, сменил вкладку или список короткий. Прыжки списка
  // из кода (нажатие на день, тесты) меню не прячут.
  bool _barHidden = false;

  /// Сколько палец увёл список в одну сторону (больше нуля — дальше по списку).
  double _drift = 0;
  static const _hideAfter = 32.0, _showAfter = 24.0;

  /// Длинный список: прокрутки больше полутора экранов.
  static bool _long(ScrollMetrics m) => m.maxScrollExtent - m.minScrollExtent > 1.5 * m.viewportDimension;

  void _setBar(bool hidden) {
    if (hidden != _barHidden) setState(() => _barHidden = hidden);
  }

  bool _onScroll(int tab, Notification n) {
    if (tab != _index || !AppStyle.of(context).design2) return false;
    final (depth, m) = switch (n) {
      ScrollNotification() => (n.depth, n.metrics),
      ScrollMetricsNotification() => (n.depth, n.metrics),
      _ => (-1, null),
    };
    // только главный список вкладки, вложенные и горизонтальные — мимо
    if (depth != 0 || m == null || m.axisDirection != AxisDirection.down || !m.hasContentDimensions) return false;
    if (!_long(m) || m.pixels <= m.minScrollExtent || m.pixels >= m.maxScrollExtent - 1) {
      _drift = 0;
      _setBar(false);
      return false;
    }
    final delta = n is ScrollUpdateNotification && n.dragDetails != null ? n.scrollDelta ?? 0 : 0.0;
    if (delta == 0) return false;
    if ((delta > 0) != (_drift > 0)) _drift = 0;
    _drift += delta;
    if (_drift > _hideAfter) _setBar(true);
    if (_drift < -_showAfter) _setBar(false);
    return false;
  }

  @override
  void initState() {
    super.initState();
    // ачивки: ловят по ответам API, плашка — сверху, «Показать где» — вкладка
    Api.onOk = (method, path, body, result) => AchStore.onApi(method, path, body, result, now());
    AchStore.onUnlock = showUnlockBanner;
    AchStore.openTab = _open;
    AchStore.api = widget.api;
    WidgetsBinding.instance.addObserver(this);
    _visit();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _ensureGroup();
      await _maybeTour();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    Api.onOk = null;
    AchStore.onUnlock = null;
    AchStore.openTab = null;
    AchStore.api = null;
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _visit();
  }

  /// Заход: дни для ачивок; виджет на экране телефона — «На столе».
  Future<void> _visit() async {
    try {
      await AchStore.load();
      await AchStore.visit(now());
      await AchStore.sync();
      final sink = HomeWidgets.sink;
      if (sink != null && await sink.installed() > 0) await AchStore.unlock('widget');
    } catch (_) {}
  }

  /// Нет группы в профиле (новый человек) — сначала выбрать её.
  Future<void> _ensureGroup() async {
    Map? me;
    try {
      me = await widget.api.get('/me') as Map?;
    } catch (_) {
      return; // нет сети или вход устарел — экраны сами скажут
    }
    if (me == null || !mounted) return;
    achName = '${me['first_name'] ?? ''}'.trim();
    appLinks(widget.api).then((l) => setAchBot(l['bot']), onError: (_) {});
    // подписочные иконки — только с подпиской (5.91): plus из /api/me
    // (у своей группы plan остаётся «own» и с подпиской), до него — plan
    AppIcon.premium.value = me['plus'] == true || me['plan'] == 'sub';
    // 152-ФЗ: согласие на обработку персональных данных — до всего (legal.dart)
    if (me['consent_needed'] == true) {
      final blocked = me['consent_blocked'] == true;
      final ok = await Navigator.of(context).push<bool>(
        MaterialPageRoute(
          builder: (_) => ConsentScreen(api: widget.api, required: blocked),
        ),
      );
      // отказался — данные удалены, ко входу; кто был до согласий может «Не сейчас»
      if (ok == false || (blocked && ok != true)) return widget.onLogout();
      if (!mounted) return;
      if (blocked) setState(() => _epoch++); // до согласия API закрыт — экраны загрузить заново
    }
    if (me['group'] != null) return;
    await pickGroup(required: true);
  }

  Future<void> pickGroup({bool required = false}) async {
    final g = await Navigator.of(context).push<Map<String, dynamic>>(
      MaterialPageRoute(
        builder: (_) => GroupPickScreen(api: widget.api, required: required),
      ),
    );
    if (g != null && mounted) setState(() => _epoch++);
  }

  Future<void> _maybeTour() async {
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getBool('uib_toured') == true || !mounted) return;
    await prefs.setBool('uib_toured', true);
    if (mounted) await tour();
  }

  final _bar = GlobalKey();

  /// Где меню-капсула: верх её коробки, по бокам — отступ Space.l, высота 64
  /// (capsule_tabbar.dart); снизу у коробки ещё отступ до края экрана.
  Rect? _barRect() {
    final box = _bar.currentContext?.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return null;
    final at = box.localToGlobal(Offset.zero);
    return Rect.fromLTWH(at.dx + Space.l, at.dy, box.size.width - 2 * Space.l, 64);
  }

  /// Короткий тур по приложению — при первом запуске и из «Ещё».
  Future<void> tour() {
    _open(tourSteps.first.tab);
    return showTour(context, onStep: _open, barRect: _barRect);
  }

  @override
  Widget build(BuildContext context) {
    final api = widget.api;
    final un = widget.onUnauthorized;
    final g = _gen;
    final pages = [
      TodayScreen(key: ValueKey('today$_epoch.${g[0]}'), api: api, onUnauthorized: un),
      WeekScreen(key: ValueKey('week$_epoch.${g[1]}'), api: api, onUnauthorized: un),
      DeadlinesScreen(key: ValueKey('dl$_epoch.${g[2]}'), api: api, onUnauthorized: un),
      StudyScreen(key: ValueKey('study$_epoch.$_sdo.${g[3]}'), api: api, onUnauthorized: un),
      MoreScreen(
        key: ValueKey('more$_epoch.${g[4]}'),
        api: api,
        onFont: widget.onFont,
        onTheme: widget.onTheme,
        onLook: widget.onLook,
        onLogout: widget.onLogout,
        onUnauthorized: un,
        onGroup: () => pickGroup(),
        onStudy: () => _open(tabByName('study')),
        onSdo: () => setState(() => _sdo++),
        onTour: tour,
      ),
    ];
    return Scaffold(
      extendBody: true,
      body: Backdrop(
        child: SafeArea(
          bottom: false,
          child: Column(
            children: [
              OfflineBanner(since: widget.api.offlineSince, slow: widget.api.offlineSlow),
              Expanded(
                child: IndexedStack(
                  index: _index,
                  children: [
                    for (final (i, page) in pages.indexed)
                      NotificationListener<Notification>(onNotification: (n) => _onScroll(i, n), child: page),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      bottomNavigationBar: CapsuleTabBar(
        key: _bar,
        items: tabs,
        index: _index,
        onTap: _open,
        // с экранным диктором меню не прячем — до вкладок всегда дойти
        hidden: _barHidden && AppStyle.of(context).design2 && !MediaQuery.accessibleNavigationOf(context),
      ),
    );
  }
}

/// «Без сети · данные от 10:07» — пока ответы идут из памяти телефона.
///
/// Новый дизайн («Загрузка», Никита 12.10): «Нет сети» — когда связи правда
/// нет, «Сервер не отвечает» — когда сеть есть, а сервер не ответил вовремя
/// (значок — не облако: читалось как погода). И тонкая строка «Обновляю ·
/// данные от 09:41», пока экран показывает запас и ждёт сеть дольше 600 мс.
class OfflineBanner extends StatefulWidget {
  final ValueListenable<DateTime?> since;

  /// Из запаса, потому что сервер не ответил вовремя (а не нет сети).
  final ValueListenable<bool>? slow;

  /// Экраны показывают запас и ждут сеть: время их данных ([Api.refreshing]).
  final ValueListenable<DateTime?>? refreshing;
  const OfflineBanner({super.key, required this.since, this.slow, this.refreshing});

  /// Через сколько показывать «Обновляю»: быстрая сеть не мигает строкой.
  static const refreshDelay = Duration(milliseconds: 600);

  /// «09:05», «вчера 22:10», «1 октября 08:00».
  static String stamp(DateTime at, DateTime today) {
    final hm = '${at.hour.toString().padLeft(2, '0')}:${at.minute.toString().padLeft(2, '0')}';
    final days = DateTime(today.year, today.month, today.day).difference(DateTime(at.year, at.month, at.day)).inDays;
    final day = switch (days) {
      0 => '',
      1 => 'вчера ',
      _ => '${at.day} ${monthsGen[at.month - 1]} ',
    };
    return '$day$hm';
  }

  static String label(DateTime at, DateTime today, {String what = 'Без сети'}) =>
      '$what · данные от ${stamp(at, today)}';

  @override
  State<OfflineBanner> createState() => _OfflineBannerState();
}

class _OfflineBannerState extends State<OfflineBanner> {
  Timer? _timer;

  /// Строка «Обновляю» видна (прошло [OfflineBanner.refreshDelay]).
  bool _late = false;

  ValueListenable<DateTime?> get _refreshing => widget.refreshing ?? Api.refreshing;

  @override
  void initState() {
    super.initState();
    _refreshing.addListener(_onRefreshing);
    _onRefreshing();
  }

  @override
  void didUpdateWidget(OfflineBanner old) {
    super.didUpdateWidget(old);
    final was = old.refreshing ?? Api.refreshing;
    if (!identical(was, _refreshing)) {
      was.removeListener(_onRefreshing);
      _refreshing.addListener(_onRefreshing);
      _onRefreshing();
    }
  }

  @override
  void dispose() {
    _refreshing.removeListener(_onRefreshing);
    _timer?.cancel();
    super.dispose();
  }

  void _onRefreshing() {
    if (_refreshing.value == null) {
      _timer?.cancel();
      _timer = null;
      if (_late) setState(() => _late = false);
    } else {
      _timer ??= Timer(OfflineBanner.refreshDelay, () {
        _timer = null;
        if (mounted && _refreshing.value != null) setState(() => _late = true);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return ListenableBuilder(
      listenable: Listenable.merge([widget.since, ?widget.slow, _refreshing]),
      builder: (context, _) {
        final at = widget.since.value;
        final busy = _refreshing.value;
        final Widget child;
        if (at != null) {
          child = _pill(s, at);
        } else if (s.design2 && _late && busy != null) {
          child = _line(s, busy);
        } else {
          child = const SizedBox(width: double.infinity);
        }
        return AnimatedSize(duration: const Duration(milliseconds: 250), curve: Curves.easeOutCubic, child: child);
      },
    );
  }

  /// Плашка «нет сети»: в старом дизайне — «Без сети» с облаком.
  Widget _pill(AppStyle s, DateTime at) {
    final slow = widget.slow?.value ?? false;
    final (icon, what) = !s.design2
        ? (Icons.cloud_off_rounded, 'Без сети')
        : slow
        ? (Icons.hourglass_bottom_rounded, 'Сервер не отвечает')
        : (Icons.wifi_off_rounded, 'Нет сети');
    return Padding(
      key: const ValueKey('banner:offline'),
      padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, 0),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.s),
        decoration: BoxDecoration(
          color: s.p.warn.withValues(alpha: 0.16),
          borderRadius: BorderRadius.circular(Radii.pill),
        ),
        child: Row(
          children: [
            Icon(icon, size: 16, color: s.p.warn),
            const SizedBox(width: Space.s),
            Expanded(
              child: Text(
                OfflineBanner.label(at, now(), what: what),
                style: s.body(13, weight: FontWeight.w600),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Тонкая приглушённая строка: экран показывает запас и ждёт свежие данные.
  Widget _line(AppStyle s, DateTime at) => Padding(
    key: const ValueKey('banner:refresh'),
    padding: const EdgeInsets.fromLTRB(Space.l, Space.xs, Space.l, 0),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(Icons.sync_rounded, size: 13, color: s.p.muted),
        const SizedBox(width: Space.xs),
        Flexible(
          child: Text(
            'Обновляю · данные от ${OfflineBanner.stamp(at, now())}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: s.body(12, color: s.p.muted),
          ),
        ),
      ],
    ),
  );
}

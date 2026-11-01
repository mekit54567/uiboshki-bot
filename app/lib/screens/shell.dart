// Оболочка: пять вкладок и меню-капсула; при первом запуске — короткий тур
// по приложению (tour.dart).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../achievements/store.dart';
import '../achievements/ui.dart';
import '../api/api.dart';
import '../api/links.dart';
import '../app_push.dart';
import '../plus/plus.dart';
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
import 'pulse_scan.dart';
import 'sdo_login.dart' show sdoWebLoginAvailable;
import 'sdo_relogin.dart';
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
    PlusBonus.api = widget.api;
    AchStore.api = widget.api;
    WidgetsBinding.instance.addObserver(this);
    AppPush.tab.addListener(_pushTab);
    _visit();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _ensureGroup();
      unawaited(PlusBonus.sendRef(widget.api)); // после согласия: до него API закрыт
      unawaited(AppPush.start(widget.api)); // нажатое уведомление, новый токен телефона
      await _maybeTour();
      if (mounted) await _sdoRefresh();
    });
  }

  /// Нажали уведомление приложения — его вкладка (как `?tab=` у веб-пуша).
  void _pushTab() {
    final t = AppPush.tab.value;
    if (t == null || !mounted) return;
    AppPush.tab.value = null;
    Navigator.of(context).popUntil((r) => r.isFirst);
    _open(tabByName(t));
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    AppPush.tab.removeListener(_pushTab);
    Api.onOk = null;
    AchStore.onUnlock = null;
    AchStore.openTab = null;
    PlusBonus.api = null;
    AchStore.api = null;
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _visit();
      _sdoRefresh();
    }
  }

  /// Вход в СДО устарел, а единый вход МИРЭА ещё помнит человека — обновить
  /// молча, «Учёба» строится заново уже с баллами (sdo_relogin.dart, 5.102.0).
  Future<void> _sdoRefresh() async {
    if (await SdoRelogin.refreshIfExpired(context, widget.api) && mounted) setState(() => _sdo++);
  }

  /// Заход: дни для ачивок; виджет на экране телефона — «На столе».
  Future<void> _visit() async {
    try {
      await AchStore.load();
      await AchStore.visit(now());
      await AchStore.sync();
      await PlusBonus.checkAll(); // ранги, закрытые раньше, — бонус ещё не забран
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
    // попросил удалить данные — до полного стирания только это, потом ко входу
    final erasing = me['erasing'];
    if (erasing is Map) {
      await confirmSheet(
        context,
        title: 'Данные удаляются',
        text: '${erasing['text']}',
        action: 'Понятно',
        cancel: 'Закрыть',
      );
      return widget.onLogout();
    }
    appLinks(widget.api).then((l) => setAchBot(l['bot']), onError: (_) {});
    // подписочные иконки — только с подпиской (5.91): plus из /api/me
    // (у своей группы plan остаётся «own» и с подпиской), до него — plan
    AppIcon.premium.value = me['plus'] == true || me['plan'] == 'sub';
    // кружок QR на «Сегодня» (сканер Пульса, 01.11) — пока у тех, кому открыт эксперимент
    if (me['lab'] == true && sdoWebLoginAvailable) setState(() => _qr = true);
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
  bool _qr = false;

  /// Сканер отметки в Пульсе; отметился — плашка «Есть, ты на паре».
  Future<void> _scan() async {
    final ok = await Navigator.of(context).push<bool>(
      MaterialPageRoute(fullscreenDialog: true, builder: (_) => const PulseScanScreen()),
    );
    if (ok == true && mounted) showToast(context, 'Есть, ты на паре', kind: ToastKind.done);
  }

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
      // QR — только на «Сегодня», всегда, над меню справа (Никита 01.11)
      floatingActionButton: _qr && _index == 0
          ? Padding(
              padding: const EdgeInsets.only(bottom: Space.s),
              child: FloatingActionButton.small(
                key: const Key('today:qr'),
                heroTag: 'qr',
                tooltip: 'Отметиться по QR',
                elevation: 2,
                backgroundColor: AppStyle.of(context).p.accent,
                foregroundColor: AppStyle.of(context).p.onAccent,
                shape: const CircleBorder(),
                onPressed: _scan,
                child: const Icon(Icons.qr_code_scanner_rounded),
              ),
            )
          : null,
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

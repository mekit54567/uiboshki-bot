// «Уведомления» — что бот присылает и в какие дни (/api/notify, notify_prefs.py).
// Как лист в WebApp: сохраняется сразу при каждом нажатии, без «Сохранить».
import 'dart:convert';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../api/models.dart';
import '../app_push.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../web_push.dart';
import '../widgets/common.dart';
import 'files.dart' show BackRow;

class NotifyScreen extends StatelessWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const NotifyScreen({super.key, required this.api, this.onUnauthorized});

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Backdrop(
      child: SafeArea(
        child: Loader<Map<String, dynamic>>(
          load: () async => Map<String, dynamic>.from(await api.get('/notify')),
          onUnauthorized: onUnauthorized,
          builder: (context, data, _) => _NotifyBody(api: api, initial: data),
        ),
      ),
    ),
  );
}

class _NotifyBody extends StatefulWidget {
  final Api api;
  final Map<String, dynamic> initial;
  const _NotifyBody({required this.api, required this.initial});

  @override
  State<_NotifyBody> createState() => _NotifyBodyState();
}

class _NotifyBodyState extends State<_NotifyBody> {
  late Map<String, dynamic> _s = widget.initial;

  /// Пуши этого телефона (app_push.dart): '' — ещё не знаем, unsupported — нет.
  String _app = '';

  @override
  void initState() {
    super.initState();
    if (!kIsWeb && AppPush.device != null) {
      AppPush.state(widget.api).then((v) {
        if (mounted) setState(() => _app = v);
      });
    }
  }

  // Быстрые нажатия (Пн, Вт, Ср подряд) не теряются: у себя меняем сразу,
  // запросы уходят по очереди, ответ сервера берём от последнего.
  Future<void> _queue = Future.value();
  int _pending = 0;

  @override
  void didUpdateWidget(_NotifyBody old) {
    super.didUpdateWidget(old);
    if (old.initial != widget.initial && _pending == 0) _s = widget.initial; // потянули — свежие с сервера
  }

  Map<String, dynamic> get _prefs => _s['prefs'] as Map<String, dynamic>;

  void _snack(String text) {
    if (mounted) showToast(context, text, kind: ToastKind.error);
  }

  Future<void> _save(Map<String, dynamic> body) {
    tick();
    setState(() {
      if (body.containsKey('subscribed')) _s['subscribed'] = body['subscribed'];
      if (body['prefs'] is Map) _prefs.addAll(Map<String, dynamic>.from(body['prefs'] as Map));
    });
    _pending++;
    return _queue = _queue.then((_) async {
      Object? fresh;
      try {
        fresh = await widget.api.post('/notify', body);
      } catch (e) {
        _snack('Не сохранилось: ${errorText(e)}');
        try {
          fresh = await widget.api.get('/notify'); // что на самом деле сохранено
        } catch (_) {}
      }
      if (--_pending == 0 && fresh is Map && fresh['prefs'] is Map && mounted) {
        setState(() => _s = Map<String, dynamic>.from(fresh as Map));
      }
    });
  }

  void _toggle(String key) => _save({
    'prefs': {key: !(_prefs[key] == true)},
  });

  void _toggleDay(String key, int day) {
    final days = List<int>.from(_prefs[key] as List);
    days.contains(day) ? days.remove(day) : days.add(day);
    days.sort();
    _save({
      'prefs': {key: days},
    });
  }

  Future<void> _customRemind(Map r) async {
    final key = r['key'] as String;
    final max = r['max'] as int;
    final v = _prefs[key] as int? ?? 0;
    final got = await inputSheet(
      context,
      title: r['title'] as String,
      text: 'За сколько минут до пары напомнить',
      hint: 'минут, до $max',
      initial: v > 0 && !(r['presets'] as List).contains(v) ? '$v' : '',
      keyboard: TextInputType.number,
    );
    if (got == null || !mounted) return;
    final n = int.tryParse(got) ?? -1;
    if (n < 1 || n > max) {
      _snack('Число минут от 1 до $max');
      return;
    }
    _save({
      'prefs': {key: n},
    });
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final on = _s['subscribed'] == true;
    final campus = _s['home_campus'] as String?;
    return ListView(
      padding: const EdgeInsets.only(bottom: Space.xxl),
      children: [
        const BackRow(),
        const ScreenTitle(title: 'Уведомления'),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.m),
          child: Row(
            children: [
              Icon(Icons.info_outline_rounded, size: 18, color: p.muted),
              const SizedBox(width: Space.s),
              Expanded(
                child: Text(
                  kIsWeb || const ['on', 'off', 'denied'].contains(_app)
                      ? 'Уведомления приходят в Telegram, а сюда — когда включишь их ниже.'
                      : 'Уведомления — в Telegram и в браузере; в приложении — скоро.',
                  style: s.body(13, color: p.muted),
                ),
              ),
            ],
          ),
        ),
        if (kIsWeb)
          _WebPushCard(api: widget.api, tgCopy: _prefs['tg_copy'] != false, onTgCopy: () => _toggle('tg_copy')),
        if (!kIsWeb && const ['on', 'off', 'denied'].contains(_app))
          _AppPushCard(
            api: widget.api,
            state: _app,
            onState: (v) => setState(() => _app = v),
            tgCopy: _prefs['tg_copy'] != false,
            onTgCopy: () => _toggle('tg_copy'),
          ),
        _Card(
          title: 'Присылать уведомления',
          sub: on ? 'Включены — ниже, что именно' : 'Выключены — бот ничего не пришлёт сам',
          switchKey: 'subscribed',
          on: on,
          onChanged: () => _save({'subscribed': !on}),
        ),
        if (on) ...[
          _Card(
            icon: Icons.wb_sunny_outlined,
            title: 'Утреннее расписание',
            sub: 'в ${_s['morning_time'] ?? '8:00'} — пары на сегодня',
            switchKey: 'morning',
            on: _prefs['morning'] == true,
            onChanged: () => _toggle('morning'),
            children: [
              _Days(days: _prefs['morning_days'] as List, daysKey: 'morning_days', onTap: _toggleDay),
              _Row(title: 'Погода', sub: 'строчка с погодой в начале', k: 'weather', prefs: _prefs, onTap: _toggle),
              _Row(
                title: 'Другой корпус',
                sub: campus != null ? 'если пары не на $campus — напишу, где' : 'если пары в другом корпусе — напишу',
                k: 'campus',
                prefs: _prefs,
                onTap: _toggle,
              ),
              _Row(
                title: 'Только если есть пары',
                sub: 'в свободный день — тишина',
                k: 'skip_empty',
                prefs: _prefs,
                onTap: _toggle,
              ),
            ],
          ),
          _Card(
            icon: Icons.alarm_outlined,
            title: 'Перед парой',
            sub: 'своё время для первой пары и после перемены',
            switchKey: 'lessons',
            on: _prefs['lessons'] == true,
            onChanged: () => _toggle('lessons'),
            children: [
              _Days(days: _prefs['lesson_days'] as List, daysKey: 'lesson_days', onTap: _toggleDay),
              for (final r in (_s['remind'] as List? ?? const []))
                _Remind(
                  r: r as Map,
                  value: _prefs[r['key']] as int? ?? 0,
                  onPick: (v) => _save({
                    'prefs': {r['key'] as String: v},
                  }),
                  onCustom: () => _customRemind(r),
                ),
            ],
          ),
          _Card(
            icon: Icons.flag_outlined,
            title: 'Дедлайны',
            sub: 'в ${_s['deadline_time'] ?? '19:00'} — что сдать в ближайшие 3 дня',
            switchKey: 'deadlines',
            on: _prefs['deadlines'] == true,
            onChanged: () => _toggle('deadlines'),
            children: [_Days(days: _prefs['deadline_days'] as List, daysKey: 'deadline_days', onTap: _toggleDay)],
          ),
          // «Срок скоро» (deadline_soon.py, Никита 25.10): за сколько часов до
          // срока напомнить, если работа не сдана; по умолчанию 3 ч.
          _Card(
            icon: Icons.hourglass_bottom_outlined,
            title: 'Срок скоро',
            sub: 'за ${soonLabel(_soonHours())} до срока, если работа не сдана',
            switchKey: 'deadline_soon',
            on: _prefs['deadline_soon'] == true,
            onChanged: () => _toggle('deadline_soon'),
            children: [
              _SoonHours(
                choices: [for (final h in (_s['deadline_soon_choices'] as List? ?? soonChoices)) h as int],
                value: _soonHours(),
                onPick: (h) => _save({
                  'prefs': {'deadline_soon_hours': h},
                }),
              ),
            ],
          ),
          _Card(
            icon: Icons.view_week_outlined,
            title: 'Обзор недели',
            sub: 'в воскресенье в 19:00 — сколько пар и что сдать',
            switchKey: 'weekly',
            on: _prefs['weekly'] == true,
            onChanged: () => _toggle('weekly'),
          ),
          _Card(
            icon: Icons.military_tech_outlined,
            title: 'Новые баллы',
            sub: 'когда проверят работу или изменятся баллы (если подключён вход в СДО)',
            switchKey: 'grades',
            on: _prefs['grades'] == true,
            onChanged: () => _toggle('grades'),
          ),
          _Card(
            icon: Icons.assignment_outlined,
            title: 'Новые задания',
            sub: 'когда в СДО появится задание или перенесут срок',
            switchKey: 'new_tasks',
            on: _prefs['new_tasks'] == true,
            onChanged: () => _toggle('new_tasks'),
          ),
          // Тесты СДО (quiz_alerts.py, Никита 12.10): один пункт, по нажатию —
          // напоминания до закрытия (несколько сразу) и «Тест открылся».
          _QuizCard(
            choices: [for (final m in (_s['quiz_choices'] as List? ?? quizChoices)) m as int],
            remind: [for (final m in (_prefs['quiz_remind'] as List? ?? const [])) m as int],
            open: _prefs['quiz_open'] != false,
            expanded: _quizExpanded,
            onExpand: () => setState(() => _quizExpanded = !_quizExpanded),
            onRemind: _toggleQuizRemind,
            onOpen: () => _save({
              'prefs': {'quiz_open': _prefs['quiz_open'] == false},
            }),
          ),
          // Вечерняя сводка на завтра (evening_digest.py, Никита 12.10) — только при
          // новом дизайне: при DESIGN2=0 сервер не отдаёт ключ, а приложение — design2.
          if (s.design2 && _prefs.containsKey('evening'))
            _Card(
              icon: Icons.bedtime_outlined,
              title: 'Вечерняя сводка',
              sub: 'Пары и сроки на завтра · ${_eveningTime()}',
              switchKey: 'evening',
              on: _prefs['evening'] == true,
              onChanged: () => _toggle('evening'),
              children: [_EveningTime(value: _eveningTime(), onPick: _setEvening, onCustom: _customEvening)],
            ),
        ],
      ],
    );
  }

  bool _quizExpanded = false;

  void _toggleQuizRemind(int m) {
    final list = [for (final x in (_prefs['quiz_remind'] as List? ?? const [])) x as int];
    list.contains(m) ? list.remove(m) : list.add(m);
    list.sort((a, b) => b.compareTo(a));
    _save({
      'prefs': {'quiz_remind': list},
    });
  }

  int _soonHours() => _prefs['deadline_soon_hours'] as int? ?? 3;

  String _eveningTime() => _prefs['evening_time'] as String? ?? '20:00';

  void _setEvening(String t) => _save({
    'prefs': {'evening_time': t},
  });

  /// «Своё» время: часы — от 17 до 23, минуты — округлим до получаса (сервер
  /// проверяет раз в 30 минут и другое не примет).
  Future<void> _customEvening() async {
    final cur = _eveningTime().split(':');
    final got = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: int.tryParse(cur.first) ?? 20, minute: int.tryParse(cur.last) ?? 0),
      helpText: 'Во сколько прислать сводку',
    );
    if (got == null || !mounted) return;
    _setEvening(eveningSlot(got.hour, got.minute));
  }
}

/// За сколько минут до закрытия теста можно напомнить (как quiz_choices сервера).
const quizChoices = [1440, 180, 60, 30, 10];

String quizLabel(int m) => m >= 1440 ? '1 день' : minText(m);

/// «за 1 день и 10 мин до закрытия · когда откроют» — под заголовком пункта.
String quizSummary(List<int> remind, bool open) {
  final names = [
    for (final m in [...remind]..sort((a, b) => b.compareTo(a))) quizLabel(m),
  ];
  final parts = [
    if (names.length == 1) 'за ${names.first} до закрытия',
    if (names.length > 1) 'за ${names.sublist(0, names.length - 1).join(', ')} и ${names.last} до закрытия',
    if (open) 'когда откроют',
  ];
  return parts.isEmpty ? 'выключено' : parts.join(' · ');
}

/// «Тесты СДО»: по нажатию раскрывается — плашки «за сколько до закрытия»
/// (несколько) и переключатель «Тест открылся».
class _QuizCard extends StatelessWidget {
  final List<int> choices, remind;
  final bool open, expanded;
  final VoidCallback onExpand, onOpen;
  final ValueChanged<int> onRemind;
  const _QuizCard({
    required this.choices,
    required this.remind,
    required this.open,
    required this.expanded,
    required this.onExpand,
    required this.onOpen,
    required this.onRemind,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final on = remind.isNotEmpty || open;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
      child: Tile(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            InkWell(
              key: const Key('notify:quiz'),
              onTap: onExpand,
              borderRadius: BorderRadius.circular(Radii.chip),
              child: Row(
                children: [
                  Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      color: p.accent.withValues(alpha: on ? 0.16 : 0.06),
                      borderRadius: BorderRadius.circular(Radii.chip),
                    ),
                    child: Icon(Icons.timer_outlined, size: 20, color: on ? p.accent : p.muted),
                  ),
                  const SizedBox(width: Space.m),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Тесты СДО',
                          style: s.body(16, weight: FontWeight.w600, color: on ? p.text : p.muted),
                        ),
                        Text(quizSummary(remind, open), style: s.body(13, color: p.muted)),
                      ],
                    ),
                  ),
                  AnimatedRotation(
                    turns: expanded ? 0.25 : 0,
                    duration: const Duration(milliseconds: 200),
                    child: Icon(Icons.chevron_right_rounded, color: p.muted),
                  ),
                ],
              ),
            ),
            if (expanded) ...[
              const SizedBox(height: Space.m),
              Text(
                'Напомнить до закрытия · можно несколько',
                style: s.body(13, weight: FontWeight.w600, color: p.muted),
              ),
              const SizedBox(height: Space.xs),
              Wrap(
                spacing: Space.xs,
                runSpacing: Space.xs,
                children: [
                  for (final m in choices)
                    _Pill(
                      key: Key('quiz:$m'),
                      text: quizLabel(m),
                      on: remind.contains(m),
                      onTap: () => onRemind(m),
                      color: p.accent,
                      wide: true,
                    ),
                ],
              ),
              Padding(
                padding: const EdgeInsets.only(top: Space.s),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Тест открылся', style: s.body(15, weight: FontWeight.w500)),
                          Text('напишу, когда преподаватель откроет тест', style: s.body(12, color: p.muted)),
                        ],
                      ),
                    ),
                    AppSwitch(key: const Key('notify:quiz_open'), value: open, onChanged: onOpen),
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

/// Время сводки из любого: до получаса, в пределах 17:00–23:30.
String eveningSlot(int hour, int minute) {
  var m = hour * 60 + ((minute + 15) ~/ 30) * 30;
  m = m.clamp(17 * 60, 23 * 60 + 30);
  String two(int x) => x.toString().padLeft(2, '0');
  return '${two(m ~/ 60)}:${two(m % 60)}';
}

/// Время вечерней сводки: частые — плашками, «своё» — часы.
/// «Срок скоро»: за сколько часов до срока (как deadline_soon_choices сервера).
const soonChoices = [1, 3, 6, 12, 24];

String soonLabel(int h) => h >= 24 ? '1 день' : '$h ч';

class _SoonHours extends StatelessWidget {
  final List<int> choices;
  final int value;
  final ValueChanged<int> onPick;
  const _SoonHours({required this.choices, required this.value, required this.onPick});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    return Wrap(
      spacing: Space.xs,
      runSpacing: Space.xs,
      children: [
        for (final h in choices)
          _Pill(key: Key('soon:$h'), text: soonLabel(h), on: value == h, onTap: () => onPick(h), color: p.accent, wide: true),
      ],
    );
  }
}

class _EveningTime extends StatelessWidget {
  static const presets = ['19:00', '20:00', '21:00', '22:00'];
  final String value;
  final ValueChanged<String> onPick;
  final VoidCallback onCustom;
  const _EveningTime({required this.value, required this.onPick, required this.onCustom});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    final own = !presets.contains(value);
    Widget chip(String text, bool on, VoidCallback tap) =>
        _Pill(key: Key('evening:$text'), text: text, on: on, onTap: tap, color: p.accent, wide: true);
    return Wrap(
      spacing: Space.xs,
      runSpacing: Space.xs,
      children: [
        for (final t in presets) chip(t, value == t, () => onPick(t)),
        chip(own ? value : 'своё', own, onCustom),
      ],
    );
  }
}

/// Переключатель в цветах темы; ключ — для тестов («notify:weather»).
class AppSwitch extends StatelessWidget {
  final bool value;
  final VoidCallback onChanged;
  const AppSwitch({super.key, required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final p = AppStyle.of(context).p;
    return Switch(
      value: value,
      onChanged: (_) => onChanged(),
      activeTrackColor: p.accent,
      activeThumbColor: p.onAccent,
      inactiveTrackColor: p.line,
      inactiveThumbColor: p.muted,
      trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
    );
  }
}

/// Карточка вида уведомлений: значок, что и когда, выключатель; включена — настройки ниже.
class _Card extends StatelessWidget {
  final IconData? icon;
  final String title, sub, switchKey;
  final bool on;
  final VoidCallback onChanged;
  final List<Widget> children;
  const _Card({
    this.icon,
    required this.title,
    required this.sub,
    required this.switchKey,
    required this.on,
    required this.onChanged,
    this.children = const [],
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
      child: Tile(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (icon != null) ...[
                  Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      color: p.accent.withValues(alpha: on ? 0.16 : 0.06),
                      borderRadius: BorderRadius.circular(Radii.chip),
                    ),
                    child: Icon(icon, size: 20, color: on ? p.accent : p.muted),
                  ),
                  const SizedBox(width: Space.m),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: s.body(16, weight: FontWeight.w600, color: on ? p.text : p.muted),
                      ),
                      Text(sub, style: s.body(13, color: p.muted)),
                    ],
                  ),
                ),
                AppSwitch(key: Key('notify:$switchKey'), value: on, onChanged: onChanged),
              ],
            ),
            if (on && children.isNotEmpty) ...[const SizedBox(height: Space.m), ...children],
          ],
        ),
      ),
    );
  }
}

/// PWA: уведомления на этом устройстве (веб-пуш) и «Дублировать в Telegram»
/// (Никита 14.10: «нажал в PWA — и приходят от PWA, а не от TG»).
class _WebPushCard extends StatefulWidget {
  final Api api;
  final bool tgCopy;
  final VoidCallback onTgCopy;
  const _WebPushCard({required this.api, required this.tgCopy, required this.onTgCopy});

  @override
  State<_WebPushCard> createState() => _WebPushCardState();
}

class _WebPushCardState extends State<_WebPushCard> {
  String _state = '';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    webPushState().then((v) {
      if (mounted) setState(() => _state = v);
    });
  }

  Future<void> _switch() async {
    if (_busy) return;
    tick();
    setState(() => _busy = true);
    try {
      if (_state == 'on') {
        final endpoint = await webPushDisable();
        if (endpoint.isNotEmpty) await widget.api.post('/push/unsubscribe', {'endpoint': endpoint});
      } else {
        final key = (await widget.api.get('/push/key'))['key'] as String;
        final sub = await webPushEnable(key);
        if (sub.isNotEmpty) await widget.api.post('/push/subscribe', jsonDecode(sub));
      }
    } catch (e) {
      if (mounted) showToast(context, 'Не получилось: ${errorText(e)}', kind: ToastKind.error);
    }
    final v = await webPushState();
    if (mounted) {
      setState(() {
        _state = v;
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_state.isEmpty || _state == 'unsupported') return const SizedBox.shrink();
    final on = _state == 'on';
    final sub = switch (_state) {
      'on' => 'Включены — приходят на это устройство',
      'denied' => 'Запрещены в настройках браузера — разреши там, потом включи здесь',
      'install' => 'Добавь Капибару на экран «Домой» (Поделиться → На экран «Домой») и открой оттуда',
      _ => 'Включи — и уведомления придут сюда, как у приложения',
    };
    return _Card(
      icon: Icons.notifications_active_outlined,
      title: 'На этом устройстве',
      sub: sub,
      switchKey: 'push',
      on: on,
      onChanged: _state == 'install' || _state == 'denied' ? () {} : _switch,
      children: [
        _Row(
          title: 'Дублировать в Telegram',
          sub: widget.tgCopy ? 'приходят и сюда, и в Telegram' : 'только сюда; не дошло — тогда в Telegram',
          k: 'tg_copy',
          prefs: {'tg_copy': widget.tgCopy},
          onTap: (_) => widget.onTgCopy(),
        ),
      ],
    );
  }
}

/// Телефон: пуши своего приложения (app_push.dart). Текст уведомления
/// шифруется ключом этого телефона — Google, Apple и RuStore видят только шифр.
class _AppPushCard extends StatefulWidget {
  final Api api;
  final String state;
  final ValueChanged<String> onState;
  final bool tgCopy;
  final VoidCallback onTgCopy;
  const _AppPushCard({
    required this.api,
    required this.state,
    required this.onState,
    required this.tgCopy,
    required this.onTgCopy,
  });

  @override
  State<_AppPushCard> createState() => _AppPushCardState();
}

class _AppPushCardState extends State<_AppPushCard> {
  bool _busy = false;

  Future<void> _switch() async {
    if (_busy) return;
    tick();
    setState(() => _busy = true);
    var v = widget.state;
    try {
      v = widget.state == 'on' ? await AppPush.disable(widget.api) : await AppPush.enable(widget.api);
    } catch (e) {
      if (mounted) showToast(context, 'Не получилось: ${errorText(e)}', kind: ToastKind.error);
      v = await AppPush.state(widget.api);
    }
    if (!mounted) return;
    setState(() => _busy = false);
    widget.onState(v);
  }

  @override
  Widget build(BuildContext context) {
    final on = widget.state == 'on';
    return _Card(
      icon: Icons.notifications_active_outlined,
      title: 'На этом телефоне',
      sub: switch (widget.state) {
        'on' => 'Включены. Текст зашифрован — сервис доставки видит только шифр',
        'denied' => 'Запрещены в настройках телефона — разреши там, потом включи здесь',
        _ => 'Включи — и уведомления придут на телефон, текст зашифрован',
      },
      switchKey: 'app_push',
      on: on,
      onChanged: _switch,
      children: [
        if (on)
          _Row(
            title: 'Дублировать в Telegram',
            sub: widget.tgCopy ? 'приходят и сюда, и в Telegram' : 'только сюда; не дошло — тогда в Telegram',
            k: 'tg_copy',
            prefs: {'tg_copy': widget.tgCopy},
            onTap: (_) => widget.onTgCopy(),
          ),
      ],
    );
  }
}

/// Строка-выключатель внутри карточки: погода, корпус, «только если есть пары».
class _Row extends StatelessWidget {
  final String title, sub, k;
  final Map<String, dynamic> prefs;
  final ValueChanged<String> onTap;
  const _Row({required this.title, required this.sub, required this.k, required this.prefs, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: Space.s),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: s.body(15, weight: FontWeight.w500)),
                Text(sub, style: s.body(12, color: s.p.muted)),
              ],
            ),
          ),
          AppSwitch(key: Key('notify:$k'), value: prefs[k] == true, onChanged: () => onTap(k)),
        ],
      ),
    );
  }
}

/// Дни недели: Пн…Вс, выходные — приглушённее.
class _Days extends StatelessWidget {
  final List days;
  final String daysKey;
  final void Function(String key, int day) onTap;
  const _Days({required this.days, required this.daysKey, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Row(
      children: [
        for (var i = 0; i < 7; i++) ...[
          if (i > 0) const SizedBox(width: Space.xs),
          Expanded(
            child: _Pill(
              key: Key('days:$daysKey:$i'),
              text: weekdaysShort[i],
              on: days.contains(i),
              dim: i >= 5,
              onTap: () => onTap(daysKey, i),
              color: p.accent,
            ),
          ),
        ],
      ],
    );
  }
}

/// Напоминание по сценарию: «выкл», пресеты и «своё».
class _Remind extends StatelessWidget {
  final Map r;
  final int value;
  final ValueChanged<int> onPick;
  final VoidCallback onCustom;
  const _Remind({required this.r, required this.value, required this.onPick, required this.onCustom});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final presets = [for (final m in r['presets'] as List) m as int];
    final own = value > 0 && !presets.contains(value);
    Widget chip(String text, bool on, VoidCallback tap) =>
        _Pill(key: Key('remind:${r['key']}:$text'), text: text, on: on, onTap: tap, color: s.p.accent, wide: true);
    return Padding(
      padding: const EdgeInsets.only(top: Space.m),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            r['title'] as String,
            style: s.body(13, weight: FontWeight.w600, color: s.p.muted),
          ),
          const SizedBox(height: Space.xs),
          Wrap(
            spacing: Space.xs,
            runSpacing: Space.xs,
            children: [
              chip('выкл', value == 0, () => onPick(0)),
              for (final m in presets) chip(minText(m), value == m, () => onPick(m)),
              chip(own ? minText(value) : 'своё', own, onCustom),
            ],
          ),
        ],
      ),
    );
  }
}

/// «1 ч 30 мин», «5 мин».
String minText(int m) => [if (m ~/ 60 > 0) '${m ~/ 60} ч', if (m % 60 > 0) '${m % 60} мин'].join(' ');

class _Pill extends StatelessWidget {
  final String text;
  final bool on, dim, wide;
  final VoidCallback onTap;
  final Color color;
  const _Pill({
    super.key,
    required this.text,
    required this.on,
    required this.onTap,
    required this.color,
    this.dim = false,
    this.wide = false,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Material(
      // line в тёмной теме полупрозрачная: альфу только уменьшаем (было alpha: 1 —
      // невыбранные плашки становились белыми с белым текстом)
      color: on ? color : p.line.withValues(alpha: p.line.a * (dim ? 0.5 : 1)),
      borderRadius: BorderRadius.circular(Radii.chip),
      child: InkWell(
        borderRadius: BorderRadius.circular(Radii.chip),
        onTap: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: wide ? Space.m : 0, vertical: Space.s),
          child: Text(
            text,
            textAlign: TextAlign.center,
            style: s.body(13, weight: FontWeight.w600, color: on ? p.onAccent : (dim ? p.muted : p.text)),
          ),
        ),
      ),
    );
  }
}

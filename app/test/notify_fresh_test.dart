// Уведомления нового дизайна (шаг 8, макеты У1 и У2, Никита 11.11): лента
// того, что приходило, за колокольчиком на «Сегодня»; «Что присылать» — три
// набора, тихие часы и куда присылать; «Настроить самому» — прежний экран
// целиком, в нём добавились тихие часы. В «Классике» всё прежнее.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/app_push.dart';
import 'package:uiboshki/screens/notify_fresh.dart';
import 'package:uiboshki/screens/today.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'util.dart';

Widget _wrap(Widget child, {bool fresh = true}) => AppStyle(
  p: fresh ? Palette.paper : Palette.notebook,
  font: FontChoice.book,
  design2: true,
  look: Look(fresh: fresh),
  child: MaterialApp(home: child),
);

Map<String, Object?> _notify({String profile = 'important', bool quiet = true, bool copy = true}) => {
  'subscribed': true,
  'profile': profile,
  'quiet_hours': {'from': '23:00', 'to': '07:30'},
  'reminder_minutes': 15,
  'reminder_choices': [5, 10, 15, 30],
  'remind': [],
  'prefs': {
    'morning': profile == 'daily',
    'morning_days': [0, 1, 2, 3, 4, 5, 6],
    'weather': true,
    'campus': true,
    'skip_empty': false,
    'lessons': true,
    'lesson_days': [0, 1, 2, 3, 4, 5, 6],
    'deadlines': true,
    'deadline_days': [0, 1, 2, 3, 4, 5, 6],
    'weekly': profile == 'daily',
    'grades': true,
    'new_tasks': true,
    'quiz_remind': [],
    'quiz_open': true,
    'deadline_soon': true,
    'deadline_soon_hours': 3,
    'tg_copy': copy,
    'quiet': quiet,
  },
};

Map<String, Object?> _inbox() {
  final today = iso(now());
  final yesterday = iso(now().subtract(const Duration(days: 1)));
  return {
    'items': [
      {
        'id': 3,
        'kind': 'deadlines',
        'title': 'Сегодня срок: Лабораторная работа 3',
        'body': 'ООАиП · до 23:59, отметки о сдаче нет',
        'tab': 'deadlines',
        'at': '${today}T08:00:00+03:00',
        'quiet': false,
        'read': false,
      },
      {
        'id': 2,
        'kind': 'grades',
        'title': 'В СДО изменились баллы',
        'body': 'Анализ данных: 24 → 28',
        'tab': 'sdo',
        'at': '${today}T02:40:00+03:00',
        'quiet': true,
        'read': false,
      },
      {
        'id': 1,
        'kind': 'ugc',
        'title': 'Запись скрыта модератором',
        'body': 'Заметка от 6 октября',
        'tab': null,
        'at': '${yesterday}T11:30:00+03:00',
        'quiet': false,
        'read': true,
      },
    ],
    'unread': 2,
    'quiet': true,
    'keep_days': 30,
  };
}

void main() {
  setUpAll(loadFonts);
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('строка в «Ещё»: набор и тихие часы; старый сервер — как раньше', () {
    expect(freshNotifySummary(_notify()), 'только важное · тихо с 23:00');
    expect(freshNotifySummary(_notify(profile: 'daily', quiet: false)), 'помощь каждый день');
    expect(freshNotifySummary(_notify(profile: 'custom', quiet: false)), 'своя настройка');
    expect(freshNotifySummary({..._notify(), 'subscribed': false}), 'выключены');
    final old = Map<String, Object?>.from(_notify(profile: 'daily', quiet: false))..remove('profile');
    expect(freshNotifySummary(old), isNot(contains('помощь'))); // прежняя строка из включённых видов
  });

  test('лента: куда ведёт строка и заголовки дней', () {
    expect(inboxAction('deadlines'), 'Открыть «Сдать»');
    expect(inboxAction('sdo'), 'Открыть «Учёбу»');
    expect(inboxAction('more'), isNull);
    expect(inboxAction(null), isNull);
    final d = DateTime(2026, 10, 9, 13);
    expect(inboxDay('2026-10-09T08:00:00+03:00', d), 'Сегодня');
    expect(inboxDay('2026-10-08T23:10:00+03:00', d), 'Вчера');
    expect(inboxDay('2026-10-01T10:00:00+03:00', d), '1 октября');
  });

  testWidgets('лента: по дням, непрочитанное с точкой, открыл — прочитано, строка ведёт во вкладку', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(
      _wrap(
        InboxScreen(
          api: fakeApi(
            requests: asked,
            overrides: {
              'GET /api/inbox': _inbox(),
              'POST /api/inbox/read': {'read': 2},
            },
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Уведомления'), findsOneWidget);
    expect(find.text('Сегодня'), findsOneWidget);
    expect(find.text('Вчера'), findsOneWidget);
    expect(find.text('Сегодня срок: Лабораторная работа 3'), findsOneWidget);
    expect(find.text('Открыть «Сдать»'), findsOneWidget);
    expect(find.text('Открыть «Учёбу»'), findsOneWidget);
    expect(find.text('08:00'), findsOneWidget);
    expect(find.byIcon(Icons.bedtime_outlined), findsOneWidget); // пришло ночью, ждало здесь
    expect(asked, contains('POST /api/inbox/read'));
    await t.tap(find.byKey(const Key('inbox:3')));
    await settle(t);
    expect(AppPush.tab.value, 'deadlines');
    AppPush.tab.value = null;
  });

  testWidgets('лента пустая — капибара и что здесь будет', (t) async {
    phone(t);
    await t.pumpWidget(
      _wrap(
        InboxScreen(
          api: fakeApi(
            overrides: {
              'GET /api/inbox': {'items': [], 'unread': 0, 'quiet': false, 'keep_days': 30},
            },
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.byKey(const Key('inbox:empty')), findsOneWidget);
    expect(find.text('Пока пусто'), findsOneWidget);
  });

  testWidgets('«Что присылать»: набор одним нажатием, тихие часы, куда присылать', (t) async {
    phone(t);
    final asked = <String>[];
    final bodies = <String, Object?>{};
    await t.pumpWidget(
      _wrap(
        NotifyHome(
          api: fakeApi(
            requests: asked,
            bodies: bodies,
            overrides: {
              'GET /api/notify': _notify(quiet: false),
              'POST /api/notify': _notify(profile: 'daily', quiet: false),
            },
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Что присылать'), findsOneWidget);
    Icon? check(String k) => t
        .widgetList<Icon>(find.descendant(of: find.byKey(Key('notify:profile:$k')), matching: find.byType(Icon)))
        .where((i) => i.icon == Icons.check_circle_rounded)
        .firstOrNull;
    expect(check('important'), isNotNull);
    expect(check('daily'), isNull);
    expect(find.text('23:00 – 07:30, по Москве'), findsOneWidget);

    await t.tap(find.byKey(const Key('notify:profile:daily')));
    await settle(t);
    expect(bodies['POST /api/notify'], {'profile': 'daily'});
    expect(check('daily'), isNotNull);

    await t.tap(find.descendant(of: find.byKey(const Key('notify:quiet')), matching: find.byType(Switch)));
    await settle(t);
    expect(bodies['POST /api/notify'], {
      'prefs': {'quiet': true},
    });

    await t.tap(find.byKey(const Key('notify:where')));
    await settle(t);
    await t.tap(find.byKey(const Key('notify:where:push')));
    await settle(t);
    expect(bodies['POST /api/notify'], {
      'prefs': {'tg_copy': false},
    });
  });

  testWidgets('«Настроить самому» — прежний экран, в нём тихие часы', (t) async {
    phone(t);
    await t.pumpWidget(
      _wrap(
        NotifyHome(
          api: fakeApi(overrides: {'GET /api/notify': _notify(profile: 'custom')}),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Сейчас своя настройка. Каждый вид отдельно'), findsOneWidget);
    await t.tap(find.byKey(const Key('notify:profile:custom')));
    await settle(t);
    expect(find.text('Тихие часы'), findsOneWidget);
    expect(find.text('Утреннее расписание'), findsOneWidget);
  });

  testWidgets('«Сегодня»: колокольчик с точкой открывает ленту; в «Классике» его нет', (t) async {
    phone(t);
    final today = Map<String, Object?>.from(demoFixtures()['GET /api/today'] as Map)..['inbox_unread'] = 2;
    final api = fakeApi(overrides: {'GET /api/today': today, 'GET /api/inbox': _inbox()});
    await t.pumpWidget(
      _wrap(
        Scaffold(
          body: SafeArea(child: TodayScreen(api: api)),
        ),
      ),
    );
    await settle(t);
    expect(find.byKey(const Key('today:bell')), findsOneWidget);
    expect(find.byKey(const Key('today:bell:dot')), findsOneWidget);
    await t.tap(find.byKey(const Key('today:bell')));
    await settle(t);
    expect(find.byType(InboxScreen), findsOneWidget);

    await t.pumpWidget(
      _wrap(
        Scaffold(
          body: SafeArea(child: TodayScreen(api: api)),
        ),
        fresh: false,
      ),
    );
    await settle(t);
    expect(find.byKey(const Key('today:bell')), findsNothing);
  });
}

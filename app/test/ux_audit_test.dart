// Правки по UX-аудиту 02.11 (Никита 11.11): «Посмотреть демо» на первом
// выборе группы; смена группы из «Ещё» — с подтверждением (п. 30); есть
// просроченное — не радуемся «сроков нет» (п. 9); время не указано — «до
// конца дня», а не «23:59» (п. 10); черновик — без прыжка и с кнопкой
// «Открыть задание в СДО» — в submit_test.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/deadline_edit.dart';
import 'package:uiboshki/screens/deadlines.dart';
import 'package:uiboshki/screens/group_pick.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/capy.dart';

import 'fake_api.dart';
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  design2: true,
  child: MaterialApp(home: Scaffold(body: child)),
);

final at = DateTime(2026, 10, 9, 13, 5);

Widget view(List<Deadline> items) => host(
  DeadlinesView(
    items: items,
    extra: {for (final d in items) d.id: DlExtra.fromJson(const {})},
    api: fakeApi(),
    at: at,
    sdo: SdoCheck.fromJson(const {
      'ok': true,
      'checked_at': '2026-10-09T12:40:00+03:00',
      'last_ok': '2026-10-09T12:40:00+03:00',
    }),
    onToggle: (_, _) async {},
    onSubmit: (_) {},
    onOpen: (_) {},
    onAdd: () {},
  ),
);

void main() {
  testWidgets('первый выбор группы: «Посмотреть демо» открывает пример на сайте', (t) async {
    phone(t);
    final opened = <Uri>[];
    final was = GroupPickScreen.openUrl;
    GroupPickScreen.openUrl = (u) async {
      opened.add(u);
      return true;
    };
    addTearDown(() => GroupPickScreen.openUrl = was);
    await t.pumpWidget(host(GroupPickScreen(api: fakeApi(), required: true)));
    await settle(t);
    await t.tap(find.byKey(const Key('group:demo')));
    expect(opened.single.path, '/about/demo');
    // из «Ещё» (группа уже есть) — кнопки нет
    await t.pumpWidget(host(GroupPickScreen(key: UniqueKey(), api: fakeApi())));
    await settle(t);
    expect(find.byKey(const Key('group:demo')), findsNothing);
  });

  testWidgets('смена группы из «Ещё» — сначала вопрос, без «Сменить» ничего не уходит', (t) async {
    phone(t);
    final asked = <String>[];
    final api = fakeApi(
      requests: asked,
      overrides: {
        'GET /api/me': {
          'id': 222,
          'group': {'id': 4928, 'name': 'УИБО-03-24', 'own': true},
        },
      },
    );
    await t.pumpWidget(host(GroupPickScreen(api: api)));
    await settle(t);
    await t.enterText(find.byType(EditableText).first, 'уибо-01');
    await settle(t);
    await t.tap(find.text('УИБО-01-24'));
    await settle(t);
    expect(find.text('Сменить группу на УИБО-01-24?'), findsOneWidget);
    expect(asked, isNot(contains('POST /api/me/group')));
    await t.tap(find.text('Отмена'));
    await settle(t);
    expect(asked, isNot(contains('POST /api/me/group')));
    await t.tap(find.text('УИБО-01-24'));
    await settle(t);
    await t.tap(find.text('Сменить'));
    await settle(t);
    expect(asked, contains('POST /api/me/group'));
  });

  testWidgets('впереди пусто, но есть просроченное — без радостного «сроков нет»', (t) async {
    phone(t);
    final late = Deadline(id: 1, subject: 'Кейс 1 · Анализ данных', dueDate: '2026-10-07', dueTime: '18:00');
    await t.pumpWidget(view([late]));
    await settle(t);
    expect(find.text('Впереди сроков нет'), findsOneWidget);
    expect(find.text('Ближайших сроков нет'), findsNothing);
    expect(find.textContaining('с прошедшим сроком: 1'), findsOneWidget);
    expect(find.byWidgetPredicate((w) => w is CapyImage && w.pose == CapyPose.joy), findsNothing);
  });

  testWidgets('время срока не указано — «до конца дня», а не «23:59»', (t) async {
    phone(t);
    final d = Deadline(id: 2, subject: 'Реферат · Философия', dueDate: '2026-10-14', dueTime: '');
    await t.pumpWidget(view([d]));
    await settle(t);
    expect(find.textContaining('до конца дня'), findsOneWidget);
    expect(find.textContaining('23:59'), findsNothing);
  });
}

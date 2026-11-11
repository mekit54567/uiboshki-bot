// «Пусто и ошибка» (дизайн 5.80, Никита выбрал А, Б, В): пусто и сбой
// выглядят по-разному. «Сдать» без сроков — радостная капибара и «СДО
// проверено в 12:40»; СДО не ответил — грустная, «Показываю сроки от 09:41»
// и «Проверить СДО» (только перечитать экран). «Учёба» без входа в
// СДО — польза, а не ошибка. Выключен новый дизайн — всё как было.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/deadline_edit.dart';
import 'package:uiboshki/screens/deadlines.dart';
import 'package:uiboshki/screens/study.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/capy.dart';

import 'fake_api.dart';
import 'util.dart';

const list = 'GET /api/deadlines?include_done=true';

Widget host(Widget child, {bool design2 = true}) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  design2: design2,
  child: MaterialApp(home: Scaffold(body: child)),
);

/// Пятница 9 октября, 13:05 по Москве.
final at = DateTime(2026, 10, 9, 13, 5);

const ok = {'ok': true, 'checked_at': '2026-10-09T12:40:00+03:00', 'last_ok': '2026-10-09T12:40:00+03:00'};
const down = {'ok': false, 'checked_at': '2026-10-09T12:40:00+03:00', 'last_ok': '2026-10-09T09:41:07+03:00'};

Deadline dl(int id, DateTime due, String subject) =>
    Deadline(id: id, subject: subject, dueDate: iso(due), dueTime: '18:00');

Widget view(List<Deadline> items, Map<String, Object?>? sdo, {bool design2 = true, VoidCallback? onRetry}) => host(
  DeadlinesView(
    items: items,
    extra: {for (final d in items) d.id: DlExtra.fromJson(const {})},
    api: fakeApi(),
    at: at,
    sdo: SdoCheck.fromJson(sdo),
    onRetry: onRetry,
    onToggle: (_, _) async {},
    onSubmit: (_) {},
    onOpen: (_) {},
    onAdd: () {},
  ),
  design2: design2,
);

bool hasCapy(WidgetTester t, CapyPose pose) => find
    .byWidgetPredicate((w) => (w is CapyImage && w.pose == pose) || (w is CapyPeek && w.pose == pose))
    .evaluate()
    .isNotEmpty;

/// «Учёба»: баллы закрыты ответом [problem], статус входа — [state].
Api studyApi(String problem, String state) => Api(
  client: MockClient((req) async {
    final (code, body) = switch (req.url.path) {
      '/api/v1/sdo/grades' => (403, {'detail': problem}),
      '/api/v1/sdo/status' => (200, {'state': state}),
      _ => (200, {'ok': true}),
    };
    return http.Response.bytes(utf8.encode(jsonEncode(body)), code, headers: {'content-type': 'application/json'});
  }),
)..token = 't';

void main() {
  test('подписи времени: сегодня, вчера, раньше — по Москве', () {
    final t = DateTime.parse('2026-10-09T12:40:00+03:00');
    expect(sdoCheckedText(t, at), 'СДО проверено в 12:40');
    expect(sdoCheckedText(DateTime.parse('2026-10-08T09:30:00Z'), at), 'СДО проверено вчера в 12:30');
    expect(sdoCheckedText(DateTime.parse('2026-10-06T23:10:00+03:00'), at), 'СДО проверено 6 октября в 23:10');
    expect(sdoShownText(DateTime.parse('2026-10-09T09:41:07+03:00'), at), 'Показываю сроки от 09:41');
    expect(sdoShownText(DateTime.parse('2026-10-08T21:00:00+03:00'), at), 'Показываю сроки от вчера, 21:00');
    expect(sdoShownText(null, at), 'Новые сроки пока не подтянулись');
    expect(SdoCheck.fromJson(null), isNull);
    expect(SdoCheck.fromJson({'ok': null}), isNull);
  });

  testWidgets('А: сроков нет — радостная капибара и «СДО проверено в 12:40»', (t) async {
    phone(t);
    await t.pumpWidget(view([], ok));
    await settle(t);
    expect(find.text('Ближайших сроков нет'), findsOneWidget);
    expect(find.text('СДО проверено в 12:40'), findsOneWidget);
    expect(hasCapy(t, CapyPose.joy), isTrue);
    expect(find.text('Проверить СДО'), findsNothing);
  });

  testWidgets('А: группа без СДО — без строки о проверке', (t) async {
    phone(t);
    await t.pumpWidget(view([], null));
    await settle(t);
    expect(find.text('Ближайших сроков нет'), findsOneWidget);
    expect(find.textContaining('СДО проверено'), findsNothing);
  });

  testWidgets('Б: СДО не ответил, сроков нет — грустная капибара и «Проверить СДО»', (t) async {
    phone(t);
    var retried = 0;
    await t.pumpWidget(view([], down, onRetry: () => retried++));
    await settle(t);
    expect(find.text('СДО не ответил'), findsOneWidget);
    expect(find.text('Показываю сроки от 09:41'), findsOneWidget);
    expect(find.text('Ближайших сроков нет'), findsNothing);
    expect(hasCapy(t, CapyPose.sad), isTrue);
    expect(hasCapy(t, CapyPose.joy), isFalse);
    await t.tap(find.text('Проверить СДО'));
    expect(retried, 1);
  });

  testWidgets('Б: сроки есть — строка над списком, список на месте', (t) async {
    phone(t);
    final items = [dl(1, DateTime(2026, 10, 14), 'Кейс 1 · Анализ данных')];
    await t.pumpWidget(view(items, down, onRetry: () {}));
    await settle(t);
    expect(find.text('СДО не ответил'), findsOneWidget);
    expect(find.text('Кейс 1'), findsOneWidget);
    expect(t.getTopLeft(find.text('СДО не ответил')).dy, lessThan(t.getTopLeft(find.text('Кейс 1')).dy));
    expect(find.text('Проверить СДО'), findsOneWidget);
    // СДО ответил — строки нет
    await t.pumpWidget(view(items, ok));
    await settle(t);
    expect(find.text('СДО не ответил'), findsNothing);
    expect(find.textContaining('СДО проверено'), findsNothing);
  });

  testWidgets('новый дизайн выключен — как было', (t) async {
    phone(t);
    await t.pumpWidget(view([], down, design2: false));
    await settle(t);
    expect(find.text('Всё сдано'), findsOneWidget);
    expect(find.text('СДО не ответил'), findsNothing);
    await t.pumpWidget(view([dl(1, DateTime(2026, 10, 14), 'Кейс 1 · Анализ данных')], down, design2: false));
    await settle(t);
    expect(find.text('СДО не ответил'), findsNothing);
  });

  testWidgets('«Проверить СДО» зовёт синк и перечитывает сроки', (t) async {
    phone(t);
    final asked = <String>[];
    final api = fakeApi(
      requests: asked,
      overrides: {
        list: {'items': [], 'stats': {}, 'sdo': down},
      },
    );
    await t.pumpWidget(host(DeadlinesScreen(api: api)));
    await settle(t);
    expect(find.text('СДО не ответил'), findsOneWidget);
    asked.clear();
    await t.tap(find.text('Проверить СДО'));
    await settle(t);
    // сначала просим сервер заново спросить СДО, потом перечитываем (UX-аудит, п. 7)
    expect(asked, ['POST /api/sdo/recheck', list]);
    expect(find.text('СДО всё ещё молчит — проверю его сам чуть позже'), findsOneWidget);
    await t.pump(const Duration(seconds: 5));
  });

  testWidgets('В: «Учёба» без входа в СДО — польза, а не ошибка', (t) async {
    phone(t);
    await t.pumpWidget(host(StudyScreen(api: studyApi('сначала подключи СДО: вкладка СДО → Вход', 'off'))));
    await settle(t);
    expect(find.text('Подключи СДО'), findsOneWidget);
    expect(find.text('Баллы, посещения и сдача работ появятся здесь'), findsOneWidget);
    expect(find.text('Сначала подключи СДО'), findsNothing);
    expect(hasCapy(t, CapyPose.sad), isFalse);
    final btn = find.text('Подключить');
    await t.scrollUntilVisible(btn, 200, scrollable: find.byType(Scrollable).first);
    await t.tap(btn);
    await settle(t);
    expect(find.text('Вход в СДО'), findsOneWidget);
  });

  testWidgets('В: вход устарел — по-прежнему «Подключить заново»; без нового дизайна — как было', (t) async {
    phone(t);
    await t.pumpWidget(
      host(StudyScreen(api: studyApi('вход в СДО устарел — подключи заново: вкладка СДО → Вход', 'expired'))),
    );
    await settle(t);
    expect(find.text('Подключить заново'), findsOneWidget);
    expect(find.text('Подключи СДО'), findsNothing);

    await t.pumpWidget(const SizedBox()); // новый экран — новая загрузка
    await t.pumpWidget(
      host(StudyScreen(api: studyApi('сначала подключи СДО: вкладка СДО → Вход', 'off')), design2: false),
    );
    await settle(t);
    expect(find.text('Сначала подключи СДО'), findsOneWidget);
    expect(find.text('Подключить СДО'), findsOneWidget);
  });

  testWidgets('узкий экран, крупный шрифт — без переполнений', (t) async {
    t.view.devicePixelRatio = 2;
    t.view.physicalSize = const Size(640, 1136);
    t.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(t.view.reset);
    addTearDown(t.platformDispatcher.clearTextScaleFactorTestValue);
    final items = [dl(1, DateTime(2026, 10, 14), 'Практическая работа 5-6 · Анализ данных и бизнес-процессов')];
    for (final w in [
      view(items, down, onRetry: () {}),
      view([], down, onRetry: () {}),
      view([], ok),
      host(StudyScreen(api: studyApi('сначала подключи СДО: вкладка СДО → Вход', 'off'))),
    ]) {
      await t.pumpWidget(const SizedBox());
      await t.pumpWidget(w);
      await settle(t);
      expect(t.takeException(), isNull);
    }
  });
}

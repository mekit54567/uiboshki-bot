// Записи людей (правило Apple 1.2, 5.99): «⋯» → «Пожаловаться» с причиной или
// «Скрыть автора»; расписание без входа (5.1.1(v)) — через /api/v1/guest/….
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/guest.dart';
import 'package:uiboshki/screens/login.dart';
import 'package:uiboshki/screens/search.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/report.dart';

import 'fake_api.dart';

Widget _wrap(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(
    home: Scaffold(body: Center(child: child)),
  ),
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  testWidgets('пожаловаться: причина уходит на сервер', (t) async {
    final bodies = <String, Object?>{};
    await t.pumpWidget(
      _wrap(
        ReportButton(
          api: fakeApi(bodies: bodies),
          kind: 'note',
          id: 5,
        ),
      ),
    );
    await t.tap(find.byKey(const Key('report:note:5')));
    await t.pumpAndSettle();
    expect(find.text('Правила Капибары'), findsOneWidget);
    await t.tap(find.byKey(const Key('reason:Спам или реклама')));
    for (var i = 0; i < 5; i++) {
      await t.pump(const Duration(milliseconds: 100)); // плашка живёт пару секунд — не ждём, пока уйдёт
    }
    expect(bodies['POST /api/report'], {'kind': 'note', 'id': 5, 'reason': 'Спам или реклама'});
    expect(find.textContaining('Посмотрим и уберём'), findsOneWidget);
    await t.pump(const Duration(seconds: 5));
  });

  testWidgets('скрыть автора: после подтверждения и только тогда', (t) async {
    final bodies = <String, Object?>{};
    var changed = 0;
    await t.pumpWidget(
      _wrap(
        ReportButton(
          api: fakeApi(bodies: bodies),
          kind: 'hw',
          id: 9,
          onChanged: () => changed++,
        ),
      ),
    );
    await t.tap(find.byKey(const Key('report:hw:9')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('report:hide')));
    await t.pumpAndSettle();
    expect(find.text('Скрыть автора?'), findsOneWidget);
    expect(bodies, isEmpty);
    await t.tap(find.text('Скрыть'));
    await t.pumpAndSettle();
    expect(bodies['POST /api/hide-author'], {'kind': 'hw', 'id': 9});
    expect(changed, 1);
    await t.pump(const Duration(seconds: 5));
  });

  test('без входа: поиск и расписание — через /guest, остальное закрыто', () async {
    final asked = <String>[];
    final api = GuestApi(
      client: MockClient((req) async {
        asked.add(req.url.path + (req.url.query.isEmpty ? '' : '?${req.url.query}'));
        expect(req.headers['Authorization'], isNull);
        return http.Response.bytes(utf8.encode(jsonEncode({'items': [], 'weeks': []})), 200);
      }),
    );
    await api.get('/search?q=уибо&type=0');
    await api.get('/target/1/7');
    expect(asked.first, startsWith('/api/v1/guest/search?q='));
    expect(asked.last, '/api/v1/guest/target/1/7');
    expect(await api.get('/pins'), {'items': []});
    expect(api.get('/me'), throwsA(isA<Exception>()));
  });

  testWidgets('на входе — «Расписание без входа»', (t) async {
    await t.pumpWidget(
      AppStyle(
        p: Palette.depth,
        font: FontChoice.book,
        child: MaterialApp(
          home: LoginScreen(api: fakeApi(token: null), onDone: () {}),
        ),
      ),
    );
    await t.pumpAndSettle();
    await t.ensureVisible(find.byKey(const Key('login-guest')));
    await t.tap(find.byKey(const Key('login-guest')));
    await t.pumpAndSettle();
    expect(find.byType(SearchScreen), findsOneWidget);
  });
}

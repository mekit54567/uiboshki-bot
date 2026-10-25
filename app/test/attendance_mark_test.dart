// Своя отметка посещений в приложении (Никита 25.10: «поставить, на каких
// лекциях был, можно только в Telegram»): лист «Посещения» с экрана предмета.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/goal_card.dart';

import 'fake_api.dart';
import 'util.dart';

Map<String, dynamic> _att(List<Map<String, dynamic>> lectures, {int leftOk = 1}) => {
  'ok': true,
  'score': 5,
  'max': 20,
  'unit': 2.5,
  'total': lectures.length,
  'past': 3,
  'attended': 2,
  'waiting': 0,
  'lectures': lectures,
  'before': {'day': '2026-09-20', 'past': 2, 'attended': 1, 'excused': 0, 'left_ok': leftOk, 'left_excused': 0},
};

void main() {
  testWidgets('«?» у лекции до начала истории — нажал, и она «был»', (t) async {
    phone(t);
    final requests = <String>[];
    final bodies = <String, Object?>{};
    const key = 'POST /api/sdo/attendance/7';
    final before = _att([
      {'date': '2026-09-06', 'n': 1, 'status': 'before', 'manual': false},
      {'date': '2026-09-13', 'n': 2, 'status': 'before', 'manual': false},
      {'date': '2026-09-27', 'n': 3, 'status': 'ok', 'manual': false},
      {'date': '2026-10-04', 'n': 4, 'status': 'future', 'manual': false},
    ]);
    final after = _att([
      {'date': '2026-09-06', 'n': 1, 'status': 'ok', 'manual': true},
      {'date': '2026-09-13', 'n': 2, 'status': 'miss', 'manual': false},
      {'date': '2026-09-27', 'n': 3, 'status': 'ok', 'manual': false},
      {'date': '2026-10-04', 'n': 4, 'status': 'future', 'manual': false},
    ], leftOk: 0);
    final api = fakeApi(requests: requests, bodies: bodies, overrides: {key: after});
    await t.pumpWidget(
      AppStyle(
        p: Palette.notebook,
        font: FontChoice.book,
        child: MaterialApp(
          home: Scaffold(
            body: AttendanceStrip(att: before, color: Colors.orange, api: api, courseId: 7),
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.textContaining('отметь сам, на каких был до 20 сентября'), findsOneWidget);
    await t.tap(find.byType(AttendanceStrip));
    await settle(t);
    expect(find.text('Посещения'), findsOneWidget);
    expect(find.textContaining('6 сентября · отметь сам'), findsOneWidget);
    await t.tap(find.text('Лекция 1'));
    await settle(t);
    expect(requests, contains(key));
    expect(bodies[key], {'day': '2026-09-06', 'mark': 'ok'});
    expect(find.textContaining('6 сентября · был · твоя отметка'), findsOneWidget);
    // плюсики кончились: остальные «Н» до начала истории — тоже можно поправить
    expect(find.textContaining('Всё отмечено'), findsOneWidget);
  });

  testWidgets('без api — просто квадратики, без перехода', (t) async {
    phone(t);
    await t.pumpWidget(
      AppStyle(
        p: Palette.notebook,
        font: FontChoice.book,
        child: MaterialApp(
          home: Scaffold(
            body: AttendanceStrip(
              att: _att([
                {'date': '2026-09-06', 'n': 1, 'status': 'ok', 'manual': false},
              ]),
              color: Colors.orange,
            ),
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.textContaining('все лекции'), findsNothing);
    expect(find.textContaining('отметь сам'), findsNothing);
  });
}

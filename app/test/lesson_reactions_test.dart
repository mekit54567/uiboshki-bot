// Реакции на пару (5.100): блок «Как пара» с четырьмя капибарами — счёт
// группы, своя отмечена, повторное нажатие снимает; в чужом расписании нет.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/lesson.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

final _lesson = Lesson(
  start: '10:40',
  end: '12:10',
  title: 'Анализ данных',
  kind: 'лекция',
  room: 'А-223 (В-78)',
  teacher: '',
  status: '',
  startAt: DateTime.utc(2026, 10, 18, 7, 40),
  endAt: DateTime.utc(2026, 10, 18, 9, 10),
);

String get _getKey =>
    'GET /api/lesson/reactions?${Uri(queryParameters: {'start': '2026-10-18T07:40:00.000Z', 'title': 'Анализ данных'}).query}';

Map<String, Object?> _state(Map<String, int> counts, String? mine, {bool open = true}) => {
  'counts': {'joy': 0, 'calm': 0, 'hard': 0, 'sleep': 0, ...counts},
  'mine': mine,
  'open': open,
};

Future<void> _open(WidgetTester t, api, {bool own = true}) async {
  await t.pumpWidget(
    AppStyle(
      p: Palette.depth,
      font: FontChoice.strict,
      child: MaterialApp(
        home: LessonScreen(api: api, lesson: _lesson, own: own),
      ),
    ),
  );
  await settle(t);
}

void main() {
  testWidgets('счёт группы и своя реакция; нажал ещё раз — снял', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    final asked = <String>[];
    final overrides = <String, Object?>{
      _getKey: _state({'joy': 3, 'sleep': 1}, null),
      'POST /api/lesson/reactions': _state({'joy': 3, 'hard': 1, 'sleep': 1}, 'hard'),
    };
    final api = fakeApi(requests: asked, bodies: bodies, overrides: overrides);
    await _open(t, api);
    expect(find.text('Как пара'), findsOneWidget);
    expect(find.text('Видит только твоя группа, без имён'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    // пятая — злая капибара (5.100.6), подпись в одну строку
    expect(find.byKey(const ValueKey('reaction-angry')), findsOneWidget);
    expect(find.text('Злой препод'), findsOneWidget);

    await t.ensureVisible(find.text('Сложно'));
    await t.tap(find.text('Сложно'));
    await settle(t);
    expect(bodies['POST /api/lesson/reactions'], {
      'start': '2026-10-18T07:40:00.000Z',
      'title': 'Анализ данных',
      'kind': 'hard',
    });
    final hard = t.widget<Semantics>(
      find.descendant(of: find.byKey(const ValueKey('reaction-hard')), matching: find.byType(Semantics)).first,
    );
    expect(hard.properties.selected, isTrue);

    overrides['POST /api/lesson/reactions'] = _state({'joy': 3, 'sleep': 1}, null);
    await t.tap(find.text('Сложно'));
    await settle(t);
    expect((bodies['POST /api/lesson/reactions'] as Map)['kind'], '');
  });

  testWidgets('до начала пары блока нет', (t) async {
    phone(t);
    final api = fakeApi(overrides: {_getKey: _state({}, null, open: false)});
    await _open(t, api);
    expect(find.text('Как пара'), findsNothing);
  });

  testWidgets('в чужом расписании реакций нет и сервер не спрашиваем', (t) async {
    phone(t);
    final asked = <String>[];
    final api = fakeApi(
      requests: asked,
      overrides: {
        _getKey: _state({'joy': 2}, null),
      },
    );
    await _open(t, api, own: false);
    expect(find.text('Как пара'), findsNothing);
    expect(asked.any((k) => k.contains('/lesson/reactions')), isFalse);
  });
}

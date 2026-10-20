// Экран пары (Никита 19.10): обсуждение — два последних и кнопка, всё и поле
// ввода — листом; долгое нажатие на чужое — жалоба/скрыть, на своё — удалить. Оценка
// преподавателя — ряд капибар под именем, лист с пятью капибарами и эмоцией.
// В чужом расписании (поиск) — ни того, ни другого. Данные выдуманные.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/lesson.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/teacher_rating.dart';

import 'fake_api.dart';
import 'util.dart';

final _lesson = Lesson(
  start: '10:40',
  end: '12:10',
  title: 'Анализ данных',
  kind: 'лекция',
  room: 'А-223 (В-78)',
  teacher: 'Сиганьков А. А.',
  status: '',
  startAt: DateTime.utc(2026, 10, 18, 7, 40),
  endAt: DateTime.utc(2026, 10, 18, 9, 10),
);

final _q = Uri(queryParameters: {'start': '2026-10-18T07:40:00.000Z', 'title': 'Анализ данных'}).query;
final _comments = 'GET /api/lesson/comments?$_q';
final _rating = 'GET /api/teacher/rating?${Uri(queryParameters: {'name': 'Сиганьков А. А.'}).query}';

Map<String, Object?> _list(List<Map<String, Object?>> items, {bool open = true}) => {
  'items': items,
  'open': open,
  'max': 500,
};

const _egor = {
  'id': 1,
  'text': 'Пару перенесли в А-17',
  'created_at': '2026-10-18 06:12:00',
  'author': 'Егор К.',
  'mine': false,
};
const _me = {
  'id': 2,
  'text': 'Сказал, что на следующей',
  'created_at': '2026-10-18 06:24:00',
  'author': 'Аня С.',
  'mine': true,
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
  testWidgets('на экране — два последних и кнопка; всё обсуждение и ввод — листом', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    const masha = {
      'id': 3,
      'text': 'А тест будет?',
      'created_at': '2026-10-18 06:20:00',
      'author': 'Маша С.',
      'mine': false,
    };
    final api = fakeApi(
      bodies: bodies,
      overrides: {
        _comments: _list([_egor, masha, _me]),
        'POST /api/lesson/comments': {
          'ok': true,
          'id': 4,
          ..._list([
            _egor,
            masha,
            _me,
            {'id': 4, 'text': 'Ок', 'created_at': '2026-10-18 06:30:00', 'author': 'Аня С.', 'mine': true},
          ]),
        },
        _rating: {'count': 0, 'avg': null, 'mine': null, 'show_min': 3, 'can_rate': false},
      },
    );
    await _open(t, api);
    await t.drag(find.byType(ListView), const Offset(0, -600));
    await settle(t);
    expect(find.text('Обсуждение группы · 3'), findsOneWidget);
    expect(find.text('Пару перенесли в А-17'), findsNothing); // старое — только в листе
    expect(find.text('А тест будет?'), findsOneWidget);
    expect(find.text('Сказал, что на следующей'), findsOneWidget);
    expect(find.byKey(const Key('comment:input')), findsNothing); // поля на экране нет

    await t.tap(find.byKey(const Key('comments:open')));
    await settle(t);
    expect(find.text('Обсуждение пары'), findsOneWidget);
    expect(find.text('Пару перенесли в А-17'), findsOneWidget);
    await t.enterText(find.byKey(const Key('comment:input')), '  Ок ');
    await t.tap(find.byKey(const Key('comment:send')));
    await settle(t);
    expect(bodies['POST /api/lesson/comments'], {
      'start': '2026-10-18T07:40:00.000Z',
      'title': 'Анализ данных',
      'text': 'Ок',
    });
    expect(find.text('Ок'), findsOneWidget);

    await t.longPress(find.byKey(const Key('sheet:comment:1')));
    await settle(t);
    expect(find.text('Пожаловаться'), findsWidgets); // лист жалобы (report.dart)
  });

  testWidgets('пусто, но открыто — «Написать группе» открывает лист с полем', (t) async {
    phone(t);
    await _open(
      t,
      fakeApi(
        overrides: {
          _comments: _list([]),
          _rating: {'count': 0, 'avg': null, 'mine': null, 'show_min': 3, 'can_rate': false},
        },
      ),
    );
    await t.drag(find.byType(ListView), const Offset(0, -600));
    await settle(t);
    expect(find.text('Написать группе'), findsOneWidget);
    await t.tap(find.byKey(const Key('comments:open')));
    await settle(t);
    expect(find.byKey(const Key('comment:input')), findsOneWidget);
  });

  testWidgets('закрыто и пусто — блока нет; в чужом расписании — не спрашивает', (t) async {
    phone(t);
    final asked = <String>[];
    await _open(t, fakeApi(requests: asked, overrides: {_comments: _list([], open: false)}));
    expect(find.textContaining('Обсуждение группы'), findsNothing);

    asked.clear();
    await _open(t, fakeApi(requests: asked), own: false);
    expect(asked.where((k) => k.contains('/lesson/comments') || k.contains('/teacher/rating')), isEmpty);
  });

  testWidgets('оценка: ряд капибар под именем, лист — эмоция и «Готово»', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    final api = fakeApi(
      bodies: bodies,
      overrides: {
        _comments: _list([], open: false),
        _rating: {'count': 12, 'avg': 4.5, 'mine': null, 'show_min': 3, 'can_rate': true},
        'POST /api/teacher/rating': {'count': 13, 'avg': 4.5, 'mine': 4, 'show_min': 3, 'can_rate': true},
      },
    );
    await _open(t, api);
    expect(find.text('4,5 · 12 оценок'), findsOneWidget);
    await t.tap(find.byKey(const Key('teacher:rating')));
    await settle(t);
    expect(find.byType(RateSheet), findsOneWidget);
    expect(find.text('Нажми на капибару'), findsOneWidget);
    await t.tap(find.byKey(const Key('rate:4')));
    await settle(t);
    expect(find.text('4 из 5'), findsOneWidget);
    expect(find.text('довольна'), findsOneWidget);
    expect(find.byKey(const Key('rate:clear')), findsNothing); // своей ещё нет
    await t.tap(find.byKey(const Key('rate:done')));
    await settle(t);
    expect(bodies['POST /api/teacher/rating'], {'name': 'Сиганьков А. А.', 'score': 4});
    expect(find.byType(RateSheet), findsNothing);
    expect(find.text('4,5 · 13 оценок'), findsOneWidget);
  });

  testWidgets('мало оценок — «оцени первым»; нельзя и мало — строки нет', (t) async {
    phone(t);
    await _open(
      t,
      fakeApi(
        overrides: {
          _comments: _list([], open: false),
          _rating: {'count': 1, 'avg': null, 'mine': null, 'show_min': 3, 'can_rate': true},
        },
      ),
    );
    expect(find.text('оцени первым'), findsOneWidget);
    await t.pumpWidget(const SizedBox()); // новый экран, а не тот же State
    await _open(
      t,
      fakeApi(
        overrides: {
          _comments: _list([], open: false),
          _rating: {'count': 1, 'avg': null, 'mine': null, 'show_min': 3, 'can_rate': false},
        },
      ),
    );
    expect(find.byKey(const Key('teacher:rating')), findsNothing);
    expect(find.text('все пары преподавателя'), findsOneWidget);
  });
}

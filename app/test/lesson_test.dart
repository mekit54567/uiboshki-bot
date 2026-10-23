import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/lesson.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

void main() {
  test('один и тот же предмет в журнале и в файлах', () {
    expect(sameSubject('Анализ данных', 'анализ данных'), isTrue);
    expect(sameSubject('Учетная деятельность на предприятии', 'Учётная деятельность на предприятии'), isTrue);
    expect(sameSubject('Анализ данных', 'Архитектура предприятия'), isFalse);
  });

  test('этаж по номеру аудитории — как на табличках', () {
    expect(roomFloor('А-223'), '2 этаж');
    expect(roomFloor('ИВЦ-102'), '1 этаж');
    expect(roomFloor('Г-103-1'), '1 этаж');
    expect(roomFloor('426'), '4 этаж');
    expect(roomFloor('А-046а'), 'цокольный этаж');
    expect(roomFloor('А-17'), ''); // большие аудитории без этажа в номере
    expect(roomFloor('1212'), '');
    expect(roomFloor('Спортзал'), '');
  });

  testWidgets('пара: где, кто, поток, баллы и лекции; все пары преподавателя', (t) async {
    phone(t);
    final asked = <String>[];
    final api = fakeApi(
      requests: asked,
      overrides: {
        'GET /api/search?q=%D0%A1%D0%B8%D0%B3%D0%B0%D0%BD%D1%8C%D0%BA%D0%BE%D0%B2+%D0%90.+%D0%90.&type=2&subject=%D0%9C%D0%BE%D0%B4%D0%B5%D0%BB%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5+%D0%B1%D0%B8%D0%B7%D0%BD%D0%B5%D1%81-%D0%BF%D1%80%D0%BE%D1%86%D0%B5%D1%81%D1%81%D0%BE%D0%B2': {
          'items': [
            {'type': 2, 'id': 77, 'title': 'Сиганьков А. А.'},
          ],
        },
        'GET /api/target/2/77': {
          'title': 'Сиганьков А. А.',
          'weeks': [
            {
              'days': [
                {
                  'date': '2099-01-05',
                  'lessons': [
                    {
                      'start': '09:00',
                      'end': '10:30',
                      'title': 'Моделирование бизнес-процессов',
                      'kind': 'лекция',
                      'room': 'А-17 (В-78)',
                      'groups': 'УИБО-01-24, УИБО-02-24',
                    },
                  ],
                },
              ],
            },
          ],
        },
      },
    );
    const lesson = Lesson(
      start: '09:00',
      end: '10:30',
      title: 'Моделирование бизнес-процессов',
      kind: 'лекция',
      room: 'А-17 (В-78)',
      teacher: 'Сиганьков А. А.',
      status: '',
      groups: 'УИБО-01-24, УИБО-02-24, УИБО-03-24',
    );
    await t.pumpWidget(
      AppStyle(
        p: Palette.depth,
        font: FontChoice.strict,
        child: MaterialApp(
          home: LessonScreen(api: api, lesson: lesson),
        ),
      ),
    );
    await settle(t);
    expect(find.text('А-17'), findsOneWidget);
    expect(find.text('корпус В-78 · расписание аудитории'), findsOneWidget);
    expect(find.text('Поток · 3 группы'), findsOneWidget);
    expect(find.text('Баллы БРС'), findsOneWidget); // предмет нашёлся в журнале
    expect(find.text('до «5» ещё 16'), findsOneWidget);

    await t.tap(find.text('Сиганьков А. А.'));
    await settle(t);
    expect(asked.any((k) => k.startsWith('GET /api/target/2/77')), isTrue);
    expect(find.text('преподаватель'), findsNothing); // без курсивной подписи над именем (2.4)
    expect(find.textContaining('УИБО-01-24, УИБО-02-24'), findsOneWidget); // чьи это пары
  });

  testWidgets('этаж — в строке аудитории, корпус не дублируется', (t) async {
    phone(t);
    final api = fakeApi();
    for (final (room, text) in [
      ('А-223 (В-78)', '2 этаж · корпус В-78 · расписание аудитории'),
      ('426', '4 этаж · расписание аудитории'),
      ('Спортзал', 'аудитория · её расписание'),
    ]) {
      await t.pumpWidget(
        AppStyle(
          p: Palette.depth,
          font: FontChoice.strict,
          child: MaterialApp(
            home: LessonScreen(
              key: UniqueKey(),
              api: api,
              lesson: Lesson(
                start: '09:00',
                end: '10:30',
                title: 'Анализ данных',
                kind: '',
                room: room,
                teacher: '',
                status: '',
              ),
            ),
          ),
        ),
      );
      await settle(t);
      expect(find.text(text), findsOneWidget, reason: room);
    }
  });

  testWidgets('2.18: карточка пары спрашивает баллы и файлы по одному разу', (t) async {
    phone(t);
    final asked = <String>[];
    final api = fakeApi(requests: asked);
    const lesson = Lesson(
      start: '09:00',
      end: '10:30',
      title: 'Моделирование бизнес-процессов',
      kind: 'лекция',
      room: 'А-17 (В-78)',
      teacher: '',
      status: '',
    );
    final font = ValueNotifier(FontChoice.strict);
    await t.pumpWidget(
      ValueListenableBuilder<FontChoice>(
        valueListenable: font,
        builder: (_, f, _) => AppStyle(
          p: Palette.depth,
          font: f,
          child: MaterialApp(
            home: Builder(
              builder: (context) =>
                  TextButton(onPressed: () => openLesson(context, api, lesson), child: const Text('пара')),
            ),
          ),
        ),
      ),
    );
    await t.tap(find.text('пара'));
    await settle(t);
    // перерисовка (смена шрифта, темы) не повторяет запросы
    font.value = FontChoice.book;
    await settle(t);
    font.value = FontChoice.strict;
    await settle(t);
    expect(find.text('Баллы БРС'), findsOneWidget);
    expect(asked.where((k) => k == 'GET /api/sdo/grades').length, 1);
    expect(asked.where((k) => k == 'GET /api/files').length, 1);
  });

  testWidgets('с кем пара: другие группы в той же аудитории (Никита 12.10)', (t) async {
    phone(t);
    final asked = <String>[];
    final at = DateTime.utc(2099, 1, 5, 6);
    String key(String room, String teacher) =>
        'GET /api/lesson/groups?${Uri(queryParameters: {'start': at.toIso8601String(), 'room': room, 'teacher': teacher}).query}';
    Lesson lesson(String room, {String teacher = 'Стебунова О. И.', String groups = ''}) => Lesson(
      start: '09:00',
      end: '10:30',
      title: 'Анализ данных',
      kind: 'лекция',
      room: room,
      teacher: teacher,
      status: '',
      groups: groups,
      startAt: at,
      endAt: at.add(const Duration(minutes: 90)),
    );
    final api = fakeApi(
      requests: asked,
      overrides: {
        key('А-17 (В-78)', 'Стебунова О. И.'): {
          'groups': ['УИБО-01-24', 'УИБО-02-24'],
          'source': 'room',
        },
        key('Б-1 (В-78)', 'Стебунова О. И.'): {
          'groups': ['УИБО-01-24'],
          'source': 'room',
        },
      },
    );
    Future<void> open(Lesson l) async {
      await t.pumpWidget(
        AppStyle(
          p: Palette.notebook,
          font: FontChoice.strict,
          child: MaterialApp(
            home: LessonScreen(key: UniqueKey(), api: api, lesson: l),
          ),
        ),
      );
      await settle(t);
    }

    await open(lesson('А-17 (В-78)'));
    expect(find.text('Общая пара · ещё 2 группы'), findsOneWidget);
    expect(find.text('УИБО-01-24, УИБО-02-24'), findsOneWidget);

    await open(lesson('Б-1 (В-78)'));
    expect(find.text('Вместе с УИБО-01-24'), findsOneWidget);
    expect(find.text('общая пара · расписание группы'), findsOneWidget);

    // пара только своя (или МИРЭА молчит) — строки нет
    await open(lesson('В-2 (В-78)'));
    expect(find.textContaining('Общая пара'), findsNothing);
    expect(find.textContaining('Вместе с'), findsNothing);

    // поток уже известен из расписания — лишний раз не спрашиваем
    asked.clear();
    await open(lesson('А-17 (В-78)', groups: 'УИБО-01-24, УИБО-02-24'));
    expect(asked.any((k) => k.startsWith('GET /api/lesson/groups')), isFalse);
    expect(find.text('Поток · 2 группы'), findsOneWidget);
  });
}

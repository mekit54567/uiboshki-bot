// Новое по итогам проверки 09.10: заметки из приложения (2.9), помощник —
// [1] кнопками и сколько вопросов осталось (2.12), «Редактировать ответ» и
// «Удалить ответ» на задании СДО (3.3).
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/chat.dart';
import 'package:uiboshki/screens/homework.dart';
import 'package:uiboshki/screens/submit.dart';
import 'package:uiboshki/screens/task.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

String _iso(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  group('заметки', () {
    testWidgets('«+» → день, пара и текст → POST /api/notes, список заново', (t) async {
      phone(t);
      final asked = <String>[];
      final bodies = <String, Object?>{};
      final d = now();
      final tomorrow = _iso(DateTime(d.year, d.month, d.day + 1));
      final api = fakeApi(
        requests: asked,
        bodies: bodies,
        overrides: {
          'GET /api/day?date=$tomorrow': {
            'lessons': [
              {'title': 'Анализ данных', 'start': '09:00'},
            ],
          },
          'POST /api/notes': {'ok': true, 'id': 7},
        },
      );
      await t.pumpWidget(host(NotesScreen(api: api)));
      await settle(t);
      expect(find.textContaining('кнопкой «+»'), findsOneWidget); // в бота больше не отсылаем
      expect(find.textContaining('/note'), findsNothing);
      await t.tap(find.byKey(const Key('notes:add')));
      await settle(t);
      expect(find.text('Новая заметка'), findsOneWidget);
      expect(find.textContaining('Это не личная заметка'), findsOneWidget); // уйдёт всей группе — сказано прямо
      await t.tap(find.text('Анализ данных')); // пара завтрашнего дня
      await settle(t);
      await t.enterText(find.byKey(const Key('note:text')), 'контрольная в 401');
      await t.ensureVisible(find.text('Показать всей группе'));
      await t.tap(find.text('Показать всей группе'));
      await settle(t);
      expect(bodies['POST /api/notes'], {'date': tomorrow, 'subject': 'Анализ данных', 'text': 'контрольная в 401'});
      expect(find.text('Новая заметка'), findsNothing);
      expect(find.byType(AppToast), findsOneWidget);
      expect(asked.where((r) => r.startsWith('GET /api/notes')).length, 4); // два дня, и ещё раз после «+»
    });

    testWidgets('пустой текст не уходит', (t) async {
      phone(t);
      final asked = <String>[];
      await t.pumpWidget(host(NotesScreen(api: fakeApi(requests: asked))));
      await settle(t);
      await t.tap(find.byKey(const Key('notes:add')));
      await settle(t);
      await t.ensureVisible(find.text('Показать всей группе'));
      await t.tap(find.text('Показать всей группе'));
      await settle(t);
      expect(find.text('Напиши, что запомнить'), findsOneWidget);
      expect(asked, isNot(contains('POST /api/notes')));
    });

    testWidgets('свою заметку можно убрать', (t) async {
      phone(t);
      final asked = <String>[];
      final d = now();
      final today = _iso(DateTime(d.year, d.month, d.day));
      final api = fakeApi(
        requests: asked,
        overrides: {
          'GET /api/notes?date=$today': {
            'items': [
              {'id': 5, 'subject': '', 'text': 'моя', 'mine': true},
              {'id': 6, 'subject': '', 'text': 'чужая', 'mine': false},
            ],
          },
        },
      );
      await t.pumpWidget(host(NotesScreen(api: api)));
      await settle(t);
      expect(find.byTooltip('Убрать заметку'), findsOneWidget); // только у своей
      await t.tap(find.byTooltip('Убрать заметку'));
      await settle(t);
      await t.tap(find.text('Убрать'));
      await settle(t);
      expect(asked, contains('DELETE /api/notes/5'));
    });
  });

  group('помощник', () {
    testWidgets('на пустом экране — что умеет и сколько вопросов осталось', (t) async {
      phone(t);
      final api = fakeApi(
        overrides: {
          'GET /api/subjects': {
            'subjects': [],
            'quota': {'left': 7, 'limit': 10},
          },
        },
      );
      await t.pumpWidget(host(ChatScreen(api: api)));
      await settle(t);
      expect(find.textContaining('Отвечает по лекциям твоей группы'), findsOneWidget);
      expect(find.text('Сегодня можно ещё 7 вопросов'), findsOneWidget);
    });

    testWidgets('без лимита (староста) — числа нет', (t) async {
      phone(t);
      final api = fakeApi(
        overrides: {
          'GET /api/subjects': {'subjects': [], 'quota': null},
        },
      );
      await t.pumpWidget(host(ChatScreen(api: api)));
      await settle(t);
      expect(find.textContaining('Отвечает по лекциям'), findsOneWidget);
      expect(find.textContaining('Сегодня можно'), findsNothing);
    });

    testWidgets('[1] в ответе — кнопка к странице лекции', (t) async {
      phone(t);
      final asked = <String>[];
      await t.pumpWidget(host(ChatScreen(api: fakeApi(requests: asked))));
      await settle(t);
      await t.enterText(find.byType(TextField), 'Чем метрика отличается от KPI?');
      await t.tap(find.byTooltip('Отправить'));
      await settle(t);
      expect(find.byKey(const Key('cite:1')), findsNWidgets(2)); // «[1]» дважды в ответе
      expect(find.byKey(const Key('cite:2')), findsOneWidget);
      await t.tap(find.byKey(const Key('cite:2')));
      await settle(t);
      expect(asked, contains('GET /api/files/4/page/5'));
    });
  });

  group('ответ на задание', () {
    final task = {
      'title': 'Практическая работа №5',
      'status': 'Отправлено для оценивания',
      'can_submit': true,
      'can_edit': true,
      'can_remove': true,
      'files': [],
      'mine': [
        {'name': 'old.docx', 'dl': '/sdl/x/old.docx'},
      ],
      'limit': 3,
      'url': 'https://online-edu.mirea.ru/mod/assign/view.php?id=4242',
    };
    const work = {'name': 'Практическая работа №5', 'module': 'assign', 'cmid': 4242, 'status': 'wait'};

    testWidgets('«Удалить ответ» — подтверждение, потом запрос', (t) async {
      phone(t);
      final asked = <String>[];
      final bodies = <String, Object?>{};
      final api = fakeApi(
        requests: asked,
        bodies: bodies,
        overrides: {
          'GET /api/sdo/task/4242': task,
          'POST /api/sdo/submission/remove': {'status': 'Ответы на задание еще не представлены'},
        },
      );
      await t.pumpWidget(host(TaskScreen(api: api, work: work)));
      await settle(t);
      expect(find.text('Сдать ещё / заменить'), findsNothing);
      await t.scrollUntilVisible(find.text('Удалить ответ'), 200, scrollable: find.byType(Scrollable).first);
      await t.tap(find.text('Удалить ответ'));
      await settle(t);
      expect(find.text('Удалить ответ?'), findsOneWidget);
      await t.tap(find.text('Отмена'));
      await settle(t);
      expect(asked, isNot(contains('POST /api/sdo/submission/remove')));
      await t.tap(find.text('Удалить ответ'));
      await settle(t);
      await t.tap(find.text('Удалить ответ').last);
      await settle(t);
      expect(bodies['POST /api/sdo/submission/remove'], {'cmid': 4242});
      expect(find.text('Ответ удалён'), findsOneWidget);
      expect(asked.where((r) => r == 'GET /api/sdo/task/4242').length, 2); // задание заново
    });

    testWidgets('«Редактировать ответ» — лист сдачи заменяет файлы', (t) async {
      phone(t);
      final bodies = <String, Object?>{};
      final api = fakeApi(bodies: bodies, overrides: {'GET /api/sdo/task/4242': task});
      Future<List<Picked>> pick(List<String> accepted) async => [
        (name: 'new.zip', bytes: Uint8List.fromList([1, 2, 3])),
      ];
      await t.pumpWidget(host(TaskScreen(api: api, work: work, pick: pick)));
      await settle(t);
      await t.scrollUntilVisible(find.text('Редактировать ответ'), 200, scrollable: find.byType(Scrollable).first);
      await t.tap(find.text('Редактировать ответ'));
      await settle(t);
      expect(find.text('Новые файлы заменят прежние'), findsOneWidget);
      await t.tap(find.text('Выбрать файл'));
      await settle(t);
      await t.tap(find.text('Заменить'));
      await settle(t);
      final body = bodies['POST /api/sdo/submit'] as Map;
      expect(body['replace'], isTrue);
      expect((body['files'] as List).single['name'], 'new.zip');
    });

    testWidgets('ответа нет или оценён — кнопок нет', (t) async {
      phone(t);
      final api = fakeApi(
        overrides: {
          'GET /api/sdo/task/4242': {...task, 'can_edit': false, 'can_remove': false, 'mine': []},
        },
      );
      await t.pumpWidget(host(TaskScreen(api: api, work: work)));
      await settle(t);
      expect(find.text('Редактировать ответ'), findsNothing);
      expect(find.text('Удалить ответ'), findsNothing);
      await t.scrollUntilVisible(find.textContaining('Сдать работу'), 200, scrollable: find.byType(Scrollable).first);
      expect(find.textContaining('Сдать работу'), findsOneWidget);
    });
  });
}

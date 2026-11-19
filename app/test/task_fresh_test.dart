// Карточка задания нового вида (Никита 18.11): из «Сдать» — полноценная
// страница, а не лист снизу; всё как в СДО (сроки, баллы, состояние ответа,
// комментарии), сдача прямо здесь — прикрепил, видишь файл, комментарий,
// «Отправить»; «Отметить», «Изменить», «Удалить» — тоже здесь.
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/deadline_edit.dart';
import 'package:uiboshki/screens/task.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';

import 'fake_api.dart';
import 'util.dart';

final _at = DateTime(2026, 11, 19, 1, 17);
const _link = 'https://online-edu.mirea.ru/mod/assign/view.php?id=4242';

final _dl = Deadline(
  id: 7,
  subject: 'Аудиторная контрольная работа №3 · Анализ данных (Экз)',
  dueDate: '2026-11-26',
  dueTime: '00:00',
  canSubmit: true,
);
final _x = DlExtra.fromJson({'description': _link, 'can_edit': true, 'edit_scope': 'me'});

final _task = {
  'title': 'Аудиторная контрольная работа №3',
  'opened': 'понедельник, 9 ноября 2026, 00:00',
  'due': 'четверг, 26 ноября 2026, 00:00',
  'description': 'Письменная работа по темам 5, 6.',
  'status': 'Ответы на задание еще не представлены',
  'grading': 'Не оценено',
  'max_grade': 15.0,
  'pass': 5.0,
  'remaining': '6 дн. 22 час. осталось',
  'modified': '',
  'files': [
    {'name': 'Варианты.pdf', 'dl': '/sdl/t/v.pdf'},
  ],
  'mine': [],
  'can_submit': true,
  'can_edit': false,
  'can_remove': false,
  'url': _link,
  'comments': {'count': 0, 'items': [], 'can_post': true},
};

Widget _host(Widget child) => AppStyle(
  p: Palette.paper,
  font: FontChoice.book,
  design2: true,
  look: const Look(fresh: true),
  child: MaterialApp(home: child),
);

void main() {
  test('дата СДО, ссылка на задание и работа из срока', () {
    expect(sdoDate('четверг, 26 ноября 2026, 00:00'), DateTime(2026, 11, 26));
    expect(sdoDate('вторник, 10 ноября 2026, 21:14'), DateTime(2026, 11, 10, 21, 14));
    expect(sdoDate('-'), isNull);
    expect(taskDay(DateTime(2026, 11, 26)), 'чт, 26 ноября, 00:00');
    expect(taskOfLink(_link), (cmid: 4242, module: 'assign'));
    expect(taskOfLink('https://online-edu.mirea.ru/mod/quiz/view.php?id=5'), (cmid: 5, module: 'quiz'));
    expect(taskOfLink('заметка'), isNull);
    expect(workOfDeadline(_dl, _link), {
      'name': 'Аудиторная контрольная работа №3',
      'cmid': 4242,
      'module': 'assign',
      'url': _link,
    });
    expect(splitCourse(_dl.subject), 'Анализ данных');
  });

  testWidgets('страница задания: срок, баллы, задание; прикрепил файл, комментарий, «Отправить»', (t) async {
    phone(t);
    final asked = <String>[];
    final bodies = <String, Object?>{};
    final acts = <String>[];
    final api = fakeApi(
      requests: asked,
      bodies: bodies,
      overrides: {
        'GET /api/sdo/task/4242': _task,
        'GET /api/sdo/submit-rules?cmid=4242&deadline_id=7': {
          'accepted': ['.pdf', '.docx'],
          'labels': ['PDF', 'Word'],
          'maxfiles': 3,
          'maxbytes': 10485760,
        },
        'POST /api/sdo/submit': {'status': 'Отправлено для оценивания', 'state': 'submitted', 'comment': 'ok'},
      },
    );
    await t.pumpWidget(
      _host(
        TaskScreen(
          api: api,
          work: workOfDeadline(_dl, _x.description),
          deadline: _dl,
          extra: _x,
          at: _at,
          pick: (_) async => [
            (name: 'kr3.pdf', bytes: Uint8List.fromList(List.filled(2048, 1))),
            (name: 'фото.heic', bytes: Uint8List.fromList([1, 2, 3])),
          ],
          onDeadline: (a, d, x) async {
            acts.add('${a?.name}');
            return (d: d, x: x);
          },
        ),
      ),
    );
    await settle(t);
    expect(find.byKey(const ValueKey('task:fresh')), findsOneWidget);
    expect(asked, contains('GET /api/sdo/task/4242'));
    // срок: отсчёт крупно и обе даты
    expect(find.text('Осталось'), findsOneWidget);
    expect(find.text('6'), findsOneWidget);
    expect(find.text('дн'), findsOneWidget);
    expect(find.text('пн, 9 ноября, 00:00'), findsOneWidget);
    expect(find.text('чт, 26 ноября, 00:00'), findsOneWidget);
    // ответ и оценка: шкала с проходным, строки по-человечески
    expect(find.text('проходной 5'), findsOneWidget);
    expect(find.text('Ещё не сдано'), findsOneWidget);
    expect(find.text('Не оценено'), findsNothing); // ответа нет — строки «Оценка» нет (сверка UI 19.11)
    expect(find.byKey(const Key('task:comments')), findsNothing); // до сдачи комментарий — в форме ответа
    expect(find.text('Анализ данных'), findsOneWidget);

    await t.scrollUntilVisible(find.byKey(const Key('task:attach')), 200, scrollable: find.byType(Scrollable).first);
    expect(find.textContaining('Принимает: PDF, Word'), findsOneWidget);
    await t.tap(find.byKey(const Key('task:attach')));
    await settle(t);
    expect(find.text('kr3.pdf'), findsOneWidget);
    expect(find.text('2 КБ · подходит'), findsOneWidget);
    expect(find.textContaining('.heic задание не примет'), findsOneWidget);
    expect(find.text('Отправить 1 файл'), findsOneWidget);
    await t.enterText(find.byKey(const Key('task:submit:comment')), 'Скан работы во вложении');
    await t.scrollUntilVisible(find.byKey(const Key('task:send')), 200, scrollable: find.byType(Scrollable).first);
    await t.tap(find.byKey(const Key('task:send')));
    await settle(t);
    final body = bodies['POST /api/sdo/submit'] as Map;
    expect(body['cmid'], 4242);
    expect(body['deadline_id'], 7);
    expect(body['comment'], 'Скан работы во вложении');
    expect([for (final f in body['files'] as List) f['name']], ['kr3.pdf']); // неподходящий не уходит
    expect(find.text('Сдано'), findsWidgets);
    await t.tap(find.text('Отлично'));
    await settle(t);
    expect(acts, ['null']); // срок перечитан: сервер сам отметил его сданным
  });

  testWidgets('свой срок без СДО: без запросов в СДО, «Отметить», «Изменить», «Убрать у себя»', (t) async {
    phone(t);
    final asked = <String>[];
    final acts = <String>[];
    final mine = Deadline(id: 9, subject: 'Курсовая: глава 1 · Бизнес-анализ', dueDate: '2026-11-20', dueTime: '');
    final x = DlExtra.fromJson({'description': 'Принести распечатку', 'personal': true, 'can_edit': true});
    await t.pumpWidget(
      _host(
        Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => TaskScreen(
                      api: fakeApi(requests: asked),
                      work: workOfDeadline(mine, x.description),
                      deadline: mine,
                      extra: x,
                      at: _at,
                      onDeadline: (a, d, x) async {
                        acts.add('${a?.name}');
                        if (a == DlAction.delete) return null;
                        if (a == DlAction.done) {
                          return (
                            d: Deadline(id: d.id, subject: d.subject, dueDate: d.dueDate, dueTime: '', done: true),
                            x: x,
                          );
                        }
                        return (d: d, x: x);
                      },
                    ),
                  ),
                ),
                child: const Text('открыть'),
              ),
            ),
          ),
        ),
      ),
    );
    await t.tap(find.text('открыть'));
    await settle(t);
    expect(asked.where((r) => r.contains('/sdo/')), isEmpty);
    expect(find.text('Принести распечатку'), findsOneWidget);
    expect(find.text('Срок в Капибаре'), findsOneWidget);
    await t.scrollUntilVisible(
      find.byKey(const ValueKey('task:act:done')),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await t.tap(find.byKey(const ValueKey('task:act:done')));
    await settle(t);
    expect(acts, ['done']);
    expect(find.text('Вернуть в активные'), findsOneWidget); // страница взяла новый срок
    expect(find.text('Сдано'), findsOneWidget);
    await t.scrollUntilVisible(
      find.byKey(const ValueKey('task:act:delete')),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Убрать у себя'), findsOneWidget);
    await t.tap(find.byKey(const ValueKey('task:act:delete')));
    await settle(t);
    expect(acts, ['done', 'delete']);
    expect(find.text('открыть'), findsOneWidget); // срок убран — страница закрылась
  });

  testWidgets('ответ уже есть: свои файлы, «Заменить файлы», «Удалить ответ», комментарии', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    final api = fakeApi(
      bodies: bodies,
      overrides: {
        'GET /api/sdo/task/4242': {
          ..._task,
          'status': 'Отправлено для оценивания',
          'submitted': true,
          'modified': 'вторник, 17 ноября 2026, 21:14',
          'mine': [
            {'name': 'kr3.pdf', 'dl': '/sdl/t/k.pdf'},
          ],
          'can_edit': true,
          'can_remove': true,
          'comments': {
            'count': 1,
            'items': [
              {'author': 'Иванова Анна Петровна', 'time': 'среда, 18 ноября 2026, 10:05', 'text': 'Получила'},
            ],
            'can_post': true,
          },
        },
        'POST /api/sdo/task/4242/comment': {
          'count': 2,
          'items': [
            {'author': 'Иванова Анна Петровна', 'time': 'среда, 18 ноября 2026, 10:05', 'text': 'Получила'},
            {'author': 'Никита', 'time': 'сейчас', 'text': 'Спасибо!'},
          ],
          'can_post': true,
        },
      },
    );
    await t.pumpWidget(
      _host(
        TaskScreen(
          api: api,
          work: const {'cmid': 4242, 'module': 'assign', 'name': 'Аудиторная контрольная работа №3'},
          course: 'Анализ данных',
          at: _at,
        ),
      ),
    );
    await settle(t);
    expect(find.text('Сдано, ждёт оценки'), findsOneWidget);
    // вместо «до срока ещё…» — когда сдано
    expect((t.widget(find.byKey(const Key('task:sent-on'))) as Text).data, startsWith('вт, 17'));
    expect(find.text('ещё не проверено'), findsOneWidget);
    expect(find.text('вт, 17 ноября, 21:14'), findsOneWidget);
    expect(find.text('Срок в Капибаре'), findsNothing); // из «Учёбы» — без своих отметок срока
    await t.scrollUntilVisible(find.byKey(const Key('task:replace')), 200, scrollable: find.byType(Scrollable).first);
    expect(find.text('kr3.pdf'), findsOneWidget);
    expect(find.byKey(const Key('task:remove')), findsOneWidget);
    expect(find.byKey(const Key('task:form')), findsNothing);
    await t.ensureVisible(find.byKey(const Key('task:replace')));
    await settle(t);
    await t.tap(find.byKey(const Key('task:replace')));
    await settle(t);
    expect(find.byKey(const Key('task:form')), findsOneWidget);
    expect(find.byKey(const Key('task:submit:comment')), findsNothing); // одно поле — в комментариях ниже
    await t.scrollUntilVisible(find.byKey(const Key('task:comment')), 200, scrollable: find.byType(Scrollable).first);
    expect(find.text('Комментарии · 1'), findsOneWidget);
    expect(find.text('Получила'), findsOneWidget);
    await t.enterText(find.byKey(const Key('task:comment')), 'Спасибо!');
    await t.tap(find.byKey(const Key('task:comment:send')));
    await settle(t);
    expect(bodies['POST /api/sdo/task/4242/comment'], {'text': 'Спасибо!'});
    expect(find.text('Комментарии · 2'), findsOneWidget);
    expect(find.text('Спасибо!'), findsOneWidget);
  });

  testWidgets('в СДО уже сдано: «Отметить сданным» не предлагаем, отсчёта нет', (t) async {
    phone(t);
    final api = fakeApi(
      overrides: {
        'GET /api/sdo/task/4242': {
          ..._task,
          'submitted': true,
          'modified': 'вторник, 17 ноября 2026, 21:14',
          'mine': [
            {'name': 'kr3.pdf', 'dl': '/sdl/t/k.pdf'},
          ],
        },
      },
    );
    await t.pumpWidget(
      _host(
        TaskScreen(
          api: api,
          work: workOfDeadline(_dl, _x.description),
          deadline: _dl,
          extra: _x,
          at: _at,
          onDeadline: (a, d, x) async => (d: d, x: x),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Осталось'), findsNothing);
    await t.scrollUntilVisible(find.byKey(const Key('task:deadline')), 200, scrollable: find.byType(Scrollable).first);
    expect(find.text('Напомнить'), findsOneWidget);
    expect(find.text('Отметить сданным'), findsNothing);
  });

  testWidgets('без СДО: срок есть, вместо баллов — «Подключи СДО»', (t) async {
    phone(t);
    final api = Api(
      client: MockClient(
        (req) async => http.Response.bytes(
          utf8.encode(jsonEncode({'detail': 'подключи СДО, чтобы видеть свои баллы'})),
          403,
          headers: {'content-type': 'application/json'},
        ),
      ),
    )..token = 't';
    await t.pumpWidget(
      _host(
        TaskScreen(
          api: api,
          work: workOfDeadline(_dl, _x.description),
          deadline: _dl,
          extra: _x,
          at: _at,
          onDeadline: (a, d, x) async => (d: d, x: x),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Осталось'), findsOneWidget);
    expect(find.byKey(const Key('task:nosdo')), findsOneWidget);
    expect(find.text('Подключить СДО'), findsOneWidget);
    expect(find.text('Срок в Капибаре'), findsOneWidget); // отметки срока работают и без СДО
  });
}

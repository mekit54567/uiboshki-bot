import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/screens/study.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/goal_card.dart';

import 'fake_api.dart';
import 'util.dart';

void main() {
  test('числа и отметки по-русски', () {
    expect(fmtNum(12), '12');
    expect(fmtNum(2.5), '2,5');
    expect(markWord('зачёт'), 'зачёт');
    expect(markWord('4'), '«4»');
    expect(dayMonth('2026-08-27'), '27 августа'); // Б6: подсказка у лекции, не «2026-08-27»
    expect(dayMonth(''), '');
  });

  test('главная строка цели называет, что мешает (2.1, 2.19)', () {
    Map<String, dynamic> g(String label, num at, num need, {Map? tk, Map<String, dynamic> more = const {}}) => {
      'label': label,
      'at': at,
      'need': need,
      'status': 'ok',
      'tk': tk ?? {'left': 0},
      'exam_pending': true,
      'auto_ok': label != '5',
      ...more,
    };
    expect(goalHeadline(g('3', 40, 0, tk: {'left': 4})), 'Нужно зачесть ещё 4 работы');
    expect(goalHeadline(g('4', 60, 12)), 'Не хватает 12 баллов');
    expect(goalSubline(g('4', 60, 12, more: {'need_exam': 12})), 'для «4» нужно 60 баллов · или 12 баллов на экзамене');
    expect(goalHeadline(g('4', 60, 0, more: {'status': 'done', 'auto': '4'})), '«4» выходит автоматом');
    expect(
      goalHeadline(g('5', 80, 20, more: {'auto': '4', 'need_exam': 20})),
      '«4» автоматом, на «5» нужно 20 баллов на экзамене',
    );
    expect(
      goalHeadline(g('5', 80, 32, more: {'need_exam': 32, 'auto_best': '4'})),
      'На «5» нужно 32 балла на экзамене',
    );
    expect(
      goalSubline(g('5', 80, 32, more: {'need_exam': 32, 'auto_best': '4'})),
      'для «5» нужно 80 баллов · «4» можно получить автоматом',
    );
    expect(goalHeadline(g('5', 80, 52, more: {'need_exam': 40, 'exam_short': 12})), 'Не хватает 12 баллов');
    // зачёт: экзамена нет
    final credit = {...g('зачёт', 40, 0), 'exam_pending': false, 'status': 'done'};
    expect(goalHeadline(credit), 'Баллов хватает');
    expect(goalSubline(credit), 'для зачёта нужно 40 баллов');
  });

  test('счёт «автомат / с экзаменом» (14.10): «не хватает» — до порога целиком', () {
    // скрин владельца: 17,5 баллов, экзамен до 50; было «не хватает 12,5» до «5»
    Map<String, dynamic> g(String mode, String label, num at, num need, [Map<String, dynamic> more = const {}]) => {
      'mode': mode,
      'label': label,
      'at': at,
      'need': need,
      'status': 'ok',
      'tk': {'left': 3},
      'exam_pending': true,
      ...more,
    };
    expect(goalHeadline(g('auto', '4', 60, 42.5)), 'Не хватает 42,5 балла');
    expect(
      goalSubline(g('auto', '4', 60, 42.5)),
      'для «4» автоматом нужно 60 баллов за семестр и зачесть ещё 3 работы',
    );
    expect(goalHeadline(g('auto', '4', 60, 0, {'status': 'done'})), '«4» выходит автоматом');
    final exam = g('exam', '5', 80, 62.5, {'need_exam': 50, 'exam_short': 12.5});
    expect(goalHeadline(exam), 'Не хватает 62,5 балла');
    expect(
      goalSubline(exam),
      'для «5» нужно 80 баллов вместе с экзаменом · с полным экзаменом добрать ещё 12,5 работами и лекциями',
    );
    expect(
      goalSubline(g('exam', '5', 80, 20, {'need_exam': 20})),
      'для «5» нужно 80 баллов вместе с экзаменом · хватит 20 баллов на экзамене',
    );
    expect(
      goalHeadline(
        g('exam', '5', 80, 0, {
          'tk': {'left': 0},
        }),
      ),
      'Хватит любого балла на экзамене',
    );
  });

  testWidgets('предмет: цель, посещения, рост баллов; смена цели', (t) async {
    phone(t);
    final asked = <String>[];
    final api = fakeApi(requests: asked);
    final fx = demoFixtures();
    final course = Course.fromJson(Map<String, dynamic>.from(fx['GET /api/sdo/grades/18673']));
    await t.pumpWidget(
      AppStyle(
        p: Palette.notebook,
        font: FontChoice.book,
        child: MaterialApp(
          home: CourseScreen(api: api, course: course),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Цель'), findsOneWidget);
    expect(find.text('впритык'), findsOneWidget);
    // цель по умолчанию — «3»: баллов 48 из 40, но зачтена 1 работа из 6 — мешают работы, а не баллы
    expect(find.text('Нужно зачесть ещё 4 работы'), findsOneWidget);
    expect(find.text('по баллам уже набрано'), findsNothing);
    expect(find.text('для «3» нужно 40 баллов'), findsOneWidget);
    expect(find.textContaining('пропущу лекцию 8 октября'), findsOneWidget);

    await t.tap(find.bySemanticsLabel('Цель 4'));
    await settle(t);
    expect(asked, contains('POST /api/sdo/goal/18673|4'));
    expect(find.text('Не хватает 12 баллов'), findsOneWidget);
    await t.tap(find.bySemanticsLabel('Цель 5'));
    await settle(t);
    expect(find.text('На «5» нужно 32 балла на экзамене'), findsOneWidget); // «5» автоматом не бывает
    expect(find.text('для «5» нужно 80 баллов · «4» можно получить автоматом'), findsOneWidget);

    final list = find.byType(Scrollable).first;
    await t.scrollUntilVisible(find.textContaining('был на 3 из 6 прошедших'), 300, scrollable: list);
    await t.scrollUntilVisible(find.text('+8 за неделю'), 300, scrollable: list);
    await settle(t);
  });

  test('откуда посещения: Пульс или СДО', () {
    expect(attendanceSource({'source': 'pulse'}), 'из Пульса МИРЭА');
    expect(attendanceSource({'source': 'pulse_lost'}), contains('по СДО'));
    expect(attendanceSource({'source': 'sdo'}), isNull);
    expect(attendanceSource({}), isNull);
  });
}

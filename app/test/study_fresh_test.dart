// «Учёба» и экран предмета нового дизайна (вторая пачка макетов, Никита
// 11.11): только при «Новом» в «Оформлении»; в «Классике» экраны прежние.
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/chat.dart';
import 'package:uiboshki/screens/study.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/look.dart';
import 'package:uiboshki/widgets/goal_card.dart';

import 'fake_api.dart';
import 'util.dart';

Widget _wrap(Widget child, {bool fresh = true}) => AppStyle(
  p: fresh ? Palette.paper : Palette.notebook,
  font: FontChoice.book,
  design2: true,
  look: Look(fresh: fresh),
  child: MaterialApp(
    home: Scaffold(body: SafeArea(child: child)),
  ),
);

/// Баллы брали из СДО десять минут назад.
int _updated() => DateTime.now().millisecondsSinceEpoch ~/ 1000 - 600;

Widget _course(int id, {bool fresh = true}) {
  final raw = Map<String, dynamic>.from(demoFixtures()['GET /api/sdo/grades/$id'] as Map);
  return _wrap(
    CourseScreen(
      api: fakeApi(
        overrides: {
          'GET /api/sdo/grades/$id': {...raw, 'updated': _updated()},
        },
      ),
      course: Course.fromJson(raw),
    ),
    fresh: fresh,
  );
}

void main() {
  setUpAll(loadFonts);
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('«обновлено», сроки работ и «до N баллов» — коротко и по Москве', () {
    final at = DateTime.parse('2026-10-08T10:07:00+03:00');
    int unix(String s) => DateTime.parse(s).millisecondsSinceEpoch ~/ 1000;
    expect(updatedText(unix('2026-10-08T09:40:00+03:00'), at), 'сегодня\u00A0в\u00A009:40');
    // полночь по Москве — уже «сегодня», хотя по UTC ещё вчера
    expect(updatedText(unix('2026-10-08T00:30:00+03:00'), at), 'сегодня\u00A0в\u00A000:30');
    expect(updatedText(unix('2026-10-07T21:10:00+03:00'), at), 'вчера\u00A0в\u00A021:10');
    expect(updatedText(unix('2026-10-05T09:05:00+03:00'), at), '5\u00A0октября\u00A0в\u00A009:05');
    expect(workDue('четверг, 8 октября 2026, 23:59', at), 'сегодня до 23:59');
    expect(workDue('пятница, 9 октября 2026, 9:00', at), 'завтра до 09:00');
    expect(workDue('четверг, 15 октября 2026, 23:59', at), 'до 15 октября, 23:59');
    expect(workDue('15 октября 2026', at), 'до 15 октября');
    expect(workDue('скоро', at), isNull);
    expect(upToPoints(41), 'до 41 балла');
    expect(upToPoints(12), 'до 12 баллов');
    expect(upToPoints(2.5), 'до 2,5 балла');
  });

  test('цель целыми фразами — те же данные, что значками в прежней карточке', () {
    final g = Map<String, dynamic>.from((demoFixtures()['GET /api/sdo/grades/18673'] as Map)['goal'] as Map);
    expect(goalFreshLines(g), [
      'Открыто 4 работы, они дают до 41 балла',
      'Лекции впереди дают до 5 баллов',
      'Экзамен даёт до 40 баллов',
      'Зачтено 1 из 6 работ, нужно 5: из 4 открытых зачесть 4',
      'Ниже порога или срок прошёл: 1. Их не считаю, пригодятся, если дадут пересдать',
    ]);
    // не хватает баллов — «если сдать всё…», с экзаменом впереди — «а потом сдать экзамен»
    final short = {...g, 'need': 12, 'best': 134};
    expect(goalFreshLines(short), contains('Если сдать всё и ходить на лекции, а потом сдать экзамен, выйдет до 134'));
  });

  testWidgets('«Учёба»: строка СДО, сводка БРС сверху, предметы одной карточкой', (t) async {
    phone(t);
    await t.pumpWidget(
      _wrap(
        StudyScreen(
          api: fakeApi(
            overrides: {
              'GET /api/sdo/grades': {...demoFixtures()['GET /api/sdo/grades'] as Map, 'updated': _updated()},
            },
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.byKey(const ValueKey('study:fresh')), findsOneWidget);
    expect(find.textContaining('баллы из СДО · обновлено '), findsOneWidget);
    // среднего балла БРС нет (Никита 17.11) — вместо него карточка автоматов
    expect(find.text('в среднем по БРС'), findsNothing);
    expect(find.byKey(const Key('study:autos')), findsOneWidget);
    // в записи стенда на «3» или зачёт хватает в трёх предметах, но работ зачтено 1 из 6 — автомата нет
    expect(find.text('Автоматов пока нет'), findsOneWidget);
    expect(find.text('Баллов хватает в 3\u00A0предметах, осталось зачесть работы'), findsOneWidget);
    expect(find.text('Kapi ИИ'), findsOneWidget);
    expect(find.text('Предметы · 6'), findsOneWidget);
    // под названием только работы (Никита 19.11): «до «4» ещё 12» и «итог — …» в строке не пишем
    expect(find.textContaining('Работ зачтено\u00A0'), findsWidgets);
    expect(find.textContaining('до «4» ещё'), findsNothing);
    expect(find.textContaining('итог —'), findsNothing);
    // прежней метки «СДО» в шапке нет
    expect(find.text('СДО'), findsNothing);

    await t.tap(find.textContaining('Объектно'));
    await settle(t);
    expect(find.byKey(const ValueKey('course:fresh')), findsOneWidget);
  });

  for (final scale in [1.0, 1.3]) {
    testWidgets('строка предмета: «18,5» и «100» внутри кольца, не на нём (шрифт ×$scale); итог из СДО не пишется', (
      t,
    ) async {
      phone(t);
      t.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(t.platformDispatcher.clearTextScaleFactorTestValue);
      final grades = Map<String, dynamic>.from(demoFixtures()['GET /api/sdo/grades'] as Map);
      final list = [for (final c in grades['courses'] as List) Map<String, dynamic>.from(c as Map)];
      // скрин Никиты 19.11: «18,5» касалось кольца; под названием «итог — Не зачтено» зелёным
      list[0] = {...list[0], 'score': 18.5, 'final': 'Не зачтено', 'works_total': 6, 'works_passed': 2};
      list[1] = {...list[1], 'score': 100};
      await t.pumpWidget(
        _wrap(
          StudyScreen(
            api: fakeApi(
              overrides: {
                'GET /api/sdo/grades': {...grades, 'courses': list},
              },
            ),
          ),
        ),
      );
      await settle(t);
      for (final n in ['18,5', '100']) {
        final text = find.text(n).first;
        final para = t.renderObject<RenderParagraph>(text);
        // ширина самих цифр на экране (с учётом FittedBox), а не ширина коробки текста
        final shown = para.getMaxIntrinsicWidth(double.infinity) * t.getRect(text).width / para.size.width;
        final ring = t.getRect(find.ancestor(of: text, matching: find.byType(ScoreRing)));
        // кольцо толщиной 4 и ещё хотя бы 3 пт воздуха с каждой стороны
        expect((ring.width - shown) / 2, greaterThanOrEqualTo(4 + 3), reason: '$n: цифры ${shown.toStringAsFixed(1)}');
      }
      expect(find.text('Работ зачтено\u00A02\u00A0из\u00A06'), findsOneWidget);
      expect(find.textContaining('Не зачтено'), findsNothing);
    });
  }

  testWidgets('карточка автоматов: сколько есть и где баллов хватает, а работ мало; без баллов — нет её', (t) async {
    phone(t);
    final grades = Map<String, dynamic>.from(demoFixtures()['GET /api/sdo/grades'] as Map);
    List<Map<String, dynamic>> courses(Map<String, dynamic> Function(Map<String, dynamic>) f) => [
      for (final c in grades['courses'] as List) f(Map<String, dynamic>.from(c as Map)),
    ];
    // сервер посчитал автомат (баллы и 75 % работ) в двух предметах из трёх с баллами
    final two = courses((c) => {...c, 'auto': c['id'] == 18675 || c['id'] == 18677});
    await t.pumpWidget(
      _wrap(
        StudyScreen(
          api: fakeApi(
            overrides: {
              'GET /api/sdo/grades': {...grades, 'courses': two},
            },
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.text('2'), findsOneWidget);
    expect(find.text('автомата'), findsOneWidget);
    expect(find.text('Ещё в 1\u00A0предмете баллов хватает, осталось зачесть работы'), findsOneWidget);

    // начало семестра: нигде не хватает даже на «3» или зачёт — карточки нет
    final low = courses((c) => {...c, 'score': 10, 'auto': false});
    await t.pumpWidget(
      _wrap(
        StudyScreen(
          key: const ValueKey('low'),
          api: fakeApi(
            overrides: {
              'GET /api/sdo/grades': {...grades, 'courses': low},
            },
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.byKey(const Key('study:autos')), findsNothing);
    expect(find.text('Kapi ИИ'), findsOneWidget);
  });

  test('автомат: баллы на «3» или зачёт и 75 % работ; сервер знает лучше', () {
    Course c(num score, int passed, {Object? auto}) => Course.fromJson({
      'id': 1,
      'score': score,
      'works_total': 6,
      'works_passed': passed,
      'marks': [
        {'at': 40, 'label': '3'},
        {'at': 60, 'label': '4'},
      ],
      'auto': ?auto,
    });
    expect(c(39, 6).firstReached, isFalse);
    expect(c(39, 6).isAuto, isFalse);
    expect(c(44, 4).firstReached, isTrue);
    expect(c(44, 4).isAuto, isFalse); // 4 из 6 — меньше 75 %
    expect(c(44, 5).isAuto, isTrue);
    expect(c(44, 6, auto: false).isAuto, isFalse); // по странице работы одна не зачтена — сервер знает
  });

  testWidgets('«Учёба» в «Классике» — прежняя', (t) async {
    phone(t);
    await t.pumpWidget(_wrap(StudyScreen(api: fakeApi()), fresh: false));
    await settle(t);
    expect(find.byKey(const ValueKey('study:fresh')), findsNothing);
    expect(find.byKey(const Key('study:autos')), findsNothing);
    expect(find.text('Kapi ИИ'), findsOneWidget);
  });

  testWidgets('предмет: цель «по текущим данным», посещения коротко, работы словами, «Сдать», файлы', (t) async {
    phone(t);
    await t.pumpWidget(_course(18673));
    await settle(t);
    expect(find.byKey(const ValueKey('course:fresh')), findsOneWidget);
    expect(find.byKey(const Key('course:score')), findsOneWidget);
    expect(find.byKey(const Key('goal:fresh')), findsOneWidget);
    expect(find.text('По текущим данным: впритык'), findsOneWidget);
    expect(find.text('Открыто 4 работы, они дают до 41 балла'), findsOneWidget);
    expect(find.textContaining('Расчёт по баллам из СДО, обновлено сегодня'), findsOneWidget);
    expect(find.textContaining('работы: открыто'), findsNothing); // прежние строки значками
    final list = find.byType(Scrollable).first;
    await t.scrollUntilVisible(find.text('Посещения лекций · был на 3 из 6'), 300, scrollable: list);
    await t.scrollUntilVisible(find.text('ждём балл'), 200, scrollable: list);
    // легенда — только из тех отметок, что есть: «отметил сам» и «уважительная» здесь не встречаются
    for (final w in ['был', 'ждём балл', 'не был', 'отметь сам']) {
      expect(find.text(w), findsOneWidget);
    }
    expect(find.text('отметил сам'), findsNothing);
    expect(find.text('уважительная'), findsNothing);
    expect(find.textContaining('прошедших'), findsNothing); // «был на 3 из 6» — в заголовке раздела

    await t.scrollUntilVisible(find.byKey(const ValueKey('course:submit:106')), 300, scrollable: list);
    expect(find.text('ниже порога'), findsOneWidget);
    expect(find.text('отправлено, ждёт оценки'), findsOneWidget);
    expect(find.text('сдаётся на занятии'), findsOneWidget);
    expect(find.text('6 / 8'), findsOneWidget);
    // «Сдать» — только у задания, которое можно сдать
    expect(find.byKey(const ValueKey('course:submit:105')), findsNothing);
    await t.scrollUntilVisible(find.byKey(const Key('course:files')), 300, scrollable: list);
    expect(find.text('Файлы предмета'), findsOneWidget);
    expect(find.text('5 файлов · лекции, практики'), findsOneWidget);
  });

  testWidgets('предмет: «Спросить Kapi» открывает чат с этим предметом', (t) async {
    phone(t);
    await t.pumpWidget(_course(18673));
    await settle(t);
    await t.tap(find.byKey(const Key('course:ask')));
    await settle(t);
    expect(find.byType(ChatScreen), findsOneWidget);
    expect(t.widget<ChatScreen>(find.byType(ChatScreen)).subject, 'Объектно-ориентированный анализ и программирование');
  });

  testWidgets('зачёт: одна отметка — «Цель · зачёт», без выбора', (t) async {
    phone(t);
    await t.pumpWidget(_course(18672));
    await settle(t);
    expect(find.text('Цель · зачёт'), findsOneWidget);
    expect(find.text('Цель'), findsNothing); // выбирать нечего — отметка названа в подписи
  });

  testWidgets('предмет в «Классике» — прежний', (t) async {
    phone(t);
    await t.pumpWidget(_course(18673, fresh: false));
    await settle(t);
    expect(find.byKey(const ValueKey('course:fresh')), findsNothing);
    expect(find.byKey(const Key('goal:fresh')), findsNothing);
    expect(find.byKey(const Key('course:ask')), findsNothing);
  });
}

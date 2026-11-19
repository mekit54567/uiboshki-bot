// «Проверка файла» (второй круг дизайна, Никита 12.10): в новом дизайне
// неподходящий файл остаётся в списке с причиной, подходящий — с галочкой.
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/screens/submit.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

const _mb = 1048576;

Picked _file(String name, int size) => (name: name, bytes: Uint8List(size));

Future<Map<String, Object?>> _open(
  WidgetTester t,
  List<Picked> files, {
  bool design2 = true,
  bool replace = false,
}) async {
  phone(t);
  final bodies = <String, Object?>{};
  final api = fakeApi(bodies: bodies);
  await t.pumpWidget(
    AppStyle(
      p: Palette.depth,
      font: FontChoice.book,
      design2: design2,
      child: MaterialApp(
        home: Scaffold(
          body: SubmitSheet(api: api, title: 'Практика 3', deadlineId: 7, replace: replace, pick: (_) async => files),
        ),
      ),
    ),
  );
  await settle(t);
  await t.tap(find.text('Выбрать файл'));
  await settle(t);
  return bodies;
}

void main() {
  test('размер по-человечески и причины', () {
    expect(fileSize(820 * 1024), '820 КБ');
    expect(fileSize(1258291), '1,2 МБ');
    expect(fileSize(15 * _mb), '15 МБ');
    final r = SubmitRules.fromJson({
      'accepted': ['.docx', '.pdf'],
      'maxbytes': 20 * _mb,
    });
    expect(r.problem(_file('макет.pages', 10)), '.pages задание не примет — нужен файл: .docx или .pdf');
    expect(r.problem(_file('отчёт.pdf', 21 * _mb)), 'больше 20\u00A0МБ — задание не примет');
    expect(r.problem(_file('отчёт.docx', 10)), isNull);
    final z = SubmitRules.fromJson({
      'accepted': ['.zip'],
      'labels': ['Архив ZIP'],
    });
    expect(z.problem(_file('README', 1)), 'Файл без расширения задание не примет — нужен файл: Архив ZIP');
  });

  testWidgets('новый дизайн: галочка у подходящего, «!» и причина у плохих, уходит только zip', (t) async {
    final bodies = await _open(t, [
      _file('отчёт.docx', 2),
      _file('архив.zip', 1258291),
      _file('большой.zip', 11 * _mb),
    ]);
    expect(find.text('отчёт.docx'), findsOneWidget);
    expect(find.text('большой.zip'), findsOneWidget);
    expect(find.text('.docx задание не примет — нужен файл: Архив ZIP'), findsOneWidget);
    expect(find.text('больше 10\u00A0МБ — задание не примет'), findsOneWidget);
    expect(find.byIcon(Icons.check_rounded), findsOneWidget);
    expect(find.byIcon(Icons.priority_high_rounded), findsNWidgets(2));
    expect(find.text('1,2 МБ'), findsOneWidget);
    expect(find.byTooltip('Убрать'), findsNWidgets(3));
    expect(find.textContaining('Задание не примет:'), findsNothing); // общей строки нет
    expect(find.text('Ещё файл'), findsOneWidget); // плохие в лимит (2) не входят
    await t.tap(find.text('Сдать 1 файл'));
    await settle(t);
    final sent = bodies['POST /api/sdo/submit'] as Map;
    expect([for (final f in sent['files'] as List) f['name']], ['архив.zip']);
    expect((sent['files'] as List).first['data'], base64Encode(Uint8List(1258291)));
    expect(find.text('Сдано'), findsOneWidget);
  });

  testWidgets('новый дизайн: только плохие — кнопка неактивна; убрал — пропал', (t) async {
    await _open(t, [_file('макет.pages', 5)], replace: true);
    expect(find.byIcon(Icons.priority_high_rounded), findsOneWidget);
    final btn = find.ancestor(
      of: find.text('Заменить'),
      matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
    );
    expect(t.widget<ButtonStyleButton>(btn).onPressed, isNull);
    await t.tap(find.byTooltip('Убрать'));
    await settle(t);
    expect(find.text('макет.pages'), findsNothing);
  });

  testWidgets('новый дизайн, замена: «Заменить 2 файла»', (t) async {
    await _open(t, [_file('a.zip', 3), _file('b.zip', 4), _file('c.zip', 5)], replace: true);
    expect(find.text('Заменить 2 файла'), findsOneWidget);
    expect(find.text('c.zip'), findsNothing); // сверх лимита задания
    expect(find.text('Ещё файл'), findsNothing);
  });

  testWidgets('прежний дизайн: плохой файл не в списке, общая строка ошибки', (t) async {
    final bodies = await _open(t, [_file('отчёт.docx', 2), _file('архив.zip', 3)], design2: false);
    expect(find.text('отчёт.docx'), findsNothing);
    expect(find.textContaining('Задание не примет: отчёт.docx'), findsOneWidget);
    expect(find.byIcon(Icons.check_rounded), findsNothing);
    expect(find.text('1 КБ'), findsOneWidget);
    await t.tap(find.text('Сдать'));
    await settle(t);
    final sent = bodies['POST /api/sdo/submit'] as Map;
    expect([for (final f in sent['files'] as List) f['name']], ['архив.zip']);
  });
}

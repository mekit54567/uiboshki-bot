// «Неделя»: подпись недели короткая и влезает целиком (Б5); при листании
// шапка, поиск и переключатель стоят, едут только подпись недели, полоса
// дней и пары, а пока грузится новая неделя — видна прошлая (3.4).
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/screens/week.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/tokens.dart';
import 'package:uiboshki/widgets/capy_refresh.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'util.dart';

Widget _wrap(Widget child, {FontChoice font = FontChoice.book}) => AppStyle(
  p: Palette.depth,
  font: font,
  child: MaterialApp(
    home: Scaffold(body: SafeArea(child: child)),
  ),
);

/// Ответы стенда; следующая неделя приходит с задержкой [slow].
Api _slowApi(List<String> asked, {Duration slow = const Duration(milliseconds: 600)}) {
  final fx = demoFixtures();
  final next = iso(mondayOf(now()).add(const Duration(days: 7)));
  return Api(
    client: MockClient((req) async {
      final path = req.url.path.replaceFirst('/api/v1/', '/api/');
      final key = '${req.method} $path${req.url.query.isEmpty ? '' : '?${req.url.query}'}';
      asked.add(key);
      if (key == 'GET /api/week?start=$next') await Future<void>.delayed(slow);
      final body =
          fx[key] ??
          switch (path) {
            '/api/day' => {'lessons': []},
            '/api/week' => {'week': null, 'days': []},
            _ => {'ok': true},
          };
      return http.Response.bytes(utf8.encode(jsonEncode(body)), 200, headers: {'content-type': 'application/json'});
    }),
  )..token = 't';
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('даты недели коротко: «5–11 окт», через месяц — «28 сен – 4 окт»', () {
    expect(weekRange(DateTime(2026, 10, 5)), '5–11 окт');
    expect(weekRange(DateTime(2026, 9, 28)), '28 сен – 4 окт');
  });

  for (final (name, size, scale) in [('320×568 ×1.3', const Size(320, 568), 1.3), ('390×844', const Size(390, 844), 1.0)]) {
    for (final font in FontChoice.values) {
      testWidgets('подпись недели целиком, без многоточия и не сжата: $name · ${font.name}', (t) async {
        await loadFonts();
        t.view.devicePixelRatio = 2;
        t.view.physicalSize = size * 2;
        t.platformDispatcher.textScaleFactorTestValue = scale;
        addTearDown(t.view.reset);
        addTearDown(t.platformDispatcher.clearTextScaleFactorTestValue);
        // самая длинная подпись: двузначный номер и неделя через два месяца
        final api = fakeApi(
          overrides: {
            'GET /api/week?start=${iso(mondayOf(now()))}': {'week': 16, 'days': []},
          },
        );
        await t.pumpWidget(_wrap(WeekScreen(api: api), font: font));
        await settle(t);
        final label = find.descendant(of: find.byType(WeekLabelText), matching: find.byType(Text));
        expect(label, findsOneWidget);
        final text = t.widget<Text>(label).data!;
        expect(text, startsWith('16 неделя · '));
        expect(text, isNot(contains('…')));
        final para = t.renderObject<RenderParagraph>(find.descendant(of: label, matching: find.byType(RichText)));
        expect(para.didExceedMaxLines, isFalse);
        // FittedBox не уменьшил: подпись помещается своим размером; неделя на
        // стыке месяцев («26 окт – 1 ноя») на 320 с крупным шрифтом — чуть мельче
        final shrink = t.getRect(label).width / t.getSize(label).width;
        if (scale == 1.0 || !text.contains(' – ')) {
          expect(shrink, closeTo(1, 0.005));
        } else {
          expect(shrink, greaterThan(0.85));
        }
        // и длиннее, через месяц
        final long = TextPainter(
          text: TextSpan(text: '16 неделя · 28 сен – 4 окт', style: para.text.style),
          textScaler: TextScaler.linear(scale),
          textDirection: TextDirection.ltr,
        )..layout();
        // место под подпись: ширина шапки без отступов и двух стрелок
        final room =
            t.getSize(find.byType(ScreenTitle)).width -
            2 * Space.xl -
            t.getSize(find.byTooltip('Следующая неделя')).width -
            t.getSize(find.byTooltip('Прошлая неделя')).width;
        // на 390 — своим размером; на 320 с крупным шрифтом — чуть мельче, но целиком
        if (scale == 1.0) expect(long.width, lessThan(room + 0.5));
        expect(long.width * 0.85, lessThan(room));
        long.dispose();
      });
    }
  }

  testWidgets('листание: шапка и переключатель стоят, едут неделя, дни и пары; без мигания', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(_wrap(WeekScreen(api: _slowApi(asked))));
    await settle(t);
    final title = t.getRect(find.text('Неделя'));
    final toggle = t.getRect(find.byTooltip('По дням'));
    final search = t.getRect(find.byTooltip('Поиск расписания'));
    final next = mondayOf(now()).add(const Duration(days: 7));

    await t.tap(find.byTooltip('Следующая неделя'));
    await t.pump(const Duration(milliseconds: 120));
    // подпись недели уже новая, а неделя ещё грузится: видна прошлая, бледнее, без крутилки
    expect(find.text('Неделя'), findsOneWidget); // шапка одна — не уезжает вместе со страницей
    expect(t.getRect(find.text('Неделя')), title);
    expect(t.getRect(find.byTooltip('По дням')), toggle);
    expect(t.getRect(find.byTooltip('Поиск расписания')), search);
    expect(find.byType(WeekLabelText), findsNWidgets(2)); // старая подпись уезжает, новая въезжает
    expect(find.textContaining(weekRange(next)), findsOneWidget);
    expect(find.byType(CapyLoading), findsNothing);
    final dim = t.widget<AnimatedOpacity>(find.byType(AnimatedOpacity).first);
    expect(dim.opacity, lessThan(1));

    await t.pump(const Duration(milliseconds: 600)); // пришла новая неделя
    await t.pump(const Duration(milliseconds: 120));
    expect(asked, contains('GET /api/week?start=${iso(next)}'));
    expect(t.getRect(find.text('Неделя')), title);
    expect(find.text('Пн'), findsNWidgets(2)); // полоса дней — старая и новая, в движении
    await settle(t);
    expect(find.text('Пн'), findsOneWidget);
    expect(find.byType(WeekLabelText), findsOneWidget);
    expect(t.widget<AnimatedOpacity>(find.byType(AnimatedOpacity).first).opacity, 1);

    // и по дням — свайп вбок листает, шапка на месте
    await t.tap(find.byTooltip('По дням'));
    await settle(t);
    final toggle2 = t.getRect(find.byTooltip('По дням'));
    await t.fling(find.text('Неделя'), const Offset(400, 0), 1500);
    await t.pump(const Duration(milliseconds: 120));
    expect(find.text('Неделя'), findsOneWidget);
    expect(t.getRect(find.byTooltip('По дням')), toggle2);
    await settle(t);
    expect(find.textContaining(weekRange(mondayOf(now()))), findsOneWidget);
  });
}

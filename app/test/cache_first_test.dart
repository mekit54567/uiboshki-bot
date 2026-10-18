// Загрузка без плашек (5.101, Никита 18.10): экран сразу показывает запас
// телефона, свежие данные тихо его заменяют; ни «Обновляю · данные от …»,
// ни «Сервер не отвечает» — время в них скакало между путями.
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'look_test.dart' show meta;
import 'util.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  final today = {'GET /api/today': Map<String, dynamic>.from(demoFixtures()['GET /api/today'])..['date'] = iso(now())};

  for (final design2 in [true, false]) {
    testWidgets('медленная сеть: запас сразу, строк о загрузке нет (design2: $design2)', (t) async {
      phone(t);
      var delay = Duration.zero;
      final api = fakeApi(delay: () => delay, overrides: {...today, ...meta(design2)});
      await api.get('/today');
      delay = const Duration(seconds: 3);
      await t.pumpWidget(UiboApp(api: api, design2: design2));
      await t.pump(const Duration(milliseconds: 100));
      await t.pump(const Duration(milliseconds: 100));
      expect(find.text('сегодня · 5 пар'), findsOneWidget); // запас, без крутилки
      for (var i = 0; i < 30; i++) {
        await t.pump(const Duration(milliseconds: 100));
        expect(find.textContaining('данные от'), findsNothing);
      }
      for (var i = 0; i < 20; i++) {
        await t.pump(const Duration(seconds: 1));
      }
    });

    testWidgets('сервер молчит: запас без плашки (design2: $design2)', (t) async {
      phone(t);
      var slow = false;
      final api = fakeApi(slow: () => slow, overrides: {...today, ...meta(design2)});
      await api.get('/today');
      slow = true;
      await t.pumpWidget(UiboApp(api: api, design2: design2));
      await settle(t);
      expect(find.text('сегодня · 5 пар'), findsOneWidget);
      expect(find.textContaining('данные от'), findsNothing);
      expect(find.textContaining('Сервер не отвечает'), findsNothing);
      expect(find.textContaining('Нет сети'), findsNothing);
    });
  }
}

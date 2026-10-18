import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/models.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'util.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  test('без сети — последний ответ из памяти, выход стирает', () async {
    var off = false;
    final api = fakeApi(offline: () => off);
    final fresh = await api.get('/me');
    expect(api.offlineSince.value, isNull);
    off = true;
    final cached = await api.get('/me');
    expect(cached, fresh);
    expect(api.offlineSince.value, isNotNull);
    await expectLater(api.get('/files'), throwsA(anything)); // не загружалось — нечего показать
    await api.logout();
    await expectLater(api.get('/me'), throwsA(anything));
    expect(api.offlineSince.value, isNull);
  });

  // 5.101 (Никита 18.10): плашки «Без сети · данные от …» больше нет —
  // приложение молча показывает сохранённое, как приложения iPhone.
  testWidgets('приложение без сети показывает сохранённое, без плашки', (t) async {
    phone(t);
    var off = false;
    final today = Map<String, dynamic>.from(demoFixtures()['GET /api/today'])..['date'] = iso(now());
    final api = fakeApi(offline: () => off, overrides: {'GET /api/today': today});
    await api.get('/today'); // была сеть — ответ сохранён
    off = true;
    await t.pumpWidget(UiboApp(api: api));
    await settle(t);
    expect(find.textContaining('данные от'), findsNothing);
    expect(find.textContaining('Без сети'), findsNothing);
    expect(find.text('сегодня · 5 пар'), findsOneWidget); // пары из сохранённого ответа
  });

  // Б1: утром в памяти — вчерашний «Сегодня» (в записи стенда — 8 октября)
  testWidgets('без сети вчерашний ответ не показывается: пары на сегодня из сохранённой недели', (t) async {
    phone(t);
    var off = false;
    final day = demoFixtures()['GET /api/day?date=2026-10-10']; // три пары
    final api = fakeApi(offline: () => off, overrides: {'GET /api/day?date=${iso(now())}': day});
    await api.get('/today');
    await api.get('/day?date=${iso(now())}'); // открывал вкладку «Неделя»
    off = true;
    await t.pumpWidget(UiboApp(api: api));
    await settle(t);
    expect(find.text('сегодня · 5 пар'), findsNothing); // вчерашние пары
    expect(find.text('сегодня · 3 пары'), findsOneWidget);
  });

  testWidgets('без сети и без сохранённого дня — честное «ещё не загружено»', (t) async {
    phone(t);
    var off = false;
    final api = fakeApi(offline: () => off);
    await api.get('/today');
    off = true;
    await t.pumpWidget(UiboApp(api: api));
    await settle(t);
    expect(find.text('сегодня · 5 пар'), findsNothing);
    expect(find.text('Расписание на сегодня ещё не загружено — нужен интернет.'), findsOneWidget);
  });
}

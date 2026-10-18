// Б2: «нет сети» и «сервер ответил ошибкой» — разные тексты.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/common.dart';

import 'util.dart';

Api _api(Future<http.Response> Function(http.Request) answer) => Api(client: MockClient(answer))..token = 't';

Future<Object> _fail(Future<Object?> call) async {
  try {
    await call;
  } catch (e) {
    return e;
  }
  fail('ошибки не было');
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('500 с HTML вместо JSON — ошибка сервера, а не «нет интернета»', () async {
    final api = _api((_) async => http.Response('<html>Internal Server Error</html>', 500));
    final e = await _fail(api.post('/sdo/submit'));
    expect(e, isA<ApiError>());
    expect((e as ApiError).server, isTrue);
    expect(errorText(e), 'Сервер сейчас не отвечает (ошибка 500) — попробуй позже.');
  });

  test('502 от Railway страницей и 502 с текстом сервера', () async {
    var e = await _fail(_api((_) async => http.Response('Bad Gateway', 502)).get('/me'));
    expect(errorText(e), contains('ошибка 502'));
    e = await _fail(
      _api(
        (_) async =>
            http.Response.bytes(utf8.encode('{"detail":"СДО не ответило вовремя — файл, возможно, не дошёл"}'), 502),
      ).post('/sdo/submit'),
    );
    expect(errorText(e), 'СДО не ответило вовремя — файл, возможно, не дошёл');
  });

  test('нет сети и таймаут — «нет интернета»', () async {
    final e = await _fail(_api((_) async => throw http.ClientException('Failed host lookup')).get('/me'));
    expect(isOffline(e), isTrue);
    expect(errorText(e), 'Нет интернета — проверь связь.');
    expect(errorText(TimeoutException('долго')), 'Нет интернета — проверь связь.');
    expect(errorText(ApiError('нет такого задания', status: 404)), 'нет такого задания');
  });

  testWidgets('экран при ошибке сервера пишет про сервер', (t) async {
    phone(t);
    final api = _api((_) async => http.Response('<html>oops</html>', 500));
    await t.pumpWidget(
      AppStyle(
        p: Palette.depth,
        font: FontChoice.strict,
        child: MaterialApp(
          home: Scaffold(
            body: Loader<dynamic>(load: () => api.get('/files'), builder: (_, _, _) => const Text('данные')),
          ),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Сервер сейчас не отвечает (ошибка 500) — попробуй позже.'), findsOneWidget);
    expect(find.textContaining('интернет'), findsNothing);
  });

  // 5.101 (Никита 18.10): плашки «Сервер не отвечает · данные от …» больше
  // нет — её время скакало между путями. Медленный ответ не теряется: экран
  // сразу получает запас, а опоздавший ответ ложится в запас к следующему разу.
  testWidgets('не дождались — запас сразу, опоздавший ответ ложится в запас', (t) async {
    var wait = Duration.zero;
    var n = 0;
    final api = _api((r) async {
      await Future<void>.delayed(wait);
      return http.Response(jsonEncode({'n': ++n}), 200, headers: {'content-type': 'application/json'});
    });
    Object? got;
    await t.runAsync(() async {
      got = await api.get('/sdo/grades');
      await Future<void>.delayed(const Duration(milliseconds: 50)); // запас пишется в фоне
    });
    expect(got, {'n': 1});
    wait = const Duration(seconds: 20);
    final slow = api.get('/sdo/grades');
    await t.pump(Api.timeout + const Duration(milliseconds: 10));
    expect(await slow, {'n': 1}); // экран не ждёт: прошлый ответ
    expect(api.offlineSince.value, isNotNull);
    await t.pump(const Duration(seconds: 15));
    wait = Duration.zero;
    Object? cached;
    await t.runAsync(() async {
      cached = await Api.fromCache<dynamic>(() => api.get('/sdo/grades'));
    });
    expect(cached, {'n': 2}); // свежий ответ уже в запасе
  });
}

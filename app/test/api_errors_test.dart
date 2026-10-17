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

  test('502 от хостинга страницей и 502 с текстом сервера', () async {
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

  test('висит один путь, а сервер отвечает — без плашки «Сервер не отвечает»', () async {
    var hang = false;
    final sdo = Completer<void>();
    Future<http.Response> answer(http.Request r) async {
      if (hang && r.url.path.contains('/sdo/')) {
        await sdo.future;
        throw TimeoutException('СДО висит');
      }
      return http.Response(jsonEncode({'ok': r.url.path}), 200, headers: {'content-type': 'application/json'});
    }

    final api = _api(answer);
    await api.get('/sdo/grades'); // запомнили
    await Future<void>.delayed(const Duration(milliseconds: 50)); // запас пишется в фоне
    hang = true;
    final slow = api.get('/sdo/grades');
    await api.get('/today'); // пока СДО висит, сервер ответил на другое
    sdo.complete();
    expect(await slow, {'ok': '/api/v1/sdo/grades'});
    expect(api.offlineSince.value, isNull);

    // сервер за это время ничего не ответил, но /meta отвечает — сам он жив,
    // висит только СДО (Никита 17.10): плашки нет
    expect(await api.get('/sdo/grades'), isNotNull);
    expect(api.offlineSince.value, isNull);
    final cold = _api(answer);
    expect(await cold.get('/sdo/grades'), isNotNull);
    expect(cold.offlineSince.value, isNull);

    // а если и /meta молчит — сервер правда не отвечает, плашка на месте
    hang = false;
    final down = _api((r) async => hang ? throw TimeoutException('висит') : answer(r));
    await down.get('/sdo/grades');
    await Future<void>.delayed(const Duration(milliseconds: 50));
    hang = true;
    expect(await down.get('/sdo/grades'), isNotNull);
    expect(down.offlineSince.value, isNotNull);
    expect(down.offlineSlow.value, isTrue);
  });
}

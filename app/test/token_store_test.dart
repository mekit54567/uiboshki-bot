// Ревью 03.11: токен — в Keychain/Keystore, а не в shared_preferences;
// действия (POST/PUT/DELETE) больше не ждут ответ бесконечно.
import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/api/token_store.dart';

class _Box implements SecureBox {
  final data = <String, String>{};
  bool broken = false;

  void _check() {
    if (broken) throw PlatformException(code: 'keystore');
  }

  @override
  Future<String?> read(String key) async {
    _check();
    return data[key];
  }

  @override
  Future<void> write(String key, String value) async {
    _check();
    data[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    _check();
    data.remove(key);
  }
}

void main() {
  late _Box box;
  setUp(() {
    box = _Box();
    TokenStore.box = box;
  });
  tearDown(() => TokenStore.box = MemoryBox());

  test('старый вход тихо переезжает из файла в хранилище', () async {
    SharedPreferences.setMockInitialValues({'uib_token': 'old'});
    final api = Api();
    await api.load();
    expect(api.token, 'old');
    expect(box.data['uib_token'], 'old');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('uib_token'), isNull);
    expect(prefs.getBool(TokenStore.marker), isTrue);
    // следующий запуск — из хранилища
    final next = Api();
    await next.load();
    expect(next.token, 'old');
  });

  test('новый вход и выход — только в хранилище', () async {
    SharedPreferences.setMockInitialValues({});
    final api = Api();
    await api.load();
    expect(api.token, isNull);
    await api.saveToken('new');
    expect(box.data['uib_token'], 'new');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('uib_token'), isNull);
    await api.saveToken(null);
    expect(box.data, isEmpty);
  });

  test('вход прошлой установки в Keychain не возвращается', () async {
    SharedPreferences.setMockInitialValues({}); // удалили приложение — файл пуст
    box.data['uib_token'] = 'stale';
    final api = Api();
    await api.load();
    expect(api.token, isNull);
    expect(box.data, isEmpty);
  });

  test('хранилище сломалось — вход остаётся в файле', () async {
    SharedPreferences.setMockInitialValues({'uib_token': 'old'});
    box.broken = true;
    final api = Api();
    await api.load();
    expect(api.token, 'old');
    await api.saveToken('new');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('uib_token'), 'new');
  });

  testWidgets('действие без ответа — таймаут и текст «проверь, сохранилось ли»', (t) async {
    final never = Completer<http.Response>();
    final api = Api(client: MockClient((_) => never.future))..token = 't';
    expect(Api.timeoutFor('/notes'), Api.writeTimeout);
    expect(Api.timeoutFor('/sdo/submit'), Api.slowTimeout);
    expect(Api.timeoutFor('/chat'), Api.slowTimeout);
    Object? err;
    unawaited(api.post('/notes', {'text': 'x'}).catchError((Object e) => err = e));
    await t.pump(const Duration(seconds: 29));
    expect(err, isNull);
    await t.pump(const Duration(seconds: 2)); // время в тесте ненастоящее
    expect(err, isA<WriteTimeout>());
    expect(errorText(err!), contains('проверь, сохранилось ли'));
    expect(isOffline(err!), isTrue); // сдача в СДО так и пишет «не знаем, дошёл ли файл»
  });
}

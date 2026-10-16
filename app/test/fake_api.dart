// Ответы API из записи стенда сайта (webapp/static/site/demo.json) —
// те же, что видит демо на /about/demo; ничьих настоящих данных.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:uiboshki/api/api.dart';

Map<String, dynamic> demoFixtures() {
  final f = File('../webapp/static/site/demo.json');
  return Map<String, dynamic>.from(jsonDecode(f.readAsStringSync())['fx']);
}

/// Api, который отвечает записанными ответами; requests — что спрашивали.
/// offline — нет сети, slow — сервер не ответил вовремя, delay — сеть медленная.
Api fakeApi({
  String? token = 'test-token',
  List<String>? requests,
  Map<String, Object?>? bodies,
  bool Function()? offline,
  bool Function()? slow,
  Duration Function()? delay,
  Map<String, Object?> overrides = const {},
}) {
  final fx = demoFixtures();
  final client = MockClient((req) async {
    if (offline?.call() ?? false) throw http.ClientException('нет сети');
    if (slow?.call() ?? false) throw TimeoutException('сервер не ответил'); // как .timeout() в Api.get
    final wait = delay?.call();
    if (wait != null && wait > Duration.zero) await Future<void>.delayed(wait);
    final path = req.url.path.replaceFirst('/api/v1/', '/api/');
    final q = req.url.query.isEmpty ? '' : '?${req.url.query}';
    var key = '${req.method} $path$q';
    if (path.startsWith('/api/sdo/goal/')) key += '|${jsonDecode(req.body)['label']}'; // как demo.js на сайте
    requests?.add(key);
    if (req.method == 'POST' && req.body.isNotEmpty) bodies?[key] = jsonDecode(req.body);
    if (req.headers['Authorization'] == null && !path.startsWith('/api/auth/')) {
      return http.Response('{"detail":"нет входа"}', 401);
    }
    Object? body = overrides.containsKey(key) ? overrides[key] : fx[key];
    // запись стенда без features.design2; приложение теперь считает это
    // «включён», а тесты по умолчанию — про прежний вид (как раньше)
    if (key == 'GET /api/meta' && body is Map && !((body['features'] as Map?)?.containsKey('design2') ?? false)) {
      final f = Map<String, dynamic>.from(body['features'] as Map? ?? {});
      body = {
        ...body,
        'features': {'design2': false, ...f},
      };
    }
    body ??= switch (path) {
      '/api/day' => {'lessons': []},
      '/api/week' => {'week': null, 'days': []},
      '/api/auth/start' => {'code': 'abc', 'link': 'https://t.me/UiboshkiBot?start=login_abc', 'pick': 47},
      '/api/auth/poll' => {'status': 'wait'},
      '/api/auth/providers' => {
        'items': [
          {'id': 'vk', 'name': 'VK ID'},
          {'id': 'yandex', 'name': 'Яндекс ID'},
        ],
      },
      '/api/auth/vk/start' => {'url': 'https://id.vk.com/authorize?state=s1'},
      '/api/auth/review' => {'status': 'ok', 'token': 'rv.demo'},
      '/api/sdo/submit-rules' => {
        'accepted': ['.zip'],
        'labels': ['Архив ZIP'],
        'maxfiles': 2,
        'maxbytes': 10485760,
      },
      '/api/sdo/submit' => {'status': 'Отправлено для оценивания'},
      '/api/groups/search' => {
        'items': [
          {'id': 5001, 'name': 'УИБО-01-24'},
        ],
      },
      '/api/me/group' => {
        'group': {'id': 5001, 'name': 'УИБО-01-24', 'own': false},
      },
      _ => {'ok': true},
    };
    return http.Response.bytes(utf8.encode(jsonEncode(body)), 200, headers: {'content-type': 'application/json'});
  });
  return Api(client: client)..token = token;
}

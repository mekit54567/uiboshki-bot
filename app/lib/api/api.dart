// Клиент API бота (/api/v1, этап 2): вход через бота, токен сессии устройства.
import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class Unauthorized implements Exception {}

class ApiError implements Exception {
  final String message;

  /// Код ответа; ≥500 или нечитаемый ответ — сбой сервера, а не сети.
  final int? status;
  ApiError(this.message, {this.status});

  /// Сервер упал или ответил не тем (500, 502 от хостинга, HTML вместо JSON).
  ApiError.server(int code)
    : this(
        code >= 400
            ? 'Сервер сейчас не отвечает (ошибка $code) — попробуй позже.'
            : 'Сервер ответил непонятно — попробуй позже.',
        status: code >= 400 ? code : 500,
      );

  bool get server => (status ?? 0) >= 500;
  @override
  String toString() => message;
}

/// Нет сети: связь оборвалась, адрес не нашёлся, ответа не дождались.
bool isOffline(Object e) =>
    e is http.ClientException || e is TimeoutException || '${e.runtimeType}'.contains('SocketException');

/// Человеческий текст ошибки для экрана: нет сети ≠ сервер ответил ошибкой.
String errorText(Object e) {
  if (e is ApiError) return e.message;
  if (isOffline(e)) return 'Нет интернета — проверь связь.';
  if (e is FormatException) return ApiError.server(200).message;
  return 'Что-то пошло не так — попробуй ещё раз.';
}

/// PKCE S256: base64url(SHA-256(verifier)) без «=» — как oauth._challenge на сервере.
String oauthChallenge(String verifier) =>
    base64Url.encode(sha256.convert(utf8.encode(verifier)).bytes).replaceAll('=', '');

class Api {
  /// Адрес сервера; пустой — тот же сайт (сборка web со стенда).
  static const base = String.fromEnvironment('API', defaultValue: 'https://www.uiboshki.ru');
  static const _tokenKey = 'uib_token';

  String? token;
  final http.Client _client;

  Api({http.Client? client}) : _client = client ?? http.Client();

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    token = prefs.getString(_tokenKey);
  }

  Future<void> saveToken(String? value) async {
    token = value;
    final prefs = await SharedPreferences.getInstance();
    if (value == null) {
      await prefs.remove(_tokenKey);
    } else {
      await prefs.setString(_tokenKey, value);
    }
  }

  Uri _uri(String path) => Uri.parse('$base/api/v1$path');

  /// Своё приложение называет себя серверу: в боте «Войти… на Капибара · iPhone»,
  /// а не «Браузер» (у Dart в User-Agent только «Dart/3»). В вебе — браузер и так виден.
  static String? get platform => kIsWeb
      ? null
      : switch (defaultTargetPlatform) {
          TargetPlatform.iOS => 'ios',
          TargetPlatform.android => 'android',
          _ => null,
        };

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (token != null) 'Authorization': 'Bearer $token',
    'X-App': ?platform,
  };

  dynamic _decode(http.Response r) {
    if (r.statusCode == 401) throw Unauthorized();
    final dynamic body;
    try {
      body = r.bodyBytes.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    } on FormatException {
      // «Internal Server Error», страница 502 от хостинга — сбой сервера, не сети
      throw ApiError.server(r.statusCode);
    }
    if (r.statusCode >= 400) {
      final detail = body is Map ? body['detail'] : null;
      if (detail is String) throw ApiError(detail, status: r.statusCode);
      throw r.statusCode >= 500
          ? ApiError.server(r.statusCode)
          : ApiError('Не получилось (ошибка ${r.statusCode}) — попробуй ещё раз.', status: r.statusCode);
    }
    return body;
  }

  /// Без сети — ответы GET из последней удачной загрузки (как sw.js у PWA).
  /// Время той загрузки — здесь; null — данные свежие. Плашки по нему больше
  /// нет (5.101, Никита 18.10: «живёт своей жизнью»): у каждого пути своё время
  /// запаса, и плашка показывала то 12:50, то 12 октября — смотря какой запрос
  /// не дождался последним. Ошибку видно там, где не прошло действие.
  final offlineSince = ValueNotifier<DateTime?>(null);
  static const _cachePrefix = 'uib_cache:';
  static const timeout = Duration(seconds: 8);

  /// Сколько ещё ждать ответ, который не уложился в [timeout]: экран уже
  /// показал запас, а свежий ответ ляжет в запас к следующему открытию. Иначе
  /// медленный путь (журнал СДО) так и оставался с данными недельной давности.
  static const lateTimeout = Duration(seconds: 60);

  /// Внутри [fromCache] get берёт только запомненное и в сеть не ходит.
  static const _cacheOnly = #uibCacheOnly;

  /// Идёт загрузка «из запаса» ([fromCache]): экран может отказаться от старого ответа.
  static bool get cacheOnly => Zone.current[_cacheOnly] == true;

  /// Загрузка экрана из запаса телефона, без сети: экран показывает прошлые
  /// данные сразу, свежие догружаются следом (владелец, 09.10: «долго грузит»).
  /// null — чего-то в запасе нет.
  static Future<T?> fromCache<T>(Future<T> Function() load) =>
      runZoned(() => load().then<T?>((v) => v).catchError((_) => null), zoneValues: {_cacheOnly: true});

  Future<dynamic> get(String path) async {
    if (cacheOnly) {
      final cached = await _cached(path);
      if (cached == null) throw StateError('нет в запасе');
      return cached.body;
    }
    final req = _client.get(_uri(path), headers: _headers);
    final http.Response r;
    try {
      r = await req.timeout(timeout);
    } catch (e) {
      final cached = await _cached(path).catchError((_) => null);
      if (cached == null) rethrow;
      if (e is TimeoutException) unawaited(_late(path, req));
      offlineSince.value = cached.at;
      return cached.body;
    }
    final body = _decode(r);
    offlineSince.value = null;
    onOk?.call('GET', path, null, body);
    // Запас — в фоне: показ данных не ждёт памяти телефона и не падает из-за неё.
    if (!path.startsWith('/auth/')) unawaited(_remember(path, r).catchError((_) {}));
    return body;
  }

  /// Опоздавший ответ — только в запас, экран его не ждёт.
  Future<void> _late(String path, Future<http.Response> req) async {
    try {
      final r = await req.timeout(lateTimeout);
      if (r.statusCode < 400 && !path.startsWith('/auth/')) await _remember(path, r);
    } catch (_) {}
  }

  Future<void> _remember(String path, http.Response r) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      '$_cachePrefix$path',
      jsonEncode({'at': DateTime.now().toIso8601String(), 'body': utf8.decode(r.bodyBytes)}),
    );
  }

  Future<({DateTime at, dynamic body})?> _cached(String path) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('$_cachePrefix$path');
    if (raw == null) return null;
    final j = jsonDecode(raw);
    return (at: DateTime.parse(j['at'] as String), body: jsonDecode(j['body'] as String));
  }

  /// Запись из загрузки «из запаса» — нельзя: бросаем, экран ждёт сеть.
  Never? _noCacheZone() {
    if (cacheOnly) throw StateError('запись без сети');
    return null;
  }

  /// Выход — данные с телефона стираются (как «выйти» в PWA).
  Future<void> clearCache() async {
    final prefs = await SharedPreferences.getInstance();
    for (final k in prefs.getKeys().where((k) => k.startsWith(_cachePrefix)).toList()) {
      await prefs.remove(k);
    }
    offlineSince.value = null;
  }

  Future<dynamic> put(String path, [Object? body]) async =>
      _noCacheZone() ?? _decode(await _client.put(_uri(path), headers: _headers, body: jsonEncode(body ?? {})));

  Future<dynamic> patch(String path, [Object? body]) async =>
      _noCacheZone() ?? _decode(await _client.patch(_uri(path), headers: _headers, body: jsonEncode(body ?? {})));

  Future<dynamic> delete(String path) async =>
      _noCacheZone() ?? _decode(await _client.delete(_uri(path), headers: _headers));

  Future<dynamic> post(String path, [Object? body]) async {
    _noCacheZone();
    final r = _decode(await _client.post(_uri(path), headers: _headers, body: jsonEncode(body ?? {})));
    onOk?.call('POST', path, body, r);
    return r;
  }

  /// Удачный ответ из сети (не из запаса): ачивки ловят по нему, что человек
  /// сделал (achievements/store.dart). Ошибка в нём запрос не ломает.
  static void Function(String method, String path, Object? body, Object? result)? onOk;

  /// Файл по подписанной ссылке сервера (/dl/…) — байтами, для «Скачать».
  Future<Uint8List> download(String url) async {
    final r = await _client.get(Uri.parse(url)).timeout(const Duration(minutes: 2));
    if (r.statusCode != 200) throw ApiError('Не скачалось — нажми ещё раз');
    return r.bodyBytes;
  }

  // ── вход через бота: код → ссылка в бота → «Да, это я» → токен ──
  /// pick — число, которое надо нажать в боте (из трёх), как у Google.
  Future<({String code, String link, int? pick})> startLogin() async {
    final r = await post('/auth/start');
    return (code: r['code'] as String, link: r['link'] as String, pick: r['pick'] as int?);
  }

  /// null — ещё ждём; иначе статус: ok / denied / expired.
  Future<String?> pollLogin(String code) async {
    final r = await post('/auth/poll', {'code': code});
    final status = r['status'] as String;
    if (status == 'ok') await saveToken(r['token'] as String);
    return status == 'wait' ? null : status;
  }

  // ── вход через VK ID / Яндекс ID (webapp/routes/auth.py) ──
  /// Какие входы кроме Telegram есть на сервере: [(id, название)].
  Future<List<({String id, String name})>> providers() async => (await loginOptions()).items;

  /// То же + code: есть ли вход по коду для проверяющих магазинов (review_demo.py),
  /// apple: вход через Apple (apple_signin.py, только iPhone-приложение).
  Future<({List<({String id, String name})> items, bool code, bool apple})> loginOptions() async {
    final r = await get('/auth/providers');
    return (
      items: [for (final p in r['items'] as List) (id: p['id'] as String, name: p['name'] as String)],
      code: r['code'] == true,
      apple: r['apple'] == true,
    );
  }

  /// Вход через Apple: токен от системы → сессия.
  Future<void> appleLogin({required String idToken, String code = '', String nonce = '', String name = ''}) async {
    final r = await post('/auth/apple', {'id_token': idToken, 'code': code, 'nonce': nonce, 'name': name});
    await saveToken(r['token'] as String);
  }

  /// Вход по коду доступа (демо-аккаунт для проверки в App Store / RuStore).
  Future<void> reviewLogin(String code) async {
    final r = await post('/auth/review', {'code': code.trim()});
    await saveToken(r['token'] as String);
  }

  /// Секрет начатого входа VK/Яндекс: сервер знает только его SHA-256, и в
  /// ru.uiboshki.app://auth вернёт одноразовый код, а не токен — чужое
  /// приложение с той же схемой код перехватит, но не обменяет (аудит 21.10, R8).
  String? _oauthVerifier;

  /// Ссылка на вход у провайдера; вернётся он на ru.uiboshki.app://auth#code=…
  /// (client 'web' — PWA: на /app#token=…).
  Future<String> startOAuth(String provider, {String client = 'app'}) async {
    final body = <String, Object?>{'client': client};
    if (client == 'app') {
      final rnd = math.Random.secure();
      final verifier = base64Url.encode(List.generate(48, (_) => rnd.nextInt(256))).replaceAll('=', '');
      _oauthVerifier = verifier;
      body['challenge'] = oauthChallenge(verifier);
    }
    return (await post('/auth/$provider/start', body))['url'] as String;
  }

  /// Адрес возврата → токен (сохраняется); null — токена нет. #code= — обмен
  /// кода на токен по секрету; #token= — сервер старше этой версии.
  Future<String?> finishOAuth(String callbackUrl) async {
    final frag = Uri.parse(callbackUrl).fragment;
    String token;
    if (frag.startsWith('code=')) {
      final verifier = _oauthVerifier;
      _oauthVerifier = null;
      if (verifier == null) return null;
      final r = await post('/auth/exchange', {'code': Uri.decodeComponent(frag.substring(5)), 'verifier': verifier});
      token = r['token'] as String;
    } else if (frag.startsWith('token=')) {
      token = Uri.decodeComponent(frag.substring(6));
    } else {
      return null;
    }
    await saveToken(token);
    return token;
  }

  Future<void> logout() async {
    try {
      await post('/auth/logout');
    } catch (_) {}
    await saveToken(null);
    await clearCache();
  }
}

// Клиент API бота (/api/v1, этап 2): вход через бота, токен сессии устройства.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class Unauthorized implements Exception {}

class ApiError implements Exception {
  final String message;

  /// Код ответа; ≥500 или нечитаемый ответ — сбой сервера, а не сети.
  final int? status;
  ApiError(this.message, {this.status});

  /// Сервер упал или ответил не тем (500, 502 от Railway, HTML вместо JSON).
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
      // «Internal Server Error», страница 502 от Railway — сбой сервера, не сети
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
  /// Время той загрузки — здесь; null — данные свежие.
  final offlineSince = ValueNotifier<DateTime?>(null);

  /// Почему из запаса: сервер не ответил вовремя (true) или сети нет вовсе
  /// (false). Плашка нового дизайна пишет «Сервер не отвечает» / «Нет сети».
  final offlineSlow = ValueNotifier<bool>(false);
  static const _cachePrefix = 'uib_cache:';
  static const timeout = Duration(seconds: 8);

  /// Когда сервер в последний раз ответил (любым кодом) — см. [get].
  DateTime? _lastOk;

  /// Проверка «сервер вообще отвечает» (/meta — лёгкий, без базы и СДО);
  /// несколько повисших запросов разом ждут одну проверку.
  Future<bool>? _ping;
  static const pingTimeout = Duration(seconds: 4);

  Future<bool> _alive() => _ping ??= () async {
    try {
      await _client.get(_uri('/meta'), headers: _headers).timeout(pingTimeout);
      _lastOk = DateTime.now();
      return true;
    } catch (_) {
      return false;
    } finally {
      _ping = null;
    }
  }();

  /// Внутри [fromCache] get берёт только запомненное и в сеть не ходит;
  /// значение зоны — [_CacheRead], куда get пишет время запомненного.
  static const _cacheOnly = #uibCacheOnly;

  /// Идёт загрузка «из запаса» ([fromCache]): экран может отказаться от старого ответа.
  static bool get cacheOnly => Zone.current[_cacheOnly] is _CacheRead;

  /// Загрузка экрана из запаса телефона, без сети: экран показывает прошлые
  /// данные сразу, свежие догружаются следом (владелец, 09.10: «долго грузит»).
  /// null — чего-то в запасе нет.
  static Future<T?> fromCache<T>(Future<T> Function() load) => fromCacheAt(load).then((r) => r?.value);

  /// То же и время запомненного (самого старого из ответов, что пошли в
  /// экран) — для строки «Обновляю · данные от 09:41».
  static Future<({T value, DateTime? at})?> fromCacheAt<T>(Future<T> Function() load) {
    final read = _CacheRead();
    return runZoned(
      () => load().then<({T value, DateTime? at})?>((v) => (value: v, at: read.at)).catchError((_) => null),
      zoneValues: {_cacheOnly: read},
    );
  }

  /// Экраны, что показывают запас и ждут свежий ответ: самое старое время
  /// их данных; null — никто не ждёт. Ключ — у каждого экрана свой.
  static final refreshing = ValueNotifier<DateTime?>(null);
  static final _waiting = <Object, DateTime>{};

  /// Экран показал запас от [at] и ждёт сеть; вернуть ключ в [refreshDone].
  static Object refreshStart(DateTime at) {
    final key = Object();
    _waiting[key] = at;
    _updateRefreshing();
    return key;
  }

  static void refreshDone(Object? key) {
    if (key == null || _waiting.remove(key) == null) return;
    _updateRefreshing();
  }

  static void _updateRefreshing() {
    refreshing.value = _waiting.isEmpty ? null : _waiting.values.reduce((a, b) => a.isBefore(b) ? a : b);
  }

  Future<dynamic> get(String path) async {
    final read = Zone.current[_cacheOnly];
    if (read is _CacheRead) {
      final cached = await _cached(path);
      if (cached == null) throw StateError('нет в запасе');
      read.saw(cached.at);
      return cached.body;
    }
    final started = DateTime.now();
    final http.Response r;
    try {
      r = await _client.get(_uri(path), headers: _headers).timeout(timeout);
    } catch (e) {
      final cached = await _cached(path).catchError((_) => null);
      if (cached == null) rethrow;
      // Пока этот путь висел, сервер ответил на другие (16.10: висели только
      // запросы к СДО) — это не «Сервер не отвечает»: запас отдаём молча,
      // плашку не ставим.
      final ok = _lastOk;
      if (e is TimeoutException && ok != null && !ok.isBefore(started)) {
        return cached.body;
      }
      // Сам сервер жив, тупит один раздел (СДО, ИИ) — тоже не «Сервер не
      // отвечает» (Никита 17.10: плашка пугала, хотя бот отвечал).
      if (e is TimeoutException && await _alive()) {
        return cached.body;
      }
      offlineSlow.value = e is TimeoutException;
      offlineSince.value = cached.at;
      return cached.body;
    }
    _lastOk = DateTime.now();
    final body = _decode(r);
    offlineSince.value = null;
    onOk?.call('GET', path, null, body);
    // Запас — в фоне: показ данных не ждёт памяти телефона и не падает из-за неё.
    if (!path.startsWith('/auth/')) unawaited(_remember(path, r).catchError((_) {}));
    return body;
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

  /// Ссылка на вход у провайдера; вернётся он на ru.uiboshki.app://auth#token=…
  /// (client 'web' — PWA: на /app#token=…).
  Future<String> startOAuth(String provider, {String client = 'app'}) async =>
      (await post('/auth/$provider/start', {'client': client}))['url'] as String;

  /// Адрес возврата → токен (сохраняется); null — токена нет.
  Future<String?> finishOAuth(String callbackUrl) async {
    final frag = Uri.parse(callbackUrl).fragment;
    if (!frag.startsWith('token=')) return null;
    final token = Uri.decodeComponent(frag.substring(6));
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

/// Что прочла загрузка из запаса: самое старое время ответов.
class _CacheRead {
  DateTime? at;
  void saw(DateTime t) {
    if (at == null || t.isBefore(at!)) at = t;
  }
}

// Пуши своего приложения (сервер — app_push.py): Android — FCM (Google) или
// RuStore, iPhone — APNs. Содержимое шифруется (152-ФЗ): телефон делает свой
// случайный ключ AES-256 и отдаёт его серверу вместе с токеном устройства,
// сервер шлёт только шифротекст {v, e}. Расшифровывает и показывает
// уведомление сам телефон, нативно: Android — сервисы в
// android/app/src/main/kotlin/ru/uiboshki/app/push, iPhone — Notification
// Service Extension (ios/KapibaraNotify, docs/app-push.md). Ключ лежит в
// хранилище приложения (Android) и в связке ключей (iPhone) — Dart его только
// создаёт и передаёт.
import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api/api.dart';

/// Телефон: что умеет сборка, разрешение, токен, ключ, нажатое уведомление.
/// На телефоне — канал uiboshki/push, тесты подменяют.
abstract class PushDevice {
  /// Какие сервисы доставки есть в этой сборке и на этом телефоне.
  Future<Map<String, bool>> available();

  /// Спросить разрешение на уведомления; true — можно.
  Future<bool> permission();

  /// Разрешение уже есть (без вопроса).
  Future<bool> granted();

  /// Токен устройства у сервиса (fcm / rustore / apns); null — не выдали.
  Future<String?> token(String platform);

  /// Ключ AES-256 (base64) — туда, где его найдёт расшифровка.
  Future<void> setKey(String key);

  /// Стереть ключ и отозвать токен на телефоне.
  Future<void> clear(String? platform);

  /// Вкладка из нажатого уведомления, с которым открылось приложение.
  Future<String?> takeTab();

  /// Нажали уведомление, пока приложение открыто; сервис сменил токен.
  void listen({
    required void Function(String tab) onTab,
    required void Function(String platform, String token) onToken,
  });
}

class _ChannelDevice implements PushDevice {
  static const _ch = MethodChannel('uiboshki/push');

  @override
  Future<Map<String, bool>> available() async {
    final m = await _ch.invokeMapMethod<String, bool>('available');
    return m ?? const {};
  }

  @override
  Future<bool> permission() async => await _ch.invokeMethod<bool>('permission') ?? false;

  @override
  Future<bool> granted() async => await _ch.invokeMethod<bool>('granted') ?? false;

  @override
  Future<String?> token(String platform) => _ch.invokeMethod<String>('token', {'platform': platform});

  @override
  Future<void> setKey(String key) => _ch.invokeMethod<void>('setKey', {'key': key});

  @override
  Future<void> clear(String? platform) => _ch.invokeMethod<void>('clear', {'platform': platform});

  @override
  Future<String?> takeTab() => _ch.invokeMethod<String>('takeTab');

  @override
  void listen({
    required void Function(String tab) onTab,
    required void Function(String platform, String token) onToken,
  }) {
    _ch.setMethodCallHandler((call) async {
      final a = call.arguments;
      if (call.method == 'tab' && a is String) onTab(a);
      if (call.method == 'token' && a is Map) onToken('${a['platform']}', '${a['token']}');
    });
  }
}

class AppPush {
  /// null — пушей приложения на платформе нет (веб: там веб-пуш, web_push.dart).
  static PushDevice? device =
      !kIsWeb && (defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS)
      ? _ChannelDevice()
      : null;

  /// Вкладка из нажатого уведомления — Shell переключается на неё.
  static final tab = ValueNotifier<String?>(null);

  static const _prefs = 'uib_app_push'; // {"platform","token"} — включено на этом телефоне

  /// Порядок: iPhone — APNs; Android — FCM, без сервисов Google — RuStore.
  static const order = ['apns', 'fcm', 'rustore'];

  static Future<Map<String, String>?> _saved() async {
    final raw = (await SharedPreferences.getInstance()).getString(_prefs);
    if (raw == null) return null;
    try {
      return Map<String, String>.from(jsonDecode(raw) as Map);
    } catch (_) {
      return null;
    }
  }

  static Future<void> _save(Map<String, String>? v) async {
    final p = await SharedPreferences.getInstance();
    v == null ? await p.remove(_prefs) : await p.setString(_prefs, jsonEncode(v));
  }

  /// Новый ключ AES-256 в base64 — свой на каждое включение.
  static String newKey([Random? rnd]) {
    final r = rnd ?? Random.secure();
    return base64Encode(List<int>.generate(32, (_) => r.nextInt(256)));
  }

  /// Какими сервисами можно слать на этот телефон: есть и в сборке, и на сервере.
  static Future<List<String>> platforms(Api api) async {
    final d = device;
    if (d == null) return const [];
    final here = await d.available();
    if (!here.values.any((v) => v)) return const []; // сборка без пушей — сервер не спрашиваем
    final server = Map<String, dynamic>.from((await api.get('/push/app'))['platforms'] as Map);
    return [
      for (final p in order)
        if (here[p] == true && server[p] == true) p,
    ];
  }

  static Future<String?> platform(Api api) async {
    final all = await platforms(api);
    return all.isEmpty ? null : all.first;
  }

  /// on / off / denied (запрещены в настройках телефона) / unsupported.
  static Future<String> state(Api api) async {
    try {
      if (await _saved() != null) return 'on';
      if (await platform(api) == null) return 'unsupported';
      return 'off';
    } catch (_) {
      return 'unsupported';
    }
  }

  /// Включить: разрешение → токен → свой ключ → сервер. → новое состояние.
  static Future<String> enable(Api api) async {
    final d = device;
    final all = await platforms(api);
    if (d == null || all.isEmpty) return 'unsupported';
    if (!await d.permission()) return 'denied';
    // Google не выдал токен (телефон без его сервисов) — пробуем RuStore
    String? p, token;
    Object? error;
    for (final candidate in all) {
      try {
        token = await d.token(candidate);
      } catch (e) {
        error = e;
        continue;
      }
      if (token != null && token.isNotEmpty) {
        p = candidate;
        break;
      }
    }
    if (p == null || token == null) {
      throw PushError(
        error is PlatformException ? (error.message ?? 'Телефон не выдал токен') : 'Телефон не выдал токен',
      );
    }
    final key = newKey();
    await d.setKey(key);
    await api.post('/push/app/subscribe', {'platform': p, 'token': token, 'key': key});
    await _save({'platform': p, 'token': token});
    return 'on';
  }

  /// Выключить: сервер забывает токен, телефон — ключ.
  static Future<String> disable(Api api) async {
    final s = await _saved();
    if (s != null) {
      try {
        await api.post('/push/app/unsubscribe', {'platform': s['platform'], 'token': s['token']});
      } finally {
        await _forgetLocal(s['platform']);
      }
    }
    return 'off';
  }

  /// Выход из аккаунта: отписаться, пока вход ещё действует; сеть не ответила —
  /// всё равно стереть ключ (сервер сам забудет токен, когда сервис скажет «нет такого»).
  static Future<void> forget(Api api) async {
    if (device == null) return;
    try {
      await disable(api);
    } catch (_) {
      await forgetLocal();
    }
  }

  /// Удалили данные: на сервере записи уже стёрты — только телефон.
  static Future<void> forgetLocal() async {
    if (device == null) return;
    try {
      final s = await _saved();
      if (s != null) await _forgetLocal(s['platform']); // не включали — стирать нечего
    } catch (_) {}
  }

  static Future<void> _forgetLocal(String? platform) async {
    try {
      await _save(null);
    } finally {
      try {
        await device?.clear(platform);
      } catch (_) {}
    }
  }

  /// При запуске: включено, а токен сменился (сервис выдал новый, пока
  /// приложение было закрыто) — сообщить серверу с прежним ключом нельзя, он
  /// только на телефоне, поэтому заново: новый ключ и новый токен.
  static Future<void> refresh(Api api) async {
    final s = await _saved();
    final d = device;
    if (s == null || d == null) return;
    try {
      if (!await d.granted()) return;
      final token = await d.token(s['platform']!);
      if (token != null && token.isNotEmpty && token != s['token']) await _reRegister(api, s['platform']!, token);
    } catch (_) {}
  }

  static Future<void> _reRegister(Api api, String platform, String token) async {
    final key = newKey();
    await device!.setKey(key);
    await api.post('/push/app/subscribe', {'platform': platform, 'token': token, 'key': key});
    await _save({'platform': platform, 'token': token});
  }

  static bool _listening = false;

  /// Shell при запуске: нажатое уведомление, смена токена.
  static Future<void> start(Api api) async {
    final d = device;
    if (d == null) return;
    try {
      if (!_listening) {
        _listening = true;
        d.listen(
          onTab: (t) {
            tab.value = t;
            unawaited(d.takeTab().catchError((_) => null)); // уже открыли — запомненное не нужно
          },
          onToken: (platform, token) async {
            final s = await _saved();
            if (s != null && s['platform'] == platform && s['token'] != token) {
              try {
                await _reRegister(api, platform, token);
              } catch (_) {}
            }
          },
        );
      }
      final t = await d.takeTab();
      if (t != null && t.isNotEmpty) tab.value = t;
    } catch (_) {}
    unawaited(refresh(api));
  }
}

class PushError implements Exception {
  final String message;
  const PushError(this.message);
  @override
  String toString() => message;
}

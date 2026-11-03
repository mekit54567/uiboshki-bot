// Где телефон хранит токен входа (ревью 03.11): iPhone — Keychain, Android —
// Keystore (flutter_secure_storage), а не обычный файл shared_preferences,
// который на Android лежит открытым текстом. Веб (PWA /app-flutter, робот,
// демо на сайте) — как раньше: `flutter.uib_token` в localStorage, его читают
// app/web/index.html и сайт.
//
// Переезд тихий: старый токен из shared_preferences при первом запуске новой
// версии переносится в хранилище и стирается из файла — заново входить не надо.
// Хранилище подвело (старый Android, сброшенный Keystore, тесты без плагина) —
// токен остаётся в shared_preferences, вход не теряется.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Хранилище с ключами — тесты подменяют его своим.
abstract class SecureBox {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

/// В памяти — для тестов (настоящий плагин в тестах не отвечает).
class MemoryBox implements SecureBox {
  final data = <String, String>{};
  @override
  Future<String?> read(String key) async => data[key];
  @override
  Future<void> write(String key, String value) async => data[key] = value;
  @override
  Future<void> delete(String key) async => data.remove(key);
}

class _SystemBox implements SecureBox {
  static const _s = FlutterSecureStorage(
    // только этот телефон (без iCloud), читается и в фоне после первой разблокировки
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
  );

  /// Хранилище зависло — не держим запуск: запасной путь через файл.
  static const _wait = Duration(seconds: 3);

  @override
  Future<String?> read(String key) => _s.read(key: key).timeout(_wait);
  @override
  Future<void> write(String key, String value) => _s.write(key: key, value: value).timeout(_wait);
  @override
  Future<void> delete(String key) => _s.delete(key: key).timeout(_wait);
}

class TokenStore {
  /// Отметка в shared_preferences: токен этой установки лежит в хранилище.
  /// Keychain на iPhone переживает удаление приложения, а shared_preferences —
  /// нет: нет отметки, а в Keychain что-то есть — это вход прошлой установки,
  /// его стираем (удалил приложение — вышел, как было раньше).
  static const marker = 'uib_token_secure';

  /// null — системное хранилище; тесты ставят своё.
  static SecureBox? box;

  /// Веб — без хранилища. Тесты могут включить путь телефона через [box].
  static bool get _secure => box != null || !kIsWeb;
  static SecureBox get _box => box ??= _SystemBox();

  static Future<String?> read(String key) async {
    final prefs = await SharedPreferences.getInstance();
    if (!_secure) return prefs.getString(key);
    try {
      final old = prefs.getString(key);
      if (prefs.getBool(marker) != true) {
        // первая версия с хранилищем или новая установка
        await _box.delete(key);
        if (old == null) {
          await prefs.setBool(marker, true);
          return null;
        }
      } else {
        final t = await _box.read(key);
        if (t != null) return t;
        if (old == null) return null;
      }
      // переносим вход из файла в хранилище
      await _box.write(key, old);
      if (await _box.read(key) != old) return old; // не записалось — остаёмся в файле
      await prefs.setBool(marker, true);
      await prefs.remove(key);
      return old;
    } on PlatformException {
      return prefs.getString(key);
    } on MissingPluginException {
      return prefs.getString(key);
    } on TimeoutException {
      return prefs.getString(key);
    }
  }

  static Future<void> write(String key, String? value) async {
    final prefs = await SharedPreferences.getInstance();
    if (_secure) {
      try {
        if (value == null) {
          await _box.delete(key);
        } else {
          await _box.write(key, value);
          await prefs.setBool(marker, true);
        }
        await prefs.remove(key);
        return;
      } on PlatformException {
        // ниже — запасной путь
      } on MissingPluginException {
        // ниже — запасной путь
      } on TimeoutException {
        // ниже — запасной путь
      }
    }
    if (value == null) {
      await prefs.remove(key);
    } else {
      await prefs.setString(key, value);
    }
  }
}

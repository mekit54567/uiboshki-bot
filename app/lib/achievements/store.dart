// Ачивки на телефоне: что открыто и когда, дни с заходами, баллы для «Плюс
// балл», сроки для «Заранее». Пока всё в памяти телефона (SharedPreferences);
// рейтинг группы и «в чат группы» — когда ачивки переедут на сервер.
// Большая часть ачивок ловится по ответам API ([AchStore.onApi]), как
// события статистики на сервере (stats.EVENT_PATHS), — экраны не трогаем.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../plus/plus.dart';
import 'catalog.dart';

String _day(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

class AchStore {
  AchStore._();

  static const _key = 'uib_ach', _daysKey = 'uib_ach_days', _scoresKey = 'uib_ach_scores';
  static const _calmKey = 'uib_ach_calm';

  /// Открытые ачивки: id → когда.
  static final got = ValueNotifier<Map<String, DateTime>>({});

  /// Новая ачивка — оболочка показывает плашку (achievements_ui.dart).
  static void Function(Achievement a)? onUnlock;

  /// «Показать где»: оболочка открывает вкладку.
  static void Function(int tab)? openTab;

  static Future<void>? _loading;

  /// Сроки из последнего списка «Сдать»: id → «2026-10-15».
  static final _dues = <int, String>{};

  static Future<void> load() => _loading ??= _load();

  static Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    final m = <String, DateTime>{};
    if (raw != null) {
      try {
        (jsonDecode(raw) as Map).forEach((k, v) {
          if (achievementById('$k') != null) m['$k'] = DateTime.fromMillisecondsSinceEpoch(v as int);
        });
      } catch (_) {}
    }
    got.value = m;
  }

  /// Для тестов: забыть, что было загружено.
  @visibleForTesting
  static void reset() {
    _loading = null;
    _dues.clear();
    got.value = {};
    onUnlock = null;
    openTab = null;
  }

  static bool has(String id) => got.value.containsKey(id);

  /// Открыть ачивку; true — новая.
  static Future<bool> unlock(String id, {DateTime? at}) async {
    final a = achievementById(id);
    if (a == null) return false;
    await load();
    if (has(id)) return false;
    final when = at ?? DateTime.now();
    got.value = {...got.value, id: when};
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode({for (final e in got.value.entries) e.key: e.value.millisecondsSinceEpoch}));
    onUnlock?.call(a);
    PlusBonus.onUnlock(a.rank); // закрыл ранг — дни «Капибары+» (plus/plus.dart)
    return true;
  }

  /// Заход в приложение: дни для «Неделя в кармане», «Месяц с Капибарой»,
  /// пятница, 13-е.
  static Future<void> visit(DateTime at) async {
    final prefs = await SharedPreferences.getInstance();
    final days = {...prefs.getStringList(_daysKey) ?? const <String>[]};
    if (days.add(_day(at))) {
      // хватит последних 60 дней: месяц — это 30 разных дней, неделя — эта
      final list = days.toList()..sort();
      await prefs.setStringList(_daysKey, list.length > 60 ? list.sublist(list.length - 60) : list);
    }
    if (at.weekday == DateTime.friday && at.day == 13) await unlock('fri13', at: at);
    if (days.length >= 30) await unlock('month', at: at);
    final monday = DateTime(at.year, at.month, at.day - (at.weekday - 1));
    if (at.weekday >= DateTime.friday &&
        [for (var i = 0; i < 5; i++) _day(DateTime(monday.year, monday.month, monday.day + i))].every(days.contains)) {
      await unlock('week5', at: at);
    }
  }

  /// Коснулся капибары на «Сегодня».
  static Future<void> capyTouched(DateTime at) async {
    if (at.hour == 22 && at.minute == 22) await unlock('t2222', at: at);
  }

  /// Удачный ответ API: по пути и ответу — какая ачивка.
  static Future<void> onApi(String method, String path, Object? body, Object? result, DateTime at) async {
    final p = path.split('?').first;
    try {
      if (p.startsWith('/summary/') && result is Map && result['summary'] != null) await unlock('summary');
      if (method == 'GET') {
        if (p == '/deadlines' && result is Map) _rememberDues(result['items']);
        if (p == '/sdo/grades' && result is Map) await _grades(result['courses']);
        if (p.startsWith('/sdo/grades/') && result is Map) await _course(result);
        if (p.startsWith('/target/2/')) await unlock('teacher');
        if (RegExp(r'^/files/\d+/page/').hasMatch(p)) await unlock('found');
      } else if (method == 'POST') {
        if (p == '/sdo/connect') await unlock('sdo');
        if (p.startsWith('/sdo/goal/')) await unlock('goal');
        if (p == '/chat') await unlock('ai');
        if (p == '/notify' && body is Map && body['prefs'] is Map) {
          final prefs = body['prefs'] as Map;
          final on =
              prefs['lessons'] == true || prefs.entries.any((e) => '${e.key}'.startsWith('remind_') && e.value is int);
          if (on) await unlock('remind');
        }
        if (p == '/sdo/submit' && body is Map) await _submitted(body['deadline_id'], at);
      }
    } catch (_) {
      // ачивка — не главное: странный ответ экран не ломает
    }
  }

  static void _rememberDues(Object? items) {
    if (items is! List) return;
    for (final d in items) {
      if (d is Map && d['id'] is int && '${d['due_date'] ?? ''}'.isNotEmpty) _dues[d['id'] as int] = '${d['due_date']}';
    }
  }

  /// Сдал из приложения: «Сдано из Капибары»; за 3 дня до срока — «Заранее»;
  /// три сдачи подряд не в последний день — «Ни одного „горит“».
  static Future<void> _submitted(Object? id, DateTime at) async {
    await unlock('submit', at: at);
    final due = DateTime.tryParse(_dues[id] ?? '');
    if (due == null) return;
    final left = DateTime(due.year, due.month, due.day).difference(DateTime(at.year, at.month, at.day)).inDays;
    if (left >= 3) await unlock('early', at: at);
    final prefs = await SharedPreferences.getInstance();
    final calm = left >= 1 ? (prefs.getInt(_calmKey) ?? 0) + 1 : 0;
    await prefs.setInt(_calmKey, calm);
    if (calm >= 3) await unlock('calm', at: at);
  }

  /// Список предметов: вошёл в СДО, баллы выросли, все работы зачтены.
  static Future<void> _grades(Object? courses) async {
    if (courses is! List || courses.isEmpty) return;
    await unlock('sdo');
    final prefs = await SharedPreferences.getInstance();
    final was = <String, dynamic>{};
    try {
      was.addAll(Map<String, dynamic>.from(jsonDecode(prefs.getString(_scoresKey) ?? '{}') as Map));
    } catch (_) {}
    final now = <String, num>{};
    var plus = false;
    for (final c in courses) {
      if (c is! Map || c['score'] is! num) continue;
      final id = '${c['id']}', score = c['score'] as num;
      now[id] = score;
      final before = was[id];
      if (before is num && score > before) plus = true;
      if (_allPassed(c)) await unlock('clean');
    }
    await prefs.setString(_scoresKey, jsonEncode(now));
    if (plus) await unlock('plus');
  }

  static bool _allPassed(Map c) {
    final total = c['works_total'], passed = c['works_passed'];
    return total is int && total > 0 && passed == total;
  }

  /// Экран предмета: цель «автомат» набрана, четыре лекции подряд без пропуска.
  static Future<void> _course(Map c) async {
    final goal = c['goal'];
    if (goal is Map && goal['mode'] == 'auto' && goal['status'] == 'done') await unlock('auto');
    if (_allPassed(c)) await unlock('clean');
    final lectures = (c['attendance'] is Map ? (c['attendance'] as Map)['lectures'] : null) as List? ?? const [];
    var run = 0;
    for (final l in lectures) {
      final st = l is Map ? l['status'] : null;
      if (st == 'future' || st == 'wait') continue; // ещё не известно — серию не рвёт
      run = st == 'ok' ? run + 1 : 0;
      if (run >= 4) {
        await unlock('streak');
        return;
      }
    }
  }
}

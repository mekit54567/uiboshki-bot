// «Капибара+» без экрана: бонусные дни за закрытый ранг ачивок и «кто позвал»
// для PWA (/app?ref=<код>). Сервер — webapp/routes/billing.py, referrals.py.
// На iPhone платного нет вовсе (правила App Store вне США) — ни запросов, ни плашек.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../achievements/catalog.dart';
import '../achievements/store.dart';
import '../achievements/ui.dart' show appNavigator;
import '../api/api.dart';
import '../api/models.dart' show plural;
import '../widgets/common.dart';

class PlusBonus {
  PlusBonus._();

  static const _refKey = 'uib_ref', _ranksKey = 'uib_plus_ranks';

  /// Чем спрашивать сервер; ставит оболочка после входа (shell.dart).
  static Api? api;

  /// Ранги, которые уже спрашивали в этот запуск (ответ «рано» — спросим в следующий).
  static final _tried = <Rank>{};

  /// Платное видно не на iPhone (Api.platform == 'ios' — сборка для App Store).
  static bool get allowed => Api.platform != 'ios';

  @visibleForTesting
  static void reset() {
    api = null;
    _tried.clear();
  }

  // ── «кто позвал»: /app?ref=<код> в PWA ──

  /// При запуске: адрес открыт с ?ref= — запомнить код до входа.
  static Future<void> rememberRef([Uri? at]) async {
    final code = (at ?? Uri.base).queryParameters['ref']?.trim() ?? '';
    if (code.isEmpty || code.length > 64) return;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_refKey, code);
    } catch (_) {}
  }

  /// После входа: отдать код серверу один раз и забыть. Нет сети — попробуем
  /// при следующем запуске.
  static Future<void> sendRef(Api api) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final code = prefs.getString(_refKey);
      if (code == null || code.isEmpty) return;
      try {
        await api.post('/plus/ref', {'code': code});
      } on ApiError catch (e) {
        if (e.server || e.status == 403) return; // сервер упал или согласия ещё нет — не забываем
      }
      await prefs.remove(_refKey);
    } catch (_) {
      // нет сети — код остаётся до следующего раза
    }
  }

  // ── бонус за ранг ──

  /// Ранги, за которые сервер дал дни или сказал «уже получено»: больше не спрашиваем.
  static Future<Set<String>> _done() async {
    final prefs = await SharedPreferences.getInstance();
    try {
      return {for (final x in jsonDecode(prefs.getString(_ranksKey) ?? '[]') as List) '$x'};
    } catch (_) {
      return {};
    }
  }

  static Future<void> _markDone(Rank r) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_ranksKey, jsonEncode([...await _done(), r.name]));
  }

  /// Все ачивки ранга открыты?
  static bool complete(Rank r) => achievements.where((a) => a.rank == r).every((a) => AchStore.has(a.id));

  /// Новая ачивка (store.dart): если ранг теперь закрыт — забрать дни.
  static void onUnlock(Rank r) => unawaited(claim(r).catchError((_) {}));

  /// При запуске (оболочка): закрытые ранги, за которые дней ещё не дали.
  static Future<void> checkAll() async {
    for (final r in Rank.values) {
      await claim(r);
    }
  }

  /// Ранг закрыт и ещё не получен — POST /plus/rank. 200 — плашка
  /// «+N дней Капибары+»; 400 «уже получен» — запомнить навсегда; другой
  /// 400 (рано, мало дней с заходами) — молча, спросим в следующий запуск.
  static Future<void> claim(Rank r) async {
    final api = PlusBonus.api;
    if (api == null || !allowed || _tried.contains(r) || !complete(r)) return;
    _tried.add(r); // до первого await: плашка ачивки и запуск не спросят дважды
    if ((await _done()).contains(r.name)) return;
    try {
      final res = await api.post('/plus/rank', {'rank': r.name});
      await _markDone(r);
      final days = res is Map && res['days'] is int ? res['days'] as int : 0;
      final overlay = appNavigator.currentState?.overlay;
      if (days > 0 && overlay != null) {
        toastOn(
          overlay,
          '+$days ${plural(days, 'день', 'дня', 'дней')} Капибары+ за ранг «${r.title}»',
          kind: ToastKind.done,
        );
      }
    } on ApiError catch (e) {
      if (e.status == 400 && (e.message.contains('уже') || e.message.contains('нет такого'))) await _markDone(r);
    } catch (_) {
      // нет сети — спросим в следующий запуск
    }
  }
}

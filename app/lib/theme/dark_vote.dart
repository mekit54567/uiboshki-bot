// Переход на новый дизайн (шаг 9, Никита 18.11, вариант «Сравнить, потом
// голос»). Сервер говорит «новое — основной вид» (/api/meta → design3 «new»
// или «on») — один раз переводим в «Новое» всех, кто был в «Классике».
// Светлым ничего не показываем. Кто открывает приложение в тёмной, видит
// экран «Мы обновили дизайн» (dark_intro.dart): «Попробовать новую» или
// «Оставить прежнюю». Дальше на «Сегодня» по одной карточке:
//  • пробует новую 3 тёмных дня — «Как тебе новая тёмная?»: нравится или
//    сравнить с прежней;
//  • сравнивает ещё 3 тёмных дня — «Какая тёмная лучше?»: что выбрал, то и
//    осталось, это и есть голос;
//  • оставил прежнюю — через неделю один раз «Попробуешь новую?».
// Голос уходит на сервер (POST /api/design/vote), Никита видит счёт в /stats.
// Сам поменял тёмную в «Оформлении» — опрос заканчивается, голос — выбранное.
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'look.dart';

/// Что спросить на «Сегодня»: как тебе новая, какая лучше, попробуешь ли.
enum DarkAsk { howNew, which, retry }

class DarkVote {
  DarkVote._();

  /// Сколько тёмных дней пожить с темой до вопроса; через сколько дней
  /// после «Оставить прежнюю» предложить ещё раз.
  static const daysToAsk = 3, daysToRetry = 7;

  /// intro — показать экран; new — пробует новую; compare — сравнивает с
  /// прежней; old — оставил прежнюю; done — ответил. null — опроса нет.
  static final stage = ValueNotifier<String?>(null);
  static final ask = ValueNotifier<DarkAsk?>(null);

  /// Поменять вид (UiboApp._setLook) и нынешний вид.
  static Future<void> Function(Look)? setLook;
  static Look Function()? look;

  /// Отправить голос на сервер (POST /design/vote); ошибка — пошлём позже.
  static Future<void> Function(String choice)? send;

  static const _kStage = 'uib_dark_stage',
      _kDays = 'uib_dark_days',
      _kLast = 'uib_dark_last',
      _kSince = 'uib_dark_since',
      _kVote = 'uib_dark_vote',
      _kSent = 'uib_dark_sent';
  static const _active = {'new', 'compare', 'old'};

  /// Как называлась прежняя тёмная.
  static String oldName(Look l) => l.dark == DarkTheme.library ? 'Библиотека' : 'Глубина';

  /// Новая тёмная — «Ночная тетрадь».
  static Look applyNew(Look l) => l.copyWith(fresh: true, freshDepth: false);

  /// Прежняя тёмная: «Глубина» живёт и в «Новом» (запасной выход), а
  /// «Библиотека» — только в «Классике».
  static Look applyOld(Look l) =>
      l.dark == DarkTheme.library ? l.copyWith(fresh: false) : l.copyWith(fresh: true, freshDepth: true);

  static String _day(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  /// Один раз, когда сервер сказал «новое по умолчанию»: кто был в
  /// «Классике» — в «Новое». Кто уже пользовался приложением (прошёл
  /// знакомство), тому при первом тёмном запуске — экран перехода.
  static Future<Look> migrate(SharedPreferences p, Look look, {required String design3}) async {
    if (!freshByDefault(design3) || p.getBool('uib_fresh_moved') == true) return look;
    await p.setBool('uib_fresh_moved', true);
    if (p.getBool('uib_look_fresh') == true) return look; // уже в новом — спрашивать не о чем
    await p.setBool('uib_look_fresh', true);
    if (p.getBool('uib_toured') == true) await p.setString(_kStage, 'intro');
    return look.copyWith(fresh: true);
  }

  /// Прочитать, где человек в опросе, и дослать голос, если не ушёл.
  static Future<void> load(SharedPreferences p, DateTime today) async {
    stage.value = p.getString(_kStage);
    ask.value = _askFor(p, today);
    final vote = p.getString(_kVote);
    if (vote != null && p.getBool(_kSent) != true) await _send(p, vote);
  }

  static DarkAsk? _askFor(SharedPreferences p, DateTime today) {
    final days = p.getInt(_kDays) ?? 0;
    switch (p.getString(_kStage)) {
      case 'new':
        return days >= daysToAsk ? DarkAsk.howNew : null;
      case 'compare':
        return days >= daysToAsk ? DarkAsk.which : null;
      case 'old':
        final since = DateTime.tryParse(p.getString(_kSince) ?? '');
        return since != null && today.difference(since).inDays >= daysToRetry ? DarkAsk.retry : null;
    }
    return null;
  }

  /// Приложение открыто в тёмной: засчитать день (раз в сутки).
  static Future<void> darkDay(DateTime today) async {
    final s = stage.value;
    if (s != 'new' && s != 'compare') return;
    final p = await SharedPreferences.getInstance();
    final d = _day(today);
    if (p.getString(_kLast) == d) return;
    await p.setString(_kLast, d);
    await p.setInt(_kDays, (p.getInt(_kDays) ?? 0) + 1);
    ask.value = _askFor(p, today);
  }

  static Future<void> _go(String next, {Look Function(Look)? change, String? vote, DateTime? today}) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_kStage, next);
    await p.setInt(_kDays, 0);
    await p.remove(_kLast);
    if (today != null) await p.setString(_kSince, _day(today));
    stage.value = next;
    ask.value = null;
    final l = look?.call();
    if (change != null && l != null) {
      _own = true;
      try {
        await setLook?.call(change(l));
      } finally {
        _own = false;
      }
    }
    if (vote != null) {
      await p.setString(_kVote, vote);
      await p.setBool(_kSent, false);
      await _send(p, vote);
    }
  }

  static bool _own = false;

  static Future<void> _send(SharedPreferences p, String vote) async {
    final f = send;
    if (f == null) return;
    try {
      await f(vote);
      await p.setBool(_kSent, true);
    } catch (_) {
      // нет сети — дошлём при следующем запуске (load)
    }
  }

  // ── ответы ──

  /// Экран перехода: «Попробовать новую».
  static Future<void> tryNew() => _go('new', change: applyNew);

  /// Экран перехода: «Оставить прежнюю» — через неделю спросим ещё раз.
  static Future<void> keepOld(DateTime today) => _go('old', change: applyOld, today: today);

  /// «Как тебе новая тёмная?» — «Нравится новая».
  static Future<void> likeNew() => _go('done', vote: 'new');

  /// «Как тебе новая тёмная?» — «Сравнить»: пара дней с прежней.
  static Future<void> compare() => _go('compare', change: applyOld);

  /// «Какая тёмная лучше?» — что выбрал, то и осталось.
  static Future<void> pick({required bool fresh}) =>
      _go('done', change: fresh ? applyNew : applyOld, vote: fresh ? 'new' : 'old');

  /// «Попробуешь новую тёмную?» — да: снова пробует новую, потом тем же путём.
  static Future<void> retry() => _go('new', change: applyNew);

  /// «Попробуешь новую тёмную?» — «Нет, спасибо»: голос за прежнюю.
  static Future<void> stayOld() => _go('done', vote: 'old');

  /// Сам поменял вид или тёмную в «Оформлении»: опрос окончен. Пока
  /// сравнивал — голос за выбранное; до экрана перехода — без голоса.
  static Future<void> manual(Look before, Look after) async {
    if (_own) return;
    final s = stage.value;
    if (s == null || s == 'done') return;
    if (before.fresh == after.fresh && before.freshDepth == after.freshDepth) return;
    await _go('done', vote: _active.contains(s) ? (after.fresh && !after.freshDepth ? 'new' : 'old') : null);
  }
}

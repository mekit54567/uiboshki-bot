// Переход на новый дизайн (шаг 9, Никита 18.11, «Сравнить, потом голос»):
// сервер говорит «new» — всех из «Классики» один раз переводим в «Новое»;
// у кого тёмная — экран «Мы обновили дизайн», потом на «Сегодня» «Как тебе
// новая тёмная?», «Какая тёмная лучше?» и голос на сервер. Светлым ничего.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/main.dart';
import 'package:uiboshki/screens/dark_intro.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/theme/dark_vote.dart';
import 'package:uiboshki/theme/look.dart';

import 'fake_api.dart';
import 'fresh_look_test.dart' show meta, styleOf;
import 'util.dart';

Future<SharedPreferences> _prefs(Map<String, Object> v) async {
  SharedPreferences.setMockInitialValues(v);
  DarkVote.stage.value = null;
  DarkVote.ask.value = null;
  return SharedPreferences.getInstance();
}

/// Опрос без приложения: вид меняется здесь, голоса копятся в [votes].
List<String> _wire(Look start, {bool fail = false}) {
  var look = start;
  final votes = <String>[];
  DarkVote.look = () => look;
  DarkVote.setLook = (l) async => look = l;
  DarkVote.send = (c) async {
    if (fail) throw Exception('нет сети');
    votes.add(c);
  };
  return votes;
}

void main() {
  setUpAll(loadFonts);

  test('переход: один раз, только по слову сервера; экран — тем, кто уже пользовался', () async {
    var p = await _prefs({'uib_toured': true, 'uib_look_fresh': false});
    var l = await DarkVote.migrate(p, Look.classic, design3: 'opt');
    expect(l.fresh, isFalse, reason: 'старое «по выбору» — никого не трогаем');
    l = await DarkVote.migrate(p, Look.classic, design3: 'new');
    expect(l.fresh, isTrue);
    expect(p.getBool('uib_look_fresh'), isTrue);
    expect(p.getString('uib_dark_stage'), 'intro');
    // вернулся в «Классику» сам — второй раз не переводим
    await p.setBool('uib_look_fresh', false);
    expect((await DarkVote.migrate(p, Look.classic, design3: 'new')).fresh, isFalse);

    p = await _prefs({'uib_toured': true, 'uib_look_fresh': true});
    await DarkVote.migrate(p, const Look(fresh: true), design3: 'new');
    expect(p.getString('uib_dark_stage'), isNull, reason: 'уже в новом — спрашивать не о чем');

    p = await _prefs({});
    expect((await DarkVote.migrate(p, Look.classic, design3: 'on')).fresh, isTrue);
    expect(p.getString('uib_dark_stage'), isNull, reason: 'новенький — прежнего вида не видел');
    expect(Look.fromPrefs(await _prefs({'uib_design3': 'new'})).fresh, isTrue);
    expect(Look.fromPrefs(await _prefs({'uib_design3': 'opt'})).fresh, isFalse);
  });

  test('попробовал новую → 3 тёмных дня → сравнить → 3 дня → какая лучше → голос', () async {
    final p = await _prefs({'uib_dark_stage': 'intro'});
    final votes = _wire(const Look(fresh: true));
    final d = DateTime(2026, 11, 18, 20);
    await DarkVote.load(p, d);
    await DarkVote.tryNew();
    expect(DarkVote.look!().freshDepth, isFalse);
    await DarkVote.darkDay(d);
    await DarkVote.darkDay(d.add(const Duration(hours: 2))); // тот же день — не считается
    await DarkVote.darkDay(d.add(const Duration(days: 1)));
    expect(DarkVote.ask.value, isNull);
    await DarkVote.darkDay(d.add(const Duration(days: 3)));
    expect(DarkVote.ask.value, DarkAsk.howNew);
    await DarkVote.compare();
    expect(DarkVote.look!(), const Look(fresh: true, freshDepth: true), reason: 'вернули «Глубину» в новом виде');
    expect(DarkVote.ask.value, isNull);
    for (var i = 4; i < 7; i++) {
      await DarkVote.darkDay(d.add(Duration(days: i)));
    }
    expect(DarkVote.ask.value, DarkAsk.which);
    await DarkVote.pick(fresh: false);
    expect(votes, ['old']);
    expect(DarkVote.stage.value, 'done');
    expect(DarkVote.look!().freshDepth, isTrue);
    await DarkVote.darkDay(d.add(const Duration(days: 20)));
    expect(DarkVote.ask.value, isNull);
  });

  test('оставил прежнюю — через неделю «Попробуешь новую?»; «Нет, спасибо» — голос за прежнюю', () async {
    final p = await _prefs({'uib_dark_stage': 'intro'});
    final votes = _wire(const Look(fresh: true));
    final d = DateTime(2026, 11, 18, 20);
    await DarkVote.keepOld(d);
    expect(DarkVote.look!().freshDepth, isTrue);
    await DarkVote.load(p, d.add(const Duration(days: 6)));
    expect(DarkVote.ask.value, isNull);
    await DarkVote.load(p, d.add(const Duration(days: 7)));
    expect(DarkVote.ask.value, DarkAsk.retry);
    await DarkVote.stayOld();
    expect(votes, ['old']);
  });

  test('«Библиотека» живёт только в «Классике»: прежняя — это «Классика»', () async {
    await _prefs({'uib_dark_stage': 'intro'});
    _wire(const Look(fresh: true, dark: DarkTheme.library));
    expect(DarkVote.oldName(DarkVote.look!()), 'Библиотека');
    await DarkVote.keepOld(DateTime(2026, 11, 18));
    expect(DarkVote.look!().fresh, isFalse);
    await DarkVote.retry();
    expect(DarkVote.look!().fresh, isTrue);
  });

  test('сам поменял тёмную в «Оформлении» — опрос окончен, голос за выбранное', () async {
    await _prefs({'uib_dark_stage': 'new'});
    final votes = _wire(const Look(fresh: true));
    final p = await SharedPreferences.getInstance();
    await DarkVote.load(p, DateTime(2026, 11, 18));
    await DarkVote.manual(const Look(fresh: true), const Look(fresh: true, paper: Paper.cell));
    expect(DarkVote.stage.value, 'new', reason: 'бумага — не про тёмную');
    await DarkVote.manual(const Look(fresh: true), const Look(fresh: true, freshDepth: true));
    expect(DarkVote.stage.value, 'done');
    expect(votes, ['old']);

    await _prefs({'uib_dark_stage': 'intro'});
    final none = _wire(const Look(fresh: true));
    await DarkVote.load(await SharedPreferences.getInstance(), DateTime(2026, 11, 18));
    await DarkVote.manual(const Look(fresh: true), Look.classic);
    expect(DarkVote.stage.value, 'done');
    expect(none, isEmpty, reason: 'до экрана — без голоса');
  });

  test('голос без сети — дошлём при следующем запуске', () async {
    final p = await _prefs({'uib_dark_stage': 'new'});
    _wire(const Look(fresh: true), fail: true);
    await DarkVote.load(p, DateTime(2026, 11, 18));
    await DarkVote.likeNew();
    expect(p.getBool('uib_dark_sent'), isFalse);
    final votes = _wire(const Look(fresh: true));
    await DarkVote.load(p, DateTime(2026, 11, 19));
    expect(votes, ['new']);
    expect(p.getBool('uib_dark_sent'), isTrue);
  });

  Map<String, Object?> fx() => {
    ...meta('new'),
    'POST /api/design/vote': {'ok': true},
  };

  testWidgets('тёмная: экран «Мы обновили дизайн», «Попробовать новую» — «Ночная тетрадь»', (t) async {
    phone(t);
    await _prefs({'uib_toured': true, 'uib_look_fresh': false, 'uib_look_dark': 'depth'});
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: fx()),
        design2: true,
        theme: ThemeChoice.dark,
      ),
    );
    await settle(t);
    expect(find.text('Мы обновили дизайн'), findsOneWidget);
    expect(find.textContaining('прежняя тёмная «Глубина»'), findsOneWidget);
    expect(find.byKey(const Key('intro:paper')), findsOneWidget);
    expect(find.byKey(const Key('intro:night')), findsOneWidget);
    await t.tap(find.byKey(const Key('intro:new')));
    await settle(t);
    expect(find.byType(DarkIntroScreen), findsNothing);
    expect(styleOf(t).fresh, isTrue);
    expect(styleOf(t).p.bg, Palette.night.bg);
    expect(DarkVote.stage.value, 'new');
  });

  testWidgets('«Оставить прежнюю» — новые экраны в «Глубине»', (t) async {
    phone(t);
    await _prefs({'uib_toured': true, 'uib_look_fresh': false});
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: fx()),
        design2: true,
        theme: ThemeChoice.dark,
      ),
    );
    await settle(t);
    await t.tap(find.byKey(const Key('intro:old')));
    await settle(t);
    expect(styleOf(t).fresh, isTrue);
    expect(styleOf(t).p.bg, Palette.depth.bg);
    expect((await SharedPreferences.getInstance()).getBool('uib_look_fresh_depth'), isTrue);
  });

  testWidgets('светлая: ничего не показываем, просто новый вид', (t) async {
    phone(t);
    await _prefs({'uib_toured': true, 'uib_look_fresh': false});
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: fx()),
        design2: true,
        theme: ThemeChoice.light,
      ),
    );
    await settle(t);
    expect(find.byType(DarkIntroScreen), findsNothing);
    expect(styleOf(t).fresh, isTrue);
    expect(styleOf(t).p.bg, Palette.paper.bg);
  });

  testWidgets('карточка на «Сегодня»: «Какая тёмная лучше?» — выбор и голос на сервер', (t) async {
    phone(t);
    await _prefs({
      'uib_toured': true,
      'uib_look_fresh': true,
      'uib_look_fresh_depth': true,
      'uib_fresh_moved': true,
      'uib_dark_stage': 'compare',
      'uib_dark_days': 3,
    });
    final bodies = <String, Object?>{};
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: fx(), bodies: bodies),
        design2: true,
        theme: ThemeChoice.dark,
        look: const Look(fresh: true, freshDepth: true),
      ),
    );
    await settle(t);
    expect(find.text('Какая тёмная лучше?'), findsOneWidget);
    await t.tap(find.byKey(const Key('dark:which:a')));
    await settle(t);
    expect(find.text('Какая тёмная лучше?'), findsNothing);
    expect(bodies['POST /api/design/vote'], {'choice': 'new'});
    expect(styleOf(t).p.bg, Palette.night.bg);
  });

  testWidgets('карточка только в тёмной', (t) async {
    phone(t);
    await _prefs({
      'uib_toured': true,
      'uib_look_fresh': true,
      'uib_fresh_moved': true,
      'uib_dark_stage': 'new',
      'uib_dark_days': 3,
    });
    await t.pumpWidget(
      UiboApp(
        api: fakeApi(overrides: fx()),
        design2: true,
        theme: ThemeChoice.light,
        look: const Look(fresh: true),
      ),
    );
    await settle(t);
    expect(DarkVote.ask.value, DarkAsk.howNew);
    expect(find.text('Как тебе новая тёмная?'), findsNothing);
  });
}

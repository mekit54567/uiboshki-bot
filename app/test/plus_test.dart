// «Капибара+»: плитка в «Ещё» только когда сервер её показывает, экран
// подписки, лист «Позвать друга», ?ref= из PWA и бонус за закрытый ранг.
// Данные выдуманные, ничьих настоящих.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/achievements/catalog.dart';
import 'package:uiboshki/achievements/store.dart';
import 'package:uiboshki/achievements/ui.dart' show appNavigator;
import 'package:uiboshki/api/api.dart';
import 'package:uiboshki/plus/plus.dart';
import 'package:uiboshki/plus/plus_screen.dart';
import 'package:uiboshki/screens/more.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

const _plus = {
  'hidden': false,
  'active': true,
  'until': '2026-11-14',
  'founder': true,
  'prices': [
    {'plan': 'month', 'title': 'Месяц', 'days': 30, 'price': 149, 'full': 199, 'founder': true},
    {'plan': 'half', 'title': 'Полгода', 'days': 182, 'price': 899, 'full': 899, 'founder': false},
  ],
  'provider': 'yookassa',
  'pay_url': 'https://www.uiboshki.ru/plus?k=demo',
  'offer_url': 'https://www.uiboshki.ru/offer',
  'invite': {
    'link': 'https://t.me/UiboshkiBot?start=ref_demo1',
    'share_text': 'Капибара — расписание и дедлайны',
    'share_image': '',
    'came': 3,
    'rewarded': 1,
    'bonus_days': 7,
    'friend_days': 3,
    'ranks': {
      'dawn': {'days': 3, 'need_days': 1, 'claimed': true},
      'noon': {'days': 5, 'need_days': 7, 'claimed': false},
      'dusk': {'days': 7, 'need_days': 14, 'claimed': false},
      'midnight': {'days': 14, 'need_days': 21, 'claimed': false},
    },
  },
};

const _invite = {
  'link': 'https://t.me/UiboshkiBot?start=ref_demo1',
  'share_text': 'Капибара — расписание и дедлайны',
  'share_image': '',
  'tg_share': 'https://t.me/share/url?url=https%3A%2F%2Ft.me%2FUiboshkiBot%3Fstart%3Dref_demo1',
  'came': 3,
  'rewarded': 1,
  'bonus_days': 7,
  'friend_days': 3,
};

Widget _more(Api api) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(
    home: Scaffold(
      body: MoreScreen(api: api, onFont: (_) {}, onLogout: () {}),
    ),
  ),
);

Widget _host(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  child: MaterialApp(navigatorKey: appNavigator, home: child),
);

/// Api с ответом /plus/rank: код и тело; requests — что спрашивали.
Api _rankApi(int code, Map body, List<String> requests) => Api(
  client: MockClient((req) async {
    requests.add('${req.method} ${req.url.path} ${req.body}');
    return http.Response.bytes(utf8.encode(jsonEncode(body)), code, headers: {'content-type': 'application/json'});
  }),
)..token = 't';

/// Список экрана подписки (под ним — «Ещё»).
Finder _list() => find.descendant(of: find.byType(PlusScreen), matching: find.byType(Scrollable)).first;

Future<void> _see(WidgetTester t, String key) async {
  await t.scrollUntilVisible(find.byKey(Key(key)), 200, scrollable: _list());
  await settle(t);
}

Future<void> _openAll(Rank r) async {
  for (final a in achievements.where((a) => a.rank == r)) {
    await AchStore.unlock(a.id);
  }
}

void main() {
  final opened = <Uri>[];
  final shared = <String>[];
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    AchStore.reset();
    PlusBonus.reset();
    opened.clear();
    shared.clear();
    PlusLinks.open = (u) async {
      opened.add(u);
      return true;
    };
    PlusLinks.share = (text, _) async => shared.add(text);
  });

  testWidgets('hidden:true (iPhone) — плитки «Капибара+» в «Ещё» нет', (t) async {
    phone(t);
    final asked = <String>[];
    await t.pumpWidget(
      _more(
        fakeApi(
          requests: asked,
          overrides: {
            'GET /api/plus': {'hidden': true},
          },
        ),
      ),
    );
    await settle(t);
    expect(asked, contains('GET /api/plus'));
    expect(find.byKey(const Key('more:notify')), findsOneWidget);
    expect(find.byKey(const Key('more:plus')), findsNothing);
    expect(find.text('Капибара+'), findsNothing);
  });

  testWidgets('без ответа /plus (старый сервер) — плитки тоже нет', (t) async {
    phone(t);
    await t.pumpWidget(_more(fakeApi()));
    await settle(t);
    expect(find.byKey(const Key('more:notify')), findsOneWidget);
    expect(find.byKey(const Key('more:plus')), findsNothing);
  });

  testWidgets('экран подписки: срок, «Основатель», цены, оплата на сайте, друзья и ранги', (t) async {
    phone(t);
    await t.pumpWidget(_more(fakeApi(overrides: {'GET /api/plus': _plus, 'GET /api/invite': _invite})));
    await settle(t);
    await t.tap(find.byKey(const Key('more:plus')));
    await settle(t);
    expect(find.byType(PlusScreen), findsOneWidget);
    expect(find.text('Действует до 14 ноября'), findsOneWidget);
    expect(find.text('Основатель'), findsWidgets);
    expect(find.text('месяц для тебя — 149 ₽, навсегда'), findsOneWidget);
    expect(find.text('ИИ сверх пробы'), findsOneWidget);
    await _see(t, 'plus:price:half');
    expect(find.byKey(const Key('plus:price:month')), findsOneWidget);
    expect(find.text('199 ₽'), findsOneWidget); // зачёркнутая полная цена
    expect(find.text('899 ₽'), findsOneWidget);

    expect(find.byKey(const Key('plus:soon')), findsNothing);
    await _see(t, 'plus:pay');
    await t.tap(find.byKey(const Key('plus:pay')));
    await settle(t);
    expect(opened.single.toString(), 'https://www.uiboshki.ru/plus?k=demo');

    await _see(t, 'plus:offer');
    await t.tap(find.byKey(const Key('plus:offer')));
    await settle(t);
    expect(opened.last.toString(), 'https://www.uiboshki.ru/offer');

    await _see(t, 'plus:invite');
    expect(find.text('+7 дней обоим, когда друг попользуется Капибарой 3 дня'), findsOneWidget);
    expect(find.text('Пришло по ссылке: 3 · засчитано: 1'), findsOneWidget);

    await _see(t, 'plus:rank:midnight');
    expect(find.text('Рассвет · +3 дня'), findsOneWidget);
    expect(find.text('получено'), findsOneWidget);
    expect(find.text('Полночь · +14 дней'), findsOneWidget);
  });

  testWidgets('подарок своей группе — «Подарок группе до …», платить не нужно', (t) async {
    phone(t);
    final api = fakeApi(
      overrides: {
        'GET /api/plus': {..._plus, 'until': '2026-12-31', 'paid_until': null, 'gift': '2026-12-31', 'founder': false},
      },
    );
    await t.pumpWidget(_host(PlusScreen(api: api)));
    await settle(t);
    expect(find.text('Подарок группе до 31 декабря'), findsOneWidget);
    expect(find.text('Платить не нужно — всё уже включено'), findsOneWidget);
  });

  testWidgets('касса не подключена — «Оплата скоро заработает», кнопки оплаты нет', (t) async {
    phone(t);
    final api = fakeApi(
      overrides: {
        'GET /api/plus': {..._plus, 'active': false, 'until': null, 'founder': false, 'pay_url': ''},
      },
    );
    await t.pumpWidget(_host(PlusScreen(api: api)));
    await settle(t);
    expect(find.text('Подписки нет'), findsOneWidget);
    await _see(t, 'plus:soon');
    expect(find.byKey(const Key('plus:pay')), findsNothing);
    expect(find.textContaining('Оплата скоро заработает'), findsOneWidget);
  });

  testWidgets('«Позвать»: лист с готовым сообщением — Telegram и «Поделиться…»', (t) async {
    phone(t);
    final api = fakeApi(overrides: {'GET /api/invite': _invite});
    await t.pumpWidget(_more(api));
    await settle(t);
    await t.drag(find.byType(MoreScreen), const Offset(0, -2000));
    await settle(t);
    await t.tap(find.text('Позвать'));
    await settle(t);
    expect(find.text('Позвать друга'), findsOneWidget);
    expect(find.text('Капибара — расписание и дедлайны\nhttps://t.me/UiboshkiBot?start=ref_demo1'), findsOneWidget);
    expect(find.byKey(const Key('invite:bonus')), findsOneWidget);

    await t.tap(find.byKey(const Key('invite:tg')));
    await settle(t);
    expect(opened.single.toString(), _invite['tg_share']);
    expect(find.text('Позвать друга'), findsNothing); // лист закрылся

    await t.tap(find.text('Позвать'));
    await settle(t);
    await t.tap(find.byKey(const Key('invite:share')));
    await settle(t);
    expect(shared.single, 'Капибара — расписание и дедлайны\nhttps://t.me/UiboshkiBot?start=ref_demo1');
  });

  testWidgets('«Позвать»: Telegram не открылся — сообщение копируется', (t) async {
    phone(t);
    final copied = <String>[];
    t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') copied.add((call.arguments as Map)['text'] as String);
      return null;
    });
    addTearDown(() => t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
    PlusLinks.open = (_) async => false;
    await t.pumpWidget(
      _host(
        Scaffold(
          body: Builder(builder: (c) => InviteSheet(data: _invite)),
        ),
      ),
    );
    await settle(t);
    await t.tap(find.byKey(const Key('invite:tg')));
    await settle(t);
    expect(copied.single, contains('ref_demo1'));
  });

  test('PWA: ?ref= запоминается, после входа уходит один раз и забывается', () async {
    await PlusBonus.rememberRef(Uri.parse('https://www.uiboshki.ru/app/?ref=demo1'));
    final asked = <String>[];
    final bodies = <String, Object?>{};
    final api = fakeApi(requests: asked, bodies: bodies);
    await PlusBonus.sendRef(api);
    expect(bodies['POST /api/plus/ref'], {'code': 'demo1'});
    asked.clear();
    await PlusBonus.sendRef(api);
    expect(asked, isEmpty);
  });

  test('PWA: без сети код не теряется', () async {
    await PlusBonus.rememberRef(Uri.parse('https://www.uiboshki.ru/app/?ref=demo2'));
    var offline = true;
    final bodies = <String, Object?>{};
    final api = fakeApi(bodies: bodies, offline: () => offline);
    await PlusBonus.sendRef(api);
    expect(bodies, isEmpty);
    offline = false;
    await PlusBonus.sendRef(api);
    expect(bodies['POST /api/plus/ref'], {'code': 'demo2'});
  });

  testWidgets('ранг закрыт — один запрос /plus/rank и плашка «+3 дня Капибары+»', (t) async {
    phone(t);
    final asked = <String>[];
    PlusBonus.api = _rankApi(200, {'ok': true, 'days': 3, 'until': '2026-10-19'}, asked);
    await t.pumpWidget(_host(const Scaffold(body: SizedBox())));
    await t.runAsync(() async {
      await _openAll(Rank.dawn);
      await Future<void>.delayed(const Duration(milliseconds: 200)); // запрос уходит в фоне
    });
    await settle(t);
    final ranks = asked.where((r) => r.contains('/plus/rank')).toList();
    expect(ranks, hasLength(1));
    expect(ranks.single, contains('"rank":"dawn"'));
    expect(find.textContaining('+3 дня Капибары+'), findsOneWidget);
    // следующий запуск: уже получено — не спрашиваем
    PlusBonus.reset();
    PlusBonus.api = _rankApi(200, {'ok': true, 'days': 3}, asked);
    asked.clear();
    await t.runAsync(PlusBonus.checkAll);
    expect(asked, isEmpty);
    await t.pump(const Duration(seconds: 6));
  });

  test('ранг: «уже получен» — больше не спрашиваем; «рано» — спросим в следующий запуск', () async {
    final asked = <String>[];
    PlusBonus.api = _rankApi(400, {'detail': 'нужно заходить хотя бы 7 разных дней (сейчас 2)'}, asked);
    await _openAll(Rank.noon);
    await PlusBonus.checkAll();
    expect(asked.where((r) => r.contains('"rank":"noon"')), hasLength(1)); // в этот запуск — один раз

    PlusBonus.reset(); // следующий запуск
    PlusBonus.api = _rankApi(400, {'detail': 'бонус за этот ранг уже получен'}, asked);
    asked.clear();
    await PlusBonus.checkAll();
    expect(asked.where((r) => r.contains('"rank":"noon"')), hasLength(1));

    PlusBonus.reset();
    PlusBonus.api = _rankApi(400, {'detail': 'бонус за этот ранг уже получен'}, asked);
    asked.clear();
    await PlusBonus.checkAll();
    expect(asked, isEmpty);
  });

  test('ранг не закрыт — не спрашиваем', () async {
    final asked = <String>[];
    PlusBonus.api = _rankApi(200, {'ok': true, 'days': 3}, asked);
    await AchStore.unlock(achievements.firstWhere((a) => a.rank == Rank.dawn).id);
    await PlusBonus.checkAll();
    expect(asked, isEmpty);
  });
}

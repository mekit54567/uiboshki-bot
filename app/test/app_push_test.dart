// Пуши своего приложения (app_push.dart): включение — свой ключ AES-256 и
// токен уходят на сервер, выключение и выход — отписка и ключ стёрт,
// нажатое уведомление открывает вкладку. Телефон подменён (FakeDevice).
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/app_push.dart';
import 'package:uiboshki/screens/notify.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

class FakeDevice implements PushDevice {
  Map<String, bool> here = {'fcm': true, 'rustore': false, 'apns': false};
  bool allow = true;
  String tok = 'fcm-token-1234567890';
  String? key, cleared, pendingTab;
  final log = <String>[];
  void Function(String)? onTab;
  void Function(String, String)? onToken;

  @override
  Future<Map<String, bool>> available() async => here;
  @override
  Future<bool> permission() async => allow;
  @override
  Future<bool> granted() async => allow;
  @override
  Future<String?> token(String platform) async => tok;
  @override
  Future<void> setKey(String k) async => key = k;
  @override
  Future<void> clear(String? platform) async {
    key = null;
    cleared = platform;
    log.add('clear');
  }

  @override
  Future<String?> takeTab() async {
    final t = pendingTab;
    pendingTab = null;
    return t;
  }

  @override
  void listen({
    required void Function(String tab) onTab,
    required void Function(String platform, String token) onToken,
  }) {
    this.onTab = onTab;
    this.onToken = onToken;
  }
}

/// Телефон без сервисов Google: FCM в сборке есть, а токена нет.
class _FailFcm extends FakeDevice {
  _FailFcm(FakeDevice base) {
    here = base.here;
  }

  @override
  Future<String?> token(String platform) async {
    if (platform == 'fcm') throw PlatformException(code: 'fcm', message: 'SERVICE_NOT_AVAILABLE');
    return 'rustore-token-1234567890';
  }
}

const _on = {
  'GET /api/push/app': {
    'platforms': {'fcm': true, 'rustore': true, 'apns': false},
    'version': 1,
  },
};

Widget _wrap(Widget child) => AppStyle(
  p: Palette.depth,
  font: FontChoice.book,
  design2: true,
  child: MaterialApp(home: child),
);

void main() {
  late FakeDevice dev;
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    dev = FakeDevice();
    AppPush.device = dev;
  });

  test('ключ — 32 случайных байта в base64, каждый раз новый', () {
    final a = base64Decode(AppPush.newKey()), b = base64Decode(AppPush.newKey());
    expect(a.length, 32);
    expect(a, isNot(equals(b)));
  });

  test('включить: разрешение, токен, ключ на телефон и на сервер', () async {
    final bodies = <String, Object?>{};
    final api = fakeApi(bodies: bodies, overrides: _on);
    expect(await AppPush.state(api), 'off');
    expect(await AppPush.enable(api), 'on');
    final sent = bodies['POST /api/push/app/subscribe'] as Map;
    expect(sent['platform'], 'fcm');
    expect(sent['token'], 'fcm-token-1234567890');
    expect(sent['key'], dev.key); // тот же ключ, что у расшифровки на телефоне
    expect(base64Decode(sent['key'] as String).length, 32);
    expect(await AppPush.state(api), 'on');

    expect(await AppPush.disable(api), 'off');
    expect(bodies['POST /api/push/app/unsubscribe'], {'platform': 'fcm', 'token': 'fcm-token-1234567890'});
    expect(dev.key, isNull);
    expect(await AppPush.state(api), 'off');
  });

  test('без сервисов Google — RuStore; сервер всё выключил — нет пушей', () async {
    dev.here = {'fcm': false, 'rustore': true};
    expect(await AppPush.platform(fakeApi(overrides: _on)), 'rustore');
    final requests = <String>[];
    expect(
      await AppPush.state(
        fakeApi(
          requests: requests,
          overrides: {
            'GET /api/push/app': {
              'platforms': {'fcm': false, 'rustore': false, 'apns': false},
            },
          },
        ),
      ),
      'unsupported',
    );
    dev.here = {};
    requests.clear();
    expect(await AppPush.state(fakeApi(requests: requests, overrides: _on)), 'unsupported');
    expect(requests, isEmpty); // сборка без пушей — сервер не спрашиваем
  });

  test('Google не выдал токен — RuStore', () async {
    dev.here = {'fcm': true, 'rustore': true};
    final fail = _FailFcm(dev);
    AppPush.device = fail;
    final bodies = <String, Object?>{};
    expect(await AppPush.enable(fakeApi(bodies: bodies, overrides: _on)), 'on');
    expect((bodies['POST /api/push/app/subscribe'] as Map)['platform'], 'rustore');
  });

  test('запретили уведомления — denied, на сервер ничего', () async {
    dev.allow = false;
    final bodies = <String, Object?>{};
    expect(await AppPush.enable(fakeApi(bodies: bodies, overrides: _on)), 'denied');
    expect(bodies.containsKey('POST /api/push/app/subscribe'), isFalse);
  });

  test('выход: отписка, даже без сети ключ стёрт', () async {
    final api = fakeApi(overrides: _on);
    await AppPush.enable(api);
    await AppPush.forget(fakeApi(overrides: _on, offline: () => true));
    expect(dev.key, isNull);
    expect(await AppPush.state(api), 'off');
  });

  test('сменился токен — новый ключ и регистрация заново', () async {
    final bodies = <String, Object?>{};
    final api = fakeApi(bodies: bodies, overrides: _on);
    await AppPush.enable(api);
    final first = dev.key;
    dev.tok = 'fcm-token-new-0987654321';
    await AppPush.refresh(api);
    final sent = bodies['POST /api/push/app/subscribe'] as Map;
    expect(sent['token'], 'fcm-token-new-0987654321');
    expect(sent['key'], dev.key);
    expect(dev.key, isNot(first));
  });

  test('нажатое уведомление — вкладка', () async {
    dev.pendingTab = 'deadlines';
    await AppPush.start(fakeApi(overrides: _on));
    expect(AppPush.tab.value, 'deadlines');
    AppPush.tab.value = null;
    dev.onTab!('week');
    expect(AppPush.tab.value, 'week');
    AppPush.tab.value = null;
  });

  testWidgets('экран уведомлений: тумблер «На этом телефоне»', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    await t.pumpWidget(
      _wrap(
        NotifyScreen(
          api: fakeApi(bodies: bodies, overrides: _on),
        ),
      ),
    );
    await settle(t);
    expect(find.text('На этом телефоне'), findsOneWidget);
    await t.tap(find.byKey(const Key('notify:app_push')));
    await settle(t);
    expect((bodies['POST /api/push/app/subscribe'] as Map)['platform'], 'fcm');
    expect(find.textContaining('Текст зашифрован'), findsOneWidget);
    expect(find.text('Дублировать в Telegram'), findsOneWidget);
  });

  testWidgets('сборка без пушей — карточки нет', (t) async {
    phone(t);
    dev.here = {};
    await t.pumpWidget(_wrap(NotifyScreen(api: fakeApi(overrides: _on))));
    await settle(t);
    expect(find.text('На этом телефоне'), findsNothing);
  });
}

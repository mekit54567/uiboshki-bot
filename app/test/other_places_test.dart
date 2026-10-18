// «Капибара в других местах» (5.97): бот, браузер и компьютер, канал — без
// слов о цене (правило Apple 3.1.1); с iPhone бот открывается со start=ios.
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/more.dart';

import 'fake_api.dart';
import 'more_header_test.dart' show host;

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'uib_toured': true}));

  const links = {'bot': 'https://t.me/KapibaraMireaBot', 'news': '@kapibara_news'};

  test('с iPhone бот — со start=ios, в браузере нет строки про браузер', () {
    final ios = MoreScreen.places(links, ios: true, web: false);
    expect(ios.map((e) => e.$2), ['Telegram-бот', 'В браузере и на компьютере', 'Канал Капибары']);
    expect(ios.first.$5, 'https://t.me/KapibaraMireaBot?start=ios');
    expect(ios.last.$5, 'https://t.me/kapibara_news');

    expect(MoreScreen.places(links, ios: false, web: false).first.$5, 'https://t.me/KapibaraMireaBot');
    final web = MoreScreen.places({'bot': 'https://t.me/b'}, ios: false, web: true);
    expect(web.map((e) => e.$2), ['Telegram-бот']); // канала нет — и строки нет
  });

  test('ни слова о цене и оплате', () {
    final text = MoreScreen.places(links, ios: true, web: false).map((e) => '${e.$2} ${e.$3} ${e.$4}').join(' ');
    for (final w in ['₽', 'оплат', 'подписк', 'Капибара+', 'дешевле', 'цен']) {
      expect(text.toLowerCase().contains(w.toLowerCase()), isFalse, reason: w);
    }
  });

  testWidgets('строка в «Ещё» открывает лист', (t) async {
    await t.pumpWidget(host(fakeApi()));
    await t.pumpAndSettle();
    final row = find.text('Капибара в других местах');
    await t.scrollUntilVisible(row, 200);
    await t.tap(row);
    await t.pumpAndSettle();
    expect(find.text('Telegram-бот'), findsOneWidget);
  });
}

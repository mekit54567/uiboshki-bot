// Иконки за ачивки и подписку (5.91): закрытые видны в листе с замком и
// подсказкой, ачивки — ещё и на сервере (не пропадают при смене телефона).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/achievements/catalog.dart';
import 'package:uiboshki/achievements/store.dart';
import 'package:uiboshki/screens/look_screen.dart';
import 'package:uiboshki/theme/app_icon.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    AchStore.reset();
    AppIcon.premium.value = false;
    AppIcon.unlockForTest = {
      'kremlin': 'rank:dawn',
      'astronaut': 'ach:ai',
      'bridge': 'all',
      'domes': 'sub',
      'riso': 'none',
    };
  });
  tearDown(() => AppIcon.unlockForTest = null);

  test('открыта ли: ранг, ачивка, все, подписка; убранной нет в списке', () {
    final i = AppIcon.byName;
    final dawn = {for (final a in achievements.where((a) => a.rank == Rank.dawn)) a.id: DateTime(2026)};
    expect(i('kremlin').isOpen({}), isFalse);
    expect(i('kremlin').isOpen(dawn), isTrue);
    expect(i('astronaut').isOpen({'ai': DateTime(2026)}), isTrue);
    expect(i('bridge').isOpen(dawn), isFalse);
    expect(i('bridge').isOpen({for (final a in achievements) a.id: DateTime(2026)}), isTrue);
    expect(i('university').isOpen({}), isTrue); // нет записи — бесплатно
    expect(AppIcon.choosable.map((x) => x.name), isNot(contains('riso')));
    // подписочная — только подписчику, и сразу открыта
    expect(AppIcon.choosable.map((x) => x.name), isNot(contains('domes')));
    AppIcon.premium.value = true;
    expect(AppIcon.choosable.map((x) => x.name), contains('domes'));
    expect(i('domes').isOpen({}), isTrue);
    expect(i('kremlin').howToOpen, 'Откроется, когда соберёшь все ачивки ранга «Рассвет»');
    expect(i('astronaut').howToOpen, 'Откроется ачивкой «Первый вопрос»');
  });

  testWidgets('закрытая в листе: замок, подсказка, не выбирается', (t) async {
    AppIcon? picked;
    await t.pumpWidget(
      AppStyle(
        p: Palette.depth,
        font: FontChoice.book,
        child: MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () async => picked = await showModalBottomSheet<AppIcon>(
                  context: context,
                  isScrollControlled: true,
                  builder: (_) => const IconPicker(current: AppIcon.classic, dark: false),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await t.tap(find.text('open'));
    await t.pumpAndSettle();
    await t.scrollUntilVisible(
      find.byKey(const Key('look:icon:kremlin')),
      200,
      scrollable: find.descendant(of: find.byKey(const Key('look:icons')), matching: find.byType(Scrollable)).first,
    );
    expect(
      find.descendant(of: find.byKey(const Key('look:icon:kremlin')), matching: find.byIcon(Icons.lock_rounded)),
      findsOneWidget,
    );
    await t.tap(find.byKey(const Key('look:icon:kremlin')));
    await t.pump(const Duration(milliseconds: 400));
    expect(find.text('Откроется, когда соберёшь все ачивки ранга «Рассвет»'), findsOneWidget);
    await t.pumpAndSettle(); // плашка ушла сама
    expect(picked, isNull);
    // открыл ранг — выбирается
    await AchStore.unlock('lesson');
    AchStore.got.value = {for (final a in achievements.where((a) => a.rank == Rank.dawn)) a.id: DateTime(2026)};
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('look:icon:kremlin')));
    await t.pumpAndSettle();
    expect(picked?.name, 'kremlin');
  });

  test('ачивки: свои — на сервер, с сервера — недостающие, время — самое раннее', () async {
    final requests = <String>[];
    final bodies = <String, Object?>{};
    final early = DateTime(2026, 10, 1).millisecondsSinceEpoch;
    AchStore.api = fakeApi(
      requests: requests,
      bodies: bodies,
      overrides: {
        'POST /api/achievements': {
          'items': {'lesson': early, 'ai': early, 'nope': early},
        },
      },
    );
    await AchStore.unlock('lesson', at: DateTime(2026, 10, 10));
    await AchStore.sync();
    expect(requests.where((r) => r == 'POST /api/achievements'), isNotEmpty);
    expect(((bodies['POST /api/achievements'] as Map)['items'] as Map).keys, contains('lesson'));
    expect(AchStore.got.value.keys.toSet(), {'lesson', 'ai'});
    expect(AchStore.got.value['lesson']!.millisecondsSinceEpoch, early);
    // и после перезапуска — с телефона
    AchStore.reset();
    await AchStore.load();
    expect(AchStore.has('ai'), isTrue);
  });

  test('нет сети — ачивка всё равно открывается', () async {
    AchStore.api = fakeApi(offline: () => true);
    expect(await AchStore.unlock('ai'), isTrue);
    await AchStore.sync();
    expect(AchStore.has('ai'), isTrue);
  });
}

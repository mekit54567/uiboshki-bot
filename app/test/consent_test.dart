// 152-ФЗ (legal.dart): галочка не стоит, «Продолжить» неактивна без неё;
// ссылка открывает текст; согласие уходит на сервер; удаление данных.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/legal.dart';
import 'package:uiboshki/theme/app_theme.dart';
import 'package:uiboshki/widgets/common.dart';

import 'fake_api.dart';
import 'util.dart';

const _doc = {
  'name': 'consent',
  'title': 'Согласие на обработку персональных данных',
  'version': '1',
  'date': '11.10.2026',
  'lead': 'Ставя галочку…',
  'sections': [
    {
      'title': 'Кому передаются',
      'blocks': [
        {'p': 'Абзац'},
        {'ul': ['Amvera (Москва) — хостинг', 'Telegram — сообщения']},
      ],
    },
  ],
};

Widget _wrap(Widget child) => AppStyle(
  p: Palette.notebook,
  font: FontChoice.strict,
  child: MaterialApp(home: child),
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('первый вход: без галочки дальше нельзя, ссылка открывает текст', (t) async {
    phone(t);
    final asked = <String>[];
    final bodies = <String, Object?>{};
    final api = fakeApi(
      requests: asked,
      bodies: bodies,
      overrides: {
        'GET /api/legal/consent': _doc,
        'POST /api/consent': {'version': '1', 'date': '11.10.2026', 'pd': true, 'sdo': false},
      },
    );
    await t.pumpWidget(_wrap(ConsentScreen(api: api)));
    await settle(t);
    final go = find.widgetWithText(FilledButton, 'Продолжить');
    expect(t.widget<FilledButton>(go).onPressed, isNull); // галочка по умолчанию не стоит

    // синяя ссылка «согласие на обработку…» — текст поверх, галочка не ставится
    await t.tapOnText(find.textRange.ofSubstring('согласие на обработку персональных данных'));
    await settle(t);
    expect(find.text('Amvera (Москва) — хостинг'), findsOneWidget);
    expect(asked, contains('GET /api/legal/consent'));
    await t.tap(find.byTooltip('Назад'));
    await settle(t);
    expect(t.widget<FilledButton>(go).onPressed, isNull);

    await t.tap(find.descendant(of: find.byType(ConsentCheck), matching: find.byType(AnimatedContainer)));
    await settle(t);
    expect(t.widget<FilledButton>(go).onPressed, isNotNull);
    await t.tap(go);
    await settle(t);
    expect(bodies['POST /api/consent'], {'kind': 'pd'});
  });

  testWidgets('кто был до согласий: один раз, «Не сейчас» закрывает', (t) async {
    phone(t);
    final asked = <String>[];
    final api = fakeApi(requests: asked, overrides: {'POST /api/consent/asked': {'ok': true}});
    Object? result = 'не закрыт';
    await t.pumpWidget(
      _wrap(
        Builder(
          builder: (c) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.of(c)
                  .push<bool>(MaterialPageRoute(builder: (_) => ConsentScreen(api: api, required: false)))
                  .then((v) => result = v),
              child: const Text('открыть'),
            ),
          ),
        ),
      ),
    );
    await t.tap(find.text('открыть'));
    await settle(t);
    expect(asked, contains('POST /api/consent/asked')); // больше не покажем
    expect(find.text('Не даю согласие'), findsNothing);
    await t.tap(find.text('Не сейчас'));
    await settle(t);
    expect(result, isNull);
    expect(find.byType(ConsentScreen), findsNothing);
  });

  testWidgets('удалить все мои данные: фразой руками, потом выход', (t) async {
    phone(t);
    final asked = <String>[];
    final api = fakeApi(
      requests: asked,
      overrides: {
        'POST /api/me/delete': {'ok': true, 'due': '2026-10-15', 'text': 'Твои данные будут удалены полностью 15.10.2026.'},
      },
    );
    late BuildContext ctx;
    await t.pumpWidget(_wrap(Builder(builder: (c) {
      ctx = c;
      return const Scaffold();
    })));
    bool? done;
    deleteMyData(ctx, api).then((v) => done = v);
    await settle(t);
    await t.enterText(find.byType(TextField), 'да');          // не та фраза — ничего
    await t.tap(find.text('Удалить'));
    await settle(t);
    await t.pump(const Duration(seconds: 5));
    expect(done, isFalse);
    expect(asked, isNot(contains('POST /api/me/delete')));

    deleteMyData(ctx, api).then((v) => done = v);
    await settle(t);
    await t.enterText(find.byType(TextField), 'Удалить мои данные.'); // вставка целиком — не проходит
    await t.pump();
    expect(t.widget<TextField>(find.byType(TextField)).controller!.text, isEmpty);
    const typed = 'Удалить мои данные.';
    for (var i = 1; i <= typed.length; i++) {
      await t.enterText(find.byType(TextField), typed.substring(0, i)); // руками, по букве
    }
    await t.pump();
    expect(t.widget<TextField>(find.byType(TextField)).controller!.text, typed);
    expect(t.widget<TextField>(find.byType(TextField)).enableInteractiveSelection, isFalse);
    await t.tap(find.text('Удалить'));
    await settle(t);
    expect(find.textContaining('удалены полностью 15.10.2026'), findsOneWidget);
    await t.tap(find.text('Понятно'));
    await settle(t);
    expect(done, isTrue);
    expect(asked, contains('POST /api/me/delete'));
    expect(api.token, isNull);
  });

  testWidgets('длинный раздел: главное, «Подробнее» — полный текст', (t) async {
    phone(t);
    final api = fakeApi(
      overrides: {
        'GET /api/legal/privacy': {
          ..._doc,
          'name': 'privacy',
          'sections': [
            {
              'title': 'Твои права',
              'short': [
                {'p': 'Коротко'},
              ],
              'blocks': [
                {'p': 'Полный текст'},
              ],
            },
          ],
        },
      },
    );
    await t.pumpWidget(_wrap(LegalScreen(api: api, name: 'privacy')));
    await settle(t);
    expect(find.text('Коротко'), findsOneWidget);
    expect(find.text('Полный текст'), findsNothing);
    await t.tap(find.text('Подробнее'));
    await settle(t);
    expect(find.text('Полный текст'), findsOneWidget);
    expect(find.text('Коротко'), findsNothing);
    expect(find.text('Подробнее'), findsNothing);
  });

  test('фраза — только руками: кусок от 8 знаков не вставляется', () {
    const f = NoPasteFormatter();
    const empty = TextEditingValue.empty;
    expect(f.formatEditUpdate(empty, const TextEditingValue(text: 'удалить мои данные')), empty);
    expect(f.formatEditUpdate(empty, const TextEditingValue(text: 'у')).text, 'у');
    const word = TextEditingValue(text: 'удалить ');
    expect(f.formatEditUpdate(word, const TextEditingValue(text: 'удалить мои ')).text, 'удалить мои ');
  });

  test('фраза удаления — как на сервере', () {
    expect(erasePhraseOk(' Удалить  мои данные. '), isTrue);
    expect(erasePhraseOk('«удалить мои данные»'), isTrue);
    expect(erasePhraseOk('удалить'), isFalse);
  });
}

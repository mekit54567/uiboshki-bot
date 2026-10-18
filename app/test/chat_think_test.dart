// «Подумать» до вопроса (Никита 18.10, по скрину чипа «Подумать ещё»:
// «чтоб можно было выбрать перед ответом сразу»): переключатель над полем
// ввода у подписчика — включил, и вопрос уходит с think_first; на один
// вопрос, потом выключается сам. Кончилось — серый; нет подписки — нет.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uiboshki/screens/chat.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'fake_api.dart';
import 'util.dart';

Widget host(Widget child) => AppStyle(
  p: Palette.notebook,
  font: FontChoice.book,
  child: MaterialApp(home: child),
);

Map<String, Object?> withThink(int left) => {
  'GET /api/subjects': {
    ...demoFixtures()['GET /api/subjects'] as Map,
    'think': {'label': 'Подумать ещё', 'left': left, 'daily': 10},
  },
  'POST /api/chat': {
    'content': 'Глубокий ответ',
    'html': 'Глубокий ответ',
    'think': {'label': 'Подумать ещё', 'left': left > 0 ? left - 1 : 0, 'daily': 10},
  },
};

Future<void> ask(WidgetTester t, String q) async {
  await t.enterText(find.byType(TextField), q);
  await t.tap(find.byTooltip('Отправить'));
  await settle(t);
}

ChoiceChip toggle(WidgetTester t) => t.widget<ChoiceChip>(find.byKey(const Key('think-toggle')));

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('включил «Подумать» — вопрос сразу с think_first, потом переключатель выключен', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    await t.pumpWidget(
      host(
        ChatScreen(
          api: fakeApi(bodies: bodies, overrides: withThink(2)),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Подумать · 2'), findsOneWidget);
    expect(toggle(t).selected, isFalse);

    await t.tap(find.byKey(const Key('think-toggle')));
    await t.pump();
    expect(toggle(t).selected, isTrue);
    expect(find.textContaining('Капибара решит, подумав подольше'), findsOneWidget);

    await ask(t, 'Что такое NPV?');
    final first = bodies['POST /api/chat'] as Map;
    expect(first['think_first'], isTrue);
    expect([for (final m in first['history'] as List) m['content']], ['Что такое NPV?']);
    expect(find.text('Глубокий ответ'), findsOneWidget); // без первого обычного ответа
    expect(toggle(t).selected, isFalse); // на один вопрос
    expect(find.text('Подумать · 1'), findsOneWidget); // счётчик — с сервера
    expect(find.text('Подумать ещё · 1'), findsOneWidget); // чип под ответом остаётся

    await ask(t, 'А пример?');
    expect((bodies['POST /api/chat'] as Map).containsKey('think_first'), isFalse);
  });

  testWidgets('на сегодня кончилось — переключатель серый и не включается', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    await t.pumpWidget(
      host(
        ChatScreen(
          api: fakeApi(bodies: bodies, overrides: withThink(0)),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Подумать · 0'), findsOneWidget);
    expect(toggle(t).onSelected, isNull);
    expect(find.textContaining('завтра снова'), findsOneWidget);
    await t.tap(find.byKey(const Key('think-toggle')));
    await ask(t, 'Что такое NPV?');
    expect((bodies['POST /api/chat'] as Map).containsKey('think_first'), isFalse);
  });

  testWidgets('безлимит — «Подумать» без счётчика и включается', (t) async {
    phone(t);
    final bodies = <String, Object?>{};
    final o = withThink(0);
    o['GET /api/subjects'] = {
      ...demoFixtures()['GET /api/subjects'] as Map,
      'think': {'label': 'Подумать ещё', 'left': null, 'daily': 10},
    };
    await t.pumpWidget(
      host(
        ChatScreen(
          api: fakeApi(bodies: bodies, overrides: o),
        ),
      ),
    );
    await settle(t);
    expect(find.text('Подумать'), findsOneWidget);
    expect(find.textContaining('завтра снова'), findsNothing);
    await t.tap(find.byKey(const Key('think-toggle')));
    await t.pump();
    expect(toggle(t).selected, isTrue);
    await ask(t, 'Что такое NPV?');
    expect((bodies['POST /api/chat'] as Map)['think_first'], isTrue);
  });

  testWidgets('у чипа «Подумать» отступы слева и справа одинаковые', (t) async {
    // робот 18.10: справа от подписи пустого места было вдвое больше, чем слева
    phone(t);
    await t.pumpWidget(host(ChatScreen(api: fakeApi(overrides: withThink(7)))));
    await settle(t);
    final chip = t.getRect(find.byKey(const Key('think-toggle')));
    final icon = t.getRect(find.descendant(of: find.byKey(const Key('think-toggle')), matching: find.byType(Icon)));
    final text = t.getRect(find.text('Подумать · 7'));
    expect(((icon.left - chip.left) - (chip.right - text.right)).abs(), lessThanOrEqualTo(1));
  });

  testWidgets('у чипа «Подумать ещё» под ответом отступы тоже одинаковые', (t) async {
    phone(t);
    await t.pumpWidget(host(ChatScreen(api: fakeApi(overrides: withThink(7)))));
    await settle(t);
    await ask(t, 'Что такое NPV?');
    final label = find.text('Подумать ещё · 6');
    final chipF = find.ancestor(of: label, matching: find.byType(ActionChip));
    final chip = t.getRect(chipF);
    final icon = t.getRect(find.descendant(of: chipF, matching: find.byType(Icon)));
    final text = t.getRect(label);
    expect(((icon.left - chip.left) - (chip.right - text.right)).abs(), lessThanOrEqualTo(1));
  });

  testWidgets('не подписчик (или iPhone, или выключено) — переключателя нет', (t) async {
    phone(t);
    await t.pumpWidget(host(ChatScreen(api: fakeApi())));
    await settle(t);
    expect(find.byKey(const Key('think-toggle')), findsNothing);
    expect(find.textContaining('Подумать'), findsNothing);
  });
}

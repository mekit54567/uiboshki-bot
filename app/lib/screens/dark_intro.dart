// Переход на новый дизайн (шаг 9, Никита 18.11): экран «Мы обновили дизайн»
// для тех, у кого приложение открывается в тёмной, и карточки опроса «какая
// тёмная лучше» на «Сегодня». Логика и сроки — theme/dark_vote.dart.
import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../theme/dark_vote.dart';
import '../theme/look.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';
import 'look_screen.dart' show LookPreview;

/// Один раз, при первом тёмном запуске после перехода: две картинки
/// настоящих экранов («Тетрадь» и «Ночная тетрадь») и выбор.
class DarkIntroScreen extends StatelessWidget {
  const DarkIntroScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final look = s.look;
    final library = look.dark == DarkTheme.library;
    final old = DarkVote.oldName(look);
    Future<void> choose(Future<void> Function() answer) async {
      tick();
      final nav = Navigator.of(context);
      await answer();
      if (nav.mounted) nav.pop();
    }

    return PopScope(
      canPop: false, // ответить надо одной из кнопок: обе ничего не ломают
      child: Scaffold(
        body: Backdrop(
          child: SafeArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(Space.l, Space.xl, Space.l, Space.l),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text('Мы обновили дизайн', style: s.title(30)),
                        const SizedBox(height: Space.s),
                        Text('Теперь по умолчанию так:', style: s.body(15, color: p.muted)),
                        const SizedBox(height: Space.l),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: _Shot(key: const Key('intro:paper'), palette: Palette.paper, title: 'Тетрадь'),
                            ),
                            const SizedBox(width: Space.m),
                            Expanded(
                              child: _Shot(
                                key: const Key('intro:night'),
                                palette: Palette.night,
                                title: 'Ночная тетрадь',
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: Space.l),
                        Text(
                          library
                              ? 'У тебя стояла тёмная «Библиотека». Она осталась в\u00A0«Классике», прежнем виде приложения.'
                              : 'У тебя стояла прежняя тёмная «$old». Она никуда не делась, но теперь не\u00A0основная.',
                          style: s.body(15),
                        ),
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      FilledButton(
                        key: const Key('intro:new'),
                        style: FilledButton.styleFrom(
                          backgroundColor: p.accent,
                          foregroundColor: p.onAccent,
                          shape: const StadiumBorder(),
                          minimumSize: const Size.fromHeight(50),
                          textStyle: s.body(16, weight: FontWeight.w600),
                        ),
                        onPressed: () => choose(DarkVote.tryNew),
                        child: const Text('Попробовать новую'),
                      ),
                      const SizedBox(height: Space.s),
                      TextButton(
                        key: const Key('intro:old'),
                        style: TextButton.styleFrom(
                          foregroundColor: p.text,
                          shape: const StadiumBorder(),
                          minimumSize: const Size.fromHeight(48),
                          textStyle: s.body(15, weight: FontWeight.w600),
                        ),
                        onPressed: () => choose(() => DarkVote.keepOld(now())),
                        child: Text(library ? 'Оставить прежний вид' : 'Оставить прежнюю'),
                      ),
                      const SizedBox(height: Space.xs),
                      Text(
                        'Поменять можно в любой момент: «Ещё», «Оформление».',
                        textAlign: TextAlign.center,
                        style: s.body(13, color: p.muted),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Маленький настоящий экран в своей теме: фон, заголовок и пары — как на
/// «Сегодня» (тот же живой пример, что в «Оформлении»).
class _Shot extends StatelessWidget {
  final Palette palette;
  final String title;
  const _Shot({super.key, required this.palette, required this.title});

  /// Ширина, в которой пример рисуется, прежде чем уменьшиться до карточки.
  static const _width = 330.0;

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final look = s.look.copyWith(fresh: true, freshDepth: false, paper: Paper.smooth, day: DayView.cards);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ExcludeSemantics(
          child: IgnorePointer(
            child: FittedBox(
              fit: BoxFit.fitWidth,
              child: SizedBox(
                width: _width,
                child: AppStyle(
                  p: palette,
                  font: FontChoice.book,
                  theme: s.theme,
                  look: look,
                  design2: true,
                  design3: s.design3,
                  child: const LookPreview(),
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: Space.s),
        Text(
          title,
          textAlign: TextAlign.center,
          style: s.body(13, weight: FontWeight.w600),
        ),
      ],
    );
  }
}

/// Карточка опроса на «Сегодня» — только в тёмной и только когда пора.
class DarkAskCard extends StatelessWidget {
  const DarkAskCard({super.key});

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<DarkAsk?>(
    valueListenable: DarkVote.ask,
    builder: (context, ask, _) {
      final s = AppStyle.of(context);
      if (ask == null || !s.p.dark) return const SizedBox.shrink();
      // прежняя — по тому, что стояло в «Классике»
      final old = DarkVote.oldName(s.look);
      final (title, text, a, b) = switch (ask) {
        DarkAsk.howNew => (
          'Как тебе новая тёмная?',
          'Можно на пару дней вернуть прежнюю, «${old == 'Глубина' ? 'Глубину' : 'Библиотеку'}», и\u00A0сравнить.',
          ('Нравится новая', DarkVote.likeNew),
          ('Сравнить', DarkVote.compare),
        ),
        DarkAsk.which => (
          'Какая тёмная лучше?',
          'Обе уже знакомы. Что выберешь, то\u00A0и\u00A0останется, а мы посчитаем голоса.',
          ('Ночная тетрадь', () => DarkVote.pick(fresh: true)),
          (old, () => DarkVote.pick(fresh: false)),
        ),
        DarkAsk.retry => (
          'Попробуешь новую тёмную?',
          '«Ночная тетрадь» теперь основная. Вернуть прежнюю можно в\u00A0любой момент.',
          ('Попробовать', DarkVote.retry),
          ('Нет, спасибо', DarkVote.stayOld),
        ),
      };
      return Padding(
        padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, 0),
        child: Tile(
          key: Key('dark:${ask.name}'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: s.title(20)),
              const SizedBox(height: Space.xs),
              Text(text, style: s.body(14, color: s.p.muted)),
              const SizedBox(height: Space.m),
              Row(
                children: [
                  Expanded(
                    child: _AskButton(key: Key('dark:${ask.name}:a'), text: a.$1, onTap: a.$2, main: true),
                  ),
                  const SizedBox(width: Space.s),
                  // «какая лучше» — обе кнопки одинаковые, чтобы не подсказывать
                  Expanded(
                    child: _AskButton(
                      key: Key('dark:${ask.name}:b'),
                      text: b.$1,
                      onTap: b.$2,
                      main: ask == DarkAsk.which,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    },
  );
}

class _AskButton extends StatelessWidget {
  final String text;
  final Future<void> Function() onTap;
  final bool main;
  const _AskButton({super.key, required this.text, required this.onTap, required this.main});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final filled = main;
    return Semantics(
      button: true,
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          borderRadius: BorderRadius.circular(22),
          onTap: () {
            tick();
            onTap();
          },
          child: Container(
            constraints: const BoxConstraints(minHeight: 44),
            alignment: Alignment.center,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: filled ? p.accent.withValues(alpha: 0.16) : null,
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: filled ? p.accent : p.edge),
            ),
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(text, maxLines: 1, style: s.body(14.5, weight: FontWeight.w600)),
            ),
          ),
        ),
      ),
    );
  }
}

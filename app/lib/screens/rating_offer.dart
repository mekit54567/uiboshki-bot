// Предложение показаться в рейтинге (Никита 18.11, варианты А + В из ревью
// 152-ФЗ). Здесь только вопрос: ничего не включается само, оба тумблера
// выключены, отказ так же прост, как согласие. Когда спрашивать, считает сервер
// (rating_offer.py): карточка на «Рейтинге», лист при входе — первый раз через
// два часа, потом не чаще раза в 14 дней, не больше трёх, «Больше не
// предлагать» — навсегда. Вариант В (по поводу) приходит пушем и ведёт в «Ещё».
//
// Нельзя: галочка заранее, серая мелкая «нет», «чтобы видеть других, покажи
// себя», одна кнопка сразу на «группе» и «всем», включение молча.
//
// Вид: RATING_OFFER=a|b — два варианта на выбор Никиты (a — карточка с
// капибарой, b — компактная полоса); после выбора второй убрать.
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/common.dart';
import 'notify.dart' show AppSwitch;
import 'rating.dart' show ratingSave, ratingShowAll;

const ratingOfferVariant = String.fromEnvironment('RATING_OFFER', defaultValue: 'a');

/// Спросить у сервера и отметить ответ; сбой сети — молча: предложение не повод тревожить.
Future<Map?> ratingOfferState(Api api) async {
  try {
    final d = await api.get('/rating/offer');
    return d is Map ? d : null;
  } on ApiError {
    return null;
  }
}

Future<void> ratingOfferAct(Api api, String action, {String? source}) async {
  try {
    await api.post('/rating/offer', {'action': action, 'source': ?source});
  } on ApiError {
    // не вышло — спросим в другой раз
  }
}

bool _hiddenMe(Map me) => me['show'] != true && me['show_all'] != true;

var _askedThisRun = false;

@visibleForTesting
void resetRatingOfferRun() => _askedThisRun = false;

/// Лист при входе (после тура и вопроса про пуши): если сервер говорит «пора».
Future<void> maybeOfferRating(BuildContext context, Api api) async {
  if (_askedThisRun || !AppStyle.of(context).fresh) return;
  _askedThisRun = true;
  final st = await ratingOfferState(api);
  if (st == null || st['sheet'] != true || !context.mounted) return;
  Map me;
  try {
    final d = await api.get('/rating');
    me = d is Map && d['me'] is Map ? d['me'] as Map : const {};
  } on ApiError {
    return;
  }
  if (!_hiddenMe(me) || !context.mounted) return;
  await ratingOfferAct(api, 'shown');
  if (!context.mounted) return;
  await showRatingOfferSheet(context, api, me, source: 'sheet');
}

/// Лист с двумя выключенными тумблерами. true — человек что-то включил.
Future<bool> showRatingOfferSheet(BuildContext context, Api api, Map me, {required String source}) async {
  final on = await appSheet<bool>(context, (_) => _OfferSheet(api: api, me: me, source: source));
  return on ?? false;
}

/// Карточка на экране «Рейтинг», пока тебя не видно. [onChanged] — что-то включили,
/// экран надо перечитать.
class RatingOfferCard extends StatefulWidget {
  final Api api;
  final Map me;
  final VoidCallback onChanged;
  const RatingOfferCard({super.key, required this.api, required this.me, required this.onChanged});

  @override
  State<RatingOfferCard> createState() => _RatingOfferCardState();
}

class _RatingOfferCardState extends State<RatingOfferCard> {
  bool _show = false;

  @override
  void initState() {
    super.initState();
    if (_hiddenMe(widget.me)) _load();
  }

  Future<void> _load() async {
    final st = await ratingOfferState(widget.api);
    if (mounted && st != null && st['card'] == true) setState(() => _show = true);
  }

  Future<void> _open() async {
    final on = await showRatingOfferSheet(context, widget.api, widget.me, source: 'card');
    if (on && mounted) widget.onChanged();
  }

  void _later() {
    tick();
    setState(() => _show = false);
    ratingOfferAct(widget.api, 'later');
  }

  void _stop() {
    tick();
    setState(() => _show = false);
    ratingOfferAct(widget.api, 'stop');
  }

  @override
  Widget build(BuildContext context) {
    if (!_show || !_hiddenMe(widget.me)) return const SizedBox.shrink();
    final compact = ratingOfferVariant == 'b';
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
      child: _OfferCard(compact: compact, onShow: _open, onLater: _later, onStop: _stop),
    );
  }
}

class _OfferCard extends StatelessWidget {
  final bool compact;
  final VoidCallback onShow, onLater, onStop;
  const _OfferCard({required this.compact, required this.onShow, required this.onLater, required this.onStop});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final words = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Тебя не видно в рейтинге группы', style: s.body(compact ? 16 : 17, weight: FontWeight.w600)),
        const SizedBox(height: 4),
        Text('Покажешься? Вместо имени — ник или «Капибара\u00A0№…».', style: s.body(14, color: p.muted)),
      ],
    );
    return Tile(
      key: const Key('rating:offer'),
      padding: EdgeInsets.fromLTRB(Space.l, compact ? Space.m : Space.l, Space.l, Space.s),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (compact)
            words
          else
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: words),
                const SizedBox(width: Space.m),
                const CapyImage(pose: CapyPose.joy, size: 64),
              ],
            ),
          SizedBox(height: compact ? Space.m : Space.l),
          // кнопки одного размера: «не сейчас» так же заметна, как «показать»
          Row(
            children: [
              Expanded(
                child: _EqualButton(
                  key: const Key('rating:offer:show'),
                  label: 'Показать',
                  filled: true,
                  onTap: onShow,
                ),
              ),
              const SizedBox(width: Space.s),
              Expanded(
                child: _EqualButton(key: const Key('rating:offer:later'), label: 'Не сейчас', onTap: onLater),
              ),
            ],
          ),
          _StopLink(key: const Key('rating:offer:stop'), onTap: onStop),
        ],
      ),
    );
  }
}

/// Две кнопки в паре одного размера и веса текста; различаются только заливкой.
class _EqualButton extends StatelessWidget {
  final String label;
  final bool filled;
  final VoidCallback onTap;
  const _EqualButton({super.key, required this.label, this.filled = false, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final fg = filled ? p.onAccent : p.text;
    return SizedBox(
      height: 46,
      child: filled
          ? FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: p.accent,
                foregroundColor: fg,
                shape: const StadiumBorder(),
              ),
              onPressed: () {
                tick();
                onTap();
              },
              child: Text(
                label,
                style: s.body(15, weight: FontWeight.w600, color: fg),
              ),
            )
          : OutlinedButton(
              style: OutlinedButton.styleFrom(
                foregroundColor: fg,
                side: BorderSide(color: p.edge),
                shape: const StadiumBorder(),
              ),
              onPressed: () {
                tick();
                onTap();
              },
              child: Text(
                label,
                style: s.body(15, weight: FontWeight.w600, color: fg),
              ),
            ),
    );
  }
}

/// «Больше не предлагать»: мельче кнопок, но читаемо и с нормальной зоной нажатия.
class _StopLink extends StatelessWidget {
  final VoidCallback onTap;
  const _StopLink({super.key, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    return Center(
      child: TextButton(
        style: TextButton.styleFrom(minimumSize: const Size(0, 44), foregroundColor: s.p.muted),
        onPressed: () {
          tick();
          onTap();
        },
        child: Text('Больше не предлагать', style: s.body(13.5, color: s.p.muted)),
      ),
    );
  }
}

class _OfferSheet extends StatefulWidget {
  final Api api;
  final Map me;
  final String source;
  const _OfferSheet({required this.api, required this.me, required this.source});

  @override
  State<_OfferSheet> createState() => _OfferSheetState();
}

class _OfferSheetState extends State<_OfferSheet> {
  late Map _me = widget.me;
  bool _busy = false;
  bool _accepted = false;

  Future<void> _reload() async {
    try {
      final d = await widget.api.get('/rating');
      if (d is Map && d['me'] is Map && mounted) setState(() => _me = d['me'] as Map);
    } on ApiError {
      // остаётся как есть
    }
  }

  /// Правка тумблера: «группе» — сразу, «всем» — через отдельный лист согласия.
  Future<void> _toggle(bool all) async {
    if (_busy) return;
    setState(() => _busy = true);
    final bool ok;
    if (all) {
      ok = await ratingShowAll(context, widget.api, _me);
    } else {
      ok = await ratingSave(context, widget.api, {'show': _me['show'] != true});
    }
    if (!mounted) return;
    if (ok) {
      await _reload();
      if (!_hiddenMe(_me) && !_accepted) {
        _accepted = true;
        ratingOfferAct(widget.api, 'accepted', source: widget.source);
      }
    }
    if (mounted) setState(() => _busy = false);
  }

  Widget _row(AppStyle s, String title, String sub, bool on, VoidCallback tap, Key k) => Padding(
    padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
    child: Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: s.body(15, weight: FontWeight.w600)),
              const SizedBox(height: 2),
              Text(sub, style: s.body(12.5, color: s.p.muted)),
            ],
          ),
        ),
        const SizedBox(width: Space.s),
        AppSwitch(key: k, value: on, onChanged: tap),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final group = _me['show'] == true;
    final all = _me['show_all'] == true;
    final anyOn = group || all;
    final capy = ratingOfferVariant == 'b';
    return SafeArea(
      child: SingleChildScrollView(
        key: const Key('rating:offer:sheet'),
        padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (capy) const Center(child: CapyImage(pose: CapyPose.joy, size: 84)) else const SizedBox.shrink(),
            Text('Показаться в рейтинге?', style: s.title(24)),
            const SizedBox(height: Space.s),
            Text(
              anyOn
                  ? 'Включено то, что ты выбрал. Выключить можно в любой момент в «Мой опыт».'
                  : 'Сейчас тебя никто не видит. Не включишь — ничего не изменится.',
              style: s.body(15, color: p.muted),
            ),
            const SizedBox(height: Space.l),
            Tile(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  _row(
                    s,
                    'Группе',
                    group ? 'группа видит твой ник и опыт' : 'одногруппники увидят твой ник и опыт',
                    group,
                    () => _toggle(false),
                    const Key('rating:offer:group'),
                  ),
                  Divider(height: 1, color: p.line),
                  _row(
                    s,
                    'Всем',
                    all
                        ? 'все видят тебя как «${_me['public_nick'] ?? 'Капибара №…'}»'
                        : 'другие группы увидят ник или «Капибара №…» · нужно отдельное согласие',
                    all,
                    () => _toggle(true),
                    const Key('rating:offer:all'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: Space.xs),
            Text(
              'Имя и фамилию не показываем. Тумблер «Всем» сначала покажет текст согласия.',
              style: s.body(12.5, color: p.muted),
            ),
            const SizedBox(height: Space.l),
            FilledButton(
              key: const Key('rating:offer:done'),
              style: FilledButton.styleFrom(
                backgroundColor: anyOn ? p.accent : p.card,
                foregroundColor: anyOn ? p.onAccent : p.text,
                minimumSize: const Size.fromHeight(50),
                shape: const StadiumBorder(),
                side: anyOn ? null : BorderSide(color: p.edge),
              ),
              onPressed: () {
                tick();
                Navigator.pop(context, anyOn);
              },
              child: Text(
                anyOn ? 'Готово' : 'Оставить скрытым',
                style: s.body(16, weight: FontWeight.w600, color: anyOn ? p.onAccent : p.text),
              ),
            ),
            if (!anyOn)
              _StopLink(
                key: const Key('rating:offer:sheet:stop'),
                onTap: () {
                  ratingOfferAct(widget.api, 'stop');
                  Navigator.pop(context, false);
                },
              ),
          ],
        ),
      ),
    );
  }
}

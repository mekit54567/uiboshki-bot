// «Поддержать проект» (Никита 18.10): донат на сайте (/donate по личной ссылке,
// webapp/routes/billing.py) — не подписка, ничего не открывает, просто спасибо.
// В приложении — только лист с пояснением и кнопка на сайт, без кассы. На
// iPhone нет вовсе: донат не через Apple — против правил App Store; сервер на
// X-App: ios отвечает {"hidden": true}, а сборка для iPhone и не спрашивает.
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';
import 'plus.dart';
import 'plus_screen.dart' show PlusLinks;

const donateNote = 'Это не подписка и ничего не открывает — просто спасибо.';

final _shown = Expando<bool>();

/// Показывать ли строку «Поддержать проект» в «Ещё»: сервер сказал
/// hidden:false. Ответ помнится на запуск; не ответил — строки нет.
Future<bool> donateShown(Api api) async {
  if (!PlusBonus.allowed) return false;
  final known = _shown[api];
  if (known != null) return known;
  try {
    final r = await api.get('/donate');
    return _shown[api] = r is Map && r['hidden'] == false;
  } catch (_) {
    return false;
  }
}

/// Лист «Поддержать проект»: ссылка свежая (живёт сутки) — спрашиваем каждый раз.
Future<void> showDonateSheet(BuildContext context, Api api) async {
  if (!PlusBonus.allowed) return;
  final toast = Overlay.of(context, rootOverlay: true);
  Map<String, dynamic> d;
  try {
    d = Map<String, dynamic>.from(await api.get('/donate') as Map);
  } catch (e) {
    toastOn(toast, errorText(e), kind: ToastKind.error);
    return;
  }
  if (d['hidden'] != false || !context.mounted) return;
  await appSheet<void>(context, (_) => DonateSheet(data: d));
}

class DonateSheet extends StatelessWidget {
  final Map<String, dynamic> data;
  const DonateSheet({super.key, required this.data});

  Future<void> _go(BuildContext context, String url) async {
    tick();
    final toast = Overlay.of(context, rootOverlay: true);
    Navigator.pop(context);
    var ok = false;
    try {
      ok = await PlusLinks.open(Uri.parse(url));
    } catch (_) {}
    if (!ok) toastOn(toast, 'Не открылось — попробуй ещё раз', kind: ToastKind.error);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final url = '${data['url'] ?? ''}';
    final amounts = [for (final a in data['amounts'] as List? ?? const []) '$a ₽'];
    final min = data['min'] is int ? data['min'] as int : 0;
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Поддержать проект', style: s.title(24)),
            const SizedBox(height: Space.s),
            Text(
              'Если Капибара помогает тебе учиться — можно сказать спасибо рублём: на сервер, ИИ и новые функции.',
              style: s.body(15, color: p.muted),
            ),
            const SizedBox(height: Space.m),
            Tile(
              key: const Key('donate:note'),
              child: Row(
                children: [
                  Icon(Icons.favorite_border_rounded, color: p.accent),
                  const SizedBox(width: Space.m),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(donateNote, style: s.body(15, weight: FontWeight.w600)),
                        const SizedBox(height: 2),
                        Text(
                          'Всё бесплатное остаётся бесплатным, «Капибара+» — отдельно: дней подписки донат не даёт.',
                          style: s.body(13, color: p.muted),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            if (amounts.isNotEmpty) ...[
              const SizedBox(height: Space.m),
              Text(
                'Сумма — на выбор: ${amounts.join(' · ')}${min > 0 ? ' или своя, от $min ₽' : ''}. '
                'Разово, без автосписаний; чек — из «Мой налог».',
                key: const Key('donate:amounts'),
                style: s.body(13, color: p.muted),
              ),
            ],
            const SizedBox(height: Space.xl),
            if (url.isEmpty)
              Tile(
                key: const Key('donate:soon'),
                child: Row(
                  children: [
                    Icon(Icons.schedule_rounded, color: p.muted),
                    const SizedBox(width: Space.m),
                    Expanded(
                      child: Text(
                        'Поддержать можно будет совсем скоро — оплата ещё подключается.',
                        style: s.body(14, color: p.muted),
                      ),
                    ),
                  ],
                ),
              )
            else
              FilledButton.icon(
                key: const Key('donate:go'),
                style: FilledButton.styleFrom(
                  backgroundColor: p.accent,
                  foregroundColor: p.onAccent,
                  minimumSize: const Size.fromHeight(52),
                  shape: const StadiumBorder(),
                ),
                onPressed: () => _go(context, url),
                icon: const Icon(Icons.open_in_new_rounded, size: 20),
                label: Text(
                  'Поддержать на сайте',
                  style: s.body(16, weight: FontWeight.w600, color: p.onAccent),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// «Роадмап» (Никита 18.10, roadmap.py): что Никита делает сейчас и что дальше —
// тем, кто поддержал проект любой суммой, как спасибо, а не покупка. Строка —
// в «Ещё» под «Поддержать проект» и показывается вместе с ней; на iPhone нет
// ни того, ни другого (сервер hidden, сборка и не спрашивает).
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';
import 'donate.dart';
import 'plus.dart';

Future<void> showRoadmapSheet(BuildContext context, Api api) async {
  if (!PlusBonus.allowed) return;
  final toast = Overlay.of(context, rootOverlay: true);
  Map<String, dynamic> d;
  try {
    d = Map<String, dynamic>.from(await api.get('/roadmap') as Map);
  } catch (e) {
    toastOn(toast, errorText(e), kind: ToastKind.error);
    return;
  }
  if (d['hidden'] != false || !context.mounted) return;
  await appSheet<void>(context, (_) => RoadmapSheet(data: d, api: api));
}

class RoadmapSheet extends StatelessWidget {
  final Map<String, dynamic> data;
  final Api api;
  const RoadmapSheet({super.key, required this.data, required this.api});

  static IconData _icon(String status) => switch (status) {
    'done' => Icons.check_circle_outline_rounded,
    'idea' => Icons.lightbulb_outline_rounded,
    _ => Icons.push_pin_outlined,
  };

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final locked = data['locked'] != false;
    final statuses = Map<String, dynamic>.from(data['statuses'] as Map? ?? const {});
    final items = [for (final i in data['items'] as List? ?? const []) Map<String, dynamic>.from(i as Map)];
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Роадмап', style: s.title(24)),
            const SizedBox(height: Space.s),
            Text('Что я делаю сейчас и что дальше', style: s.body(15, color: p.muted)),
            const SizedBox(height: Space.m),
            if (locked) ...[
              Tile(
                key: const Key('roadmap:locked'),
                child: Row(
                  children: [
                    Icon(Icons.favorite_border_rounded, color: p.accent),
                    const SizedBox(width: Space.m),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Для тех, кто поддержал проект', style: s.body(15, weight: FontWeight.w600)),
                          const SizedBox(height: 2),
                          Text(
                            'Любая сумма от ${data['min'] ?? 50} ₽ — это спасибо, а не покупка. Роадмап откроется сам.',
                            style: s.body(13, color: p.muted),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: Space.xl),
              FilledButton.icon(
                key: const Key('roadmap:donate'),
                style: FilledButton.styleFrom(
                  backgroundColor: p.accent,
                  foregroundColor: p.onAccent,
                  minimumSize: const Size.fromHeight(52),
                  shape: const StadiumBorder(),
                ),
                onPressed: () {
                  tick();
                  Navigator.pop(context);
                  showDonateSheet(context, api);
                },
                icon: const Icon(Icons.favorite_border_rounded, size: 20),
                label: Text('Поддержать проект', style: s.body(16, weight: FontWeight.w600, color: p.onAccent)),
              ),
            ] else ...[
              for (final st in statuses.keys)
                if (items.any((i) => i['status'] == st)) ...[
                  Padding(
                    padding: const EdgeInsets.only(top: Space.m, bottom: Space.s),
                    child: Text('${statuses[st]}'.toUpperCase(), style: s.body(12, color: p.muted, weight: FontWeight.w600)),
                  ),
                  for (final i in items.where((i) => i['status'] == st))
                    Padding(
                      padding: const EdgeInsets.only(bottom: Space.s),
                      child: Tile(
                        key: Key('roadmap:${i['title']}'),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(_icon(st), color: st == 'done' ? p.muted : p.accent, size: 22),
                            const SizedBox(width: Space.m),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('${i['title']}', style: s.body(15, weight: FontWeight.w600)),
                                  const SizedBox(height: 2),
                                  Text('${i['about']}', style: s.body(13, color: p.muted)),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                ],
              const SizedBox(height: Space.s),
              Text(
                'Спасибо, что поддержал! Планы — не обещания: что-то может сдвинуться.',
                style: s.body(13, color: p.muted),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

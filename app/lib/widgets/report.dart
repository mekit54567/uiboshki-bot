// «⋯» у чужой записи — заметки, ДЗ, файла, общего дедлайна (правило Apple 1.2,
// 5.99.0): «Пожаловаться» — запись уйдёт владельцу на проверку (ugc.py на
// сервере), «Скрыть автора» — его записи пропадут только у тебя; вернуть всех —
// «Ещё → Безопасность».
import 'package:flutter/material.dart';

import '../api/api.dart';
import '../screens/legal.dart' show openLegal;
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import 'common.dart';

const reportReasons = ['Оскорбление или травля', 'Спам или реклама', 'Чужие личные данные', 'Другое'];

class ReportButton extends StatelessWidget {
  final Api api;
  final String kind;
  final int id;

  /// Скрыл автора — экран перезагружает список.
  final VoidCallback? onChanged;
  const ReportButton({super.key, required this.api, required this.kind, required this.id, this.onChanged});

  @override
  Widget build(BuildContext context) => IconButton(
    key: Key('report:$kind:$id'),
    tooltip: 'Пожаловаться или скрыть',
    visualDensity: VisualDensity.compact,
    onPressed: () => openReportMenu(context, api, kind: kind, id: id, onChanged: onChanged),
    icon: Icon(Icons.more_horiz_rounded, size: 20, color: AppStyle.of(context).p.muted),
  );
}

Future<void> openReportMenu(
  BuildContext context,
  Api api, {
  required String kind,
  required int id,
  VoidCallback? onChanged,
}) async {
  tick();
  final choice = await appSheet<String>(context, (ctx) => _ReportSheet(api: api));
  if (choice == null || !context.mounted) return;
  final toast = Overlay.of(context, rootOverlay: true);
  try {
    if (choice == _hide) {
      final ok = await confirmSheet(
        context,
        title: 'Скрыть автора?',
        text: 'Его заметки, ДЗ и файлы пропадут у тебя. У остальных всё останется. Вернуть — «Ещё → Безопасность».',
        action: 'Скрыть',
      );
      if (!ok) return;
      await api.post('/hide-author', {'kind': kind, 'id': id});
      toastOn(toast, 'Скрыл — его записей у тебя больше нет', kind: ToastKind.done);
      onChanged?.call();
    } else {
      await api.post('/report', {'kind': kind, 'id': id, 'reason': choice});
      toastOn(toast, 'Спасибо! Посмотрим и уберём, если нарушает правила', kind: ToastKind.done);
    }
  } on ApiError catch (e) {
    toastOn(toast, e.message, kind: ToastKind.error);
  } catch (e) {
    toastOn(toast, errorText(e), kind: ToastKind.error);
  }
}

const _hide = '__hide';

class _ReportSheet extends StatelessWidget {
  final Api api;
  const _ReportSheet({required this.api});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    Widget row(String text, String value, {IconData? icon, Key? key}) => InkWell(
      key: key,
      borderRadius: BorderRadius.circular(Radii.chip),
      onTap: () => Navigator.pop(context, value),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.m),
        child: Row(
          children: [
            if (icon != null) ...[Icon(icon, size: 20, color: p.muted), const SizedBox(width: Space.m)],
            Expanded(child: Text(text, style: s.body(16))),
          ],
        ),
      ),
    );
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Пожаловаться', style: s.title(24)),
            const SizedBox(height: Space.s),
            Text('Что не так с записью? Посмотрим и уберём, если нарушает правила.', style: s.body(15, color: p.muted)),
            const SizedBox(height: Space.s),
            for (final r in reportReasons) row(r, r, key: Key('reason:$r')),
            Divider(height: Space.l, color: p.line),
            row('Скрыть автора', _hide, icon: Icons.visibility_off_outlined, key: const Key('report:hide')),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(
                style: TextButton.styleFrom(padding: EdgeInsets.zero, foregroundColor: p.muted),
                onPressed: () => openLegal(context, api, 'rules'),
                child: Text('Правила Капибары', style: s.body(14, color: p.muted)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

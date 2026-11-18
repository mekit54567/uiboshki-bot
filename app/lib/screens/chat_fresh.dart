// Kapi ИИ нового дизайна (шаг 8, макет «Kapi ИИ», Никита 11.11): три понятных
// начала вместо случайных примеров — они подставляются в поле, а не уходят
// сразу; остаток вопросов и где лежит история — строкой над полем; источники
// ответа — строками, по которым удобно попасть пальцем; «Скопировать» и
// «Подумать ещё · N» — под ответом. Только при «Новом».
part of 'chat.dart';

/// «С чего начать»: что подставить в поле. subject — сначала выбрать предмет.
const freshStarters = [
  ('Объяснить лекцию', 'выберешь предмет и номер', 'Объясни лекцию '),
  ('Разобрать задачу', 'можно фото или файл', 'Разбери задачу: '),
  ('Что сдать на этой неделе', '', 'Что сдать на этой неделе?'),
];

/// Строка над полем: «Сегодня осталось 17 вопросов из 20. История чатов
/// хранится на этом телефоне.»
String freshQuotaLine(int? left, int? limit) {
  const where = 'История чатов хранится на этом телефоне.';
  if (left == null) return where;
  if (left <= 0) return 'На сегодня вопросы кончились, завтра можно снова. $where';
  final of = limit != null && limit > 0 ? ' из $limit' : '';
  return 'Сегодня ${plural(left, 'остался', 'осталось', 'осталось')} $left '
      '${plural(left, 'вопрос', 'вопроса', 'вопросов')}$of. $where';
}

/// Предмет в шапке капсулой: точка цвета предмета, «Все предметы» — без неё.
class _FreshSubject extends StatelessWidget {
  final String subject;
  final VoidCallback onTap;
  const _FreshSubject({required this.subject, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Semantics(
      button: true,
      child: GestureDetector(
        key: const Key('chat:subject'),
        behavior: HitTestBehavior.opaque,
        onTap: () {
          tick();
          onTap();
        },
        child: Container(
          height: 36,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: p.edge),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (subject.isNotEmpty) ...[
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(color: s.ink(subject), shape: BoxShape.circle),
                ),
                const SizedBox(width: 8),
              ],
              Flexible(
                child: Text(
                  subject.isEmpty ? 'Все предметы' : subject,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: s.body(13.5, weight: FontWeight.w600),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// «С чего начать»: три строки в карточке.
class _FreshStart extends StatelessWidget {
  final ValueChanged<int> onPick;
  const _FreshStart({required this.onPick});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Section('С чего начать'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l),
          child: Tile(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                for (final (i, (title, sub, _)) in freshStarters.indexed) ...[
                  if (i > 0) Divider(height: 1, color: p.line),
                  InkWell(
                    key: Key('chat:start:$i'),
                    onTap: () {
                      tick();
                      onPick(i);
                    },
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(title, style: s.body(15, weight: FontWeight.w600)),
                                if (sub.isNotEmpty) Text(sub, style: s.body(13, color: p.muted)),
                              ],
                            ),
                          ),
                          Icon(Icons.chevron_right_rounded, color: p.muted),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Строка источника: номер (или значок файла), название, где именно.
typedef FreshSourceRow = ({int? n, String title, String? where, VoidCallback onTap});

/// Название лекции для строки источника: без «!» и «_» в начале — так файлы
/// поднимают наверх в СДО (как human_title на сервере).
String freshSourceTitle(Map<String, dynamic> src) {
  final raw = '${src['title'] ?? src['label'] ?? ''}'.trim();
  final t = raw.replaceFirst(RegExp(r'^[\s!#*_~.\-–—]+'), '').trim();
  return t.isEmpty ? raw : t;
}

/// «слайд 3», «слайды 3–4», «стр. 7» — хвост подписи сервера после « · »;
/// у DOCX/TXT («часть») и у файла целиком — ничего.
String? freshSourceWhere(Map<String, dynamic> src) {
  if (src['page'] == null || src['kind'] == 'часть') return null;
  final label = '${src['label'] ?? ''}';
  final i = label.lastIndexOf(' · ');
  if (i >= 0) return label.substring(i + 3);
  return 'стр. ${(src['page'] as num).toInt()}';
}

/// Источники ответа строками, по которым удобно попасть пальцем.
class _FreshSources extends StatelessWidget {
  final List<FreshSourceRow> rows;
  const _FreshSources({required this.rows});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Tile(
      key: const Key('chat:sources'),
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          for (final (i, r) in rows.indexed) ...[
            if (i > 0) Divider(height: 1, color: p.line),
            InkWell(
              key: Key('chat:source:$i'),
              onTap: () {
                tick();
                r.onTap();
              },
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 56),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.m, Space.m),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 24,
                        child: r.n != null
                            ? Text(
                                '${r.n}',
                                style: s.body(14, weight: FontWeight.w700, color: p.accent),
                              )
                            : Icon(Icons.insert_drive_file_outlined, size: 16, color: p.accent),
                      ),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              r.title,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: s.body(14.5, weight: FontWeight.w600),
                            ),
                            if (r.where != null) Text(r.where!, style: s.body(12.5, color: p.muted)),
                          ],
                        ),
                      ),
                      const SizedBox(width: Space.s),
                      Icon(Icons.chevron_right_rounded, color: p.muted),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Маленькая кнопка под ответом: «Скопировать», «Подумать ещё · 9».
class _FreshChip extends StatelessWidget {
  final String text;
  final VoidCallback? onTap;
  const _FreshChip({super.key, required this.text, this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Semantics(
      button: true,
      enabled: onTap != null,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap == null
            ? null
            : () {
                tick();
                onTap!();
              },
        // без alignment: в Wrap контейнер с выравниванием растягивается во всю ширину
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: p.card,
            borderRadius: BorderRadius.circular(17),
            border: Border.all(color: p.line),
          ),
          child: Text(
            text,
            style: s.body(13, weight: FontWeight.w600, color: onTap == null ? p.muted : p.text),
          ),
        ),
      ),
    );
  }
}

// Ссылки из /api/meta (канал бота, «написать нам», гайд по СДО) — один
// запрос на запуск: адреса задаёт сервер (CHANNEL_URL, CONTACT_URL), а не сборка.
import 'api.dart';

/// Приписка для магазинов (App Store 5.2.1): приложение не от института.
const unofficialNote = 'Неофициальное приложение для студентов РТУ МИРЭА. Его сделали студенты, а не университет.';

Map<String, String>? _cache;

Future<Map<String, String>> appLinks(Api api) async {
  if (_cache != null) return _cache!;
  final m = await api.get('/meta');
  final links = (m is Map ? m['links'] : null) as Map? ?? {};
  return _cache = {for (final e in links.entries) '${e.key}': '${e.value ?? ''}'};
}

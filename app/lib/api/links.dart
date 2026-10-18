// Ссылки из /api/meta (канал бота, «написать нам», гайд по СДО) — один
// запрос на запуск: адреса задаёт сервер (CHANNEL_URL, CONTACT_URL), а не сборка.
// Там же — что включено на сервере (features: карта корпусов и т. п.).
import 'api.dart';

Map<String, String>? _cache;
Map<String, bool>? _features;

Future<Map<String, String>> appLinks(Api api) async {
  if (_cache != null) return _cache!;
  final m = await api.get('/meta');
  final links = (m is Map ? m['links'] : null) as Map? ?? {};
  final f = (m is Map ? m['features'] : null) as Map? ?? {};
  _features = {for (final e in f.entries) '${e.key}': e.value == true};
  return _cache = {for (final e in links.entries) '${e.key}': '${e.value ?? ''}'};
}

/// Включено ли на сервере (/api/meta → features): «map» — карта корпусов (5.100.4).
Future<bool> appFeature(Api api, String name) async {
  if (_features == null) await appLinks(api);
  return _features?[name] ?? false;
}

/// То же без ожидания — когда [appLinks] уже ответил (плитки «Ещё»).
bool featureOn(String name) => _features?[name] ?? false;

/// Тестам: забыть ответ /api/meta (в одном файле тестов — разный сервер).
void forgetLinks() {
  _cache = null;
  _features = null;
}

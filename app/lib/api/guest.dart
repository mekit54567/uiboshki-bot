// Расписание без входа (правило Apple 5.1.1(v), 5.99.0): тот же поиск и
// экран расписания, что во вкладке «Неделя → Поиск», но через публичные
// /api/v1/guest/… — справочник МИРЭА публичный, ничего личного. Закреплять и
// открывать пару нельзя: это уже аккаунт.
import 'api.dart';

class GuestApi extends Api {
  GuestApi({super.client});

  @override
  Future<dynamic> get(String path) {
    if (path == '/pins') return Future.value(<String, dynamic>{'items': <dynamic>[]});
    if (path.startsWith('/search') || path.startsWith('/target/')) return super.get('/guest$path');
    return Future.error(Unauthorized());
  }
}

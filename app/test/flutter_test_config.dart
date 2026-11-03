// Общая настройка тестов: плашки новых ачивок выключены — они выезжают сверху
// и закрывали бы кнопки в чужих тестах; редкие фразы и «идеальная волна» не
// выпадают — подписи в тестах не зависят от случая. Тест ачивок включает сам.
// Токен — в хранилище в памяти: плагин Keychain/Keystore в тестах не отвечает.
import 'dart:async';
import 'dart:math' as math;

import 'package:uiboshki/achievements/ui.dart';
import 'package:uiboshki/api/token_store.dart';
import 'package:uiboshki/widgets/capy.dart';

/// Случай, которому никогда не везёт: nextInt(n) — всегда n − 1.
class NoLuck implements math.Random {
  @override
  int nextInt(int max) => max - 1;
  @override
  double nextDouble() => 0.5;
  @override
  bool nextBool() => false;
}

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  achBanners = false;
  capyRandom = NoLuck();
  TokenStore.box = MemoryBox();
  await testMain();
}

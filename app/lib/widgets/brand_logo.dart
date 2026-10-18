// Логотипы VK ID, Яндекс ID и Telegram на кнопках входа — официальные знаки
// (Никита 18.10: «лого ВК и Яндекса», «лого ТГ тоже»). Исходники SVG и откуда
// каждый — design/brands/, PNG собирает tools/brand_icons.js. Цвета знаков
// фирменные и не зависят от темы: так требуют брендбуки.
import 'package:flutter/material.dart';

const brandLogos = {'vk': 'vk', 'yandex': 'yandex', 'telegram': 'telegram'};

class BrandLogo extends StatelessWidget {
  final String id;
  final double size;
  const BrandLogo(this.id, {super.key, this.size = 22});

  static bool has(String id) => brandLogos.containsKey(id);

  @override
  Widget build(BuildContext context) => Image.asset(
    'assets/brands/${brandLogos[id]}.png',
    key: Key('logo:$id'),
    width: size,
    height: size,
    filterQuality: FilterQuality.medium,
    excludeFromSemantics: true,
  );
}

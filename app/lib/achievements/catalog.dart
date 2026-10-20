// Ачивки (Никита 14–15.10): четыре ранга по времени суток — «Рассвет ·
// Полдень · Сумерки · Полночь». Рассветные учат пользоваться приложением
// (у каждой «Показать где»), полуденные — привычка, сумеречные — учёба,
// полночные — секретные: как получить, не пишем, пока не нашёл.
// Подписи для полароида и фразы капибары — в captions.dart (их проще править).
import 'package:flutter/material.dart';

import '../widgets/capy.dart' show CapyPose;

enum Rank { dawn, noon, dusk, midnight }

extension RankInfo on Rank {
  String get title => const ['Рассвет', 'Полдень', 'Сумерки', 'Полночь'][index];

  /// Поза капибары на значке — как на «Сегодня» в это время суток.
  CapyPose get pose => const [CapyPose.morning, CapyPose.day, CapyPose.evening, CapyPose.night][index];

  /// Небо значка сверху вниз.
  List<Color> get sky => const [
    [Color(0xFFFFE7C2), Color(0xFFFFB38A), Color(0xFFF08A6E)],
    [Color(0xFF7CC6FF), Color(0xFF5BA6F7), Color(0xFF3D8BF2)],
    [Color(0xFF3B2A6E), Color(0xFFB24B8F), Color(0xFFFF9A5A)],
    [Color(0xFF0A0D2A), Color(0xFF13173C), Color(0xFF1A1F4D)],
  ][index];

  /// Цвет капибары на этом небе.
  Color get ink => const [Color(0xFF5B2A1A), Colors.white, Colors.white, Color(0xFFFFE9A8)][index];

  /// Наклейка ранга на полароиде.
  Color get sticker => const [Color(0xFFFFD9B0), Color(0xFFCFE8FF), Color(0xFFFFC7A8), Color(0xFFFFE9A8)][index];
}

/// Куда ведёт «Показать где»: вкладка оболочки и подсказка, что там нажать.
class AchPlace {
  final int tab;
  final String hint;
  const AchPlace(this.tab, this.hint);
}

class Achievement {
  final String id;
  final Rank rank;
  final String title;

  /// Как получить. У полночных видно только после того, как нашёл.
  final String how;
  final AchPlace? place;
  const Achievement(this.id, this.rank, this.title, this.how, [this.place]);

  bool get secret => rank == Rank.midnight;
}

// вкладки — как в shell.dart: 0 Сегодня, 1 Неделя, 2 Сдать, 3 Учёба, 4 Ещё
const achievements = [
  Achievement(
    'lesson',
    Rank.dawn,
    'Где пара?',
    'Открыть пару: где она, кто ведёт и что по баллам',
    AchPlace(0, 'Нажми на пару'),
  ),
  Achievement(
    'week_next',
    Rank.dawn,
    'Листаю неделю',
    'Перелистнуть на следующую неделю',
    AchPlace(1, 'Смахни неделю влево'),
  ),
  Achievement(
    'goal',
    Rank.dawn,
    'Своя цель',
    'Выбрать цель по предмету: автомат или с экзаменом',
    AchPlace(3, 'Открой предмет, там карточка «Цель»'),
  ),
  Achievement(
    'sdo',
    Rank.dawn,
    'Свой вход в СДО',
    'Подключить свой вход, чтобы видеть баллы',
    AchPlace(3, 'Нажми «Подключить СДО»'),
  ),
  Achievement(
    'widget',
    Rank.dawn,
    'На столе',
    'Поставить виджет Капибары на экран телефона',
    AchPlace(0, 'Зажми пустое место на экране телефона → Виджеты → Капибара'),
  ),
  Achievement(
    'look',
    Rank.dawn,
    'По-своему',
    'Поменять оформление, тему или иконку',
    AchPlace(4, 'Нажми «Оформление»'),
  ),
  Achievement('ai', Rank.dawn, 'Первый вопрос', 'Спросить ИИ по лекциям группы', AchPlace(3, 'Нажми «Kapi ИИ»')),
  Achievement(
    'summary',
    Rank.dawn,
    'Конспект',
    'Открыть конспект лекции',
    AchPlace(3, 'Открой «Файлы» и нажми на лекцию'),
  ),
  Achievement(
    'remind',
    Rank.dawn,
    'Будильник на пару',
    'Настроить напоминание перед парой',
    AchPlace(4, 'Нажми «Уведомления»'),
  ),
  Achievement(
    'teacher',
    Rank.dawn,
    'Знаю препода',
    'Найти расписание преподавателя',
    AchPlace(1, 'Нажми на поиск вверху недели'),
  ),
  Achievement(
    'submit',
    Rank.noon,
    'Сдано из Капибары',
    'Сдать работу в СДО прямо из приложения',
    AchPlace(2, 'Нажми «Сдать» у задания'),
  ),
  Achievement('week5', Rank.noon, 'Неделя в кармане', 'Заходить в Капибару каждый день с понедельника по пятницу'),
  Achievement(
    'early',
    Rank.noon,
    'Заранее',
    'Сдать работу из приложения за три дня до срока',
    AchPlace(2, 'Сроки — на вкладке «Сдать»'),
  ),
  Achievement(
    'streak',
    Rank.noon,
    'Без пропусков',
    'Четыре лекции подряд по одному предмету без пропуска',
    AchPlace(3, 'Посещения — на экране предмета'),
  ),
  Achievement('plus', Rank.noon, 'Плюс балл', 'Получить новый балл в СДО', AchPlace(3, 'Баллы — на вкладке «Учёба»')),
  Achievement(
    'found',
    Rank.noon,
    'Найдено в лекциях',
    'Открыть слайд лекции из поиска или из ответа ИИ',
    AchPlace(3, 'Открой «Файлы» и поищи в тексте лекций'),
  ),
  Achievement(
    'auto',
    Rank.dusk,
    'Автомат',
    'Набрать цель «автомат» по предмету',
    AchPlace(3, 'Открой предмет, там карточка «Цель»'),
  ),
  Achievement(
    'clean',
    Rank.dusk,
    'Чистый лист',
    'Все работы по предмету зачтены',
    AchPlace(3, 'Работы — на экране предмета'),
  ),
  Achievement('month', Rank.dusk, 'Месяц с Капибарой', 'Заходить в Капибару 30 разных дней'),
  Achievement(
    'calm',
    Rank.dusk,
    'Ни одного «горит»',
    'Сдать из приложения три работы подряд не в последний день',
    AchPlace(2, 'Сроки — на вкладке «Сдать»'),
  ),
  Achievement('t2222', Rank.midnight, '22:22', 'Коснуться капибары ровно в 22:22'),
  Achievement('wave', Rank.midnight, 'Идеальная волна', 'Поймать редкую волну, пока капибара обновляет экран'),
  Achievement('fri13', Rank.midnight, 'Пятница, 13-е', 'Зайти в Капибару в пятницу, 13-е'),
  Achievement(
    'secret',
    Rank.midnight,
    'Тайная фраза',
    'Услышать от капибары фразу, которая выпадает раз на сотню касаний',
  ),
  Achievement('one_of_us', Rank.midnight, 'Один из нас', 'Капибара повернулась к тебе: раз на десять тысяч касаний'),
];

Achievement? achievementById(String id) {
  for (final a in achievements) {
    if (a.id == id) return a;
  }
  return null;
}

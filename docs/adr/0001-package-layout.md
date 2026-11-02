# 0001. Код сервера — пакет `kapibara/`, папки по темам

Статус: принято (02.11.2026)

## Контекст
В корне репозитория 102 файла `.py` (21 тыс. строк): СДО, расписание, ИИ,
оплата, рассылки и инфраструктура лежат вперемешку. Чтобы понять одну тему,
приходится искать по префиксам имён (`sdo_*`, `schedule_*`, `pulse_*`).

## Решение
Весь код сервера переезжает в один пакет `kapibara/` (как бренд и папка
`/opt/kapibara` на сервере):

    bot.py             точка входа, остаётся в корне навсегда
    kapibara/
      core/            config, errors, logging, utils, net, locks, ratelimit
      features/<тема>  sdo, schedule, pulse, ai, lectures, deadlines,
                       notifications, groups, billing, social, identity,
                       privacy, content
      bot/             Telegram: handlers, middleware, keyboards
      web/             сайт и API (нынешний webapp/, переезжает последним)
      jobs/            планировщик
      ops/             здоровье, бэкапы, диагностика

Префикс уходит в путь: `sdo_grades.py` → `kapibara/features/sdo/grades.py`.

## Почему не иначе
- **Папки по типам** (`parsers/`, `services/`, `integrations/`): СДО
  размазалось бы по трём местам, а чинят обычно одну тему целиком.
  Деление «сеть / разбор / база» делаем внутри темы, где оно реально мешает.
- **`src/`-раскладка и установка пакетом:** лишняя смена способа запуска
  (`python bot.py` в Dockerfile, Procfile, start.sh) без выгоды для нас.

## Последствия
Переезд — около 14 PR, по теме за PR, по технике из [0003](0003-safe-moves.md).
`config`, `database`, `scheduler`, `webapp` — последними: на них завязано всё.

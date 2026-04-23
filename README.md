# 🎓 MIREA Bot — Бот для группы Бизнес-информатики

Telegram-бот для студентов МИРЭА: расписание, дедлайны, решалка заданий.

---

## 📁 Структура проекта

```
mirea_bot/
├── bot.py              # Точка входа
├── config.py           # Все настройки и ключи
├── database.py         # SQLite: пользователи и дедлайны
├── groq_solver.py      # AI-решалка через Groq API
├── schedule_parser.py  # Парсинг iCal расписания МИРЭА
├── scheduler.py        # Утренние рассылки (APScheduler)
├── handlers/
│   ├── __init__.py     # Регистрация роутеров
│   ├── start.py        # /start, /help, подписка
│   ├── schedule.py     # /schedule — расписание
│   ├── deadlines.py    # /deadlines, /add, /done, /del
│   └── solver.py       # Решалка задач (текст + фото)
├── requirements.txt
├── Procfile            # Для Railway
└── railway.toml        # Конфиг деплоя
```

---

## 🚀 Деплой на Railway (шаг за шагом)

### 1. Подготовь GitHub репозиторий
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/ТВО_ИМЯ/mirea-bot.git
git push -u origin main
```

### 2. Создай проект на Railway
1. Зайди на [railway.app](https://railway.app)
2. New Project → Deploy from GitHub repo
3. Выбери репозиторий `mirea-bot`

### 3. Добавь переменные окружения
В Railway → Variables добавь:

| Переменная    | Значение                                |
|---------------|-----------------------------------------|
| `BOT_TOKEN`   | Твой токен Telegram бота                |
| `GROQ_API_KEY`| Твой ключ Groq                          |
| `ICAL_URL`    | Ссылка iCal расписания                  |

> ⚠️ **Важно**: удали токены из `config.py` перед пушем в GitHub!
> Оставь только `os.getenv(...)` без дефолтных значений.

### 4. Railway сам запустит бота ✅

---

## 💬 Команды бота

| Команда / Кнопка | Действие |
|---|---|
| `/start` | Главное меню + регистрация |
| `/schedule` или 📅 | Расписание на сегодня |
| `/deadlines` или 📋 | Список активных дедлайнов |
| `/add` или ➕ | Добавить дедлайн (пошаговый ввод) |
| `/done 3` | Отметить дедлайн #3 выполненным |
| `/del 3` | Удалить дедлайн #3 |
| `/solve` или 🤖 | Решить задачу (текст или фото) |
| `/subscribe` 🔔 | Включить утренние уведомления |
| `/unsubscribe` 🔕 | Выключить уведомления |

---

## ⏰ Автоматические уведомления

- **7:30 МСК** — расписание на сегодня всем подписанным
- **8:00 МСК** — дедлайны на ближайшие 3 дня (если есть)

Изменить время → `config.py`:
```python
SCHEDULE_HOUR   = 7   # часы
SCHEDULE_MINUTE = 30  # минуты
```

---

## 🤖 Как работает решалка

1. Нажми кнопку **🤖 Решить задачу** или пришли текст длиннее 20 символов
2. Можно прислать **фото** с задачей — бот прочитает через Groq Vision
3. Получаешь структурированный ответ с объяснением

---

## 🛠 Локальный запуск (для теста)

```bash
pip install -r requirements.txt
python bot.py
```

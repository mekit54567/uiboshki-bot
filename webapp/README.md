# WebApp (Telegram Mini App)

HTTP-бэкенд (FastAPI) + статический фронтенд для бота УИБО-03-24. Отдельный
процесс от `bot.py` (тот — чистый long polling), делит с ним ту же SQLite-базу
и все существующие модули (`database.py`, `schedule_parser.py`, `ai_solver.py`
и т.д.) — ничего не задублировано, WebApp просто даёт HTTP-фасад.

## Что нужно, чтобы поднять (со стороны владельца — сервер/HTTPS/регистрация)

1. **Хостинг с HTTPS.** Telegram требует, чтобы `web_app.url` у кнопки был
   `https://`. Годится любой сервер (тот же, что и для бота), обратный прокси
   (Caddy/nginx) с автоматическим сертификатом (Let's Encrypt) — самый простой
   вариант.
2. **Запуск процесса** (второй, отдельно от `python bot.py`):
   ```
   uvicorn webapp.server:app --host 0.0.0.0 --port 8000
   ```
   Переменные окружения — те же, что уже нужны боту (`BOT_TOKEN`,
   `DATABASE_PATH`, `DEEPSEEK_API_KEY` — для чата обязателен, без него
   `/api/chat` будет отвечать 502).
3. **`WEBAPP_URL`** — задать в окружении **самого бота** (`bot.py`), это
   HTTPS-адрес шага 1-2 (например `https://example.com`). Пока не задан —
   бот просто не показывает кнопку "Открыть приложение" (см. `config.py`),
   ничего не ломается.
4. **Регистрация в BotFather:** `/newapp` → выбрать бота → указать тот же
   HTTPS-адрес. Дальше кнопка в самом Telegram-клиенте (меню бота / кнопка
   рядом с полем ввода) тоже будет открывать WebApp — в дополнение к кнопке
   внутри чата (`/app`, см. `handlers/start.py`).
5. **Подпись initData** — уже реализована на бэкенде (`webapp/auth.py`,
   HMAC-SHA256 по `BOT_TOKEN`, ровно по алгоритму из офдоков Telegram Mini
   Apps), больше ничего настраивать не нужно — единственное требование:
   `BOT_TOKEN` у `webapp/server.py` и у `bot.py` должен быть один и тот же.

## API

Каждый запрос — заголовок `X-Telegram-Init-Data: <Telegram.WebApp.initData>`,
без него 401. См. `/docs` (Swagger, включён по умолчанию FastAPI) на живом
сервере для полного списка полей.

- `GET  /api/me`
- `GET  /api/schedule/today|tomorrow|week|next`
- `GET  /api/deadlines?include_done=false` — общая таблица дедлайнов/ДЗ
  (поле `done` — это и есть чекбокс доски ДЗ, отдельной сущности "homework"
  в базе нет, см. PLAN.md)
- `POST /api/deadlines/{id}/toggle` `{"done": true|false}`
- `GET  /api/files?q=&subject=`
- `GET  /api/notes?date=YYYY-MM-DD`
- `GET  /api/calendar/link` — возвращает `{"token", "ics_path"}` для личной
  ICS-подписки (см. ниже)
- `POST /api/chat` `{"history": [{"role":"user","content":"..."}]}` →
  `{"content": "...", "reasoning": "..."}` — DeepSeek `deepseek-reasoner`,
  `reasoning` — трейс "мышления" для сворачиваемого блока на фронте.

## Личный ICS-календарь

`GET /ics/{token}` — **БЕЗ** `X-Telegram-Init-Data` (календарные приложения
не умеют слать кастомные заголовки при периодической автоподписке).
Токен — случайная непредсказуемая строка на студента (`/calendar` в самом
боте её выдаёт, генерится лениво при первом обращении), секретность держится
на непредсказуемости токена в пути, как у обычных calendar-share ссылок.
Отдаёт `.ics` с конкретными `VEVENT` на каждую пару (не `RRULE`) на 45 дней
вперёд, с ДЗ/заметками в `DESCRIPTION`, если они привязаны к этой дате и
предмету (см. `webapp/calendar_feed.py`, `handlers/announce.py:
parse_lesson_date`).

Файлы отдаются не напрямую (Telegram `file_id` не резолвится в URL без похода
через `getFile` от лица бота) — кнопка "Открыть" в WebApp делает
`Telegram.WebApp.openTelegramLink("https://t.me/<bot>?start=file_<id>")`,
бот ловит этот диплинк (`handlers/start.py: cmd_start_deeplink`) и присылает
документ в чат.

## Локальный прогон/тест

```
pip install -r requirements.txt
BOT_TOKEN=... DATABASE_PATH=mirea_bot.db uvicorn webapp.server:app --reload
```
Открыть `http://localhost:8000` — API отдаст 401 на реальные данные (initData
нет вне Telegram), но статика и структура страницы видны. Полноценно
протестировать WebApp можно только через настоящий Telegram-клиент после
регистрации в BotFather (`/newapp`) — локальный браузер не выдаёт `initData`.

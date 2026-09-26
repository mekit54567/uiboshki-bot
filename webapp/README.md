# WebApp (Telegram Mini App)

HTTP-бэкенд (FastAPI) + статический фронтенд для бота УИБО-03-24. Крутится
**в том же процессе, что и бот** (`bot.py` → `start_webapp`, порт — `$PORT`):
одна служба на Railway и один том с SQLite — отдельный процесс не видел бы ту
же базу. Все модули (`database.py`, `schedule_parser.py`, `ai_solver.py`)
общие — WebApp просто даёт им HTTP-фасад.

## Как включить на Railway (один раз)

1. **Домен.** Railway → сервис бота → **Settings → Networking → Generate
   Domain**, порт — `8080`. Получится адрес вида
   `https://uiboshki-bot-production.up.railway.app`.
2. **Переменные.** Railway → **Variables**: `WEBAPP_URL` = этот адрес (с
   `https://`, без `/` в конце) и `PORT` = `8080` (явно — чтобы порт сервера
   точно совпал с портом домена). Railway перезапустит бота; в Deploy Logs
   появится «🌐 WebApp слушает порт 8080».
3. **Всё.** При старте бот сам ставит кнопку меню «Приложение» слева от поля
   ввода (`setup_bot_menu` в `bot.py`), `/app` и `/start` показывают кнопку
   запуска, `/calendar` начинает выдавать ссылки.
4. **(По желанию) BotFather** — чтобы у бота в профиле была кнопка «Открыть»
   и работала ссылка `t.me/<бот>/app`: `/mybots` → бот → **Bot Settings →
   Configure Mini App → Enable Mini App** → тот же адрес. Для кнопки меню это
   не нужно — её ставит сам бот.

Проверка: `https://<домен>/health` в браузере → `{"ok":true}`. Сам
WebApp вне Telegram покажет «Не удалось авторизоваться» — так и должно быть:
данные отдаются только с подписью Telegram (`initData`, см. ниже).

**Подпись initData** — `webapp/auth.py`, HMAC-SHA256 по `BOT_TOKEN`, ровно по
алгоритму из офдоков Telegram Mini Apps; настраивать ничего не нужно.

**Чат** — DeepSeek `deepseek-reasoner` с трейсом «хода мыслей», если задан
`DEEPSEEK_API_KEY`; без него — Gemini, как решалка в боте.

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
  `{"content": "...", "reasoning": "...", "html": "..."}` — DeepSeek
  `deepseek-reasoner` (`reasoning` — трейс "мышления" для сворачиваемого
  блока), без его ключа — Gemini (`reasoning` пустой); `html` — ответ в том же
  виде, что и в боте (жирный, код, x² вместо x^2), уже экранированный.

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
протестировать WebApp можно только через настоящий Telegram-клиент (кнопка
меню бота или `/app`) — локальный браузер не выдаёт `initData`.

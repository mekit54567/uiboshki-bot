# Веб-часть Капибары (FastAPI)

HTTP-сервер Капибары: API для Mini App в Telegram, PWA `uiboshki.ru/app` и
своего приложения (Flutter, `app/`), сайт `/about`, страницы оплаты и
документов. Крутится **в том же процессе, что и бот** (`bot.py` →
`start_webapp`, порт — `$PORT`, по умолчанию 8080): одна служба и одна база
SQLite.

## Где что

- `server.py` — каркас: CORS, заголовки безопасности, `/health`, `/ready`,
  `/api/v1/…` = `/api/…`, подключение роутеров, статика (последней).
- `deps.py` — кто спрашивает (`CurrentUser`): подпись Telegram `initData`
  (`auth.py`, HMAC-SHA256 по `BOT_TOKEN`) или токен сессии устройства
  (`Authorization: Bearer`, вход через бота, VK ID, Яндекс ID или Apple).
- `routes/*.py` — обработчики по темам: расписание, сроки, файлы, ИИ-чат,
  СДО, аккаунт и вход, пуши, оплата, сайт, документы и другие. Новый модуль —
  в цикл `include_router` в `server.py`.
- `pages.py` — `index.html` Mini App с метками версий файлов (`?v=хэш`).
- `static/` — Mini App (`index.html`, `app.css`, `js/`), PWA на HTML
  (`app-html/`), сайт (`site/`), иконки PWA и `sw.js`.
- `flutter/` — запасная веб-сборка приложения (`/app-flutter`), её собирает
  GitHub Actions — руками не править.

Полный список путей — `/docs` (Swagger) на сервере, снимок контракта —
`tests/api_contract.json` (убрал путь — CI красный, добавил — `python
tools/api_snapshot.py`).

## Личный ICS-календарь

`GET /ics/{token}` — без входа: календарные приложения не умеют слать свои
заголовки. Токен — случайная строка на человека (`/calendar` в боте или
`/api/calendar/link`). Отдаёт `.ics` с парами на 45 дней вперёд и ДЗ/заметками
в описании (`calendar_feed.py`).

## Локальный запуск

```
pip install -r requirements.txt
BOT_TOKEN=... DATABASE_PATH=kapibara.db uvicorn webapp.server:app --reload
```

`http://localhost:8000/about` — сайт, `/app` — PWA (вход через бота).
API без входа отвечает 401. Тесты фронта — `tests/test_webapp_static.py` и
дымовой прогон в Chromium (`tests/test_webapp_smoke_browser.py`).

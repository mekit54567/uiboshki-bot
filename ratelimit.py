"""
Ограничение частоты для дорогих и чувствительных действий (экран
«Безопасность»): вопросы ИИ (бесплатный лимит Gemini не сжечь одному
человеку), сдача работ и подключение СДО (не долбить СДО чужими куками
перебором). Память процесса, скользящее окно — без базы и без внешних
сервисов; после рестарта счётчики начинаются заново, это нормально.
"""

import time
from collections import defaultdict, deque

# действие → (сколько, за сколько секунд)
LIMITS = {
    "ai": (15, 60),
    "submit": (6, 600),
    "sdo_connect": (5, 600),
    "send": (20, 60),          # файлы в чат: бот не должен заваливать личку и упираться в лимиты Telegram
    "deadline": (20, 600),     # свои дедлайны
    "note": (5, 600),          # заметки к парам (общие для группы); за сутки — ugc.note_spam
    "report": (10, 600),       # жалобы на записи людей (ugc.py) — владельцу в бота
    "reaction": (30, 600),     # реакции на пару (lesson_reactions.py)
    "sdo_fresh": (3, 300),     # «обновить» баллы: каждый раз — журнал каждого предмета в СДО с IP сервера
    "site_search": (40, 60),   # сайт /about: поиск расписания без входа — по IP
    "site_target": (15, 60),
    "site_all": (300, 60),
    "auth_start": (10, 600),   # коды входа в приложение без Telegram — по IP (webapp/routes/auth.py)
    "auth_review": (5, 600),   # код демо-входа проверяющих магазинов — по IP (review_demo.py)
    "lsearch": (30, 60),       # поиск внутри лекций: каждый запрос — вектор у Gemini     # сайт /about: все посетители вместе — зеркало МИРЭА не долбить
}
MAX_KEYS = 5000                # ключей больше — выкинуть отжившие (IP с сайта не копятся вечно)
_hits: dict[tuple[str, int], deque] = defaultdict(deque)


def _sweep(now: float):
    stale = [k for k, q in _hits.items() if not q or now - q[-1] > LIMITS[k[0]][1]]
    for k in stale:
        del _hits[k]


def allow(action: str, user_id: int) -> bool:
    limit, window = LIMITS[action]
    now = time.monotonic()
    if len(_hits) > MAX_KEYS:
        _sweep(now)
    q = _hits[(action, user_id)]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def reset():
    _hits.clear()

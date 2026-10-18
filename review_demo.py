"""Демо-вход для проверяющих магазинов (App Store, RuStore).

Проверяющий Apple не войдёт ни в Telegram-бота, ни в СДО МИРЭА, а Apple
требует рабочий вход (правило 2.1). Поэтому — код доступа: `REVIEW_CODE`
(секрет хостинга; не задан — входа по коду нет). Код → сессия устройства
особого аккаунта `DEMO_UID`, токен с приставкой `rv.`; все его запросы
/api/… отвечает этот модуль из записи стенда `webapp/static/site/demo.json`
(та же, что у демо на сайте и робота приложения: ничьих настоящих данных
нет). Настоящие функции и база демо-аккаунта не касаются: «удалить
аккаунт» и выход отвечают «готово», данные остаются для следующего
проверяющего.

Запись сделана на неделе 5–11 октября 2026. Чтобы «сегодня» в приложении
совпадало с данными, всё сдвигается на целое число недель к текущей
(дни недели те же): даты в запросах — назад, в ответах — вперёд.
"""

import copy
import hmac
import json
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

DEMO_UID = -19_000_000_000          # ниже LOCAL_BASE: «без Telegram», в рассылки не попадёт
TOKEN_PREFIX = "rv."
REC_MONDAY = date(2026, 10, 5)      # неделя записи demo.json
FIXTURES = Path(__file__).parent / "webapp" / "static" / "site" / "demo.json"

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

# что приложение спрашивает, но в записи стенда нет (как test/fake_api.dart;
# остальное — {"ok": true})
DEFAULTS = {
    "/api/day": {"lessons": []},
    "/api/week": {"week": None, "days": []},
    "/api/sdo/submit-rules": {"accepted": [], "labels": [], "maxfiles": 3, "maxbytes": 10485760},
    "/api/sdo/submit": {"status": "Отправлено для оценивания"},
    "/api/groups/search": {"items": [{"id": 4928, "name": "УИБО-03-24"}]},
    "/api/me/group": {"group": {"id": 4928, "name": "УИБО-03-24", "own": True}},
}
# настоящие обработчики: без данных человека
PASS = ("/api/meta", "/api/legal/", "/api/auth/review", "/api/auth/providers")


def code() -> str:
    import config
    return config.REVIEW_CODE


def enabled() -> bool:
    return bool(code())


def check_code(value: str) -> bool:
    want = code()
    return bool(want) and hmac.compare_digest(value.strip().encode(), want.encode())


async def login(device: str) -> str:
    """Новая сессия демо-аккаунта → токен (rv.…)."""
    import secrets
    from database._conn import connect
    from database.sessions import SESSION_TTL, _now, _ts, token_hash
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    async with connect() as db:
        await db.execute("INSERT INTO sessions (user_id, token_hash, device, last_seen, expires_at) "
                         "VALUES (?, ?, ?, ?, ?)", (DEMO_UID, token_hash(token), device[:120],
                                                    _ts(_now()), _ts(_now() + SESSION_TTL)))
        await db.commit()
    return token


@lru_cache(maxsize=1)
def fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["fx"]


def shift_days(today: date) -> int:
    monday = today - timedelta(days=today.weekday())
    return (monday - REC_MONDAY).days // 7 * 7


_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_LONG = re.compile(r"(?:(%s), )?(\d{1,2}) (%s) (\d{4})" % ("|".join(WEEKDAYS), "|".join(MONTHS)))


def _move_iso(text: str, days: int) -> str:
    def sub(m):
        try:
            d = date(int(m[1]), int(m[2]), int(m[3])) + timedelta(days=days)
        except ValueError:
            return m[0]
        return d.isoformat()
    return _ISO.sub(sub, text)


def _move_long(text: str, days: int) -> str:
    def sub(m):
        d = date(int(m[4]), MONTHS.index(m[3]) + 1, int(m[2])) + timedelta(days=days)
        head = f"{WEEKDAYS[d.weekday()]}, " if m[1] else ""
        return f"{head}{d.day} {MONTHS[d.month - 1]} {d.year}"
    return _LONG.sub(sub, text)


def _fix(obj, today: date, weeks: int):
    """Поля, которые зависят от «сегодня»: подписи дат, «через N дней», номер недели."""
    if isinstance(obj, list):
        for x in obj:
            _fix(x, today, weeks)
    elif isinstance(obj, dict):
        d = _date(obj.get("date"))
        if d and isinstance(obj.get("label"), str) and re.fullmatch(r"\d{1,2} \w+", obj["label"]):
            obj["label"] = f"{d.day} {MONTHS[d.month - 1]}"
        due = _date(obj.get("due_date"))
        if due and isinstance(obj.get("days"), int):
            obj["days"] = (due - today).days
        if isinstance(obj.get("week"), int) and isinstance(obj.get("days"), list):
            obj["week"] += weeks
        for v in obj.values():
            _fix(v, today, weeks)


def _date(v) -> date | None:
    try:
        return date.fromisoformat(v) if isinstance(v, str) and len(v) == 10 else None
    except ValueError:
        return None


def shifted(body, now: datetime):
    """Ответ из записи → ответ «на сегодня»."""
    days = shift_days(now.date())
    text = _move_long(_move_iso(json.dumps(body, ensure_ascii=False), days), days)
    out = json.loads(text)
    _fix(out, now.date(), days // 7)
    return out


def today_view(now: datetime) -> dict:
    """/api/today на настоящий день недели: шаблон записи + пары этого дня."""
    fx = fixtures()
    days = shift_days(now.date())
    rec = now.date() - timedelta(days=days)
    out = copy.deepcopy(fx["GET /api/today"])
    day = fx.get(f"GET /api/day?date={rec.isoformat()}", {"lessons": []})
    nxt = fx.get(f"GET /api/day?date={(rec + timedelta(days=1)).isoformat()}", {"lessons": []})
    out.update(date=rec.isoformat(), weekday=day.get("weekday", out["weekday"]),
               lessons=copy.deepcopy(day.get("lessons", [])),
               tomorrow_first=copy.deepcopy(nxt["lessons"][0]) if nxt.get("lessons") else None)
    out = shifted(out, now)
    out["now"], out["hour"] = now.isoformat(), now.hour
    for les in out["lessons"]:
        try:
            start, end = datetime.fromisoformat(les["start_iso"]), datetime.fromisoformat(les["end_iso"])
        except (KeyError, ValueError):
            continue
        les["status"] = "now" if start <= now < end else ("past" if end <= now else "later")
    return out


def answer(method: str, path: str, query: str, body: bytes, now: datetime):
    """Запрос демо-аккаунта → (код, JSON)."""
    fx = fixtures()
    if method == "GET" and path == "/api/today":
        return 200, today_view(now)
    days = shift_days(now.date())
    q = _move_iso(query, -days)
    key = f"{method} {path}" + (f"?{q}" if q else "")
    if path.startswith("/api/sdo/goal/"):
        try:
            key += "|" + str(json.loads(body or b"{}").get("label", ""))
        except ValueError:
            pass
    if method == "POST" and path == "/api/notify":
        key = "GET /api/notify"
    hit = fx.get(key, fx.get(f"{method} {path}"))
    if hit is None:
        hit = DEFAULTS.get(path, {"ok": True})     # как test/fake_api.dart: робот приложения так и проверен
    return 200, shifted(hit, now)


class ReviewDemo:
    """ASGI: запросы с токеном демо-входа (rv.…) не доходят до настоящих
    обработчиков. Стоит внутри ApiV1 — пути уже без /v1."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/") or scope["path"].startswith(PASS):
            return await self.app(scope, receive, send)
        auth = dict(scope.get("headers") or []).get(b"authorization", b"").decode("latin-1")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if not token.startswith(TOKEN_PREFIX):
            return await self.app(scope, receive, send)
        from database.sessions import session_user
        from starlette.responses import JSONResponse
        if await session_user(token) != DEMO_UID:
            resp = JSONResponse({"detail": "сессия закончилась — войди заново"}, status_code=401)
            return await resp(scope, receive, send)
        body = b""
        more = True
        while more:
            msg = await receive()
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
        method, path = scope["method"], scope["path"]
        query = scope.get("query_string", b"").decode()
        if method == "GET" and (path == "/api/search" or path.startswith("/api/target/")):
            status, data = await _schedule(path, query)
        else:
            from utils import TZ
            status, data = answer(method, path, query, body, datetime.now(TZ))
        resp = JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store"})
        await resp(scope, receive, send)


async def _schedule(path: str, query: str):
    """Поиск расписания — настоящий, как у публичного поиска на сайте."""
    from urllib.parse import parse_qs
    from webapp.routes.schedule import api_search, api_target
    try:
        if path == "/api/search":
            p = parse_qs(query)
            return 200, await api_search(q=p.get("q", [""])[0][:60], type=int(p.get("type", ["0"])[0] or 0),
                                         user={"id": 0})
        _, _, _, t, i = path.split("/")[:5]
        return 200, await api_target(int(t), int(i), user={"id": 0})
    except Exception:  # noqa: BLE001 — демо не должно падать 500 из-за МИРЭА
        if path == "/api/search":
            return 200, {"items": []}
        return 404, {"detail": "не нашлось"}

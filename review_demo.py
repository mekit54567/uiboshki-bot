"""Демо-вход для проверяющих магазинов (App Store, RuStore).

Проверяющий Apple не войдёт ни в Telegram-бота, ни в СДО МИРЭА, а Apple
требует рабочий вход (правило 2.1). Поэтому — код доступа: `REVIEW_CODE`
(секрет хостинга; не задан — входа по коду нет). Код → сессия устройства
особого аккаунта `DEMO_UID`, токен с приставкой `rv.`; все его запросы
/api/… отвечает этот модуль из записи стенда `webapp/static/site/demo.json`
(та же, что у демо на сайте и робота приложения: ничьих настоящих данных
нет). Настоящие функции и база демо-аккаунта не касаются: «удалить
аккаунт» и выход отвечают «готово», данные остаются для следующего
проверяющего. ИИ-чат — исключение: отвечает настоящая модель, но по
демо-данным (`demo_chat`: пары, дедлайны, баллы из записи и придуманные
лекции `demo_lectures.json`), со своим суточным лимитом.

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
LECTURES = FIXTURES.with_name("demo_lectures.json")    # придуманные лекции для ИИ-чата демо
DEMO_AI_DAILY = 40                                    # вопросов ИИ демо-аккаунту в сутки (ratelimit «ai_demo»)

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

# что приложение спрашивает, но в записи стенда нет (как test/fake_api.dart;
# остальное — {"ok": true})
DEFAULTS = {
    "/api/day": {"lessons": []},
    "/api/week": {"week": None, "days": []},
    "/api/sdo/submit-rules": {"accepted": [], "labels": [], "maxfiles": 3, "maxbytes": 10485760},
    "/api/sdo/submit": {"status": "Отправлено для оценивания", "state": "submitted"},
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
    m = re.fullmatch(r"/api/files/(\d+)/page/(\d+)", path)
    if method == "GET" and m and f"GET {path}" not in fx:
        page = lecture_page(int(m[1]), int(m[2]))
        if page:
            return 200, page
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


# ── ИИ-чат демо: настоящая модель, но только по демо-данным ──────────────

@lru_cache(maxsize=1)
def lectures() -> list[dict]:
    return json.loads(LECTURES.read_text(encoding="utf-8"))["lectures"]


def lecture_page(file_id: int, page: int) -> dict | None:
    """Страница придуманной лекции — как /api/files/{id}/page/{n} (лист под чипом)."""
    lec = next((x for x in lectures() if x["id"] == file_id), None)
    if not lec:
        return None
    nums = sorted(int(n) for n in lec["text"])
    page = min(nums, key=lambda n: (abs(n - page), n))
    return {"id": file_id, "title": lec["title"], "page": page, "pages": lec["pages"], "kind": lec["kind"],
            "text": lec["text"][str(page)], "image": None}


def demo_lectures(query: str, subject: str = "", top: int = 4) -> tuple[str, list[dict] | None]:
    """Куски демо-лекций под вопрос — в том же виде, что поиск по смыслу
    (semantic_search.build_context: [n] и источники); по словам, без индекса."""
    from lecture_picker import _stems, expand
    from semantic_search import build_context
    q = _stems(expand(query or ""))
    if not q:
        return "", None
    scored = []
    for lec in lectures():
        if subject and lec["subject"] != subject:
            continue
        for n, text in lec["text"].items():
            score = 2 * len(q & _stems(text)) + len(q & _stems(lec["title"]))
            if score:
                scored.append((score, {"file_id": lec["id"], "title": lec["title"], "subject": lec["subject"],
                                       "kind": lec["kind"], "page_from": int(n), "page_to": int(n), "text": text}))
    scored.sort(key=lambda x: (-x[0], x[1]["file_id"], x[1]["page_from"]))
    if not scored:
        return "", None
    return build_context([h for _, h in scored[:top]])


def _day_lines(label: str, day: dict) -> list[str]:
    head = f"{label}: {day.get('weekday', '').lower()}, {day.get('label', '')}"
    if not day.get("lessons"):
        return [head + " — пар нет"]
    out = [head]
    for les in day["lessons"]:
        bits = [f"{les.get('start', '')}–{les.get('end', '')}", f"{les['title']} ({les.get('kind', '')})"]
        bits += [x for x in (les.get("room"), les.get("teacher")) if x]
        out.append(f"  {les.get('num', '')}) " + " · ".join(bits))
    return out


def demo_context(now: datetime) -> str:
    """Контекст группы для ИИ — как group_context.build_group_context у
    настоящего студента, но из записи стенда: пары недели, дедлайны, ДЗ, баллы БРС."""
    from lecture_day import NIGHT_UNTIL
    fx = fixtures()
    today = now.date()
    lines = [
        "Контекст группы УИБО-03-24 (используй, если вопрос про учёбу группы; не пересказывай без нужды).",
        f"Сегодня {today.strftime('%d.%m.%Y')}, {WEEKDAYS[today.weekday()]}, {now.strftime('%H:%M')} по Москве.",
    ]
    if now.hour < NIGHT_UNTIL:
        lines.append(f"Сейчас ночь: «завтра» в вопросе студента почти наверняка значит наступивший день — "
                     f"{WEEKDAYS[today.weekday()]} {today.strftime('%d.%m')} (он ещё не спал). Отвечай про этот день "
                     "и не поправляй студента.")
    lines.append("Расписание на 7 дней:")
    for i in range(7):
        d = today + timedelta(days=i)
        _, day = answer("GET", "/api/day", f"date={d.isoformat()}", b"", now)
        day.setdefault("label", f"{d.day} {MONTHS[d.month - 1]}")
        day.setdefault("weekday", WEEKDAYS[d.weekday()])
        label = "Сегодня" if i == 0 else "Завтра" if i == 1 else "Дальше"
        lines += _day_lines(label, day)

    deadlines = shifted(fx.get("GET /api/deadlines", {"items": []}), now)["items"]
    upcoming = [x for x in deadlines if not x.get("done")
                and today <= date.fromisoformat(x["due_date"]) <= today + timedelta(days=21)]
    if upcoming:
        lines.append("Ближайшие дедлайны:")
        for x in sorted(upcoming, key=lambda x: (x["due_date"], x.get("due_time") or ""))[:15]:
            when = date.fromisoformat(x["due_date"]).strftime("%d.%m") + (f" {x['due_time']}" if x.get("due_time") else "")
            lines.append(f"- {when} — {x['subject']}")
    else:
        lines.append("Активных дедлайнов на ближайшие три недели нет.")

    hw = shifted(fx.get("GET /api/homework", {"items": []}), now)["items"]
    if hw:
        lines.append("Домашние задания (свежие):")
        for h in hw:
            when = f" (к {date.fromisoformat(h['lesson_date']).strftime('%d.%m')})" if h.get("lesson_date") else ""
            lines.append(f"- {h['subject']}{when}: {(h.get('content') or '[файл]')[:200]}")

    courses = fx.get("GET /api/sdo/grades", {}).get("courses", [])
    if courses:
        lines.append("Баллы БРС в СДО (итог = семестр + экзамен):")
        for c in courses:
            marks = ", ".join(f"«{m['label']}» от {m['at']}" for m in c.get("marks", []))
            works = (f"; работ зачтено {c['works_passed']} из {c['works_total']}"
                     if c.get("works_total") else "")
            lines.append(f"- {c['title']}: {c['score']} из {c['max']} ({marks}){works}")
    return "\n".join(lines)


async def demo_chat(raw: bytes, now: datetime) -> tuple[int, dict]:
    """POST /api/chat демо-аккаунта: та же модель и тот же вид ответа, что у
    настоящего чата (webapp.routes.chat.reply), но контекст и лекции — из
    записи стенда: база, лимиты людей, поиск по смыслу и group_context не
    трогаются. Сбой модели — прежний ответ из записи, не 500."""
    import ai_quota
    import ratelimit
    import think
    from fastapi import HTTPException
    from lecture_picker import search_query
    from pydantic import ValidationError
    from webapp.routes.chat import ChatBody, clean_history, reply
    try:
        body = ChatBody.model_validate_json(raw or b"{}")
    except ValidationError:
        return 422, {"detail": "неверный запрос"}
    if body.think or body.think_first:
        return 403, {"detail": think.PLUS_TEXT}
    if not ratelimit.allow("ai", DEMO_UID):
        return 429, {"detail": ai_quota.MINUTE_TEXT}
    if not ratelimit.allow("ai_demo", DEMO_UID):
        return 429, {"detail": ai_quota.SUB_TEXT.format(n=DEMO_AI_DAILY)}
    history = clean_history(body.history)
    if not history:
        return 400, {"detail": "пустая история"}
    subject = body.subject.strip()
    lectures_text, sources = ("", None) if body.attachment else demo_lectures(search_query(history), subject)
    try:
        return 200, await reply(history, subject, demo_context(now), lectures_text, sources, body.attachment)
    except HTTPException as e:
        if e.status_code != 502:            # вложение не то — как у настоящего чата
            return e.status_code, {"detail": e.detail}
    except Exception:  # noqa: BLE001 — демо не должно падать 500
        pass
    import logging
    logging.getLogger(__name__).warning("демо-чат: модель не ответила — запись стенда")
    return 200, shifted(fixtures()["POST /api/chat"], now)


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
        from utils import TZ
        if method == "GET" and (path == "/api/search" or path.startswith("/api/target/")):
            status, data = await _schedule(path, query)
        elif method == "POST" and path == "/api/chat":
            status, data = await demo_chat(body, datetime.now(TZ))
        else:
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

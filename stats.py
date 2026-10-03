"""
Статистика бота для старосты (/stats): сколько людей пользуются, что
открывают и когда. Пишется только «кто, что, когда» (таблица events) —
без текстов вопросов ИИ, названий файлов, оценок и кук. Старше 180 дней
удаляется (scheduler.py).

Откуда события:
  • WebApp — по пути запроса (EVENT_PATHS): каждый экран и так ходит в свой
    API с initData, отдельная слежка во фронте не нужна;
  • чат с ботом — любое сообщение (StatsMiddleware в middleware.py).
Просмотры экранов пишутся не чаще раза в 30 минут на человека (иначе база
раздуется на перелистываниях), действия — каждое.

«Кто пользуется» (кнопка под картинкой): имя и ник в Telegram, когда
заходил последний раз, сколько дней из периода и какими разделами — те же
события, без содержимого.

Картинка рисуется Pillow в цветах приложения (шрифт DejaVu лежит в
assets/fonts — на сервере может не быть кириллических шрифтов).
"""

import asyncio
import io
import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from config import TIMEZONE

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

VIEW_COOLDOWN = 30 * 60
_last: dict[tuple[int, str], float] = {}

# (метод, начало пути, вид события). Порядок важен: точнее — выше.
EVENT_PATHS = [
    ("POST", "/api/files/delete", None),
    ("POST", "/api/sdo/submit", "submit"),
    ("POST", "/api/sdo/connect", "sdo_connect"),
    ("POST", "/api/chat", "ai"),
    ("POST", "/api/summary", "summary"),          # «Сделать конспект» (открыть готовый — не событие)
    ("POST", "/api/files/", "download"),          # /api/files/{id}/link и /send
    ("GET", "/api/me", "open"),
    ("GET", "/api/deadlines", "deadlines"),
    ("GET", "/api/files", "files"),
    ("POST", "/api/plan/done", "plan_done"),
    ("GET", "/api/plan", "plan"),
    ("GET", "/api/sdo/grades", "sdo"),
    ("GET", "/api/sdo/task", "sdo"),
    ("GET", "/api/search", "search"),
    ("GET", "/api/target", "search"),
]
VIEWS = {"open", "deadlines", "files", "sdo", "search", "bot", "plan"}

# Экраны для полосок «что открывают» — подписи и цвета как в приложении
SCREENS = [("open", "Приложение", "#4a8ff7"), ("deadlines", "Дедлайны", "#f0884b"),
           ("files", "Файлы", "#2bb3a3"), ("ai", "Чат с ИИ", "#9b7cf6"),
           ("sdo", "СДО и баллы", "#2aa39a"), ("search", "Поиск", "#f06292"),
           ("plan", "План", "#7c7ff5"), ("bot", "Чат с ботом", "#8e8e93")]
ACTIONS = [("submit", "сдано работ"), ("download", "файлов скачано"), ("ai", "вопросов ИИ"),
           ("sdo_connect", "подключений СДО")]


def kind_for(method: str, path: str) -> str | None:
    for m, prefix, kind in EVENT_PATHS:
        if method == m and path.startswith(prefix):
            return kind
    return None


async def track(user_id: int, kind: str | None):
    """Записать событие (просмотры — не чаще раза в 30 минут). Ошибки
    статистики никогда не ломают сам запрос."""
    if not kind or not user_id:
        return
    if kind in VIEWS:
        key, now = (user_id, kind), time.monotonic()
        if now - _last.get(key, -1e9) < VIEW_COOLDOWN:
            return
        _last[key] = now
    try:
        from database import add_event
        await add_event(user_id, kind)
    except Exception as e:
        logger.info(f"stats: {e}")


def _msk(at: str) -> datetime:
    return datetime.fromisoformat(at).replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)


async def collect(days: int = 30) -> dict:
    from database import count_sdo_connected, count_users, events_since
    rows = await events_since(max(days, 30))
    now = datetime.now(TZ)
    today = now.date()
    since = today - timedelta(days=days - 1)
    users_by_day: dict = defaultdict(set)
    screens: dict = defaultdict(set)
    actions = Counter()
    heat = [[0] * 24 for _ in range(7)]
    active_day, active_week, active_month, active_period = set(), set(), set(), set()
    for uid, kind, at in rows:
        t = _msk(at)
        d = t.date()
        if (today - d).days < 30:
            active_month.add(uid)
        if (today - d).days < 7:
            active_week.add(uid)
        if d == today:
            active_day.add(uid)
        if d < since:
            continue
        active_period.add(uid)
        users_by_day[d].add(uid)
        screens[kind].add(uid)
        heat[t.weekday()][t.hour] += 1
        if kind in dict(ACTIONS):
            actions[kind] += 1
    return {
        "days": days, "since": since, "today": today,
        "total": await count_users(), "sdo": await count_sdo_connected(),
        "day": len(active_day), "week": len(active_week), "month": len(active_month),
        "period": len(active_period),
        "daily": [(since + timedelta(i), len(users_by_day.get(since + timedelta(i), ()))) for i in range(days)],
        "screens": [(label, color, len(screens.get(k, ()))) for k, label, color in SCREENS],
        "actions": [(label, actions.get(k, 0)) for k, label in ACTIONS],
        "heat": heat,
    }


# Чем пользуется — коротко, для списка «кто пользуется»
USES = {"open": "приложение", "bot": "бот", "deadlines": "дедлайны", "files": "файлы", "download": "файлы",
        "ai": "ИИ", "summary": "конспекты", "sdo": "СДО", "sdo_connect": "СДО", "submit": "сдача работ", "search": "поиск",
        "plan": "план", "plan_done": "план"}


def period_label(days: int) -> str:
    return "семестр" if days >= 180 else f"{days} дн."


async def people(days: int = 30) -> dict:
    """Кто заходил за days дней (как в collect: сегодня и days−1 дней назад):
    последний заход, сколько разных дней, чем пользуется; и кто в боте, но
    за период не заходил."""
    from database import events_since, get_all_users
    rows = await events_since(days)
    today = datetime.now(TZ).date()
    since = today - timedelta(days=days - 1)
    seen: dict[int, dict] = {}
    for i, (uid, kind, at) in enumerate(rows):
        t = _msk(at)
        if t.date() < since:
            continue
        p = seen.setdefault(uid, {"last": t, "days": set(), "uses": Counter()})
        p["last"], p["seq"] = max(p["last"], t), i     # seq — кто позже при равном времени (секунды)
        p["days"].add(t.date())
        if kind in USES:
            p["uses"][USES[kind]] += 1
    users = {u["user_id"]: u for u in await get_all_users()}

    def who(uid: int) -> dict:
        u = users.get(uid) or {}
        return {"id": uid, "name": (u.get("full_name") or "").strip(), "username": u.get("username") or ""}

    active = [{**who(uid), "last": p["last"], "days": len(p["days"]),
               "uses": [label for label, _ in p["uses"].most_common(4)]}
              for uid, p in sorted(seen.items(), key=lambda x: (x[1]["last"], x[1]["seq"]), reverse=True)]
    idle = [who(uid) for uid in users if uid not in seen]
    return {"days": days, "today": today, "active": active, "idle": idle}


def _when(t: datetime, today) -> str:
    if t.date() == today:
        return f"сегодня {t:%H:%M}"
    if (today - t.date()).days == 1:
        return f"вчера {t:%H:%M}"
    return f"{t:%d.%m}"


def _person(p: dict) -> str:
    from utils import esc
    name = esc(p["name"] or (f"@{p['username']}" if p["username"] else f"id {p['id']}"))
    nick = f" @{esc(p['username'])}" if p["username"] and p["name"] else ""
    return f'<a href="tg://user?id={p["id"]}">{name}</a>{nick}'


def people_text(p: dict) -> str:
    """Список для старосты: имя (ссылкой на профиль) и ник, последний заход,
    дней с заходами, чем пользуется. Никаких текстов, файлов и оценок."""
    lines = [f"👥 <b>Кто пользуется · {period_label(p['days'])}</b> — {len(p['active'])} чел.", ""]
    for i, a in enumerate(p["active"], 1):
        uses = ", ".join(a["uses"]) or "—"
        lines.append(f"{i}. {_person(a)} — {_when(a['last'], p['today'])} · дней: {a['days']} · {uses}")
    if not p["active"]:
        lines.append("За этот период никто не заходил.")
    if p["idle"]:
        lines += ["", f"В боте, но за период не заходили ({len(p['idle'])}): "
                  + ", ".join(_person(u) for u in p["idle"])]
    return "\n".join(lines)


def summary(s: dict) -> str:
    acts = " · ".join(f"{n} {label}" for label, n in s["actions"])
    return (f"📊 <b>Статистика за {s['days']} дн.</b>\n"
            f"Всего в боте: <b>{s['total']}</b> · СДО подключили: <b>{s['sdo']}</b>\n"
            f"Активны: сегодня <b>{s['day']}</b> · неделя <b>{s['week']}</b> · месяц <b>{s['month']}</b>\n"
            f"{acts}")


# ── картинка ─────────────────────────────────────────────────────────────────

FONTS = Path(__file__).parent / "assets" / "fonts"
BG, CARD, LINE, HINT, TEXT, ACCENT = "#0f1115", "#181b22", "#2a2e3a", "#9aa0ac", "#f2f3f7", "#4a8ff7"


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(FONTS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)
    except OSError:
        return ImageFont.load_default()


def _card(draw, box, title=None):
    draw.rounded_rectangle(box, radius=28, fill=CARD, outline=LINE, width=2)
    if title:
        draw.text((box[0] + 32, box[1] + 26), title.upper(), font=_font(22, True), fill=HINT)


def render(s: dict) -> bytes:
    """Дашборд 1200×1500: плитки, активные по дням, экраны, когда заходят."""
    from PIL import Image, ImageDraw
    W, H = 1200, 1560
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((48, 44), "УИБО-бот · статистика", font=_font(46, True), fill=TEXT)
    d.text((48, 104), f"за {s['days']} дн. · {s['since']:%d.%m} – {s['today']:%d.%m.%Y}", font=_font(26), fill=HINT)

    # плитки
    tiles = [("в боте", s["total"], "#4a8ff7"), ("сегодня", s["day"], "#2bb3a3"),
             ("за неделю", s["week"], "#9b7cf6"), ("за месяц", s["month"], "#f0884b"),
             ("с СДО", s["sdo"], "#f06292")]
    tw, x = (W - 96 - 4 * 18) // 5, 48
    for label, n, color in tiles:
        d.rounded_rectangle((x, 166, x + tw, 316), radius=26, fill=CARD, outline=LINE, width=2)
        d.rounded_rectangle((x + 22, 190, x + 30, 292), radius=4, fill=color)
        d.text((x + 46, 186), str(n), font=_font(56, True), fill=TEXT)
        d.text((x + 46, 258), label, font=_font(24), fill=HINT)
        x += tw + 18

    # активные по дням
    _card(d, (48, 344, W - 48, 724), "Активные люди по дням")
    daily = s["daily"]
    top = max([n for _, n in daily] + [1])
    cx0, cx1, cy0, cy1 = 90, W - 90, 420, 670
    bw = (cx1 - cx0) / len(daily)
    for i, (day, n) in enumerate(daily):
        h = (cy1 - cy0) * n / top
        bx = cx0 + i * bw
        d.rounded_rectangle((bx + bw * .18, cy1 - max(h, 3), bx + bw * .82, cy1), radius=int(min(8, bw / 3)),
                            fill=ACCENT if day.weekday() < 6 else "#2f5fae")
        if len(daily) <= 31 and (i % max(1, len(daily) // 6) == 0 or i == len(daily) - 1):
            d.text((bx + bw / 2, cy1 + 12), f"{day:%d.%m}", font=_font(20), fill=HINT, anchor="mt")
    d.text((W - 80, 370), f"макс. {top} в день", font=_font(20), fill=HINT, anchor="ra")

    # что открывают
    _card(d, (48, 752, 640, 1172), "Что открывают (людей)")
    screens = s["screens"]
    smax = max([n for *_, n in screens] + [1])
    y, step = 816, min(48, 344 // max(1, len(screens)))
    for label, color, n in screens:
        d.text((80, y), label, font=_font(24), fill=TEXT)
        d.rounded_rectangle((300, y + 4, 300 + 270, y + 26), radius=11, fill="#232733")
        d.rounded_rectangle((300, y + 4, 300 + max(12, 270 * n / smax), y + 26), radius=11, fill=color)
        d.text((600, y), str(n), font=_font(24, True), fill=TEXT)
        y += step

    # действия
    _card(d, (668, 752, W - 48, 1172), "Действия")
    for i, (label, n) in enumerate(s["actions"]):        # сетка 2×2
        x, y = 700 + (i % 2) * 230, 830 + (i // 2) * 160
        d.text((x, y), str(n), font=_font(56, True), fill=TEXT)
        d.text((x, y + 70), label, font=_font(22), fill=HINT)

    # когда заходят
    _card(d, (48, 1200, W - 48, H - 48), "Когда заходят (МСК)")
    heat = s["heat"]
    hmax = max([v for row in heat for v in row] + [1])
    gx0, gy0, cw, ch = 130, 1262, (W - 48 - 40 - 130) / 24, 30
    for r, name in enumerate(["пн", "вт", "ср", "чт", "пт", "сб", "вс"]):
        d.text((gx0 - 18, gy0 + r * (ch + 4) + ch / 2), name, font=_font(20), fill=HINT, anchor="rm")
        for hcol in range(24):
            v = heat[r][hcol] / hmax
            color = _mix(CARD, ACCENT, 0.12 + 0.88 * v) if heat[r][hcol] else "#1d2029"
            x0 = gx0 + hcol * cw
            d.rounded_rectangle((x0 + 2, gy0 + r * (ch + 4), x0 + cw - 2, gy0 + r * (ch + 4) + ch), radius=6, fill=color)
    for hcol in range(0, 24, 3):
        d.text((gx0 + hcol * cw + cw / 2, gy0 + 7 * (ch + 4) + 6), f"{hcol}", font=_font(18), fill=HINT, anchor="mt")

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


async def report(days: int = 30) -> tuple[bytes, str]:
    s = await collect(days)
    png = await asyncio.to_thread(render, s)
    return png, summary(s)

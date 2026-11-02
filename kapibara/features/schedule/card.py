"""
Картинки расписания для inline-режима (@бот в любом чате), всегда тёмные,
в стиле приложения. День — пары карточками: время, номер, тип цветом,
название, аудитория, преподаватель. Неделя — список по дням. Рисует Pillow
(шрифт DejaVu, assets/fonts), JPEG. Отдаёт их webapp/server.py по
подписанной ссылке /card/… — Telegram сам забирает картинку по URL.
"""

import hashlib
import hmac
import io
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).parent / "assets" / "fonts"
W = 1080
PAD = 48
BG = (15, 17, 21)
CARD = (24, 27, 34)
TEXT = (242, 243, 247)
MUTED = (150, 155, 170)
ACCENT = (124, 127, 245)
KIND_COLORS = {"лекция": (124, 127, 245), "практика": (67, 198, 172), "лабораторная": (240, 160, 80)}
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
KIND_SHORT = {"лекция": "лек", "практика": "пр", "лабораторная": "лаб"}


def _font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(str(FONTS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw, text: str, font, width: int, max_lines: int = 2) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while draw.textlength(lines[-1] + "…", font=font) > width and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return lines


def _pairs_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "пара"
    return "пары" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "пар"


def _jpeg(img) -> bytes:
    # progressive: если Telegram всё же получит файл не целиком, видна вся
    # картинка чуть мутнее, а не верх и серая полоса (живой тест, 2 октября)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85, optimize=True, progressive=True)
    return buf.getvalue()


THUMB_W = 320


def thumbnail(data: bytes) -> bytes:
    """Маленькое превью для списка inline-результатов — отдельным файлом по
    своей ссылке (?thumb=1). Раньше превью и фото были одной ссылкой: Telegram
    качает превью с ограничением размера и, похоже, тем же файлом отдавал и
    фото в чат — картинка в сообщении обрезалась снизу серым."""
    img = Image.open(io.BytesIO(data))
    img.thumbnail((THUMB_W, THUMB_W * 4))
    return _jpeg(img)


def _header(d, title: str, subtitle: str):
    d.rounded_rectangle((PAD, PAD + 8, PAD + 10, PAD + 62), 5, fill=ACCENT)
    d.text((PAD + 30, PAD), title, font=_font(54, True), fill=TEXT)
    d.text((PAD + 30, PAD + 74), subtitle, font=_font(32), fill=MUTED)


def day_subtitle(lessons: list[dict]) -> str:
    if not lessons:
        return "пар нет"
    n = sum(l.get("pairs", 1) for l in lessons)
    return f"{n} {_pairs_word(n)} · {lessons[0]['start']}–{lessons[-1]['end']}"


def render_day(title: str, subtitle: str, lessons: list[dict], footer: str) -> bytes:
    """title — «Понедельник, 5 октября», subtitle — «3 пары · 09:00–14:10»,
    lessons — из schedule_parser.lessons_for_date, footer — «УИБО-03-24 · @UiboshkiBot»."""
    f_sub = _font(32)
    f_time, f_name, f_meta, f_pill = _font(34, True), _font(38, True), _font(30), _font(26, True)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    inner = W - 2 * PAD - 2 * 36
    blocks = []
    for l in lessons:
        name = _wrap(tmp, l["title"], f_name, inner)
        meta = " · ".join(x for x in (l.get("room"), l.get("teacher")) if x)
        blocks.append((l, name, meta, 36 + 44 + 16 + len(name) * 48 + (44 if meta else 0) + 30))
    h = PAD + 70 + 50 + 40 + sum(b[3] + 20 for b in blocks) + (120 if not lessons else 0) + 70 + PAD
    img = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(img)
    _header(d, title, subtitle)
    y = PAD + 160
    if not lessons:
        d.text((PAD, y + 20), "Пар нет — можно отдохнуть", font=f_name, fill=TEXT)
        y += 120
    for l, name, meta, bh in blocks:
        d.rounded_rectangle((PAD, y, W - PAD, y + bh), 28, fill=CARD)
        x, cy = PAD + 36, y + 36
        d.text((x, cy), f"{l['start']}–{l['end']}", font=f_time, fill=TEXT)
        kind = (l.get("kind") or "").lower()
        if kind:
            col = KIND_COLORS.get(kind, MUTED)
            pw = d.textlength(kind, font=f_pill) + 36
            d.rounded_rectangle((W - PAD - 36 - pw, cy, W - PAD - 36, cy + 42), 21,
                                fill=tuple(int(c * 0.25 + b * 0.75) for c, b in zip(col, CARD)))
            d.text((W - PAD - 36 - pw + 18, cy + 6), kind, font=f_pill, fill=col)
        num = str(l.get("num") or "")
        if num:
            tx = x + d.textlength(f"{l['start']}–{l['end']}", font=f_time) + 20
            d.text((tx, cy + 4), f"{num} пара", font=f_meta, fill=MUTED)
        cy += 60
        for line in name:
            d.text((x, cy), line, font=f_name, fill=TEXT)
            cy += 48
        if meta:
            d.text((x, cy + 6), meta, font=f_meta, fill=MUTED)
        y += bh + 20
    d.text((PAD, y + 20), footer, font=f_sub, fill=MUTED)
    return _jpeg(img)


def render_week(title: str, subtitle: str, days: list[tuple[date, list[dict]]], footer: str) -> bytes:
    """Неделя списком: по дню карточка, в ней строка на пару —
    «09:00  Название  лек · А-15». Дни без пар — одной строкой внизу."""
    f_day, f_time, f_name, f_meta, f_sub = _font(34, True), _font(30, True), _font(30), _font(26), _font(32)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    name_x = PAD + 36 + 150
    name_w = W - PAD - 36 - name_x
    busy = [(d, ls) for d, ls in days if ls]
    free = [DAYS_SHORT[d.weekday()] for d, ls in days if not ls and d.weekday() < 6]
    blocks = []
    for d, ls in busy:
        rows = []
        for l in ls:
            name = _wrap(tmp, l["title"], f_name, name_w, max_lines=1)[0]
            meta = " · ".join(x for x in (KIND_SHORT.get((l.get("kind") or "").lower(), l.get("kind") or ""),
                                          l.get("room")) if x)
            rows.append((l, name, meta))
        blocks.append((d, rows, 30 + 50 + len(rows) * 82 + 14))
    h = PAD + 160 + sum(b[2] + 20 for b in blocks) + (80 if free else 0) + (120 if not busy else 0) + 70 + PAD
    img = Image.new("RGB", (W, h), BG)
    dr = ImageDraw.Draw(img)
    _header(dr, title, subtitle)
    y = PAD + 160
    if not busy:
        dr.text((PAD, y + 20), "Пар нет — можно отдохнуть", font=_font(38, True), fill=TEXT)
        y += 120
    from schedule_parser import MONTHS_GEN
    for d, rows, bh in blocks:
        dr.rounded_rectangle((PAD, y, W - PAD, y + bh), 28, fill=CARD)
        n = sum(l.get("pairs", 1) for l, _, _ in rows)
        dr.text((PAD + 36, y + 28), f"{DAYS_SHORT[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}",
                font=f_day, fill=ACCENT)
        label = f"{n} {_pairs_word(n)}"
        dr.text((W - PAD - 36 - dr.textlength(label, font=f_meta), y + 34), label, font=f_meta, fill=MUTED)
        cy = y + 30 + 56
        for l, name, meta in rows:
            col = KIND_COLORS.get((l.get("kind") or "").lower(), MUTED)
            dr.rounded_rectangle((PAD + 36, cy + 6, PAD + 42, cy + 66), 3, fill=col)
            dr.text((PAD + 56, cy + 2), l["start"], font=f_time, fill=TEXT)
            dr.text((name_x, cy), name, font=f_name, fill=TEXT)
            if meta:
                dr.text((name_x, cy + 40), meta, font=f_meta, fill=MUTED)
            cy += 82
        y += bh + 20
    if free:
        dr.text((PAD, y + 16), "Свободно: " + ", ".join(free), font=f_sub, fill=MUTED)
        y += 80
    dr.text((PAD, y + 20), footer, font=f_sub, fill=MUTED)
    return _jpeg(img)


# ── ссылки и сборка ─────────────────────────────────────────────────────────
# Ссылка на картинку подписана (HMAC от токена бота), чтобы сервер не рисовал
# по чужим запросам расписание чего угодно. Ключ включает дату и метку
# времени — Telegram кэширует картинки по URL, а расписание меняется.

def sign(key: str) -> str:
    from config import BOT_TOKEN
    return hmac.new(BOT_TOKEN.encode(), f"card:{key}".encode(), hashlib.sha256).hexdigest()[:24]


def card_url(base: str, kind: str, target_type: int = 0, target_id: int = 0) -> str:
    """kind: today / tomorrow / week (своя группа) или target (неделя найденного).
    Превью для inline — та же ссылка с «&thumb=1» (handlers/inline._photo)."""
    key = f"{kind}-{target_type}-{target_id}-{int(time.time()) // 600}"
    return f"{base.rstrip('/')}/card/{key}.jpg?sig={sign(key)}"


# Ссылка живёт месяц: иначе ссылку из старого сообщения можно дёргать вечно
# (каждый раз рендер Pillow и запрос к зеркалу). Метка — десятиминутки.
CARD_MAX_AGE = 30 * 24 * 6


def parse_key(key: str, sig: str) -> tuple[str, int, int] | None:
    if not hmac.compare_digest(sig, sign(key)):
        return None
    parts = key.split("-")
    if len(parts) != 4 or parts[0] not in ("today", "tomorrow", "week", "target"):
        return None
    try:
        kind, target_type, target_id, stamp = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        return None
    if not 0 <= int(time.time()) // 600 - stamp <= CARD_MAX_AGE:
        return None
    return kind, target_type, target_id


def _monday_for(today: date) -> date:
    """Неделя для картинки: текущая, а в воскресенье — следующая."""
    return today - timedelta(days=today.weekday()) + (timedelta(days=7) if today.weekday() == 6 else timedelta(0))


def week_title(raw: bytes, monday: date) -> tuple[str, str]:
    from schedule_parser import MONTHS_GEN, week_number
    sunday = monday + timedelta(days=6)
    num = week_number(raw, monday) or week_number(raw, monday + timedelta(days=1))
    span = (f"{monday.day}–{sunday.day} {MONTHS_GEN[sunday.month - 1]}" if monday.month == sunday.month
            else f"{monday.day} {MONTHS_GEN[monday.month - 1]} – {sunday.day} {MONTHS_GEN[sunday.month - 1]}")
    return (f"Неделя {num}" if num else "Неделя"), span


def build_own(raw: bytes, kind: str, now: datetime, group: str, bot: str) -> bytes:
    from schedule_parser import DAY_NAMES, MONTHS_GEN, lessons_for_date
    footer = f"{group} · @{bot}"
    if kind == "week":
        monday = _monday_for(now.date())
        days = [(monday + timedelta(days=i), lessons_for_date(raw, monday + timedelta(days=i))) for i in range(7)]
        title, span = week_title(raw, monday)
        n = sum(l.get("pairs", 1) for _, ls in days for l in ls)
        return render_week(title, f"{span} · {n} {_pairs_word(n)}", days, footer)
    d = now.date() + timedelta(days=1 if kind == "tomorrow" else 0)
    lessons = lessons_for_date(raw, d)
    return render_day(f"{DAY_NAMES[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}", day_subtitle(lessons),
                      lessons, footer)


def build_target(raw: bytes, title: str, now: datetime, bot: str) -> bytes:
    from schedule_parser import target_weeks
    monday = _monday_for(now.date())
    week = target_weeks(raw, monday, weeks=1)[0]
    days = [(date.fromisoformat(x["date"]), x["lessons"]) for x in week["days"]]
    wt, span = week_title(raw, monday)
    return render_week(title, f"{wt.lower()} · {span}", days, f"@{bot}")

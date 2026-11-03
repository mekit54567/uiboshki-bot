"""
Картинки расписания для inline-режима (@бот в любом чате) в стиле
приложения. День — пары лентой: время, полоса цвета предмета, название,
тип, аудитория, преподаватель, перерывы. Неделя — по дню карточка.
Рисует Pillow (шрифты приложения — assets/fonts), JPEG. Отдаёт их
webapp/routes/schedule.py по подписанной ссылке /card/… — Telegram сам
забирает картинку по URL. Оформление — STYLES, по умолчанию STYLE.
"""

import asyncio
import functools
import hashlib
import hmac
import io
import logging
import random
import re
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from kapibara.core.errors import NETWORK
from kapibara.core.paths import ROOT

logger = logging.getLogger(__name__)

FONTS = ROOT / "assets" / "fonts"            # данные в корне проекта (kapibara/core/paths.py)
CAPY = ROOT / "webapp" / "static" / "img" / "capy"
W = 1080
PAD = 56
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
KIND_SHORT = {"лекция": "лек", "практика": "пр", "лабораторная": "лаб"}

# Цвета предметов — как в приложении (design/tokens.json: subjects и
# subjects_ink; индекс — тот же хэш названия, что в app_theme.dart).
SUBJECTS = ["#8B7CF6", "#F5A524", "#2EC4B6", "#FF6B6B", "#4F8CFF", "#E86FB0", "#7BC67E", "#F2994A"]
SUBJECTS_INK = ["#5B4BC4", "#8C5800", "#0F6E66", "#B83A3A", "#2F5FC0", "#A83C7A", "#376F3A", "#985019"]


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t: float) -> tuple[int, int, int]:
    """a → b на долю t."""
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=False))


# Оформления. heading/body/num — (файл, вес); texture — фон: бумага, доска мелом, клетка.
STYLES = {
    "paper": {                                     # «Тетрадь» приложения
        "bg": "#E9E3D8", "card": "#F3EEE5", "line": "#DBD3C4", "text": "#2A2721", "muted": "#7D776B", "accent": "#B75438",
        "subjects": SUBJECTS_INK, "tint": 0.16, "heading": ("SourceSerif4.ttf", 640), "body": ("Onest.ttf", 400),
        "bold": ("Onest.ttf", 640), "num": ("SourceSerif4.ttf", 640), "texture": "paper", "outline": False},
    "chalk": {                                     # «Мел»: доска, как иконка
        "bg": "#1F2321", "card": "#272C2A", "line": "#3A403D", "text": "#ECEBE4", "muted": "#A4A89F", "accent": "#F2D492",
        "subjects": ["#B9AEF7", "#F7CB79", "#86E0D6", "#FF9E9E", "#94B8FF", "#F2A6CF", "#A9DCAB", "#F6BC88"],
        "tint": 0.22, "heading": ("Neucha.ttf", 0), "body": ("Onest.ttf", 400), "bold": ("Onest.ttf", 600),
        "num": ("Neucha.ttf", 0), "texture": "chalk", "outline": True},
    "grid": {                                      # тетрадь в клетку, поля красным
        "bg": "#FBF9F3", "card": "#FFFFFF", "line": "#D9E1EA", "text": "#24304A", "muted": "#6E7787", "accent": "#C2453A",
        "subjects": SUBJECTS_INK, "tint": 0.14, "heading": ("Neucha.ttf", 0), "body": ("Onest.ttf", 400),
        "bold": ("Onest.ttf", 640), "num": ("Onest.ttf", 700), "texture": "grid", "outline": False},
}
STYLE = "chalk"                # Никита 03.11: «Мел», как иконка


@functools.lru_cache(maxsize=64)
def _font(size: int, face: tuple[str, int] = ("Onest.ttf", 400)):
    """Шрифт с весом (у Onest и Source Serif — переменный). Кэш: файл
    читается один раз, а не на каждую картинку (раньше первая — 0,7 с)."""
    name, weight = face
    try:
        f = ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        try:
            f = ImageFont.truetype(str(FONTS / "DejaVuSans.ttf"), size)
        except OSError:
            return ImageFont.load_default()
        return f
    if weight:
        try:
            axes = f.get_variation_axes()
            f.set_variation_by_axes([weight if i == 0 else min(max(size / 2, a["minimum"]), a["maximum"])
                                     for i, a in enumerate(axes)])
        except (OSError, AttributeError) as e:     # без веса — обычное начертание
            logger.info(f"card: вес шрифта {name}: {e}")
    return f


class _P:
    """Палитра оформления: цвета — кортежами, шрифты — по роли."""

    def __init__(self, style: str):
        s = STYLES.get(style) or STYLES[STYLE]
        self.name = style if style in STYLES else STYLE
        for k in ("bg", "card", "line", "text", "muted", "accent"):
            setattr(self, k, _rgb(s[k]))
        self.subjects = [_rgb(c) for c in s["subjects"]]
        self.tint, self.texture, self.outline = s["tint"], s["texture"], s["outline"]
        self._faces = {k: s[k] for k in ("heading", "body", "bold", "num")}

    def f(self, role: str, size: int):
        face = self._faces[role]
        if face[0] == "Neucha.ttf":            # рукописный мельче на глаз — чуть крупнее
            size = round(size * 1.12)
        return _font(size, face)

    def subject(self, title: str):
        h = 0
        for c in title.lower():                  # как codeUnits в Dart: кириллица — одна единица
            h = (h * 31 + ord(c)) & 0x7FFFFFFF
        return self.subjects[h % len(self.subjects)]

    def pill(self, col):
        return _mix(self.card, col, self.tint)


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
    lines = lines or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] += "…"
    while draw.textlength(lines[-1], font=font) > width and len(lines[-1]) > 2:
        lines[-1] = lines[-1][:-2].rstrip() + "…"
    return lines


def _pairs_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "пара"
    return "пары" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "пар"


def _jpeg(img) -> bytes:
    # progressive: если Telegram всё же получит файл не целиком, видна вся
    # картинка чуть мутнее, а не верх и серая полоса (живой тест, 2 октября)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=88, optimize=True, progressive=True, subsampling=0)
    return buf.getvalue()


THUMB_W = 320


def thumbnail(data: bytes) -> bytes:
    """Маленькое превью для списка inline-результатов — отдельным файлом по
    своей ссылке (?thumb=1). Раньше превью и фото были одной ссылкой: Telegram
    качает превью с ограничением размера и, похоже, тем же файлом отдавал и
    фото в чат — картинка в сообщении обрезалась снизу серым. Превью — верх
    карточки не выше квадрата: в списке видно заголовок и первые пары."""
    img = Image.open(io.BytesIO(data))
    if img.height > img.width:
        img = img.crop((0, 0, img.width, img.width))
    img.thumbnail((THUMB_W, THUMB_W))
    return _jpeg(img)


# ── фон и украшения ─────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _noise_tile() -> Image.Image:
    """Зерно фона — один раз и всегда одинаковое (своё зерно случайности):
    одинаковое расписание даёт байт в байт ту же картинку, а значит, ту же
    ссылку — Telegram берёт её из своего кэша, а не качает заново."""
    rnd = random.Random(7)
    w, h = W // 2, 1200
    small = Image.frombytes("L", (w // 2, h // 2), bytes(rnd.randrange(80, 176) for _ in range(w * h // 4)))
    return small.resize((w, h), Image.BILINEAR)


def _noise(h: int) -> Image.Image:
    tile, out = _noise_tile(), Image.new("L", (W // 2, h // 2 + 1))
    for y in range(0, out.height, tile.height):
        out.paste(tile, (0, y))
    return out.resize((W, h))


def _canvas(p: _P, h: int) -> Image.Image:
    img = Image.new("RGB", (W, h), p.bg)
    rnd = random.Random(h)                       # одна и та же картинка — один и тот же фон
    if p.texture == "chalk":
        # доска: мелкое зерно и пара размытых разводов мела
        img = Image.blend(img, Image.merge("RGB", (_noise(h),) * 3), 0.06)
        smudge = Image.new("L", (W, h), 0)
        sd = ImageDraw.Draw(smudge)
        for _ in range(3):
            x, y = rnd.randint(-200, W), rnd.randint(-200, h)
            sd.ellipse((x, y, x + rnd.randint(300, 600), y + rnd.randint(120, 260)), fill=rnd.randint(10, 20))
        smudge = smudge.filter(ImageFilter.GaussianBlur(60))
        img = Image.composite(Image.new("RGB", (W, h), p.text), img, smudge)
    elif p.texture == "grid":
        d = ImageDraw.Draw(img)
        for x in range(0, W, 36):
            d.line((x, 0, x, h), fill=p.line, width=1)
        for y in range(0, h, 36):
            d.line((0, y, W, y), fill=p.line, width=1)
        d.line((PAD - 20, 0, PAD - 20, h), fill=_mix(p.bg, p.accent, 0.55), width=3)
    elif p.texture == "paper":
        img = Image.blend(img, Image.merge("RGB", (_noise(h),) * 3), 0.025)
    return img


def _capy(img, p: _P, pose: str, box: tuple[int, int, int]):
    """Силуэт капибары (маска из приложения) цветом темы."""
    x, y, size = box
    try:
        m = Image.open(CAPY / f"{pose}.png").convert("LA").split()[-1].resize((size, size), Image.LANCZOS)
    except OSError:
        return
    col = _mix(p.bg, p.accent, 0.85 if p.texture == "chalk" else 0.75)
    img.paste(Image.new("RGB", (size, size), col), (x, y), m)


def _card(d, p: _P, box, radius=30, col=None):
    if p.outline:                                # мелом — контур, а не заливка
        d.rounded_rectangle(box, radius, fill=p.card, outline=_mix(p.card, p.text, 0.28), width=3)
    else:
        d.rounded_rectangle(box, radius, fill=p.card, outline=p.line if p.texture == "grid" else None,
                            width=2)


def _header(img, d, p: _P, title: str, subtitle: str, pose: str) -> int:
    """Шапка: заголовок, подзаголовок, капибара справа. Возвращает y под ней."""
    _capy(img, p, pose, (W - PAD - 190, PAD - 12, 190))
    tw = W - 2 * PAD - 210
    size = 64
    f = p.f("heading", size)
    while d.textlength(title, font=f) > tw and size > 40:
        size -= 4
        f = p.f("heading", size)
    d.text((PAD, PAD + 6), title, font=f, fill=p.text)
    d.text((PAD, PAD + 96), subtitle, font=p.f("body", 34), fill=p.muted)
    return PAD + 190


def _footer(d, p: _P, y: int, footer: str):
    d.line((PAD, y, W - PAD, y), fill=p.line, width=2)
    left, _, right = footer.rpartition(" · ")
    f = p.f("body", 30)
    if left:
        d.text((PAD, y + 26), left, font=f, fill=p.muted)
    d.text((W - PAD - d.textlength(right, font=f), y + 26), right, font=p.f("bold", 30), fill=p.accent)


def _gap(a: str, b: str) -> int:
    try:
        h1, m1 = map(int, a.split(":"))
        h2, m2 = map(int, b.split(":"))
    except ValueError:
        return 0
    return h2 * 60 + m2 - h1 * 60 - m1


def _gap_label(mins: int) -> str:
    h, m = divmod(mins, 60)
    return "перерыв " + (f"{h} ч {m} мин" if h and m else f"{h} ч" if h else f"{m} мин")


# ── день ────────────────────────────────────────────────────────────────────

BIG_GAP = 40          # перерыв от 40 минут — строкой между парами


def day_subtitle(lessons: list[dict]) -> str:
    if not lessons:
        return "пар нет"
    n = sum(l.get("pairs", 1) for l in lessons)
    return f"{n} {_pairs_word(n)} · {lessons[0]['start']}–{lessons[-1]['end']}"


def render_day(title: str, subtitle: str, lessons: list[dict], footer: str, style: str = "",
               pose: str = "day", highlight: tuple[int, str] | None = None) -> bytes:
    """title — «Понедельник, 5 октября», subtitle — «3 пары · 09:00–14:10»,
    lessons — из schedule_parser.lessons_for_date, footer — «УИБО-03-24 · @UiboshkiBot»,
    highlight — (номер пары в списке, метка «идёт»): обвести акцентом."""
    p = _P(style or STYLE)
    f_time, f_end = p.f("num", 42), p.f("body", 28)
    f_name, f_meta, f_pill = p.f("bold", 38), p.f("body", 29), p.f("bold", 25)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    left = PAD + 36 + 140 + 30                   # колонка времени, полоса, текст
    inner = W - PAD - 36 - left
    blocks = []
    for i, l in enumerate(lessons):
        name = _wrap(tmp, l["title"], f_name, inner)
        meta = " · ".join(x for x in (l.get("room"), l.get("teacher")) if x)
        bh = 34 + 46 + len(name) * 48 + (42 if meta else 0) + 34
        gap = _gap(lessons[i - 1]["end"], l["start"]) if i else 0
        blocks.append((l, name, meta, max(bh, 150), gap if gap >= BIG_GAP else 0))
    h = PAD + 190 + sum(b[3] + 18 + (54 if b[4] else 0) for b in blocks) + (230 if not lessons else 0) + 110 + PAD
    img = _canvas(p, h)
    d = ImageDraw.Draw(img)
    y = _header(img, d, p, title, subtitle, "joy" if not lessons else pose)
    if not lessons:
        _card(d, p, (PAD, y, W - PAD, y + 200))
        d.text((PAD + 40, y + 50), "Пар нет", font=p.f("heading", 48), fill=p.text)
        d.text((PAD + 40, y + 120), "можно выспаться и отдохнуть", font=f_meta, fill=p.muted)
        y += 230
    for i, (l, name, meta, bh, gap) in enumerate(blocks):
        if gap:
            label = _gap_label(gap)
            d.text((PAD + 36, y + 6), label, font=f_end, fill=p.muted)
            lx = PAD + 36 + d.textlength(label, font=f_end) + 20
            for x in range(int(lx), W - PAD - 36, 22):         # пунктир до края
                d.line((x, y + 24, x + 10, y + 24), fill=p.line, width=3)
            y += 54
        col = p.subject(l["title"])
        _card(d, p, (PAD, y, W - PAD, y + bh))
        if highlight and highlight[0] == i:
            d.rounded_rectangle((PAD, y, W - PAD, y + bh), 30, outline=p.accent, width=5)
            tw = d.textlength(highlight[1], font=f_pill)
            d.text((W - PAD - 36 - tw, y + 36), highlight[1], font=f_pill, fill=p.accent)
        x0 = PAD + 36
        d.text((x0, y + 30), l["start"], font=f_time, fill=p.text)
        d.text((x0, y + 84), l["end"], font=f_end, fill=p.muted)
        bx = PAD + 36 + 140
        d.rounded_rectangle((bx, y + 32, bx + 7, y + bh - 32), 4, fill=col)
        cy = y + 30
        kind = (l.get("kind") or "").lower()
        px = left
        if kind:
            pw = d.textlength(kind, font=f_pill) + 32
            d.rounded_rectangle((px, cy, px + pw, cy + 40), 20, fill=p.pill(col))
            d.text((px + 16, cy + 6), kind, font=f_pill, fill=col)
            px += pw + 16
        num = str(l.get("num") or "")
        if num:
            d.text((px, cy + 5), f"{num} пара", font=f_end, fill=p.muted)
        cy += 56
        for line in name:
            d.text((left, cy), line, font=f_name, fill=p.text)
            cy += 48
        if meta:
            d.text((left, cy + 4), _wrap(tmp, meta, f_meta, inner, 1)[0], font=f_meta, fill=p.muted)
        y += bh + 18
    _footer(d, p, y + 26, footer)
    return _jpeg(img)


# ── неделя ──────────────────────────────────────────────────────────────────

def render_week(title: str, subtitle: str, days: list[tuple[date, list[dict]]], footer: str,
                style: str = "", today: date | None = None) -> bytes:
    """Неделя: по дню карточка, в ней строка на пару — время, полоса цвета
    предмета, название, «лек · А-15». Дни без пар — одной строкой внизу."""
    p = _P(style or STYLE)
    f_day, f_time, f_name, f_meta, f_sub = p.f("heading", 38), p.f("num", 32), p.f("bold", 31), \
        p.f("body", 26), p.f("body", 30)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    name_x = PAD + 36 + 130
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
        blocks.append((d, rows, 32 + 60 + len(rows) * 84 + 14))
    h = PAD + 190 + sum(b[2] + 18 for b in blocks) + (90 if free else 0) + (230 if not busy else 0) + 110 + PAD
    img = _canvas(p, h)
    dr = ImageDraw.Draw(img)
    y = _header(img, dr, p, title, subtitle, "joy" if not busy else "surf")
    if not busy:
        _card(dr, p, (PAD, y, W - PAD, y + 200))
        dr.text((PAD + 40, y + 50), "Пар нет", font=p.f("heading", 48), fill=p.text)
        dr.text((PAD + 40, y + 120), "вся неделя свободна", font=f_meta, fill=p.muted)
        y += 230
    from kapibara.features.schedule.format import MONTHS_GEN
    for d, rows, bh in blocks:
        _card(dr, p, (PAD, y, W - PAD, y + bh))
        if today and d == today:                     # сегодня — рамкой акцента
            dr.rounded_rectangle((PAD, y, W - PAD, y + bh), 30, outline=p.accent, width=4)
        n = sum(l.get("pairs", 1) for l, _, _ in rows)
        dr.text((PAD + 36, y + 26), f"{DAYS_SHORT[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}",
                font=f_day, fill=p.accent)
        label = ("сегодня · " if today and d == today else "") + f"{n} {_pairs_word(n)}"
        dr.text((W - PAD - 36 - dr.textlength(label, font=f_meta), y + 36), label, font=f_meta, fill=p.muted)
        cy = y + 32 + 62
        for l, name, meta in rows:
            col = p.subject(l["title"])
            dr.text((PAD + 36, cy + 2), l["start"], font=f_time, fill=p.text)
            dr.rounded_rectangle((name_x - 26, cy + 6, name_x - 20, cy + 70), 3, fill=col)
            dr.text((name_x, cy), name, font=f_name, fill=p.text)
            if meta:
                dr.text((name_x, cy + 42), meta, font=f_meta, fill=p.muted)
            cy += 84
        y += bh + 18
    if free:
        dr.text((PAD, y + 20), "Свободно: " + ", ".join(free), font=f_sub, fill=p.muted)
        y += 90
    _footer(dr, p, y + 26, footer)
    return _jpeg(img)


# ── ссылки и сборка ─────────────────────────────────────────────────────────
# Ссылка на картинку подписана (HMAC от токена бота), чтобы сервер не рисовал
# по чужим запросам расписание чего угодно. Ключ включает дату и метку
# времени — Telegram кэширует картинки по URL, а расписание меняется.

def sign(key: str) -> str:
    from kapibara.core.config import BOT_TOKEN
    return hmac.new(BOT_TOKEN.encode(), f"card:{key}".encode(), hashlib.sha256).hexdigest()[:24]


DAY = 24 * 6          # десятиминуток в сутках


def card_url(base: str, kind: str, target_type: int = 0, target_id: int = 0, ver: str = "") -> str:
    """kind: today / tomorrow / week (своя группа) или target (неделя найденного).
    Метка — начало суток (в десятиминутках, как раньше), ver — хэш готовой
    картинки (prepare): пока расписание то же, ссылка та же и Telegram не
    качает картинку заново. Превью — та же ссылка с «&thumb=1»."""
    key = f"{kind}-{target_type}-{target_id}-{int(time.time()) // 86400 * DAY}" + (f"-{ver}" if ver else "")
    return f"{base.rstrip('/')}/card/{key}.jpg?sig={sign(key)}"


# Ссылка живёт месяц: иначе ссылку из старого сообщения можно дёргать вечно
# (каждый раз рендер Pillow и запрос к зеркалу). Метка — десятиминутки.
CARD_MAX_AGE = 30 * 24 * 6


def parse_key(key: str, sig: str) -> tuple[str, int, int] | None:
    if not hmac.compare_digest(sig, sign(key)):
        return None
    parts = key.split("-")
    if len(parts) == 5 and re.fullmatch(r"[0-9a-f]{1,16}", parts[4]):
        parts = parts[:4]
    if len(parts) != 4 or not (parts[0] in ("today", "tomorrow", "week", "target", "now")
                               or re.fullmatch(r"d\d{8}", parts[0])):
        return None
    try:
        kind, target_type, target_id, stamp = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        return None
    if not 0 <= int(time.time()) // 600 - stamp <= CARD_MAX_AGE:
        return None
    return kind, target_type, target_id


# ── готовые картинки ────────────────────────────────────────────────────────
# Раньше картинка рисовалась, только когда за ней приходил Telegram, а
# ссылка менялась каждые 10 минут — превью в списке @бота грузились секундами
# (Никита 03.11). Теперь бот рисует их, пока отвечает на запрос (prepare), и
# кладёт сюда вместе с превью: Telegram приходит — всё уже готово.

CACHE_TTL = 30 * 60
CACHE_MAX = 120
PREPARE_TIMEOUT = 4.0
_cache: OrderedDict[str, tuple[float, bytes, bytes | None]] = OrderedDict()


def cached(key: str, thumb: bool = False) -> bytes | None:
    hit = _cache.get(key)
    if not hit or hit[0] < time.time():
        return None
    return hit[2] if thumb else hit[1]


def put(key: str, data: bytes, thumb: bytes | None = None):
    _cache[key] = (time.time() + CACHE_TTL, data, thumb)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


async def render(kind: str, target_type: int = 0, target_id: int = 0, now: datetime | None = None) -> bytes | None:
    """Нарисовать карточку (None — расписание не загрузилось)."""
    from kapibara.core.config import BOT_USERNAME, GROUP_NAME
    from kapibara.core.utils import TZ
    now = now or datetime.now(TZ)
    if kind == "target" or target_id:
        from kapibara.features.schedule import index as schedule_index
        from kapibara.features.schedule.mirea_api import fetch_ical
        ttype = target_type if kind == "target" else 1
        raw = await fetch_ical(target_id, ttype)
        if raw is None:
            return None
        title = await schedule_index.get_title(ttype, target_id)
        if kind == "target":
            return await asyncio.to_thread(build_target, raw, title or "Расписание", now, BOT_USERNAME)
        return await asyncio.to_thread(build_own, raw, kind, now, title or "Группа", BOT_USERNAME)
    from kapibara.features.schedule.parser import fetch_schedule_raw
    raw = await fetch_schedule_raw()
    return await asyncio.to_thread(build_own, raw, kind, now, GROUP_NAME, BOT_USERNAME)


async def prepare(base: str, kind: str, target_type: int = 0, target_id: int = 0) -> str:
    """Нарисовать заранее и вернуть ссылку с хэшем картинки. Не успели или
    сбой — ссылка без хэша: сервер дорисует, когда Telegram придёт."""
    try:
        data = await asyncio.wait_for(render(kind, target_type, target_id), PREPARE_TIMEOUT)
        if data is None:
            raise ValueError("расписание не загрузилось")
        thumb = await asyncio.to_thread(thumbnail, data)
    except (*NETWORK, OSError, ValueError, RuntimeError) as e:   # ответ всё равно уйдёт — дорисует /card
        logger.info(f"card: заранее не нарисовали {kind} {target_type}/{target_id}: {type(e).__name__}: {e}")
        return card_url(base, kind, target_type, target_id)
    url = card_url(base, kind, target_type, target_id, hashlib.sha1(data).hexdigest()[:10])
    put(url.split("/card/")[1].split(".jpg")[0], data, thumb)
    return url


def _monday_for(today: date) -> date:
    """Неделя для картинки: текущая, а в воскресенье — следующая."""
    return today - timedelta(days=today.weekday()) + (timedelta(days=7) if today.weekday() == 6 else timedelta(0))


def week_title(raw: bytes, monday: date) -> tuple[str, str]:
    from kapibara.features.schedule.parser import MONTHS_GEN, week_number
    sunday = monday + timedelta(days=6)
    num = week_number(raw, monday) or week_number(raw, monday + timedelta(days=1))
    span = (f"{monday.day}–{sunday.day} {MONTHS_GEN[sunday.month - 1]}" if monday.month == sunday.month
            else f"{monday.day} {MONTHS_GEN[monday.month - 1]} – {sunday.day} {MONTHS_GEN[sunday.month - 1]}")
    return (f"Неделя {num}" if num else "Неделя"), span


def build_own(raw: bytes, kind: str, now: datetime, group: str, bot: str) -> bytes:
    from kapibara.features.schedule.parser import DAY_NAMES, MONTHS_GEN, lessons_for_date
    footer = f"{group} · @{bot}"
    if kind == "week":
        monday = _monday_for(now.date())
        days = [(monday + timedelta(days=i), lessons_for_date(raw, monday + timedelta(days=i))) for i in range(7)]
        title, span = week_title(raw, monday)
        n = sum(l.get("pairs", 1) for _, ls in days for l in ls)
        return render_week(title, f"{span} · {n} {_pairs_word(n)}", days, footer, today=now.date())
    if kind == "now":
        return build_now(raw, now, footer)
    d = kind_date(kind, now.date())
    lessons = lessons_for_date(raw, d)
    return render_day(f"{DAY_NAMES[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}", day_subtitle(lessons),
                      lessons, footer)


def kind_date(kind: str, today: date) -> date:
    """today / tomorrow / dГГГГММДД (любой день, inline «пятница», «12 ноября»)."""
    if kind.startswith("d") and len(kind) == 9:
        return date(int(kind[1:5]), int(kind[5:7]), int(kind[7:9]))
    return today + timedelta(days=1 if kind == "tomorrow" else 0)


def _mins(m: int) -> str:
    h, m = divmod(max(m, 0), 60)
    return f"{h} ч {m} мин" if h and m else f"{h} ч" if h else f"{m} мин"


def build_now(raw: bytes, now: datetime, footer: str) -> bytes:
    """«Сейчас»: идущая пара или ближайшая следующая (до недели вперёд) и
    остальные пары того же дня."""
    from kapibara.features.schedule.parser import DAY_NAMES, MONTHS_GEN, lessons_for_date
    today = now.date()
    hm = now.strftime("%H:%M")
    lessons = lessons_for_date(raw, today)
    rest = [l for l in lessons if l["end"] > hm]
    if rest:
        l = rest[0]
        if l["start"] <= hm:
            title = f"Идёт {l['num']} пара" if l.get("num") else "Идёт пара"
            sub = f"до конца {_mins(_gap(hm, l['end']))}"
            tag = "идёт"
        else:
            title = f"Через {_mins(_gap(hm, l['start']))}"
            sub = f"следующая пара · в {l['start']}"
            tag = "следующая"
        more = len(rest) - 1
        sub += f" · потом ещё {more}" if more else " · последняя сегодня"
        return render_day(title, sub, rest, footer, pose="day", highlight=(0, tag))
    for i in range(1, 8):
        d = today + timedelta(days=i)
        if ls := lessons_for_date(raw, d):
            when = "завтра" if i == 1 else f"{DAY_NAMES[d.weekday()].lower()}, {d.day} {MONTHS_GEN[d.month - 1]}"
            return render_day("Сегодня пар больше нет" if lessons else "Сегодня пар нет",
                              f"следующие — {when} с {ls[0]['start']}", ls, footer, pose="night",
                              highlight=(0, "следующая"))
    return render_day("Пар нет", "ближайшую неделю свободно", [], footer)


def build_target(raw: bytes, title: str, now: datetime, bot: str) -> bytes:
    from kapibara.features.schedule.parser import target_weeks
    monday = _monday_for(now.date())
    week = target_weeks(raw, monday, weeks=1)[0]
    days = [(date.fromisoformat(x["date"]), x["lessons"]) for x in week["days"]]
    wt, span = week_title(raw, monday)
    return render_week(title, f"{wt.lower()} · {span}", days, f"@{bot}", today=now.date())

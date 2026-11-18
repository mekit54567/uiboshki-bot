"""Рисование картинок расписания (часть card.py): палитра и оформление
(STYLES, по умолчанию STYLE — «Мел»), фон с шумом и капибарой, карточка дня —
пары лентой с перерывами — и неделя по дню на карточку. Pillow, шрифты
приложения из assets/fonts, JPEG. Ссылки, кэш и сборка — в card.py; снаружи
имена берут оттуда, это те же объекты."""

import functools
import io
import logging
import random
from datetime import date
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from kapibara.core.paths import ROOT

logger = logging.getLogger("kapibara.features.schedule.card")    # то же имя, что до разделения (/status)

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
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mix(a, b, t: float) -> tuple[int, int, int]:
    """a → b на долю t."""
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=False))


# Оформления. heading/body/num — (файл, вес); texture — фон: бумага, доска мелом, клетка.
STYLES: dict[str, dict[str, Any]] = {
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
            f.set_variation_by_axes([weight if i == 0 else min(max(size / 2, a["minimum"] or 0), a["maximum"] or 0)
                                     for i, a in enumerate(axes)])
        except (OSError, AttributeError) as e:     # без веса — обычное начертание
            logger.info(f"card: вес шрифта {name}: {e}")
    return f


class _P:
    """Палитра оформления: цвета — кортежами, шрифты — по роли."""

    def __init__(self, style: str):
        s = STYLES.get(style) or STYLES[STYLE]
        self.name = style if style in STYLES else STYLE
        self.bg, self.card, self.line = _rgb(s["bg"]), _rgb(s["card"]), _rgb(s["line"])
        self.text, self.muted, self.accent = _rgb(s["text"]), _rgb(s["muted"]), _rgb(s["accent"])
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
    img: Image.Image = Image.open(io.BytesIO(data))
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
    return small.resize((w, h), Image.Resampling.BILINEAR)


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
        m = Image.open(CAPY / f"{pose}.png").convert("LA").split()[-1].resize((size, size), Image.Resampling.LANCZOS)
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
        px: float = left
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

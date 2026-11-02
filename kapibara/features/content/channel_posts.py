"""
Посты канала бота (этап 3): лежат в репозитории, публикует сам бот — админ
канала, — по кнопке старосты (`/channel`, handlers/channel.py).

Каждый пост — папка channel/posts/NN-имя/ («news» в имени — пост для
открытого канала Капибары, остальные — канал разработки, target):
  • post.html — текст в разметке Telegram (HTML: <b>, <i>, <u>, <s>,
    <tg-spoiler>, <code>, <pre><code class="language-python">, <blockquote>,
    <blockquote expandable>, <a href>), до 4096 символов;
  • 1.png, 2.jpg… — картинки по порядку. Бот собирает их в одну обложку
    (скрины рядом на фоне цвета аватара канала, cover_jpeg).

Пост — всегда одно сообщение (одно «Прокомментировать»): короткий текст —
подписью к обложке, длинный (подпись у бота — до 1024 символов) — обычным
сообщением, а обложка встаёт над текстом большим превью ссылки: её отдаёт
сервер WebApp по /chimg/<пост>.jpg (webapp/routes/channel.py).

Почему через бота, а не руками в Telegram Web: разметка (раскрывающиеся
цитаты, блоки кода, альбомы) приходит ровно как задумано, а староста видит
точное превью у себя в личке до публикации.
"""

import asyncio
import hashlib
import io
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

POSTS_DIR = Path(__file__).parent / "channel" / "posts"
CAPTION_LIMIT = 1024     # подпись к фото/альбому
TEXT_LIMIT = 4096        # обычное сообщение
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
COVER_VERSION = "1"      # поменять — Telegram заберёт обложки заново


def target(slug: str) -> str:
    """Куда выходит пост: «news» в имени папки (`25-news-hello-pinned`) —
    открытый канал Капибары для всех (LOGIN_CHANNEL, Никита 19.10), остальные —
    канал разработки (CHANNEL_ID). Не задан — пусто."""
    import config
    import login_channel
    return login_channel.channel() if "news" in slug.split("-") else config.CHANNEL_ID


def visible_len(html: str) -> int:
    """Длина текста так, как её считает Telegram — без тегов и с раскрытыми &amp;."""
    text = re.sub(r"<[^>]+>", "", html)
    return len(text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&"))


def title_of(html: str, slug: str) -> str:
    m = re.search(r"<b>(.*?)</b>", html, re.S)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else slug


def load_posts(root: Path | None = None) -> list[dict]:
    """Все посты по порядку папок: [{"slug", "title", "html", "images"}]."""
    root = root or POSTS_DIR
    posts = []
    if not root.exists():
        return posts
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        f = d / "post.html"
        if not f.exists():
            continue
        html = f.read_text(encoding="utf-8").strip()
        images = sorted((p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXT),
                        key=lambda p: (len(p.stem), p.stem))
        posts.append({"slug": d.name, "title": title_of(html, d.name), "html": html, "images": images})
    return posts


def check(post: dict) -> str:
    """Что не так с постом («» — всё в порядке): длина, число картинок."""
    n = visible_len(post["html"])
    if n > TEXT_LIMIT:
        return f"текст {n} символов — больше {TEXT_LIMIT}"
    if len(post["images"]) > 4:
        return "больше 4 картинок — обложка выйдет слишком узкой по высоте"
    return ""


def cover_key(post: dict) -> str:
    """Метка содержимого обложки: другая картинка — другая ссылка, и
    Telegram не покажет старое превью из своего кэша."""
    h = hashlib.sha1(COVER_VERSION.encode())
    for p in post["images"]:
        h.update(p.name.encode() + p.read_bytes())
    return h.hexdigest()[:10]


def cover_url(base_url: str, post: dict) -> str:
    return f"{base_url.rstrip('/')}/chimg/{post['slug']}.jpg?v={cover_key(post)}"


_covers: dict[str, bytes] = {}


def cover_jpeg(post: dict) -> bytes:
    """Одна обложка из всех картинок поста: скрины в ряд, одного масштаба
    (самый высокий — во всю высоту, короткие — по центру), со скруглением и
    тенью, на фиолетовом градиенте как у аватара канала. Один скрин — квадрат,
    несколько — шире."""
    key = f"{post['slug']}:{cover_key(post)}"
    if key in _covers:
        return _covers[key]
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    H, PAD, GAP, R = 1320, 80, 56, 34
    shots = [Image.open(p).convert("RGB") for p in post["images"]]
    scale = (H - 2 * PAD) / max(im.height for im in shots)
    shots = [im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS) for im in shots]
    W = max(H, sum(im.width for im in shots) + GAP * (len(shots) - 1) + 2 * PAD)
    # градиент по диагонали: светлый фиолетовый → глубокий
    a, b = (142, 140, 242), (79, 70, 200)
    v = Image.linear_gradient("L")                       # 0 сверху → 255 снизу
    grad = ImageChops.add(v.resize((W, H)), v.rotate(90).transpose(Image.FLIP_LEFT_RIGHT).resize((W, H)), scale=2)
    bg = Image.composite(Image.new("RGB", (W, H), b), Image.new("RGB", (W, H), a), grad)
    x = (W - (sum(im.width for im in shots) + GAP * (len(shots) - 1))) // 2
    for im in shots:
        y = (H - im.height) // 2
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), R, fill=255)
        shadow = Image.new("L", (W, H), 0)
        shadow.paste(mask, (x, y + 14))
        shadow = shadow.filter(ImageFilter.GaussianBlur(22))
        bg = Image.composite(Image.new("RGB", (W, H), (30, 24, 80)), bg, shadow.point(lambda v: v * 0.55))
        bg.paste(im, (x, y), mask)
        x += im.width + GAP
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=88, optimize=True)
    _covers[key] = buf.getvalue()
    return _covers[key]


async def send_post(bot, chat_id, post: dict, base_url: str = "") -> list[int]:
    """Отправить пост (в канал или старосте — превью) одним сообщением:
    короткий — подписью к обложке, длинный — текстом с обложкой над ним
    (превью ссылки base_url/chimg/…). Без base_url (нет WEBAPP_URL) длинный
    пост с картинками уходит как раньше: обложка, следом текст.
    → id отправленных сообщений."""
    from aiogram.types import BufferedInputFile, LinkPreviewOptions
    html, images = post["html"], post["images"]
    if not images:
        m = await bot.send_message(chat_id, html, parse_mode="HTML",
                                   link_preview_options=LinkPreviewOptions(is_disabled=True))
        return [m.message_id]
    if visible_len(html) > CAPTION_LIMIT and base_url:
        m = await bot.send_message(chat_id, html, parse_mode="HTML", link_preview_options=LinkPreviewOptions(
            url=cover_url(base_url, post), prefer_large_media=True, show_above_text=True))
        return [m.message_id]
    # склейка картинок Pillow — в отдельном потоке, бот в это время отвечает
    photo = BufferedInputFile(await asyncio.to_thread(cover_jpeg, post), filename=f"{post['slug']}.jpg")
    if visible_len(html) <= CAPTION_LIMIT:
        m = await bot.send_photo(chat_id, photo, caption=html, parse_mode="HTML")
        return [m.message_id]
    m1 = await bot.send_photo(chat_id, photo)
    m2 = await bot.send_message(chat_id, html, parse_mode="HTML",
                                link_preview_options=LinkPreviewOptions(is_disabled=True))
    return [m1.message_id, m2.message_id]


async def edit_post(bot, chat_id, post: dict, ids: list[int], base_url: str = "") -> str:
    """Поправить уже выпущенный пост текстом из репозитория — тем же видом,
    что и send_post: правка с аккаунта в Telegram снимает обложку (превью
    ссылки, которой нет в тексте) и не берёт раскрывающиеся цитаты, а бот —
    автор поста — правит без потерь. → "ok", "same" (текст уже такой) или
    текст ошибки."""
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import LinkPreviewOptions
    html, images = post["html"], post["images"]
    try:
        if not images:
            await bot.edit_message_text(html, chat_id=chat_id, message_id=ids[0], parse_mode="HTML",
                                        link_preview_options=LinkPreviewOptions(is_disabled=True))
        elif visible_len(html) <= CAPTION_LIMIT:
            await bot.edit_message_caption(chat_id=chat_id, message_id=ids[0], caption=html, parse_mode="HTML")
        elif len(ids) == 1 and base_url:
            await bot.edit_message_text(html, chat_id=chat_id, message_id=ids[0], parse_mode="HTML",
                                        link_preview_options=LinkPreviewOptions(
                                            url=cover_url(base_url, post), prefer_large_media=True, show_above_text=True))
        elif len(ids) == 2:            # старый вид: обложка, следом текст
            await bot.edit_message_text(html, chat_id=chat_id, message_id=ids[1], parse_mode="HTML",
                                        link_preview_options=LinkPreviewOptions(is_disabled=True))
        else:
            return "нужен WEBAPP_URL — без него обложку над текстом не сохранить"
    except TelegramBadRequest as e:
        if "not modified" in str(e).lower():
            return "same"
        return str(e)
    return "ok"


async def published() -> dict:
    """{slug: {"ids": [...], "at": "…"}} — что уже в канале."""
    from database import get_setting
    raw = await get_setting("channel:published")
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


async def forget_published():
    from database import set_setting
    await set_setting("channel:published", "{}")


async def mark_published(slug: str, ids: list[int]):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from config import TIMEZONE
    from database import set_setting
    from locks import lock
    async with lock("channel:published"):      # две публикации подряд — в списке обе
        done = await published()
        done[slug] = {"ids": ids, "at": datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="minutes")}
        await set_setting("channel:published", json.dumps(done, ensure_ascii=False))


def post_link(channel: str, msg_id: int) -> str:
    """t.me/<канал>/<id> для публичного канала (@имя), иначе пусто."""
    return f"https://t.me/{channel.lstrip('@')}/{msg_id}" if channel.startswith("@") else ""

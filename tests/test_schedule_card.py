"""Картинки расписания для inline-режима: рисуются (день, неделя, пустой
день), ссылка подписана — чужая подпись не проходит, inline отдаёт фото,
если есть адрес сервера."""
import io
from datetime import date, datetime, timedelta

import pytest
from PIL import Image

from kapibara.features.schedule import card as schedule_card
from tests.test_inline import _ask
from kapibara.core.utils import TZ

L = {"num": 1, "pairs": 1, "start": "09:00", "end": "10:30", "title": "Моделирование бизнес-процессов",
     "kind": "лекция", "room": "А-15 (В-78)", "teacher": "Иванов И."}


def _img(data: bytes):
    img = Image.open(io.BytesIO(data))
    assert img.format == "JPEG" and img.width == schedule_card.W
    return img


def test_render_day_and_long_title():
    long = dict(L, title="Очень длинное название предмета " * 6, kind="практика", num=2)
    a = _img(schedule_card.render_day("Понедельник, 5 октября", "2 пары", [L, long], "УИБО · @bot"))
    b = _img(schedule_card.render_day("Понедельник, 5 октября", "2 пары", [L, L], "УИБО · @bot"))
    assert a.height > b.height          # длинное название — в две строки, не вылезает за край
    _img(schedule_card.render_day("Суббота, 10 октября", "пар нет", [], "УИБО · @bot"))


def test_render_week_skips_free_days():
    mon = date(2026, 10, 5)
    days = [(mon + timedelta(days=i), [L] if i in (0, 3) else []) for i in range(7)]
    two = _img(schedule_card.render_week("Неделя 6", "5–11 октября", days, "@bot"))
    days[1] = (days[1][0], [L])
    three = _img(schedule_card.render_week("Неделя 6", "5–11 октября", days, "@bot"))
    assert three.height > two.height


def test_day_subtitle():
    assert schedule_card.day_subtitle([]) == "пар нет"
    assert schedule_card.day_subtitle([L, dict(L, start="10:40", end="12:10")]) == "2 пары · 09:00–12:10"


def test_signed_key():
    url = schedule_card.card_url("https://x.app/", "target", 2, 77)
    key, sig = url.split("/card/")[1].split(".jpg?sig=")
    assert schedule_card.parse_key(key, sig) == ("target", 2, 77)
    assert schedule_card.parse_key(key.replace("77", "78"), sig) is None
    assert schedule_card.parse_key(key, "0" * 24) is None


def test_card_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from kapibara.features.schedule import parser as schedule_parser
    import webapp.server as server
    calls = []

    async def raw(force=False):
        calls.append(1)
        return b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    schedule_card._cache.clear()
    c = TestClient(server.app)
    url = schedule_card.card_url("http://testserver", "week").replace("http://testserver", "")
    r = c.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    _img(r.content)
    assert c.get(url).status_code == 200 and len(calls) == 1       # второй раз — из памяти
    assert c.get(url.split("?")[0] + "?sig=bad").status_code == 403
    # превью — отдельным маленьким файлом (живой тест: с одной ссылкой на
    # превью и фото картинка в чате приходила обрезанной снизу)
    t = c.get(url + "&thumb=1")
    assert t.status_code == 200 and len(t.content) < len(r.content)
    assert Image.open(io.BytesIO(t.content)).width == schedule_card.THUMB_W and len(calls) == 1


def test_build_own_today(monkeypatch):
    from kapibara.features.schedule import parser as schedule_parser
    monkeypatch.setattr(schedule_parser, "lessons_for_date", lambda raw, d, now=None: [L])
    _img(schedule_card.build_own(b"", "today", datetime(2026, 10, 5, 8, 0, tzinfo=TZ), "УИБО", "bot"))


@pytest.mark.asyncio
async def test_inline_sends_photos_when_server_known(monkeypatch):
    from kapibara.core import config
    monkeypatch.setattr(config, "WEBAPP_URL", "https://bot.example")
    ans = await _ask("")
    assert [type(r).__name__ for r in ans.results] == ["InlineQueryResultPhoto"] * 4
    assert all(r.photo_url.startswith("https://bot.example/card/") for r in ans.results)
    assert all(r.thumbnail_url == r.photo_url + "&thumb=1" for r in ans.results)
    assert (await _ask("завтра")).results[0].photo_url.split("/card/")[1].startswith("tomorrow-")


@pytest.mark.parametrize("style", list(schedule_card.STYLES))
def test_styles_render(style):
    _img(schedule_card.render_day("Понедельник, 5 октября", "1 пара", [L], "УИБО · @bot", style=style))
    mon = date(2026, 10, 5)
    _img(schedule_card.render_week("Неделя 6", "5–11 октября", [(mon, [L])], "@bot", style=style, today=mon))


def test_same_schedule_same_bytes():
    """Одно расписание — байт в байт та же картинка (зерно фона не случайное):
    иначе хэш в ссылке менялся бы, и Telegram качал бы картинку заново."""
    a = schedule_card.render_day("Понедельник, 5 октября", "1 пара", [L], "УИБО · @bot")
    assert a == schedule_card.render_day("Понедельник, 5 октября", "1 пара", [L], "УИБО · @bot")


def test_break_line_makes_card_taller():
    late = dict(L, start="14:20", end="15:50")
    near = dict(L, start="10:40", end="12:10")
    far = _img(schedule_card.render_day("Пн", "2 пары", [L, late], "@bot"))
    close = _img(schedule_card.render_day("Пн", "2 пары", [L, near], "@bot"))
    assert far.height > close.height          # перерыв от 40 минут — строкой


@pytest.mark.asyncio
async def test_prepare_draws_before_telegram_comes(monkeypatch):
    """Медленные превью (Никита 03.11): картинка рисуется, пока бот отвечает,
    ссылка стабильна, а /card отдаёт готовое без нового рендера."""
    from fastapi.testclient import TestClient
    from kapibara.features.schedule import parser as schedule_parser
    import webapp.server as server
    calls = []

    async def raw(force=False):
        calls.append(1)
        return b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    schedule_card._cache.clear()
    url = await schedule_card.prepare("http://testserver", "week")
    assert url == await schedule_card.prepare("http://testserver", "week")      # та же ссылка
    key = url.split("/card/")[1].split(".jpg")[0]
    assert len(key.split("-")) == 5 and schedule_card.cached(key, thumb=True)
    n = len(calls)
    c = TestClient(server.app)
    path = url.replace("http://testserver", "")
    assert c.get(path + "&thumb=1").status_code == 200
    r = c.get(path)
    assert r.status_code == 200 and "max-age" in r.headers["cache-control"]
    assert len(calls) == n                                                   # без нового рендера


@pytest.mark.asyncio
async def test_prepare_falls_back_to_plain_link(monkeypatch):
    async def broken(*a, **kw):
        raise OSError("зеркало молчит")

    monkeypatch.setattr(schedule_card, "render", broken)
    url = await schedule_card.prepare("https://x.app", "today")
    key, sig = url.split("/card/")[1].split(".jpg?sig=")
    assert len(key.split("-")) == 4 and schedule_card.parse_key(key, sig) == ("today", 0, 0)


def test_now_card(monkeypatch):
    """«Сейчас»: идёт пара — она первой и обведена; пар больше нет — ближайший день."""
    from kapibara.features.schedule import parser as schedule_parser
    late = dict(L, num=3, start="12:40", end="14:10")
    seen = []

    def lessons(raw, d, now=None):
        seen.append(d)
        return [L, late] if d == date(2026, 10, 5) or d == date(2026, 10, 7) else []

    monkeypatch.setattr(schedule_parser, "lessons_for_date", lessons)
    _img(schedule_card.build_own(b"", "now", datetime(2026, 10, 5, 9, 30, tzinfo=TZ), "УИБО", "bot"))
    seen.clear()
    _img(schedule_card.build_own(b"", "now", datetime(2026, 10, 5, 20, 0, tzinfo=TZ), "УИБО", "bot"))
    assert seen[-1] == date(2026, 10, 7)                    # вторник пустой — взяли среду


def test_any_day_key():
    url = schedule_card.card_url("https://x.app", "d20261106")
    key, sig = url.split("/card/")[1].split(".jpg?sig=")
    assert schedule_card.parse_key(key, sig) == ("d20261106", 0, 0)
    assert schedule_card.kind_date("d20261106", date(2026, 11, 3)) == date(2026, 11, 6)

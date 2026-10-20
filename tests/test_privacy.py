"""152-ФЗ (privacy.py): согласие, «удалить все мои данные», срок хранения.

Главный сторож — test_erase_leaves_nothing: обходит ВСЕ таблицы схемы с
колонкой user_id, кладёт в каждую строку человека и соседа и проверяет, что
после удаления от человека не осталось ни строки, а сосед цел. Новая таблица
с user_id попадёт в проверку сама."""
import json

import aiosqlite
import pytest

from tests.conftest import STAROSTA_ID
from tests.test_review_bot import Session, TOKEN, press, send  # noqa: F401 — фикстуры ниже
from tests.test_review_bot import bot, dp  # noqa: F401

ME, OTHER = 222, 333

from database.privacy import get_consents  # noqa: E402


async def _fill_user_tables(path, uid):
    """В каждую таблицу с user_id — строку этого человека (остальные колонки — что угодно)."""
    async with aiosqlite.connect(path) as conn:
        from database.privacy import user_tables
        tables = await user_tables(conn)
        for t in tables:
            cols = await (await conn.execute(f"PRAGMA table_info({t})")).fetchall()
            names, values = [], []
            for _, name, typ, *_ in cols:
                names.append(name)
                if name == "user_id":
                    values.append(uid)
                elif "INT" in (typ or "").upper():
                    values.append(uid * 10 + len(names))
                else:
                    values.append(f"{name}-{uid}")
            await conn.execute(f"INSERT OR REPLACE INTO {t} ({','.join(names)}) VALUES ({','.join('?' * len(names))})",
                               values)
        await conn.commit()
    return tables


@pytest.mark.asyncio
async def test_erase_leaves_nothing(db):
    from database.homework import init_hw_table
    await init_hw_table()
    import privacy
    tables = await _fill_user_tables(db.DATABASE_PATH, ME)
    await _fill_user_tables(db.DATABASE_PATH, OTHER)
    assert {"users", "sessions", "identities", "sdo_sessions", "consents", "events",
            "sdo_score_history", "push_subs", "app_push"} <= set(tables)

    personal = await db.add_deadline("Своё", "личное", "2026-10-05", None, ME)
    shared = await db.add_deadline("Общее", "группы", "2026-10-05", None, ME, group_id=5000)   # староста чужой группы
    sdo = await db.add_deadline("СДО", "задание", "2026-10-05", None, 0)
    await db.set_setting(f"goals:{ME}", "{}")
    await db.set_setting(f"member:{ME}", "1:0")
    await db.set_setting(f"goals:{OTHER}", "{}")
    await db.set_setting("ai_day:2026-10-11", json.dumps({str(ME): 3, str(OTHER): 2}))
    from database.social import feed_author_hash
    async with aiosqlite.connect(db.DATABASE_PATH) as conn:
        await conn.execute("INSERT INTO files (title, subject, file_id, uploaded_by) VALUES ('Лекция 1','Матан','f1',?)", (ME,))
        await conn.execute("INSERT INTO feed_posts (text, author_id) VALUES ('пост', ?)", (feed_author_hash(ME),))
        await conn.execute("INSERT INTO homework (subject, content, created_by) VALUES ('Матан','дз',?)", (ME,))
        await conn.commit()

    await privacy.erase(ME)

    async with aiosqlite.connect(db.DATABASE_PATH) as conn:
        for t in tables:
            mine = (await (await conn.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id=?", (ME,))).fetchone())[0]
            other = (await (await conn.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id=?", (OTHER,))).fetchone())[0]
            assert mine == 0, f"{t}: остались строки человека"
            assert other == 1, f"{t}: задело соседа"
        ids = {r[0]: r[1] for r in await (await conn.execute("SELECT id, created_by FROM deadlines")).fetchall()}
        assert personal not in ids                      # личный — удалён
        assert ids[shared] == 0 and ids[sdo] == 0       # общий — остался группе, без автора
        assert (await (await conn.execute("SELECT uploaded_by FROM files")).fetchone())[0] is None
        assert (await (await conn.execute("SELECT author_id FROM feed_posts")).fetchone())[0] == 0
        assert (await (await conn.execute("SELECT created_by FROM homework")).fetchone())[0] is None
    assert await db.get_setting(f"goals:{ME}") is None and await db.get_setting(f"member:{ME}") is None
    assert await db.get_setting(f"goals:{OTHER}") == "{}"
    assert json.loads(await db.get_setting("ai_day:2026-10-11")) == {str(OTHER): 2}


@pytest.mark.asyncio
async def test_consent_versions(db, monkeypatch):
    import privacy
    await db.upsert_user(ME, "me", "Я")
    assert await privacy.needs(ME) and await privacy.needs(ME, "sdo")
    await privacy.give(ME, "pd", "bot")
    assert not await privacy.needs(ME) and await privacy.needs(ME, "sdo")
    monkeypatch.setattr(privacy, "VERSION", privacy.VERSION + "+")          # новый текст — спросить заново
    assert await privacy.needs(ME)
    with pytest.raises(ValueError):
        await privacy.give(ME, "ads", "bot")


@pytest.mark.asyncio
async def test_retention_purge(db):
    import privacy
    for uid in (ME, OTHER, STAROSTA_ID):
        await db.upsert_user(uid, "", "x")
    async with aiosqlite.connect(db.DATABASE_PATH) as conn:
        await conn.execute("UPDATE users SET last_seen=datetime('now','-400 days') WHERE user_id IN (?, ?)",
                           (ME, STAROSTA_ID))
        await conn.execute("INSERT INTO solver_history (user_id, task_text, answer, created_at) "
                           "VALUES (?, 'старое', 'a', datetime('now','-200 days')), (?, 'новое', 'b', datetime('now'))",
                           (OTHER, OTHER))
        await conn.commit()
    await privacy.purge()
    assert await db.get_user(ME) is None                  # год без заходов — стёрт
    assert await db.get_user(OTHER) and await db.get_user(STAROSTA_ID)   # староста — нет
    async with aiosqlite.connect(db.DATABASE_PATH) as conn:
        left = [r[0] for r in await (await conn.execute("SELECT task_text FROM solver_history")).fetchall()]
    assert left == ["новое"]


@pytest.mark.asyncio
async def test_seen_marks_last_visit(db):
    import privacy
    await db.upsert_user(ME, "", "x")
    async with aiosqlite.connect(db.DATABASE_PATH) as conn:
        await conn.execute("UPDATE users SET last_seen='2020-01-01 00:00:00' WHERE user_id=?", (ME,))
        await conn.commit()
    privacy._seen.pop(ME, None)
    import stats
    await stats.track(ME, "bot")
    assert (await db.get_user(ME))["last_seen"] > "2026"


def _client(monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}


@pytest.mark.asyncio
async def test_api_consent_and_delete(db, monkeypatch):
    c, h = _client(monkeypatch)
    assert c.get("/api/me", headers=h).json()["consent_needed"] is True
    assert c.post("/api/consent", json={"kind": "ads"}, headers=h).status_code == 400
    r = c.post("/api/consent", json={"kind": "pd"}, headers=h).json()
    assert r["pd"] is True and r["sdo"] is False
    assert c.get("/api/me", headers=h).json()["consent_needed"] is False
    assert (await get_consents(ME))[0]["via"] == "tg"

    assert c.post("/api/me/delete", json={}, headers=h).status_code == 400   # без фразы — нет
    assert c.post("/api/me/delete", json={"confirm": True}, headers=h).status_code == 400
    assert c.post("/api/me/delete", json={"phrase": "удалить"}, headers=h).status_code == 400
    r = c.post("/api/me/delete", json={"phrase": " Удалить мои  данные. "}, headers=h).json()
    assert r["ok"] and r["days"] == 7 and "без гарантии" in r["text"]
    assert await db.get_user(ME) and await get_consents(ME) == []     # сразу — согласия, данные — через 7 дней


@pytest.mark.consent_real
@pytest.mark.asyncio
async def test_erase_after_seven_days(db, monkeypatch):
    """Никита 18.10: «удалить мои данные» — фразой; сразу выход везде и из СДО,
    обработка встаёт; полностью — через 7 дней; до этого староста может
    вернуть (/undelete), согласие тогда спросят заново."""
    from datetime import timedelta

    from utils import today_msk

    import privacy
    from database.sessions import create_session
    c, h = _client(monkeypatch)
    await db.upsert_user(ME, "me", "Я")
    await privacy.give(ME, "pd", "tg")
    token = await create_session(ME, "Chrome")
    assert c.get("/api/notify", headers=h).status_code == 200
    r = c.post("/api/me/delete", json={"phrase": "удалить мои данные"}, headers=h).json()
    assert r["due"] == (today_msk() + timedelta(days=7)).isoformat()
    assert c.get("/api/notify", headers={"Authorization": "Bearer " + token}).status_code == 401  # вышли везде
    assert await privacy.blocked(ME)                                   # ничего не обрабатываем
    res = c.get("/api/notify", headers=h)
    assert res.status_code == 403 and "удаляются" in res.json()["detail"]
    me = c.get("/api/me", headers=h).json()
    assert me["erasing"]["due"] == r["due"] and me["consent_blocked"]
    assert c.post("/api/consent", json={"kind": "pd"}, headers=h).status_code == 409   # согласие не берём
    assert not await privacy.ask_once(ME)

    await privacy.purge()                                              # рано — ещё есть
    assert await db.get_user(ME)
    assert await privacy.undo_erase(ME) and not await privacy.erasing(ME)   # вернули по заявке
    assert await privacy.blocked(ME)                                   # но согласие — заново
    await privacy.give(ME, "pd", "tg")
    assert not await privacy.blocked(ME)

    c.post("/api/me/delete", json={"phrase": "удалить мои данные"}, headers=h)
    import utils
    later = today_msk() + timedelta(days=7)
    monkeypatch.setattr(utils, "today_msk", lambda: later)
    await privacy.purge()                                              # прошло 7 дней — насовсем
    assert await db.get_user(ME) is None and not await privacy.erasing(ME)


@pytest.mark.asyncio
async def test_erasing_hidden_everywhere(db):
    """Ревью 152-ФЗ 18.10: в эти 7 дней человек не попадает ни в рассылки, ни
    в /stats, ни в выборки по людям (NOT_ERASING)."""
    import privacy
    from database import count_users, events_since, get_all_subscribed_users, get_all_users, get_reminder_users
    from database.service import add_event, flush_events
    for uid in (ME, OTHER):
        await db.upsert_user(uid, "u", "U")
        await add_event(uid, "bot")
    await flush_events()
    await privacy.request_erase(ME)
    assert ME not in await get_all_subscribed_users() and OTHER in await get_all_subscribed_users()
    assert ME not in {u["user_id"] for u in await get_reminder_users()}
    assert ME not in {u["user_id"] for u in await get_all_users()} and await count_users() == 1
    assert {e[0] for e in await events_since(1)} == {OTHER}


@pytest.mark.consent_real
@pytest.mark.asyncio
async def test_refuse_consent_erases_now(db, monkeypatch):
    """Новый человек отказался от согласия на листе — хранить нечего, сразу."""
    c, h = _client(monkeypatch)
    c.get("/api/me", headers=h)
    assert c.post("/api/me/delete", json={"confirm": True}, headers=h).json() == {"ok": True, "now": True}
    assert await db.get_user(ME) is None


def test_legal_texts_and_pages(monkeypatch):
    import legal_texts
    import privacy
    c, _ = _client(monkeypatch)
    # у согласия версия — privacy.VERSION (по ней спрашивают заново); у политики может быть своя,
    # не ниже: 2.1 — «Поддержка проекта» (донат — исполнение договора, согласие не меняется)
    assert legal_texts.PRIVACY["version"] >= privacy.VERSION and "поддержк" in str(legal_texts.PRIVACY)
    for name, title in (("consent", "Согласие на обработку персональных данных"),
                        ("privacy", "Политика обработки персональных данных")):
        d = c.get("/api/legal/" + name).json()
        src = legal_texts.DOCS[name]
        version, date = src.get("version", privacy.VERSION), src.get("date", privacy.DATE)
        assert d["title"] == title and d["version"] == version and d["date"] == date and d["sections"]
        assert all(set(b) in ({"p"}, {"ul"}) for s in d["sections"] for b in s["blocks"])   # JSON без HTML
        assert "{" not in json.dumps(d, ensure_ascii=False).replace('{"', "").replace("{}", "")  # всё подставлено
        page = c.get("/" + name)
        assert page.status_code == 200 and title in page.text and date in page.text
    assert c.get("/api/legal/ads").status_code == 404
    text = json.dumps(c.get("/api/legal/privacy").json(), ensure_ascii=False)
    assert "Railway" not in text and "us-west" not in text  # переезд 16.10: сервер в России
    assert "на платформе Amvera" in text and "ИНН 9724135016" in text and "перечень — на сайте Amvera" in text
    assert "Онланта" not in text and "доступа к содержимому у них нет" not in text   # договор поручения Amvera
    assert "бесплатном тарифе" in text and "для улучшения своих моделей" in text   # ревью 17.10: Gemini
    for name in ("consent", "privacy"):                    # Никита 18.10: компании, не модели ИИ
        text = json.dumps(c.get("/api/legal/" + name).json(), ensure_ascii=False)
        assert "Gemini" not in text and "Ling" not in text and "OpenRouter, Inc. (США)" in text
        assert "удалить мои данные" in text and "7 дней" in text and "без гарантии" in text
    from pathlib import Path
    assert "Gemini" not in Path("webapp/static/js/more.js").read_text(encoding="utf-8").split("Вопросы к ИИ")[1][:300]


def test_legal_short_and_more(monkeypatch):
    """Никита 18.10: в длинных разделах сразу главное, полный текст — по
    «Подробнее»; сам полный текст на месте."""
    import legal_texts
    c, _ = _client(monkeypatch)
    want = {"consent": {"Срок и отзыв"}, "privacy": {"Что храним и сколько", "Твои права"}}
    for name, titles in want.items():
        d = c.get("/api/legal/" + name).json()
        short = {s["title"] for s in d["sections"] if s.get("short")}
        assert short == titles
        for s in d["sections"]:
            assert all(set(b) in ({"p"}, {"ul"}) for b in s.get("short", []))
        full = json.dumps(d["sections"], ensure_ascii=False)
        assert "{" not in full.replace('{"', "")
        assert all(len(json.dumps(s["short"], ensure_ascii=False)) < len(json.dumps(s["blocks"], ensure_ascii=False))
                   for s in d["sections"] if s.get("short"))
        assert len(legal_texts.DOCS[name]["sections"]) == len(d["sections"])
        page = c.get("/" + name).text
        assert page.count("<summary>Подробнее</summary>") == len(titles)
    d = c.get("/api/legal/consent").json()
    term = next(s for s in d["sections"] if s["title"] == "Срок и отзыв")
    assert "удалить мои данные" in json.dumps(term["blocks"], ensure_ascii=False)   # фраза — в полном тексте


def test_erasing_text_official():
    """Никита 18.10: строка «войдёшь заново» звучала как сленг — что будет до
    и после срока, официально."""
    import privacy
    t = privacy.erasing_text("2026-10-25")
    assert "войдёшь заново" not in t and "ничего не делаем" not in t
    assert "Повторный вход до 25.10.2026 удаление не отменяет" in t
    assert "не обрабатываются" not in t and "только хранятся, никак не используются и никому не видны" in t
    assert "После 25.10.2026 данные восстановить нельзя" in t and "без гарантии" in t


def test_erase_phrase_no_paste():
    """Никита 18.10: фразу удаления не вставить и не скопировать из текста выше."""
    from pathlib import Path
    js = Path("webapp/static/js/privacy.js").read_text(encoding="utf-8")
    field = js[js.index('id="erase-phrase"'):js.index('id="erase-go"')]
    assert 'onpaste="return false"' in field and 'ondrop="return false"' in field and "noPasteInput" in field
    assert '<b class="no-copy"' in js
    assert "user-select: none" in Path("webapp/static/app.css").read_text(encoding="utf-8").split(".no-copy")[1][:120]
    dart = Path("app/lib/screens/legal.dart").read_text(encoding="utf-8")
    assert "noPaste: true" in dart


@pytest.mark.asyncio
async def test_bot_deleteme(db, dp, bot):  # noqa: F811
    """/deleteme — фразой руками; не та — ничего; та — через 7 дней, старосте
    сообщение с /undelete; /undelete — вернуть."""
    import privacy
    await db.upsert_user(ME, "", "x")
    await send(dp, bot, "/deleteme")
    assert "Удалить все твои данные" in bot.session.texts()[-1] and "удалить мои данные" in bot.session.texts()[-1]
    await send(dp, bot, "да")
    assert "не совпала" in bot.session.texts()[-1] and not await privacy.erasing(ME)
    await send(dp, bot, "/deleteme")
    await send(dp, bot, "удалить мои данные")
    assert await privacy.erasing(ME) and await db.get_user(ME)
    assert "без гарантии" in bot.session.texts()[-1]
    assert any(f"/undelete {ME}" in t for t in bot.session.texts())     # старосте
    await press(dp, bot, "erase:yes")                                  # старая кнопка — ничего
    assert await db.get_user(ME)
    await send(dp, bot, f"/undelete {ME}", uid=STAROSTA_ID)
    assert not await privacy.erasing(ME) and "Вернул" in " ".join(bot.session.texts())


@pytest.mark.asyncio
async def test_bot_consent_prompt(db, bot):  # noqa: F811
    """Кто был до согласий: бот работает и спрашивает один раз — и после деплоя
    (новый процесс) не спрашивает снова (Никита, 11.10: «зачем каждый день»)."""
    import privacy
    await db.upsert_user(ME, "", "x")
    d = _gated_dp()
    try:
        await send(d, bot, "/help")
        await send(d, bot, "/help")
    finally:
        _release(d)
    d = _gated_dp()                                         # «после деплоя»
    try:
        await send(d, bot, "/help")
        prompts = [t for t in bot.session.texts() if "Даю согласие" in t]
        assert len(prompts) == 1 and len(bot.session.texts()) == 4
        await press(d, bot, "consent:pd")
        assert not await privacy.needs(ME)
        assert (await get_consents(ME))[0]["via"] == "bot"
    finally:
        _release(d)


def test_webapp_consent_wiring():
    """Mini App и PWA: галочка не стоит, кнопка неактивна; ссылки открывают текст листом."""
    from pathlib import Path
    static = Path("webapp/static")
    html = (static / "index.html").read_text(encoding="utf-8")
    js = {p.name: p.read_text(encoding="utf-8") for p in (static / "js").glob("*.js")}
    assert 'id="consent-sheet"' in html and 'id="legal-sheet"' in html and "js/privacy.js" in html
    assert "checked" not in js["privacy.js"].split("function consentRow")[1].split("\n}\n")[0]
    assert '"sdo-save" disabled' in js["more.js"] and "agree: true" in js["more.js"]
    assert "maybeConsent(m)" in js["home.js"] and "deleteMyData()" in js["more.js"]
    assert "/api/legal/" in js["privacy.js"] and "preventDefault" in js["privacy.js"]


# ── Без согласия — ничего (ревьюер 152-ФЗ, 11.10) ───────────────────────────

def _gated_dp():
    """Как в bot.py: статистика и согласие на сообщениях, кнопках и inline."""
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from handlers import register_handlers
    from middleware import ConsentMiddleware, StatsMiddleware
    d = Dispatcher(storage=MemoryStorage())
    consent = ConsentMiddleware()
    d.message.outer_middleware(StatsMiddleware())
    d.message.outer_middleware(consent)
    d.callback_query.outer_middleware(consent)
    d.inline_query.outer_middleware(consent)
    register_handlers(d)
    return d


def _release(d):
    for r in list(d.sub_routers):
        r._parent_router = None


async def _events(path, uid):
    async with aiosqlite.connect(path) as conn:
        return (await (await conn.execute("SELECT COUNT(*) FROM events WHERE user_id=?", (uid,))).fetchone())[0]


@pytest.mark.consent_real
@pytest.mark.asyncio
async def test_new_user_gets_only_consent(db, bot):  # noqa: F811
    import privacy
    import stats
    stats._last.clear()                                 # «не чаще раза в 30 минут» — с нуля
    d = _gated_dp()
    try:
        await send(d, bot, "/start")
        texts = bot.session.texts()
        assert len(texts) == 1 and "Привет" in texts[0] and "Даю согласие" in texts[0]
        await send(d, bot, "/help")
        await send(d, bot, "скинь лекцию 3")
        assert len(bot.session.texts()) == 3 and all("Даю согласие" in t for t in bot.session.texts())
        await press(d, bot, "act:today")
        assert "согласие" in bot.session.named("AnswerCallbackQuery")[-1].text
        assert await _events(db.DATABASE_PATH, ME) == 0               # ни событий,
        assert (await db.get_user(ME) or {}).get("full_name", "") == ""   # ни имени

        await send(d, bot, "/privacy")                                # можно и до согласия
        assert "Политике" in bot.session.texts()[-1]

        await press(d, bot, "consent:pd")
        assert not await privacy.blocked(ME)
        assert "Привет, <b>X</b>" in bot.session.texts()[-1]          # дальше — обычный /start
        assert (await db.get_user(ME))["full_name"] == "X"
        n = len(bot.session.texts())
        await send(d, bot, "/help")
        assert len(bot.session.texts()) == n + 1 and "Даю согласие" not in bot.session.texts()[-1]
        assert await _events(db.DATABASE_PATH, ME) == 1
    finally:
        _release(d)


@pytest.mark.consent_real
@pytest.mark.asyncio
async def test_new_user_can_delete_and_log_in(db, bot):  # noqa: F811
    d = _gated_dp()
    try:
        await send(d, bot, "/start login_nope")                       # вход в приложение — можно
        assert "устарела" in bot.session.texts()[-1] or "Войти" in bot.session.texts()[-1]
        await send(d, bot, "/deleteme")
        assert "Удалить все твои данные" in bot.session.texts()[-1]
        await press(d, bot, "erase:yes")
        assert "удалено" in bot.session.named("EditMessageText")[-1].text
    finally:
        _release(d)


async def _legacy(db, uid):
    await db.upsert_user(uid, "me", "Я")
    async with aiosqlite.connect(db.DATABASE_PATH) as conn:
        await conn.execute("UPDATE users SET legacy=1 WHERE user_id=?", (uid,))
        await conn.commit()


@pytest.mark.consent_real
@pytest.mark.asyncio
async def test_old_users_never_blocked(db, monkeypatch):
    """Никита 11.10: кто уже пользуется — пусть пользуется, без срока."""
    import privacy
    await _legacy(db, ME)
    assert not await privacy.blocked(ME)                  # был до согласий — можно
    assert await privacy.blocked(OTHER)                   # новый — нельзя
    assert not await privacy.blocked(STAROSTA_ID)         # староста — оператор
    assert not hasattr(privacy, "GRACE_UNTIL")
    assert await privacy.ask_once(ME) and not await privacy.ask_once(ME)   # спросить — один раз
    monkeypatch.setattr(privacy, "VERSION", privacy.VERSION + "+")
    assert await privacy.ask_once(ME)                     # новый текст — ещё раз


@pytest.mark.consent_real
@pytest.mark.asyncio
async def test_old_user_sheet_once(db, monkeypatch):
    c, h = _client(monkeypatch)
    await _legacy(db, ME)
    me = c.get("/api/me", headers=h).json()
    assert me["consent_needed"] is True and me["consent_blocked"] is False
    assert c.get("/api/me", headers=h).json()["consent_needed"] is True    # /api/me не отмечает
    assert c.get("/api/notify", headers=h).status_code == 200               # и пользоваться можно
    assert c.post("/api/consent/asked", headers=h).json() == {"ok": True}
    assert c.get("/api/me", headers=h).json()["consent_needed"] is False    # лист показан — всё


@pytest.mark.consent_real
@pytest.mark.asyncio
async def test_blocked_get_no_broadcasts(db, bot):  # noqa: F811
    import delivery
    assert await delivery.deliver(bot, OTHER, "утро", kind="morning") is None
    assert bot.session.texts() == []


@pytest.mark.consent_real
@pytest.mark.asyncio
async def test_api_closed_until_consent(db, monkeypatch):
    c, h = _client(monkeypatch)
    me = c.get("/api/me", headers=h).json()
    assert me["consent_needed"] is True and me["consent_blocked"] is True
    r = c.get("/api/notify", headers=h)
    assert r.status_code == 403 and "согласие" in r.json()["detail"]
    assert c.get("/api/v1/notify", headers=h).status_code == 403
    assert (await db.get_user(ME))["full_name"] == ""            # имя — только после согласия
    assert await _events(db.DATABASE_PATH, ME) == 0
    assert c.post("/api/consent", json={"kind": "pd"}, headers=h).status_code == 200
    assert c.get("/api/me", headers=h).json()["consent_blocked"] is False
    assert c.get("/api/notify", headers=h).status_code == 200
    assert (await db.get_user(ME))["full_name"]


def test_legal_texts_after_review(monkeypatch):
    """Ревью 11.10: копии в Telegram (ОАЭ), цели, основание, поручение хостингу,
    фото вопроса, срок ответа; данные оператора — из переменных окружения."""
    c, _ = _client(monkeypatch)
    for name in ("consent", "privacy"):
        text = json.dumps(c.get("/api/legal/" + name).json(), ensure_ascii=False)
        assert "Telegram FZ-LLC (ОАЭ)" in text and "резервн" in text
        assert "Амвера" in text and "договор поручения Amvera от 14.07.2026" in text   # ревью 17.10
        assert "id от Apple" in text and "скрыт" in text and "только если" in text and "вход через Apple" in text   # #200
        assert "текст или фото" in text and "не дольше" not in text
    text = json.dumps(c.get("/api/legal/privacy").json(), ensure_ascii=False)
    assert '"Цели"' in text and "ст. 6 ч. 1 п. 1" in text and "п. 5" in text and "рабочих дней" in text


@pytest.mark.asyncio
async def test_status_warns_without_operator(db, monkeypatch):
    """Ревьюер 11.10: без ФИО и почты оператора тексты выкатывать нельзя — /status напоминает."""
    import health
    import privacy
    monkeypatch.setattr(privacy, "FIO", "")
    monkeypatch.setattr(privacy, "EMAIL", "")
    assert {"PD_FIO", "PD_EMAIL"} <= set(privacy.operator_missing())
    assert "PD_FIO" in await health.report()
    for k in ("FIO", "INN", "EMAIL", "CITY"):
        monkeypatch.setattr(privacy, k, "x")
    assert privacy.operator_missing() == [] and "данных оператора" not in await health.report()


@pytest.mark.consent_real
@pytest.mark.asyncio
async def test_new_version_does_not_block_who_consented(db, monkeypatch):
    """Переезд 16.10, новая версия текста: давший прошлую версию не
    блокируется — его один раз спрашивают, как старых своих; новый — как раньше."""
    import privacy
    await db.upsert_user(ME, "me", "Я")
    await db.upsert_user(OTHER, "other", "Он")
    await privacy.give(ME, "pd", "bot")
    monkeypatch.setattr(privacy, "VERSION", "99")
    privacy._given.clear()
    assert await privacy.needs(ME) and not await privacy.blocked(ME)
    assert await privacy.should_ask(ME) and await privacy.ask_once(ME) and not await privacy.ask_once(ME)
    assert await privacy.blocked(OTHER)


def test_legal_backup_where(monkeypatch):
    """Бэкап в российском S3 (BACKUP_S3_*) — в текстах хранилище вместо Telegram
    и срок, за который удалённое уходит из копий; не задан — Telegram, как было."""
    c, _ = _client(monkeypatch)
    text = json.dumps(c.get("/api/legal/privacy").json(), ensure_ascii=False)
    assert "Telegram FZ-LLC (ОАЭ) — хранение ночной резервной копии" in text
    for k in ("BACKUP_S3_BUCKET", "BACKUP_S3_KEY_ID", "BACKUP_S3_SECRET"):
        monkeypatch.setenv(k, "x")
    for name in ("consent", "privacy"):
        text = json.dumps(c.get("/api/legal/" + name).json(), ensure_ascii=False)
        assert "резервной копии базы у оператора" not in text and "Yandex Cloud (Россия)" in text
        assert "7 дней" in text and "год" not in text            # ст. 21 ч. 5: не дольше 30 дней


def test_legal_proxy_as_configured(monkeypatch):
    """Ревью 16.10: как уходят запросы за границу — как устроено на сервере:
    туннель Xray на сервер оператора (страна — PROXY_COUNTRY) или сеть хостинга."""
    c, _ = _client(monkeypatch)
    monkeypatch.delenv("XRAY_CONFIG", raising=False)
    text = json.dumps(c.get("/api/legal/privacy").json(), ensure_ascii=False)
    assert "через сеть хостинга Amvera" in text and "туннель" not in text
    monkeypatch.setenv("XRAY_CONFIG", "x")
    monkeypatch.setenv("PROXY_COUNTRY", "Нидерландах")
    text = json.dumps(c.get("/api/legal/privacy").json(), ensure_ascii=False)
    assert "туннель на сервер оператора в Нидерландах" in text and "не расшифровывается" in text


@pytest.mark.consent_real
@pytest.mark.asyncio
async def test_blocked_cached_and_batch(db, monkeypatch):
    """19.10, медленный диск Amvera: blocked открывал базу по 4 раза — 3 раза
    на запрос и на каждого человека в рейтинге (рейтинг 162 с). Теперь «можно»
    помнится до просьбы удалить, а рейтинг проверяет всех одним подключением."""
    import database._conn
    import database.privacy as dbp
    import privacy
    from database.privacy import give_consent
    NEW, OLD_V, GONE = 444, 555, 666
    await _legacy(db, ME)
    for uid in (OTHER, NEW, OLD_V, GONE):
        await db.upsert_user(uid, "", "x")
    await give_consent(NEW, "pd", privacy.VERSION, "bot")
    await give_consent(OLD_V, "pd", "old", "bot")
    await give_consent(GONE, "pd", "old", "bot")
    await privacy.request_erase(GONE)
    everyone = [ME, OTHER, NEW, OLD_V, GONE, STAROSTA_ID]
    one_by_one = {u for u in everyone if await privacy.blocked(u)}
    assert one_by_one == {OTHER, GONE}
    privacy._given.clear()
    privacy._open.clear()
    assert await privacy.blocked_ids(everyone) == one_by_one

    opened = []
    real = database._conn.connect
    monkeypatch.setattr(dbp, "connect", lambda: opened.append(1) or real())
    assert not await privacy.blocked(ME) and not await privacy.blocked(OLD_V)
    assert opened == []                                   # ответ «можно» — из памяти
    assert await privacy.blocked_ids(everyone) == {OTHER, GONE}
    assert len(opened) == 1                               # заблокированные — одним подключением
    monkeypatch.setattr(dbp, "connect", real)
    await privacy.request_erase(ME)                       # попросил удалить — память сбрасывается
    assert await privacy.blocked(ME)

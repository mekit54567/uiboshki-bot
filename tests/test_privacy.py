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
            "sdo_score_history", "push_subs"} <= set(tables)

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

    assert c.post("/api/me/delete", json={}, headers=h).status_code == 400   # без подтверждения — нет
    assert c.post("/api/me/delete", json={"confirm": True}, headers=h).json() == {"ok": True}
    assert await db.get_user(ME) is None and await get_consents(ME) == []


def test_legal_texts_and_pages(monkeypatch):
    import privacy
    c, _ = _client(monkeypatch)
    for name, title in (("consent", "Согласие на обработку персональных данных"),
                        ("privacy", "Политика обработки персональных данных")):
        d = c.get("/api/legal/" + name).json()
        assert d["title"] == title and d["version"] == privacy.VERSION and d["sections"]
        assert all(set(b) in ({"p"}, {"ul"}) for s in d["sections"] for b in s["blocks"])   # JSON без HTML
        assert "{" not in json.dumps(d, ensure_ascii=False).replace('{"', "").replace("{}", "")  # всё подставлено
        page = c.get("/" + name)
        assert page.status_code == 200 and title in page.text and privacy.DATE in page.text
    assert c.get("/api/legal/ads").status_code == 404
    text = json.dumps(c.get("/api/legal/privacy").json(), ensure_ascii=False)
    assert "Railway" in text and "США" in text            # правда о том, где сервер


@pytest.mark.asyncio
async def test_bot_deleteme(db, dp, bot):  # noqa: F811
    await db.upsert_user(ME, "", "x")
    await send(dp, bot, "/deleteme")
    assert "Удалить все твои данные" in bot.session.texts()[-1]
    await press(dp, bot, "erase:no")
    assert await db.get_user(ME)
    await press(dp, bot, "erase:yes")
    assert await db.get_user(ME) is None
    assert "всё о тебе удалено" in bot.session.named("EditMessageText")[-1].text


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
    """Ревью 11.10: копии в Telegram (ОАЭ), цели, основание, поручение Railway,
    фото вопроса, срок ответа; данные оператора — из переменных окружения."""
    c, _ = _client(monkeypatch)
    for name in ("consent", "privacy"):
        text = json.dumps(c.get("/api/legal/" + name).json(), ensure_ascii=False)
        assert "Telegram FZ-LLC (ОАЭ)" in text and "резервн" in text and "по поручению" in text
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

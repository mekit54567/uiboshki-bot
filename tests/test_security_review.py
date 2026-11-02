"""Ревью безопасности 09.10: границы групп (дедлайны, ДЗ, файлы), «делиться
СДО» своей группой, веб-пуши, размер сдачи в СДО."""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fastapi.testclient import TestClient

from kapibara.core import config
from tests.conftest import STAROSTA_ID
from tests.test_deadlines_routing import FakeSession

HOME = config.HOME_GROUP_ID
OTHER = 5001
HOME_USER, OTHER_ADMIN = 401, 402


@pytest.fixture
async def people(db):
    from database.groups import add_group_admin, upsert_group
    await upsert_group(OTHER, "УИБО-01-24")
    for uid, gid in ((HOME_USER, HOME), (OTHER_ADMIN, OTHER)):
        await db.upsert_user(uid, "", f"u{uid}")
        await db.set_user_group(uid, gid)
    await add_group_admin(OTHER, OTHER_ADMIN, STAROSTA_ID)                 # староста группы OTHER
    return db


def _client(monkeypatch, uid):
    import webapp.server as server
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data(user={"id": uid, "first_name": "U"})}


# ── 1. Общий дедлайн своей группы (group_id NULL) — не группа запроса ───────

@pytest.mark.asyncio
async def test_other_group_admin_cannot_touch_home_deadlines(people, monkeypatch):
    db = people
    shared = await db.add_deadline("Общий УИБО-03", "-", "2099-01-01", None, STAROSTA_ID)
    sdo = await db.add_deadline("СДО УИБО-03", "-", "2099-01-01", None, 0, external_id="e1")
    c, h = _client(monkeypatch, OTHER_ADMIN)
    body = {"subject": "взлом", "description": "", "due_date": "2099-01-02", "due_time": ""}
    for did in (shared, sdo):
        assert c.patch(f"/api/deadlines/{did}", headers=h, json=body).status_code == 404
        assert c.delete(f"/api/deadlines/{did}", headers=h).status_code == 404
        assert c.post(f"/api/deadlines/{did}/toggle", headers=h, json={"done": True}).status_code in (403, 404)
        d = await db.get_deadline(did)
        assert d and d["subject"] != "взлом"
    # вне запроса (рассылки) NULL — тоже своя группа
    from database.groups import current_group
    token = current_group.set(OTHER)
    try:
        assert await db.deadline_group(await db.get_deadline(shared)) == HOME
    finally:
        current_group.reset(token)


@pytest.mark.asyncio
async def test_other_group_admin_cannot_delete_home_homework(people):
    import handlers.announce as announce          # handlers.homework — вложенный роутер announce
    from kapibara.bot.middleware import GroupContextMiddleware
    db = people
    hid = await db.add_hw("Анализ", "задачи", "", "", STAROSTA_ID)            # ДЗ своей группы (NULL)
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(GroupContextMiddleware())
    dp.include_router(announce.router)
    user = User(id=OTHER_ADMIN, is_bot=False, first_name="Оля")
    try:
        cb = CallbackQuery(id="1", from_user=user, chat_instance="c", data=f"hwdel:{hid}",
                           message=Message(message_id=2, date=0, chat=Chat(id=OTHER_ADMIN, type="private"),
                                           from_user=user, text="ДЗ"))
        await dp.feed_update(bot, Update(update_id=int(time.time()), callback_query=cb))
    finally:
        announce.router._parent_router = None
    from database.homework import get_hw
    assert await get_hw(hid) is not None


# ── 2. Файлы и конспекты чужой группы по номеру — 404 ──────────────────────

@pytest.mark.asyncio
async def test_files_of_other_group_not_reachable_by_id(people, monkeypatch):
    from kapibara.features.lectures import summary as lecture_summary
    from kapibara.features.ai import semantic_index as si
    import webapp.deps as deps
    db = people
    mine = await db.add_file("Лекция 1", "Анализ", "tg1", "l1.pdf", STAROSTA_ID)
    theirs = await db.add_file("Их лекция", "Финансы", "tg2", "l2.pdf", OTHER_ADMIN, group_id=OTHER)
    for fid in (mine, theirs):
        await db.save_file_text(fid, "Дисконтирование и NPV " * 10)
        await si.index_file(fid, None, "l.pdf", "Дисконтирование и NPV " * 10)

    class FakeBot:
        async def get_file(self, tg_id):
            return type("F", (), {"file_path": "x/l.pdf"})()

    monkeypatch.setattr(deps, "tg_bot", lambda: FakeBot())
    made = []

    async def fake_make(*a, **k):
        made.append(a)
        return {"content": "конспект", "created_at": ""}

    monkeypatch.setattr(lecture_summary, "make", fake_make)
    c, h = _client(monkeypatch, HOME_USER)
    assert c.post(f"/api/files/{theirs}/link", headers=h).status_code == 404
    assert c.get(f"/api/files/{theirs}/page/1", headers=h).status_code == 404
    assert c.get(f"/api/summary/{theirs}", headers=h).status_code == 404
    assert c.post(f"/api/summary/{theirs}", headers=h).status_code == 404 and made == []
    assert c.patch(f"/api/files/{theirs}", headers=h,
                   json={"title": "x", "subject": "", "category": "lecture"}).status_code == 404
    # свои — как раньше
    assert c.post(f"/api/files/{mine}/link", headers=h).status_code == 200
    assert c.get(f"/api/files/{mine}/page/1", headers=h).status_code == 200
    assert c.get(f"/api/summary/{mine}", headers=h).status_code == 200
    # их староста свой файл видит, а файл своей группы, общий с ними, править не может
    c2, h2 = _client(monkeypatch, OTHER_ADMIN)
    assert c2.get(f"/api/summary/{theirs}", headers=h2).status_code == 200
    from database._conn import connect
    async with connect() as conn:
        await conn.execute("INSERT INTO file_groups (file_id, group_id) VALUES (?, ?)", (mine, OTHER))
        await conn.commit()
    assert c2.get(f"/api/summary/{mine}", headers=h2).status_code == 200
    assert c2.patch(f"/api/files/{mine}", headers=h2,
                    json={"title": "x", "subject": "", "category": "lecture"}).status_code == 403



# ── 3. «Делиться СДО» в своей группе — дубли всех дедлайнов ────────────────

@pytest.mark.asyncio
async def test_home_group_cannot_share_sdo(people, monkeypatch):
    from kapibara.features.groups import sync as group_sync
    c, h = _client(monkeypatch, HOME_USER)
    assert c.post("/api/sdo/share", headers=h, json={"share": True}).status_code == 400
    assert (await group_sync.sync_group(HOME)).get("error")


# ── 4. Веб-пуши: не больше 5 подписок на человека ──────────────────────────

@pytest.mark.asyncio
async def test_push_subs_capped(people):
    from database.push import MAX_SUBS, get_push_subs, save_push_sub
    for i in range(MAX_SUBS + 2):
        await save_push_sub(HOME_USER, f"https://fcm.googleapis.com/fcm/send/{i}", "k", "a")
    subs = sorted(s["endpoint"] for s in await get_push_subs(HOME_USER))
    assert len(subs) == MAX_SUBS and subs[0].endswith("/2")          # самые старые вытеснены



# ── 5. Сдача в СДО: число и размер — до раскодирования ─────────────────────

@pytest.mark.asyncio
async def test_submit_checks_size_before_decoding(people, monkeypatch):
    from kapibara.features.sdo import accounts as sdo_accounts
    from kapibara.features.sdo import submit as sdo_submit
    called = []

    async def cookie_for(uid):
        return "cookie"

    async def submit_file(*a, **k):
        called.append(a)
        return {"ok": True}

    monkeypatch.setattr(sdo_accounts, "cookie_for", cookie_for)
    monkeypatch.setattr(sdo_submit, "submit_file", submit_file)
    c, h = _client(monkeypatch, HOME_USER)
    four = [{"name": f"{i}.pdf", "data": "QUJD"} for i in range(sdo_submit.MAX_FILES + 1)]
    assert c.post("/api/sdo/submit", headers=h, json={"cmid": 7, "files": four}).status_code == 400
    big = [{"name": "big.pdf", "data": "A" * (sdo_submit.MAX_BYTES * 4 // 3 + 8)}]
    assert c.post("/api/sdo/submit", headers=h, json={"cmid": 7, "files": big}).status_code == 413
    assert called == []



# ── 6. «Выйти везде» — и пуши ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logout_everywhere_drops_push_subs(people, monkeypatch):
    from database.push import get_push_subs, save_push_sub
    from database.sessions import create_session
    await save_push_sub(HOME_USER, "https://fcm.googleapis.com/fcm/send/old", "k", "a")
    token = await create_session(HOME_USER, "Chrome · Android")
    c, _ = _client(monkeypatch, HOME_USER)
    r = c.post("/api/auth/logout?everywhere=true", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and await get_push_subs(HOME_USER) == []

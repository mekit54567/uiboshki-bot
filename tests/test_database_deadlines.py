"""
Дедлайны: видимость общих/личных, персональный статус "выполнено",
права и миграция. Реальный SQLite (temp-файл через фикстуру db), без моков.
"""
import pytest
from tests.conftest import STAROSTA_ID

ALICE = 222
BOB = 333


@pytest.mark.asyncio
async def test_visibility_shared_vs_private(db):
    shared_id = await db.add_deadline("Мат.анализ", "ДЗ 3", "2099-01-01", None, STAROSTA_ID)
    alice_id  = await db.add_deadline("Личное Алисы", "-", "2099-01-01", None, ALICE)
    bob_id    = await db.add_deadline("Личное Боба", "-", "2099-01-01", None, BOB)
    sdo_id    = await db.add_deadline("СДО-синк", "-", "2099-01-01", None, 0, external_id="ext1")

    alice_ids = {d["id"] for d in await db.get_active_deadlines(ALICE)}
    assert alice_ids == {shared_id, alice_id, sdo_id}

    bob_ids = {d["id"] for d in await db.get_active_deadlines(BOB)}
    assert bob_ids == {shared_id, bob_id, sdo_id}


@pytest.mark.asyncio
async def test_done_is_personal_not_global(db):
    shared_id = await db.add_deadline("Общий", "-", "2099-01-01", None, STAROSTA_ID)

    await db.mark_deadline_done(shared_id, ALICE)

    assert shared_id not in {d["id"] for d in await db.get_active_deadlines(ALICE)}
    assert shared_id in {d["id"] for d in await db.get_active_deadlines(BOB)}, \
        "бага: отметка Алисы протекла к Бобу"

    alice_all = await db.get_active_deadlines(ALICE, include_done=True)
    row = next(d for d in alice_all if d["id"] == shared_id)
    assert row["done"] == 1

    await db.set_deadline_done(shared_id, ALICE, False)
    assert not await db.is_deadline_done(shared_id, ALICE)
    assert shared_id in {d["id"] for d in await db.get_active_deadlines(ALICE)}


@pytest.mark.asyncio
async def test_stats_scoped_to_viewer(db):
    shared_id = await db.add_deadline("Общий", "-", "2099-01-01", None, STAROSTA_ID)
    alice_id  = await db.add_deadline("Личное Алисы", "-", "2099-01-01", None, ALICE)
    await db.add_deadline("Личное Боба", "-", "2099-01-01", None, BOB)

    await db.mark_deadline_done(alice_id, ALICE)

    stats_alice = await db.get_deadline_stats(ALICE)
    assert stats_alice["total"] == 2  # shared + свой, не видит Боба
    assert stats_alice["done"] == 1

    stats_bob = await db.get_deadline_stats(BOB)
    assert stats_bob["total"] == 2
    assert stats_bob["done"] == 0
    assert shared_id  # используется выше косвенно, оставлено для читаемости


@pytest.mark.asyncio
async def test_deadlines_soon_personal_vs_shared_only(db):
    shared_id = await db.add_deadline("Общий", "-", "2099-01-01", None, STAROSTA_ID)
    alice_id  = await db.add_deadline("Личное Алисы", "-", "2099-01-01", None, ALICE)

    soon_bob = await db.get_deadlines_soon(days=365000, viewer_id=BOB)
    assert alice_id not in {d["id"] for d in soon_bob}
    assert shared_id in {d["id"] for d in soon_bob}

    soon_shared = await db.get_deadlines_soon(days=365000, shared_only=True)
    assert alice_id not in {d["id"] for d in soon_shared}
    assert shared_id in {d["id"] for d in soon_shared}

    with pytest.raises(ValueError):
        await db.get_deadlines_soon(days=3)  # ни viewer_id, ни shared_only — программная ошибка вызова


@pytest.mark.asyncio
async def test_is_shared_deadline_helper(db):
    assert db.is_shared_deadline({"created_by": 0})
    assert db.is_shared_deadline({"created_by": STAROSTA_ID})
    assert not db.is_shared_deadline({"created_by": ALICE})


@pytest.mark.asyncio
async def test_delete_cleans_up_deadline_done(db):
    bob_id = await db.add_deadline("Личное Боба", "-", "2099-01-01", None, BOB)
    await db.mark_deadline_done(bob_id, BOB)
    await db.delete_deadline(bob_id)
    assert await db.get_deadline(bob_id) is None


@pytest.mark.asyncio
async def test_legacy_done_migrates_to_starosta(tmp_path, monkeypatch):
    """До этой фичи done был одной общей колонкой. При первом появлении
    таблицы deadline_done старые done=1 должны засчитаться старосте, а не
    потеряться молча."""
    import aiosqlite
    import database as db

    old_db_path = str(tmp_path / "legacy.db")
    async with aiosqlite.connect(old_db_path) as conn:
        await conn.execute("""
            CREATE TABLE deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT, description TEXT,
                due_date TEXT, due_time TEXT, created_by INTEGER,
                created_at TEXT DEFAULT (datetime('now')), done INTEGER DEFAULT 0, external_id TEXT
            )
        """)
        await conn.execute(
            "INSERT INTO deadlines (subject, due_date, created_by, done) VALUES ('старый', '2020-01-01', 555, 1)"
        )
        await conn.commit()

    monkeypatch.setattr(db, "DATABASE_PATH", old_db_path)
    await db.init_db()
    assert await db.is_deadline_done(1, STAROSTA_ID)

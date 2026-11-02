"""Новые задания из СДО — каждому, у кого включено (new_tasks.py)."""
import pytest

from kapibara.features.notifications import new_tasks


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


def test_build_text():
    text = new_tasks.build([{"subject": "Практика 3 · Анализ данных", "due_date": "2026-10-08", "due_time": "23:59"},
                            {"subject": "Тест <2>", "due_date": "2026-10-07", "due_time": None}])
    assert text.startswith("🆕 В СДО новые задания:")
    assert text.index("Тест &lt;2&gt;") < text.index("Практика 3")                     # по сроку
    assert "чт, 8 октября до 23:59" in text and "ср, 7 октября" in text


@pytest.mark.asyncio
async def test_announce_respects_prefs_done_and_mass(db):
    for uid in (1, 2, 3):
        await db.upsert_user(uid, "", "")
    await db.set_notify(2, {"new_tasks": False})                                     # выключил
    await db.upsert_user(4, "", "")
    await db.set_subscription(4, 0)                                                  # отписан от всего
    d1 = await db.add_deadline("Практика 3 · Анализ данных", "", "2026-10-08", "23:59", 0, external_id="sdo:1")
    d2 = await db.add_deadline("Тест 2 · Учётная деятельность", "", "2026-10-09", None, 0, external_id="sdo:2")
    await db.mark_deadline_done(d2, 3)                                               # уже сдал
    bot = FakeBot()
    assert await new_tasks.announce(bot, [d1, d2]) == 2
    got = dict(bot.sent)
    assert set(got) == {1, 3}
    assert "Практика 3" in got[3] and "Тест 2" not in got[3]
    assert "Практика 3" in got[1] and "Тест 2" in got[1]
    bot = FakeBot()
    assert await new_tasks.announce(bot, list(range(1, new_tasks.MASS + 2))) == 0 and not bot.sent   # выгрузка всего
    assert await new_tasks.announce(bot, []) == 0


@pytest.mark.asyncio
async def test_moved_deadline_announced(db):
    """Преподаватель продлил срок — тем, кто не сдал: «Срок перенесли … теперь … (было …)»."""
    await db.upsert_user(1, "", "")
    await db.upsert_user(2, "", "")
    d = await db.add_deadline("Практика 2 · Анализ данных", "", "2026-10-09", "23:59", 0, external_id="sdo:7")
    await db.mark_deadline_done(d, 2)
    bot = FakeBot()
    assert await new_tasks.announce(bot, [], {d: "2026-10-08"}) == 1
    (uid, text), = bot.sent
    assert uid == 1 and text.startswith("📅 Срок перенесли:")
    assert "теперь пт, 9 октября до 23:59 (было 8 октября)" in text
    both = new_tasks.build([{"subject": "Тест", "due_date": "2026-10-10", "due_time": None}],
                           [{"subject": "Практика", "due_date": "2026-10-09", "due_time": None, "was": "2026-10-09"}])
    assert both.index("🆕") < both.index("📅") and "(было" not in both     # сдвинули только время — без «было»


@pytest.mark.asyncio
async def test_optional_subject_skipped_unless_attends(db, monkeypatch):
    """Задание по предмету по выбору — только тем, кто ответил «хожу»."""
    from kapibara.core import config
    monkeypatch.setattr(config, "OPTIONAL_SUBJECTS", ["Военная кафедра"])
    await db.upsert_user(1, "", "")
    await db.upsert_user(2, "", "")
    await db.set_optional_answer(2, "Военная кафедра", True)
    d = await db.add_deadline("Тест 1 · Военная кафедра", "", "2026-10-09", None, 0, external_id="sdo:v")
    bot = FakeBot()
    assert await new_tasks.announce(bot, [d]) == 1 and bot.sent[0][0] == 2


@pytest.mark.asyncio
async def test_scheduler_sync_announces(monkeypatch):
    """Синк СДО по расписанию передаёт рассылке новые id и перенесённые сроки."""
    from kapibara.ops import health
    from kapibara.features.notifications import new_tasks as nt
    from kapibara.jobs import scheduler
    from kapibara.features.sdo import parser as sdo_parser
    got = []

    async def sync():
        return {"added": 1, "updated": 1, "skipped": 0, "new_ids": [7], "moved": {8: "2026-10-08"}, "expired": False}

    async def announce(bot, ids, moved=None):
        got.append((ids, moved))
        return 1

    async def note(*a, **kw):
        pass

    monkeypatch.setattr(sdo_parser, "sync_deadlines", sync)
    monkeypatch.setattr(nt, "announce", announce)
    monkeypatch.setattr(health, "note", note)
    monkeypatch.setattr(scheduler, "STAROSTA_ID", 0)
    await scheduler.sync_sdo_deadlines(FakeBot())
    assert got == [([7], {8: "2026-10-08"})]

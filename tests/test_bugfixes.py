"""
Регрессионные тесты на пачку реальных багов, найденных при ревью всего
бота (см. описание PR): неэкранированный HTML, "сегодня" по UTC вместо МСК,
команды без проверки прав, дедуп напоминаний без даты, СДО-синк, который не
замечал перенос срока, год по умолчанию у дат без года.
"""
import time
from datetime import date

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, Chat, User, Update

import handlers.announce as announce
from tests.conftest import STAROSTA_ID
from tests.test_deadlines_routing import FakeSession
from utils import esc, parse_day_month, split_by_lines, utc_to_msk_date

USER = User(id=222, is_bot=False, first_name="Alice")
STAROSTA = User(id=STAROSTA_ID, is_bot=False, first_name="Starosta")


# ── utils ────────────────────────────────────────────────────────────────────

def test_esc():
    assert esc("x < 5 & y > 2") == "x &lt; 5 &amp; y &gt; 2"
    assert esc(None) == ""
    assert esc('кавычки "как есть"') == 'кавычки "как есть"'


@pytest.mark.parametrize("raw,today,expected", [
    ("15.01", date(2026, 12, 20), date(2027, 1, 15)),       # декабрь → январь следующего года
    ("25.09", date(2026, 9, 26), date(2026, 9, 25)),        # вчера — остаётся просроченным
    ("30.05", date(2026, 9, 26), date(2026, 5, 30)),        # недавнее прошлое — текущий год
    ("1.3", date(2026, 9, 26), date(2027, 3, 1)),           # больше полугода назад → вперёд
    ("15.01.2026", date(2026, 12, 20), date(2026, 1, 15)),  # явный год не трогаем
    ("29.02", date(2027, 12, 1), date(2028, 2, 29)),        # до високосного — следующий год
    ("29.02", date(2028, 3, 1), date(2028, 2, 29)),         # вчерашнее 29.02 остаётся
    ("29.02", date(2026, 9, 26), None),                     # ни в этом, ни в следующем году
    ("31.02", date(2026, 9, 26), None),
    ("30-05", date(2026, 9, 26), None),
    ("", date(2026, 9, 26), None),
])
def test_parse_day_month(raw, today, expected):
    assert parse_day_month(raw, today) == expected


def test_utc_to_msk_date():
    assert utc_to_msk_date("2026-09-25 22:30:00") == "2026-09-26"  # 01:30 МСК
    assert utc_to_msk_date("2026-09-25 12:00:00") == "2026-09-25"
    assert utc_to_msk_date("мусор") == "мусор"


def test_split_by_lines_never_cuts_inside_a_line():
    line = "┌ <b>Пара 1</b>  ⏰ 09:00–10:30 │ 📖 R&amp;D"
    text = "\n".join([line] * 300)
    chunks = split_by_lines(text, limit=1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    assert all(l == line for c in chunks for l in c.split("\n"))
    assert "\n".join(chunks) == text


# ── Экранирование HTML в форматтерах ────────────────────────────────────────

def test_format_deadlines_escapes_user_text():
    from handlers.deadlines import format_deadlines
    text = format_deadlines([{
        "id": 1, "subject": "C++ <templates>", "description": "R&D, x < 5",
        "due_date": "2099-01-01", "due_time": None,
    }])
    assert "C++ &lt;templates&gt;" in text
    assert "R&amp;D, x &lt; 5" in text
    assert "<templates>" not in text


def test_deadline_reminders_escape_user_text():
    from scheduler import _format_deadline_reminders
    text = _format_deadline_reminders([{
        "subject": "<b>", "description": "a & b", "due_date": "2099-01-01", "due_time": None,
    }])
    assert "&lt;b&gt;" in text and "a &amp; b" in text


def test_no_triple_newlines_under_headers():
    # Живой тест в Telegram: под "📅 Суббота, 26.09.2026" стояли три пустые
    # строки (header + "" склеивались через "\n\n"), под заголовком
    # /deadlines и утренней рассылки — две.
    from datetime import date
    from handlers.deadlines import format_deadlines
    from schedule_parser import format_day
    from scheduler import _format_deadline_reminders

    day = format_day([{"time": "09:00–10:30", "summary": "ЛК Матан", "location": "А-18"}], date(2026, 9, 26))
    assert day.startswith("📅 <b>Суббота, 26 сентября</b>\n1 пара · 09:00–10:30\n\n1️⃣ <b>09:00–10:30</b>")
    d = {"id": 1, "subject": "Лаба", "description": "", "due_date": "2099-01-01", "due_time": None}
    for text in (day, format_deadlines([d]), _format_deadline_reminders([d])):
        assert "\n\n\n" not in text


@pytest.mark.asyncio
async def test_notes_block_escapes_notes(db):
    # _notes_block уходит и в бот (parse_mode=HTML), и в WebApp через
    # innerHTML — неэкранированная заметка там была XSS.
    from handlers.schedule import _notes_block
    await db.add_lesson_note("2099-01-01", "Матан", "<img src=x onerror=alert(1)>", USER.id)
    block = await _notes_block("2099-01-01")
    assert "<img" not in block
    assert "&lt;img src=x onerror=alert(1)&gt;" in block


def test_schedule_diff_escapes_summary():
    from schedule_diff import diff_events
    changes = diff_events([], [{"summary": "R&D <лаб>", "time": "09:00–10:30", "location": "А-1"}])
    assert changes and "R&amp;D &lt;лаб&gt;" in changes[0]


# ── "Сегодня" по Москве в SQL ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deadline_queries_use_moscow_today(db, monkeypatch):
    monkeypatch.setattr(db, "today_msk", lambda: date(2099, 1, 10))
    yesterday = await db.add_deadline("Вчера", "", "2099-01-09", None, USER.id)
    today = await db.add_deadline("Сегодня", "", "2099-01-10", None, USER.id)
    in_3_days = await db.add_deadline("Через 3 дня", "", "2099-01-13", None, USER.id)
    later = await db.add_deadline("Позже", "", "2099-01-14", None, USER.id)

    soon = {d["id"] for d in await db.get_deadlines_soon(days=3, viewer_id=USER.id)}
    assert soon == {today, in_3_days}
    assert yesterday not in soon and later not in soon

    stats = await db.get_deadline_stats(USER.id)
    assert stats["overdue"] == 1
    assert stats["active"] == 3


# ── Напоминания о парах: дедуп по дате ───────────────────────────────────────

@pytest.mark.asyncio
async def test_lesson_reminder_dedupe_resets_next_day(monkeypatch):
    """Раньше ключ дедупа был без даты и чистился только ровно в 00:00 —
    пропущенный полуночный запуск навсегда глушил напоминание о паре в то же
    время на следующий день."""
    from datetime import datetime, timedelta
    import scheduler

    fake_now = {"value": datetime(2099, 1, 10, 8, 45, tzinfo=scheduler.TZ)}

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now["value"]

    def fake_events(raw, day):
        start = datetime(day.year, day.month, day.day, 9, 0, tzinfo=scheduler.TZ)
        return [{"summary": "Матан", "location": "А-1", "time": "09:00–10:30",
                 "time_start": start, "time_end": start + timedelta(minutes=90)}]

    async def fake_raw():
        return b""

    async def fake_users():
        return [USER.id]

    async def fake_get_user(uid):
        return {"user_id": uid, "reminder_minutes": 15}

    sent = []

    class FakeBot:
        async def send_message(self, uid, text, **kwargs):
            sent.append((uid, text))

    monkeypatch.setattr(scheduler, "datetime", FakeDatetime)
    monkeypatch.setattr(scheduler, "fetch_schedule_raw", fake_raw)
    monkeypatch.setattr(scheduler, "parse_events_for_date", fake_events)
    monkeypatch.setattr(scheduler, "get_all_subscribed_users", fake_users)
    monkeypatch.setattr(scheduler, "get_user", fake_get_user)
    monkeypatch.setattr(scheduler, "_sent_reminders", set())

    await scheduler.check_lesson_reminders(FakeBot())
    await scheduler.check_lesson_reminders(FakeBot())  # та же минута — без дубля
    assert len(sent) == 1

    # Следующий день, запуска в 00:00 не было вообще.
    fake_now["value"] = datetime(2099, 1, 11, 8, 45, tzinfo=scheduler.TZ)
    await scheduler.check_lesson_reminders(FakeBot())
    assert len(sent) == 2


# ── СДО: перенос срока ───────────────────────────────────────────────────────

def _sdo_html(unix_ts: int) -> str:
    return f"""
    <div data-type="event" data-event-component="mod_assign" data-event-eventtype="due"
         data-event-id="42" data-event-title="Практика 1">
      <a href="https://sdo/calendar/view.php?view=day&amp;time={unix_ts}">Когда</a>
      <a href="https://sdo/course/view.php?id=7">Анализ данных</a>
      <a class="card-link" href="https://sdo/mod/assign/view.php?id=9">Перейти</a>
    </div>
    """


@pytest.mark.asyncio
async def test_sdo_sync_updates_moved_deadline(db, monkeypatch):
    import sdo_parser

    html = {"value": _sdo_html(4102444800)}  # 2100-01-01 03:00 МСК

    async def fake_fetch():
        return html["value"]

    monkeypatch.setattr(sdo_parser, "fetch_upcoming_html", fake_fetch)

    first = await sdo_parser.sync_deadlines()
    assert (first["added"], first["updated"]) == (1, 0)

    again = await sdo_parser.sync_deadlines()
    assert (again["added"], again["updated"], again["skipped"]) == (0, 0, 1)

    html["value"] = _sdo_html(4102444800 + 86400)  # препод продлил на сутки
    moved = await sdo_parser.sync_deadlines()
    assert (moved["added"], moved["updated"]) == (0, 1)

    d = await db.get_deadline_by_external_id("sdo:42")
    assert d["due_date"] == "2100-01-02"


# ── Хендлеры через настоящий Dispatcher ──────────────────────────────────────

@pytest.fixture
def bot():
    return Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=FakeSession())


@pytest.fixture
def make_dp():
    """Роутеры — модульные синглтоны (один на всё приложение), поэтому
    после теста отвязываем их, как в test_deadlines_routing.py."""
    attached = []

    def _make(*routers):
        d = Dispatcher(storage=MemoryStorage())
        for r in routers:
            d.include_router(r)
            attached.append(r)
        return d

    yield _make
    for r in attached:
        r._parent_router = None


@pytest.fixture
def hw_db(db, monkeypatch):
    # handlers/announce.py держит свой DATABASE_PATH (импорт из config).
    monkeypatch.setattr(announce, "DATABASE_PATH", db.DATABASE_PATH)
    return db


async def _feed(dp, bot, text, user=USER):
    msg = Message(message_id=int(time.time() * 1000) % 1000000, date=0,
                  chat=Chat(id=user.id, type="private"), from_user=user, text=text)
    await dp.feed_update(bot, Update(update_id=int(time.time() * 1000000) % 10**9, message=msg))


@pytest.mark.asyncio
async def test_delfile_requires_uploader_or_starosta(hw_db, make_dp, bot):
    from handlers.files import router as files_router
    dp = make_dp(files_router)
    sess = bot.session

    foreign = await hw_db.add_file("Лекция 1", "Матан", "tg-file-1", "l1.pdf", 999)
    await _feed(dp, bot, f"/delfile {foreign}")
    assert any("только тот, кто его загрузил" in t for _, t in sess.sent_texts)
    assert any(f["id"] == foreign for f in await hw_db.get_files())

    own = await hw_db.add_file("Мой конспект", "Матан", "tg-file-2", "c.pdf", USER.id)
    await _feed(dp, bot, f"/delfile {own}")
    assert not any(f["id"] == own for f in await hw_db.get_files())

    await _feed(dp, bot, f"/delfile {foreign}", user=STAROSTA)
    assert not any(f["id"] == foreign for f in await hw_db.get_files())


@pytest.mark.asyncio
async def test_closevote_requires_author_or_starosta(db, make_dp, bot):
    from handlers.social import router as social_router
    dp = make_dp(social_router)
    sess = bot.session

    vote_id = await db.create_vote("Идём в пятницу?", 999)
    await _feed(dp, bot, "/closevote")
    assert any("только его автор или староста" in t for _, t in sess.sent_texts)
    assert (await db.get_active_vote())["id"] == vote_id

    await _feed(dp, bot, "/closevote", user=STAROSTA)
    assert await db.get_active_vote() is None


@pytest.mark.asyncio
async def test_setzam_rejects_non_numeric_and_is_editor_survives_bad_value(hw_db, make_dp, bot):
    dp = make_dp(announce.router)
    sess = bot.session

    await _feed(dp, bot, "/setzam @someone", user=STAROSTA)
    assert any("числовой Telegram ID" in t for _, t in sess.sent_texts)
    assert await announce.get_setting("zam_id") is None

    # Значение, записанное до появления проверки, больше не роняет is_editor.
    await announce.set_setting("zam_id", "@someone")
    assert await announce.is_editor(USER.id) is False
    assert await announce.is_editor(STAROSTA_ID) is True


@pytest.mark.asyncio
async def test_is_editor_on_fresh_db_without_settings_table(hw_db):
    # Первый /addhw на свежей базе (до любого /hw) раньше падал "no such table".
    assert await announce.is_editor(USER.id) is False


@pytest.mark.asyncio
async def test_rating_shows_anon_instead_of_at_none_and_escapes(hw_db, make_dp, bot):
    dp = make_dp(announce.router)
    sess = bot.session

    await hw_db.get_or_create_calendar_token(501)  # юзер без имени и username
    await hw_db.upsert_user(502, "", "<script>Bob")
    await hw_db.add_solver_history(501, "задача", "ответ")
    await hw_db.add_solver_history(502, "задача", "ответ")

    await _feed(dp, bot, "/rating")
    text = next(t for _, t in sess.sent_texts if "Рейтинг" in t)
    assert "@None" not in text and "Аноним" in text
    assert "&lt;script&gt;Bob" in text


@pytest.mark.asyncio
async def test_history_escapes_task_text(db, make_dp, bot):
    from handlers.solver import router as solver_router
    dp = make_dp(solver_router)
    sess = bot.session

    await db.add_solver_history(USER.id, "Докажи, что x < 5 & y > 2", "ответ", "Матан")
    await _feed(dp, bot, "/history")
    text = next(t for _, t in sess.sent_texts if "Последние" in t)
    assert "x &lt; 5 &amp; y &gt; 2" in text


@pytest.mark.asyncio
async def test_feed_post_published_but_reactions_failed_is_not_marked_deleted(db, monkeypatch):
    """Пост уже ушёл в группу, упало только навешивание кнопок — это не
    "не смог опубликовать": иначе автор без кулдауна постит дубль."""
    import handlers.feed as feed
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey

    monkeypatch.setattr(feed, "GROUP_CHAT_ID", -100)

    class FakeBot:
        async def send_message(self, chat_id, text, **kwargs):
            class Sent:
                message_id = 777
            return Sent()

        async def edit_message_reply_markup(self, *args, **kwargs):
            raise RuntimeError("Too Many Requests: retry after 5")

    answers = []

    class FakeMessage:
        text = "Кто-нибудь видел мои наушники?"
        caption = None
        photo = None
        from_user = USER

        async def answer(self, text, **kwargs):
            answers.append(text)

    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=USER.id, user_id=USER.id))
    await feed.publish_feed_post(FakeMessage(), state, FakeBot())

    assert any("Опубликовано" in a for a in answers)
    post = await db.get_feed_post(1)
    assert post["deleted"] == 0 and post["message_id"] == 777


@pytest.mark.asyncio
async def test_sdo_sync_tells_missing_cookie_from_expired(db, monkeypatch):
    # Живой тест: /syncsdo отвечал «кука протухла», хотя её просто не задали —
    # а «протухла» значит, что СДО с сервера открылся и попросил вход.
    import sdo_parser
    monkeypatch.setattr(sdo_parser, "SDO_SESSION_COOKIE", "")
    res = await sdo_parser.sync_deadlines()
    assert res["expired"] and res["missing"]

    async def login_page():
        raise sdo_parser.SdoSessionExpired("редирект на /login/index.php")

    monkeypatch.setattr(sdo_parser, "SDO_SESSION_COOKIE", "abc")
    monkeypatch.setattr(sdo_parser, "fetch_upcoming_html", login_page)
    res = await sdo_parser.sync_deadlines()
    assert res["expired"] and not res["missing"]

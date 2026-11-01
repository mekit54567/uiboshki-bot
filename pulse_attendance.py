"""
Посещения лекций из Пульса МИРЭА (01.11, Никита): если человек подключил
Пульс (pulse_accounts), отметки по лекциям берём оттуда, а не угадываем по
баллам СДО. Только лекции — за практики баллов не дают. Только свои отметки:
GetAttendanceForLesson отдаёт всю группу, его не зовём.

Каждую отметку храним у себя (pulse_attendance): Пульс отвалился — прошлые
лекции остаются такими, как сказал Пульс, а по СДО считаются только те, о
которых Пульс ещё ничего не сказал (attendance.for_course).

Схема (разведка с телефона, архив 01.11):
  LessonService/GetDailyLessonsCountForSemesterOfAvailableVisitingLogs
    запрос 2{1: от, unix}, 3{1: до} → 1{2{год, месяц, день}, 4{1: id пары,
    2{2: «ЛК|ПР|СР|ДОП»}, 3{1: номер пары}}}
  AttendanceService/GetAttendanceInLessonForStudent
    запрос 1: id пары → 1.2.1 «id|n|Present» (или Absent…),
    4{3{2: предмет}, 4{2: тип}, 5{1: начало, unix}}
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

import aiosqlite
import httpx

import pulse_accounts
import pulse_probe
from database._conn import connect

logger = logging.getLogger(__name__)

DAILY = "rtu_tc.attendance.api.LessonService/GetDailyLessonsCountForSemesterOfAvailableVisitingLogs"
IN_LESSON = "rtu_tc.attendance.api.AttendanceService/GetAttendanceInLessonForStudent"
LECTURE = "ЛК"
FINAL_DAYS = 14           # отметку могут поставить позже — до двух недель переспрашиваем
SYNC_HOURS = 3            # не чаще (поддержание входа зовёт sync_due)
BACK_DAYS = 160           # семестр целиком
PAUSE = 0.15              # между запросами — не долбить Пульс
MSK = timezone(timedelta(hours=3))

STATUS = {"present": "ok", "absent": "miss", "excused": "excused",
          "excusedabsence": "excused", "absentwithreason": "excused", "valid": "excused"}


class PulseExpired(Exception):
    """Пульс не принял вход."""


# --- protobuf ------------------------------------------------------------------

def _vint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(num: int, val) -> bytes:
    if isinstance(val, int):
        return _vint(num << 3) + _vint(val)
    raw = val.encode() if isinstance(val, str) else val
    return _vint(num << 3 | 2) + _vint(len(raw)) + raw


def daily_request(start: datetime, end: datetime) -> bytes:
    return _field(2, _field(1, int(start.timestamp()))) + _field(3, _field(1, int(end.timestamp())))


def lesson_request(lesson_id: str) -> bytes:
    return _field(1, lesson_id)


def _get(fields, *path):
    """Первое значение по пути номеров полей."""
    cur = fields
    for num in path:
        if not isinstance(cur, list):
            return None
        cur = next((v for f, v in cur if f == num), None)
    return cur


def _all(fields, num):
    return [v for f, v in fields if f == num] if isinstance(fields, list) else []


def parse_daily(msgs: list[list]) -> list[dict]:
    """Ответ «пары по дням» → [{id, day, kind}]."""
    out = []
    for m in msgs:
        for day in _all(m, 1):
            y, mo, d = (_get(day, 2, i) for i in (1, 2, 3))
            if not all(isinstance(x, int) for x in (y, mo, d)):
                continue
            for les in _all(day, 4):
                lid = _get(les, 1)
                if isinstance(lid, str):
                    out.append({"id": lid, "day": date(y, mo, d).isoformat(), "kind": _get(les, 2, 2) or ""})
    return out


def parse_status(raw) -> str | None:
    """«uuid|123|Present» → ok/miss/excused; неизвестное — None (не трогаем)."""
    if not isinstance(raw, str) or "|" not in raw:
        return None
    word = raw.rsplit("|", 1)[1].strip().lower().replace("_", "")
    return STATUS.get(word)


def parse_in_lesson(msgs: list[list]) -> dict | None:
    """Своя отметка на паре: статус, предмет, тип, день (МСК)."""
    for m in msgs:
        raw = _get(m, 1, 2, 1)
        lesson = _get(m, 4)
        if raw is None or not isinstance(lesson, list):
            continue
        start = _get(lesson, 5, 1)
        day = datetime.fromtimestamp(start, MSK).date().isoformat() if isinstance(start, int) else None
        return {"status": parse_status(raw), "raw": str(raw).rsplit("|", 1)[-1][:32],
                "subject": _get(lesson, 3, 2) or "", "kind": _get(lesson, 4, 2) or "", "day": day}
    return None


# --- запросы -------------------------------------------------------------------

async def _call(client: httpx.AsyncClient, method: str, cookie: str, message: bytes) -> list[list]:
    headers = pulse_probe._headers(cookie, pulse_accounts.APP_VERSION)
    resp = await client.post(f"{pulse_probe.PULSE}/{method}", content=pulse_probe.frame(message), headers=headers)
    if resp.status_code == 401:
        raise PulseExpired()
    resp.raise_for_status()
    msgs, trailer = pulse_probe.unframe(resp.content)
    status = trailer.get("grpc-status", resp.headers.get("grpc-status", "0"))
    if status == "16":
        raise PulseExpired()
    if status != "0":
        raise RuntimeError(f"grpc {status} {trailer.get('grpc-message', '')}")
    return [pulse_probe.decode(m) for m in msgs]


# --- база ----------------------------------------------------------------------

async def stored(user_id: int) -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM pulse_attendance WHERE user_id=? ORDER BY day", (user_id,))
        return [dict(r) for r in await cur.fetchall()]


async def _save(user_id: int, lesson_id: str, info: dict, now: datetime):
    async with connect() as db:
        await db.execute(
            "INSERT INTO pulse_attendance (user_id, lesson_id, day, subject, kind, status, raw, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id, lesson_id) DO UPDATE SET day=excluded.day, "
            "subject=excluded.subject, kind=excluded.kind, status=excluded.status, raw=excluded.raw, "
            "checked_at=excluded.checked_at",
            (user_id, lesson_id, info["day"], info["subject"], info["kind"], info["status"], info["raw"],
             now.strftime("%Y-%m-%d %H:%M:%S")))
        await db.commit()


def lecture_marks(rows: list[dict], subject: str, match) -> dict[str, str]:
    """{день: ok|miss|excused} по лекциям предмета; match(имя Пульса) → предмет расписания."""
    out = {}
    for r in rows:
        if r.get("kind") == LECTURE and r.get("status") and match(r.get("subject") or "") == subject:
            out[r["day"]] = r["status"]
    return out


# --- синк ----------------------------------------------------------------------

async def sync(user_id: int, cookie: str | None = None, now: datetime | None = None,
               transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Забрать свои отметки по лекциям. Уже окончательные (лекция старше
    FINAL_DAYS и отметка есть) не переспрашиваем."""
    now = now or datetime.now(MSK)
    cookie = cookie or await pulse_accounts.cookie_for(user_id)
    if not cookie:
        return {"state": "off"}
    known = {r["lesson_id"]: r for r in await stored(user_id)}
    today = now.astimezone(MSK).date()
    done, asked = 0, 0
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": pulse_accounts.UA}, transport=transport) as client:
        try:
            days = parse_daily(await _call(client, DAILY, cookie,
                                           daily_request(now - timedelta(days=BACK_DAYS), now + timedelta(days=1))))
            for les in days:
                if les["kind"] != LECTURE or les["day"] > today.isoformat():
                    continue
                old = known.get(les["id"])
                if old and old["status"] and (today - date.fromisoformat(les["day"])).days > FINAL_DAYS:
                    continue
                await asyncio.sleep(PAUSE)
                asked += 1
                info = parse_in_lesson(await _call(client, IN_LESSON, cookie, lesson_request(les["id"])))
                if info and info["day"]:
                    await _save(user_id, les["id"], info, now)
                    done += 1
        except PulseExpired:
            return {"state": "expired", "saved": done}
    from database import set_setting
    await set_setting(f"pulse_sync:{user_id}", now.isoformat())
    return {"state": "ok", "asked": asked, "saved": done}


async def sync_due(user_id: int, now: datetime | None = None) -> dict | None:
    """Из поддержания входа: не чаще раза в SYNC_HOURS."""
    from database import get_setting
    now = now or datetime.now(MSK)
    last = await get_setting(f"pulse_sync:{user_id}")
    if last and now - datetime.fromisoformat(last) < timedelta(hours=SYNC_HOURS):
        return None
    try:
        return await sync(user_id, now=now)
    except Exception as e:          # сеть, DDoS-Guard — попробуем при следующей проверке
        logger.info(f"Пульс посещения {user_id}: {type(e).__name__}")
        return None

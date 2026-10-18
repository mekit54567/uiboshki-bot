"""Опыт и рейтинг групп (5.100.3, Никита 18.10).

Опыт — только за то, что сервер может проверить сам, а не за нажатия:
  • баллы БРС в СДО — 1 опыт за балл (сумма по предметам за семестр, в ней и
    посещения);
  • сданная работа, которую подтвердило СДО (sdo_done, via='sdo'), — SUBMIT;
  • сдал за сутки до срока и раньше — ещё EARLY;
  • ачивка приложения (таблица achievements, 5.91) — по её рангу, ACH_RANK
    (Никита 18.10: «в зависимости от ранга»); создателю (STAROSTA_ID) ачивки
    открыты все сразу — в опыт они не идут;
  • файл, который человек сам выложил группе (не из СДО), — FILE, не больше
    FILE_CAP файлов.
Галочка «сделал» от руки опыта не даёт: её можно поставить не сдав.

Рейтинг — прежде всего групп: опыт группы = сумма опыта её людей, место в
своём институте (institutes.py, по шифру) и во всём университете. В рейтинг
попадает группа, где опыт есть хотя бы у MIN_PEOPLE человек: иначе «опыт
группы» — это опыт одного человека. Люди внутри группы видны только своей
группе и только с согласия (rating_profiles.show, по умолчанию нет), под ником.
Кому обрабатывать данные нельзя (privacy.blocked: нет согласия, ждёт удаления),
в рейтинге нет совсем.
"""

import time

from database._conn import connect

SUBMIT, EARLY, ACH, FILE = 15, 10, 5, 2
# Опыт за ачивку по рангу (achievements.RANKS, 5.91): чем реже, тем больше;
# ранг неизвестен (нет модуля или новая ачивка) — ACH.
ACH_RANK = {"dawn": 3, "noon": 8, "dusk": 15, "midnight": 25}
FILE_CAP = 20
SEMESTER_DAYS = 160
MIN_PEOPLE = 3
TOP = 10
CACHE_SECONDS = 300
# Тумблер «Показывать меня группе» — отдельное согласие (ревью 152-ФЗ 18.10):
# включил — запись в consents вида rating, выключил — запись снимается.
CONSENT_KIND, CONSENT_VERSION = "rating", "1"

_cache: tuple[float, dict] | None = None


def forget():
    global _cache
    _cache = None


async def _table_exists(db, name: str) -> bool:
    row = await (await db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))).fetchone()
    return row is not None


def _ach_worth() -> dict[str, int]:
    """Опыт за каждую ачивку по её рангу."""
    try:
        from achievements import RANKS
    except ImportError:
        return {}
    return {a: ACH_RANK.get(rank, ACH) for rank, ids in RANKS.items() for a in ids}


async def _collect() -> dict[int, dict]:
    """Опыт каждого: {user_id: {"brs", "submit", "early", "ach", "file", "total"}}."""
    window = f"-{SEMESTER_DAYS} days"
    out: dict[int, dict] = {}

    def add(uid, key, value):
        row = out.setdefault(uid, {"brs": 0, "submit": 0, "early": 0, "ach": 0, "file": 0})
        row[key] += int(round(value or 0))

    async with connect() as db:
        # последняя точка истории по каждому предмету — сумма баллов сейчас
        for uid, total in await (await db.execute(
            "SELECT h.user_id, SUM(h.score) FROM sdo_score_history h "
            "JOIN (SELECT user_id, course_id, MAX(day) AS day FROM sdo_score_history "
            "      WHERE day >= date('now', ?) GROUP BY user_id, course_id) last "
            "  ON last.user_id = h.user_id AND last.course_id = h.course_id AND last.day = h.day "
            "GROUP BY h.user_id", (window,))).fetchall():
            add(uid, "brs", total)
        # сдачи, подтверждённые СДО; «заранее» — отметка за сутки до срока
        # (done_at — UTC, срок — по Москве)
        for uid, n, early in await (await db.execute(
            "SELECT dd.user_id, COUNT(*), SUM(CASE WHEN datetime(dd.done_at, '+3 hours') <= "
            "  datetime(d.due_date || ' ' || COALESCE(NULLIF(d.due_time, ''), '23:59'), '-1 day') THEN 1 ELSE 0 END) "
            "FROM deadline_done dd JOIN deadlines d ON d.id = dd.deadline_id "
            "WHERE dd.via = 'sdo' AND d.due_date >= date('now', ?) GROUP BY dd.user_id", (window,))).fetchall():
            add(uid, "submit", n * SUBMIT)
            add(uid, "early", (early or 0) * EARLY)
        if await _table_exists(db, "achievements"):
            from config import STAROSTA_IDS
            worth = _ach_worth()
            for uid, ach_id in await (await db.execute("SELECT user_id, ach_id FROM achievements")).fetchall():
                if uid not in STAROSTA_IDS:
                    add(uid, "ach", worth.get(ach_id, ACH))
        for uid, n in await (await db.execute(
            "SELECT uploaded_by, COUNT(*) FROM files WHERE uploaded_by IS NOT NULL AND source IS NULL "
            "AND created_at >= datetime('now', ?) GROUP BY uploaded_by", (window,))).fetchall():
            add(uid, "file", min(n, FILE_CAP) * FILE)
    for row in out.values():
        row["total"] = sum(v for k, v in row.items() if k != "total")
    return out


async def _people() -> dict[int, dict]:
    """Все люди: группа (NULL — своя), имя, профиль рейтинга."""
    from database.groups import home
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT u.user_id, COALESCE(u.group_id, ?), COALESCE(u.full_name, ''), "
            "       p.nick, COALESCE(p.show, 0) "
            "FROM users u LEFT JOIN rating_profiles p ON p.user_id = u.user_id", (home(),))).fetchall()
    return {uid: {"group": gid, "name": name, "nick": nick, "show": bool(show)}
            for uid, gid, name, nick, show in rows}


async def _group_names(ids) -> dict[int, str]:
    import config
    from database.groups import home
    ids = list(ids)
    if not ids:
        return {}
    async with connect() as db:
        rows = await (await db.execute(
            f"SELECT id, name FROM groups WHERE id IN ({','.join('?' * len(ids))})", ids)).fetchall()
    names = {i: n for i, n in rows if n}
    names.setdefault(home(), config.GROUP_NAME)
    return names


async def board() -> dict:
    """Опыт людей и групп с местами — общий для всех, кэш CACHE_SECONDS."""
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    import institutes
    import privacy
    xp, people = await _collect(), await _people()
    # Без согласия или в ожидании удаления (privacy.blocked) — ни в опыте
    # группы, ни среди людей (ревью 152-ФЗ 18.10).
    people = {uid: p for uid, p in people.items() if not await privacy.blocked(uid)}
    groups: dict[int, dict] = {}
    for uid, person in people.items():
        total = xp.get(uid, {}).get("total", 0)
        g = groups.setdefault(person["group"], {"id": person["group"], "xp": 0, "people": 0})
        g["xp"] += total
        g["people"] += total > 0
    names = await _group_names(groups)
    for g in groups.values():
        g["name"] = names.get(g["id"], "")
        g["institute"] = institutes.of(g["name"])
    ranked = sorted((g for g in groups.values() if g["people"] >= MIN_PEOPLE and g["name"]),
                    key=lambda g: (-g["xp"], g["name"]))
    for i, g in enumerate(ranked, 1):
        g["place"] = i
    by_inst: dict[str, list] = {}
    for g in ranked:
        if g["institute"]:
            by_inst.setdefault(g["institute"], []).append(g)
    for lst in by_inst.values():
        for i, g in enumerate(lst, 1):
            g["place_inst"] = i
    data = {"xp": xp, "people": people, "groups": groups, "ranked": ranked, "by_inst": by_inst}
    _cache = (now, data)
    return data


def _row(g: dict, mine: int) -> dict:
    return {"name": g["name"], "xp": g["xp"], "institute": g["institute"], "place": g.get("place"),
            "place_inst": g.get("place_inst"), "mine": g["id"] == mine}


def nick_of(person: dict) -> str:
    import nick_filter
    return person.get("nick") or nick_filter.default(person.get("name") or "")


async def for_user(user_id: int, group_id: int) -> dict:
    """Экран «Рейтинг»: своя группа и её места, топы института и
    университета, люди своей группы (только согласившиеся) и свой опыт."""
    import institutes
    b = await board()
    me = b["people"].get(user_id) or {"group": group_id, "name": "", "nick": None, "show": False}
    g = b["groups"].get(group_id) or {"id": group_id, "xp": 0, "people": 0, "name": "", "institute": ""}
    inst = g.get("institute") or ""
    in_inst = b["by_inst"].get(inst, [])
    mates = sorted(
        ({"nick": nick_of(p), "xp": b["xp"].get(uid, {}).get("total", 0), "me": uid == user_id,
          "hidden": not p["show"]}
         for uid, p in b["people"].items()
         if p["group"] == group_id and (p["show"] or uid == user_id)),
        key=lambda r: (-r["xp"], r["nick"]))
    parts = b["xp"].get(user_id) or {"brs": 0, "submit": 0, "early": 0, "ach": 0, "file": 0, "total": 0}
    return {
        "me": {**parts, "nick": nick_of(me), "custom_nick": bool(me.get("nick")), "show": me["show"]},
        "group": {**_row(g, group_id), "people": g["people"], "need": max(0, MIN_PEOPLE - g["people"]),
                  "institute_name": institutes.INSTITUTES.get(inst, ""),
                  "groups_inst": len(in_inst), "groups_all": len(b["ranked"])},
        "institute_top": [_row(x, group_id) for x in in_inst[:TOP]],
        "university_top": [_row(x, group_id) for x in b["ranked"][:TOP]],
        "people": mates,
        "rules": {"brs": 1, "submit": SUBMIT, "early": EARLY, "ach": ACH, "file": FILE, "min_people": MIN_PEOPLE,
                  "ach_min": min(ACH_RANK.values()), "ach_max": max(ACH_RANK.values())},
    }


# ── Свой профиль: ник и согласие ─────────────────────────────────────────────

async def profile(user_id: int) -> dict:
    async with connect() as db:
        row = await (await db.execute(
            "SELECT nick, show, locked FROM rating_profiles WHERE user_id = ?", (user_id,))).fetchone()
    return {"nick": row[0], "show": bool(row[1]), "locked": bool(row[2])} if row else \
        {"nick": None, "show": False, "locked": False}


async def save(user_id: int, *, nick: str | None = None, show: bool | None = None, via: str = "app") -> dict:
    """nick='' — вернуть ник по умолчанию. Плохой ник → ValueError с причиной."""
    import nick_filter
    from database.privacy import give_consent, revoke_consent
    cur = await profile(user_id)
    new_nick = cur["nick"]
    if nick is not None:
        nick = " ".join(nick.split())
        if nick and cur["locked"]:
            raise ValueError("свой ник тебе поставить нельзя — остаётся имя")
        if nick and (why := nick_filter.problem(nick)):
            raise ValueError(why)
        new_nick = nick or None
    new_show = cur["show"] if show is None else bool(show)
    changed = new_nick != cur["nick"] and new_nick is not None
    async with connect() as db:
        await db.execute(
            "INSERT INTO rating_profiles (user_id, nick, show, nick_at, reviewed) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET nick = excluded.nick, show = excluded.show, "
            "nick_at = CASE WHEN ? THEN excluded.nick_at ELSE nick_at END, "
            "reviewed = CASE WHEN ? THEN 0 ELSE reviewed END",
            (user_id, new_nick, int(new_show), _now() if changed else None, 0 if changed else 1,
             int(changed), int(changed)))
        await db.commit()
    if new_show and not cur["show"]:
        await give_consent(user_id, CONSENT_KIND, CONSENT_VERSION, via)
    elif cur["show"] and not new_show:
        await revoke_consent(user_id, CONSENT_KIND)
    forget()
    return await profile(user_id)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ── Модерация ников (Никита: «ручную модерацию раз в пару дней») ─────────────

async def unreviewed(limit: int = 50) -> list[dict]:
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT p.user_id, p.nick, COALESCE(u.full_name, ''), COALESCE(u.username, '') "
            "FROM rating_profiles p LEFT JOIN users u ON u.user_id = p.user_id "
            "WHERE p.reviewed = 0 AND p.nick IS NOT NULL ORDER BY p.nick_at LIMIT ?", (limit,))).fetchall()
    return [{"user_id": r[0], "nick": r[1], "name": r[2], "username": r[3]} for r in rows]


async def mark_reviewed(user_ids) -> None:
    ids = list(user_ids)
    if not ids:
        return
    async with connect() as db:
        await db.execute(f"UPDATE rating_profiles SET reviewed = 1 WHERE user_id IN ({','.join('?' * len(ids))})", ids)
        await db.commit()


async def reset_nick(user_id: int, lock: bool = True) -> None:
    """Ник — обратно на имя; lock — свой больше не поставить."""
    async with connect() as db:
        await db.execute("UPDATE rating_profiles SET nick = NULL, reviewed = 1, locked = ? WHERE user_id = ?",
                         (int(lock), user_id))
        await db.commit()
    forget()

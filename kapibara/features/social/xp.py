"""Опыт и рейтинг групп (5.100.3, Никита 18.10; графики и люди групп — 5.100.5).

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
группы» — это опыт одного человека. Люди видны под ником и только с согласия
(оба по умолчанию выключены): «Показывать меня группе» (rating_profiles.show) —
своей группе, «Показывать меня всем» (show_all) — и тем, кто открыл группу из
рейтинга; ему нужно отдельное согласие на распространение (ст. 10.1,
legal_texts.RATING_ALL), а чужим группам виден только свой ник или «Капибара
№…» со случайным номером (alias), не имя. История по неделям (графики)
считается из тех же отметок по их датам.
Кому обрабатывать данные нельзя (privacy.blocked: нет согласия, ждёт удаления),
в рейтинге нет совсем.
"""

import secrets
import time
from datetime import datetime, timedelta, timezone

from database._conn import connect

SUBMIT, EARLY, ACH, FILE = 15, 10, 5, 2
# Опыт за ачивку по рангу (achievements.RANKS, 5.91): чем реже, тем больше;
# ранг неизвестен (нет модуля или новая ачивка) — ACH.
ACH_RANK = {"dawn": 3, "noon": 8, "dusk": 15, "midnight": 25}
FILE_CAP = 20
SEMESTER_DAYS = 160
MIN_PEOPLE = 3
TOP = 10
WEEKS = 8
CACHE_SECONDS = 300
PARTS = ("brs", "submit", "early", "ach", "file")
# Тумблеры — отдельные согласия (ревью 152-ФЗ 18.10): включил — запись в
# consents своего вида, выключил — запись снимается.
CONSENT_KIND, CONSENT_ALL_KIND, CONSENT_VERSION = "rating", "rating_all", "1"
ALIAS_MIN, ALIAS_MAX = 1000, 99999
MSK = timezone(timedelta(hours=3))

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


async def _raw() -> dict:
    """Все отметки, из которых складывается опыт, с датами — одним заходом в базу."""
    window = f"-{SEMESTER_DAYS} days"
    async with connect() as db:
        scores = await (await db.execute(
            "SELECT user_id, course_id, day, score FROM sdo_score_history WHERE day >= date('now', ?) "
            "ORDER BY day", (window,))).fetchall()
        # сдачи, подтверждённые СДО; «заранее» — отметка за сутки до срока
        # (done_at — UTC, срок — по Москве)
        submits = await (await db.execute(
            "SELECT dd.user_id, dd.done_at, CASE WHEN datetime(dd.done_at, '+3 hours') <= "
            "  datetime(d.due_date || ' ' || COALESCE(NULLIF(d.due_time, ''), '23:59'), '-1 day') THEN 1 ELSE 0 END "
            "FROM deadline_done dd JOIN deadlines d ON d.id = dd.deadline_id "
            "WHERE dd.via = 'sdo' AND d.due_date >= date('now', ?)", (window,))).fetchall()
        achs = []
        if await _table_exists(db, "achievements"):
            from config import STAROSTA_IDS
            # создателю ачивки открыты все сразу (5.91.4) — в опыт не идут
            achs = [r for r in await (await db.execute("SELECT user_id, ach_id, at FROM achievements")).fetchall()
                    if r[0] not in STAROSTA_IDS]
        files = await (await db.execute(
            "SELECT uploaded_by, created_at FROM files WHERE uploaded_by IS NOT NULL AND source IS NULL "
            "AND created_at >= datetime('now', ?)", (window,))).fetchall()
    brs: dict[tuple[int, int], list] = {}
    for uid, cid, day, score in scores:
        brs.setdefault((uid, cid), []).append((day, score or 0))
    return {"brs": brs, "submits": submits, "achs": achs, "files": files}


def _totals(raw: dict, end: datetime | None = None) -> dict[int, dict]:
    """Опыт каждого на момент end (None — сейчас): {user_id: {части…, "total"}}."""
    cut_day = cut_utc = None
    cut_ms = None
    if end is not None:
        cut_day = (end.astimezone(MSK) - timedelta(microseconds=1)).date().isoformat()
        cut_utc = end.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cut_ms = int(end.timestamp() * 1000)
    out: dict[int, dict] = {}

    def add(uid, key, value):
        row = out.setdefault(uid, dict.fromkeys(PARTS, 0))
        row[key] += int(round(value or 0))

    for (uid, _cid), points in raw["brs"].items():
        last = None
        for day, score in points:                       # по возрастанию дня
            if cut_day is not None and day > cut_day:
                break
            last = score
        if last is not None:
            add(uid, "brs", last)
    for uid, done_at, early in raw["submits"]:
        if cut_utc is None or (done_at or "") < cut_utc:
            add(uid, "submit", SUBMIT)
            add(uid, "early", EARLY if early else 0)
    worth = _ach_worth()
    for uid, ach_id, at in raw["achs"]:
        if cut_ms is None or (at or 0) < cut_ms:
            add(uid, "ach", worth.get(ach_id, ACH))
    files: dict[int, int] = {}
    for uid, created in raw["files"]:
        if cut_utc is None or (created or "") < cut_utc:
            files[uid] = files.get(uid, 0) + 1
    for uid, n in files.items():
        add(uid, "file", min(n, FILE_CAP) * FILE)
    for row in out.values():
        row["total"] = sum(row[k] for k in PARTS)
    return out


async def _collect() -> dict[int, dict]:
    """Опыт каждого сейчас: {user_id: {"brs", "submit", "early", "ach", "file", "total"}}."""
    return _totals(await _raw())


# «Показывать меня всем» действует только с согласием нынешней версии текста:
# подняли RATING_ALL_VERSION — у всех выключено, пока не согласятся заново.
_SHOW_ALL_SQL = ("(COALESCE(p.show_all, 0) AND EXISTS (SELECT 1 FROM consents c WHERE c.user_id = p.user_id "
                 "AND c.kind = ? AND c.version = ?))")


def _all_args() -> tuple[str, str]:
    import legal_texts
    return CONSENT_ALL_KIND, legal_texts.RATING_ALL_VERSION


async def _people() -> dict[int, dict]:
    """Все люди: группа (NULL — своя), имя, профиль рейтинга."""
    from database.groups import home
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT u.user_id, COALESCE(u.group_id, ?), COALESCE(u.full_name, ''), "
            f"       p.nick, COALESCE(p.show, 0), {_SHOW_ALL_SQL}, p.alias "
            "FROM users u LEFT JOIN rating_profiles p ON p.user_id = u.user_id", (home(), *_all_args()))).fetchall()
    return {uid: {"group": gid, "name": name, "nick": nick, "show": bool(show), "show_all": bool(show_all),
                  "alias": alias}
            for uid, gid, name, nick, show, show_all, alias in rows}


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


def _rank(groups: dict[int, dict]) -> tuple[list, dict]:
    """Места: во всём вузе (place) и в институте (place_inst) — прямо в словари групп."""
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
    return ranked, by_inst


def _groups(xp: dict, people: dict, names: dict) -> dict[int, dict]:
    import institutes
    groups: dict[int, dict] = {}
    for uid, person in people.items():
        mine = xp.get(uid)
        gid = person["group"]
        g = groups.setdefault(gid, {"id": gid, "xp": 0, "people": 0, "parts": dict.fromkeys(PARTS, 0),
                                    "name": names.get(gid, ""), "institute": institutes.of(names.get(gid, ""))})
        if mine:
            g["xp"] += mine["total"]
            g["people"] += mine["total"] > 0
            for k in PARTS:
                g["parts"][k] += mine[k]
    return groups


def _week_ends(now: datetime) -> list[datetime]:
    """Концы WEEKS недель (понедельник 00:00 по Москве), последняя — сейчас."""
    msk = now.astimezone(MSK)
    monday = (msk - timedelta(days=msk.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return [monday - timedelta(weeks=i) for i in range(WEEKS - 2, -1, -1)] + [msk]


async def board() -> dict:
    """Опыт людей и групп с местами и историей по неделям — общий для всех,
    кэш CACHE_SECONDS."""
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    import privacy
    raw, people = await _raw(), await _people()
    # Без согласия или в ожидании удаления (privacy.blocked) — ни в опыте
    # группы, ни среди людей (ревью 152-ФЗ 18.10).
    blocked = await privacy.blocked_ids(people)
    people = {uid: p for uid, p in people.items() if uid not in blocked}
    xp = _totals(raw)
    names = await _group_names({p["group"] for p in people.values()})
    groups = _groups(xp, people, names)
    ranked, by_inst = _rank(groups)
    # история: та же раскладка на конец каждой недели (неделя подписана своим понедельником)
    history: dict[int, list] = {}
    ends = _week_ends(datetime.now(timezone.utc))
    for i, end in enumerate(ends):
        start = end - timedelta(weeks=1) if i < len(ends) - 1 else ends[-2]
        label = start.strftime("%d.%m")
        past = _groups(_totals(raw, end), people, names)
        _rank(past)
        for gid, g in past.items():
            history.setdefault(gid, []).append({"week": label, "xp": g["xp"], "place": g.get("place"),
                                                "place_inst": g.get("place_inst")})
    data = {"xp": xp, "people": people, "groups": groups, "ranked": ranked, "by_inst": by_inst,
            "history": history}
    _cache = (now, data)
    return data


def _row(g: dict, mine: int) -> dict:
    return {"id": g["id"], "name": g["name"], "xp": g["xp"], "institute": g["institute"], "place": g.get("place"),
            "place_inst": g.get("place_inst"), "mine": g["id"] == mine}


def nick_of(person: dict) -> str:
    import nick_filter
    return person.get("nick") or nick_filter.default(person.get("name") or "")


def public_nick(person: dict) -> str | None:
    """Как человека видят все (не своя группа): свой ник или «Капибара №…» —
    не «Имя Ф.» (ревью 152-ФЗ 18.10). Номера ещё нет — None."""
    if person.get("nick"):
        return person["nick"]
    return f"Капибара №{person['alias']}" if person.get("alias") else None


def _people_of(b: dict, group_id: int, viewer_id: int, member: bool) -> tuple[list, int]:
    """Люди группы, которых видно этому человеку: своей группе — кто включил
    «группе» или «всем», чужим — только «всем»; сам себя видит всегда (с
    пометкой hidden, если его не видят). Кто виден только по «всем» — под
    public_nick, и своей группе тоже. → (строки, сколько с опытом скрыто)."""
    rows, hidden = [], 0
    for uid, p in b["people"].items():
        if p["group"] != group_id:
            continue
        total = b["xp"].get(uid, {}).get("total", 0)
        by_group = member and p["show"]
        seen = by_group or (p["show_all"] and public_nick(p) is not None)
        if seen or uid == viewer_id:
            nick = nick_of(p) if member and (by_group or uid == viewer_id) else (public_nick(p) or nick_of(p))
            rows.append({"nick": nick, "xp": total, "me": uid == viewer_id, "hidden": not seen})
        elif total > 0:
            hidden += 1
    rows.sort(key=lambda r: (-r["xp"], r["nick"]))
    return rows, hidden


def _group_full(b: dict, g: dict, viewer_gid: int) -> dict:
    import institutes
    inst = g.get("institute") or ""
    return {**_row(g, viewer_gid), "people": g["people"], "need": max(0, MIN_PEOPLE - g["people"]),
            "institute_name": institutes.INSTITUTES.get(inst, ""),
            "groups_inst": len(b["by_inst"].get(inst, [])), "groups_all": len(b["ranked"]),
            "parts": dict(g.get("parts") or dict.fromkeys(PARTS, 0)),
            "history": b["history"].get(g["id"], [])}


def _empty_group(gid: int) -> dict:
    return {"id": gid, "xp": 0, "people": 0, "name": "", "institute": "", "parts": dict.fromkeys(PARTS, 0)}


async def for_user(user_id: int, group_id: int, member: bool = True) -> dict:
    """Экран «Рейтинг»: своя группа, её места, опыт по неделям и из чего он,
    топы института и университета, люди своей группы (только согласившиеся)
    и свой опыт. member — человек правда в этой группе (своя — участник чата)."""
    b = await board()
    me = b["people"].get(user_id) or {"group": group_id, "name": "", "nick": None, "show": False, "show_all": False,
                                      "alias": None}
    g = b["groups"].get(group_id) or _empty_group(group_id)
    in_inst = b["by_inst"].get(g.get("institute") or "", [])
    mates, _hidden = _people_of(b, group_id, user_id, member)
    parts = b["xp"].get(user_id) or {**dict.fromkeys(PARTS, 0), "total": 0}
    return {
        "me": {**parts, "nick": nick_of(me), "custom_nick": bool(me.get("nick")), "show": me["show"],
               "show_all": me["show_all"], "public_nick": public_nick(me)},
        "group": _group_full(b, g, group_id),
        "institute_top": [_row(x, group_id) for x in in_inst[:TOP]],
        "university_top": [_row(x, group_id) for x in b["ranked"][:TOP]],
        "people": mates,
        "rules": {"brs": 1, "submit": SUBMIT, "early": EARLY, "ach": ACH, "file": FILE, "min_people": MIN_PEOPLE,
                  "ach_min": min(ACH_RANK.values()), "ach_max": max(ACH_RANK.values())},
    }


async def group_view(viewer_id: int, viewer_gid: int, group_id: int) -> dict | None:
    """Группа из рейтинга по нажатию: места, опыт по неделям, из чего он и её
    люди — только кто разрешил (см. _people_of). Нет такой группы — None."""
    b = await board()
    g = b["groups"].get(group_id)
    if not g or not g.get("name"):
        return None
    member = bool(viewer_gid) and viewer_gid == group_id
    people, hidden = _people_of(b, group_id, viewer_id, member)
    return {**_group_full(b, g, viewer_gid), "people_list": people, "hidden": hidden, "member": member}


# ── Свой профиль: ник и согласия ─────────────────────────────────────────────

async def profile(user_id: int) -> dict:
    async with connect() as db:
        row = await (await db.execute(
            f"SELECT nick, show, locked, {_SHOW_ALL_SQL}, alias FROM rating_profiles p WHERE user_id = ?",
            (*_all_args(), user_id))).fetchone()
    return {"nick": row[0], "show": bool(row[1]), "locked": bool(row[2]), "show_all": bool(row[3]),
            "alias": row[4]} if row else \
        {"nick": None, "show": False, "locked": False, "show_all": False, "alias": None}


async def _new_alias(db) -> int:
    """Случайный номер для «Капибара №…»: не из id и не по порядку — по нему
    человека не найти; один раз на человека, не меняется."""
    while True:
        n = ALIAS_MIN + secrets.randbelow(ALIAS_MAX - ALIAS_MIN + 1)
        if not await (await db.execute("SELECT 1 FROM rating_profiles WHERE alias = ?", (n,))).fetchone():
            return n


async def save(user_id: int, *, nick: str | None = None, show: bool | None = None, show_all: bool | None = None,
               consent: str | None = None, via: str = "app") -> dict:
    """nick='' — вернуть ник по умолчанию. Плохой ник → ValueError с причиной.
    Включить show_all — только с галочкой отдельного согласия: consent —
    версия текста legal_texts.RATING_ALL, которую человек видел."""
    import legal_texts
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
    new_all = cur["show_all"] if show_all is None else bool(show_all)
    if new_all and not cur["show_all"] and consent != legal_texts.RATING_ALL_VERSION:
        raise ValueError("чтобы тебя видели все, нужно отдельное согласие — открой тумблер ещё раз")
    changed = new_nick != cur["nick"] and new_nick is not None
    async with connect() as db:
        alias = cur["alias"] or (await _new_alias(db) if new_all else None)
        await db.execute(
            "INSERT INTO rating_profiles (user_id, nick, show, show_all, nick_at, reviewed, alias) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET nick = excluded.nick, show = excluded.show, "
            "show_all = excluded.show_all, alias = excluded.alias, "
            "nick_at = CASE WHEN ? THEN excluded.nick_at ELSE nick_at END, "
            "reviewed = CASE WHEN ? THEN 0 ELSE reviewed END",
            (user_id, new_nick, int(new_show), int(new_all), _now() if changed else None, 0 if changed else 1,
             alias, int(changed), int(changed)))
        await db.commit()
    for kind, was, now, asked, ver in (
            (CONSENT_KIND, cur["show"], new_show, show, CONSENT_VERSION),
            (CONSENT_ALL_KIND, cur["show_all"], new_all, show_all, legal_texts.RATING_ALL_VERSION)):
        if now and not was:
            await give_consent(user_id, kind, ver, via)
        elif not now and (was or asked is False):
            await revoke_consent(user_id, kind)
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

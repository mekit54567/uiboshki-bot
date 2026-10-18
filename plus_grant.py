"""Ручные выдачи «Капибары+» — только Никита (config.is_starosta), командой
/grant в боте (handlers/plus.py):

  /grant @ник | id                 — что у человека сейчас и последние выдачи;
  /grant @ник 3m | 45d | 1y        — продлить подписку (м/д/г тоже можно), дни
                                     идут после текущего срока и подарка группе;
  /grant @ник unlimited [ДД.ММ.ГГГГ] (или «безлимит») — безлимит навсегда или
                                     до дня: всё из «Капибары+» и ИИ без лимитов;
  /grant @ник off [sub|unlimited]  — снять ручное: безлимит и/или ручные дни.

Всё, что после срока или даты, — личная приписка Никиты: уходит человеку
вместе с сообщением о выдаче (plus_welcome.text, отдельной строкой курсивом)
и пишется в журнал (plus_grants.note): «/grant @ник 3m Спасибо за помощь!».

Месяц — 30 дней, год — 300: июль и август в срок не считаются (billing.add_days),
так 1y ≈ календарный год. Каждое продление (и оплаты с бонусами — в
billing.grant) пишется в журнал plus_grants, поэтому «off» снимает только
ручные дни: срок возвращается к тому, что было до первой ручной выдачи, и
к нему заново прибавляются оплаты и бонусы, пришедшие после неё, — купленное
не пропадает. Человеку о выдаче пишет бот (plus_welcome.text, delivery)."""

import re
from datetime import date, datetime, timedelta

UNIT_DAYS = {"d": 1, "д": 1, "m": 30, "м": 30, "y": 300, "г": 300, "л": 300}
_TERM = re.compile(r"^(\d{1,4})\s*(d|days?|д|дн|дней|дня|день|m|months?|мес|м|y|years?|г|год|года|лет)$")
UNLIMITED_WORDS = ("unlimited", "безлимит", "unlim", "∞")
_DATE_LIKE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")
NOTE_MAX = 600                       # приписка — не письмо: длиннее — пусть пишет сам


class GrantError(Exception):
    pass


def parse_term(s: str) -> int | None:
    """«3m», «45d», «1y», «3 мес», «2г» → дней; не срок — None."""
    m = _TERM.match((s or "").strip().lower())
    if not m:
        return None
    n = int(m.group(1))
    days = n * UNIT_DAYS[m.group(2)[0]]
    return days if 0 < days <= 3000 else None


def parse_day(s: str) -> str | None:
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y").date().isoformat()
    except ValueError:
        return None


def fmt(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.%Y") if iso else ""


async def find_user(who: str) -> dict:
    """@ник (без учёта регистра), Telegram id или id аккаунта приложения
    (вход VK/Яндекс — отрицательный номер, database/identities.is_local)."""
    import aiosqlite

    from database._conn import connect
    w = (who or "").strip()
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        if re.fullmatch(r"-?\d+", w):
            row = await (await db.execute(
                "SELECT user_id, username, full_name FROM users WHERE user_id = ?", (int(w),))).fetchone()
            if not row:
                raise GrantError(f"Нет человека с id {w} — он ещё не заходил в бота или приложение.")
            return dict(row)
        name = w.lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_]{3,40}", name):
            raise GrantError("Кого? Так: <code>@ник</code>, Telegram id или id из приложения.")
        rows = await (await db.execute(
            "SELECT user_id, username, full_name FROM users WHERE lower(username) = lower(?)", (name,))).fetchall()
    if not rows:
        raise GrantError(f"Не нашёл @{name}: такого ника нет среди тех, кто заходил в бота.")
    if len(rows) > 1:
        ids = ", ".join(f"<code>{r['user_id']}</code>" for r in rows)
        raise GrantError(f"@{name} — несколько аккаунтов ({ids}). Укажи id.")
    return dict(rows[0])


def who_text(u: dict) -> str:
    from utils import esc
    name = esc(u.get("full_name") or "")
    nick = f"@{esc(u['username'])}" if u.get("username") else ""
    parts = [p for p in (name, nick) if p]
    return " ".join(parts + [f"(<code>{u['user_id']}</code>)"])


async def extend(uid: int, days: int, by: int, note: str | None = None) -> str:
    """Продлить подписку на days дней вручную → последний день."""
    import billing
    import locks
    async with locks.lock("plus_grant", uid):
        return await billing.grant(uid, days, "manual", by=by, note=note)


async def unlimited(uid: int, until: str | None, by: int, note: str | None = None):
    """Безлимит навсегда (until=None) или до дня включительно."""
    import locks
    from database.billing import get_unlimited, log_grant, put_unlimited
    async with locks.lock("plus_grant", uid):
        prev = await get_unlimited(uid)
        await put_unlimited(uid, until, by)
        await log_grant(uid, "unlimited", "manual", None, prev and (prev["until"] or "forever"),
                        until or "forever", by, note=note)


async def off(uid: int, what: str, by: int) -> dict:
    """Снять ручное: what — all, sub или unlimited. → {"unlimited": снят ли,
    "sub": (было, стало) или None — ручных дней не было}."""
    import billing
    import locks
    from database.billing import del_unlimited, get_sub, grant_log, log_grant, put_sub, revoke_grants
    from utils import today_msk
    out = {"unlimited": False, "sub": None}
    async with locks.lock("plus_grant", uid):
        if what in ("all", "unlimited") and await del_unlimited(uid):
            out["unlimited"] = True
            await log_grant(uid, "off", "unlimited", None, None, None, by)
        if what in ("all", "sub"):
            log = [e for e in await grant_log(uid) if e["kind"] == "sub" and not e["revoked"]]
            manual = [e for e in log if e["source"] == "manual"]
            if manual:
                first = manual[0]
                today = today_msk().isoformat()
                base = first["prev_until"]
                cur = base if base and base >= today else None
                for e in log:                        # оплаты и бонусы после первой ручной — заново
                    if e["id"] > first["id"] and e["source"] != "manual" and e["days"]:
                        cur = await billing.extend_from(uid, cur, e["days"])
                final = cur or base or (today_msk() - timedelta(days=1)).isoformat()
                sub = await get_sub(uid)
                was = sub["until"] if sub else None
                await put_sub(uid, final, "manual-off")
                await revoke_grants(uid, [e["id"] for e in manual])
                await log_grant(uid, "off", "sub", None, was, final, by)
                out["sub"] = (was, final)
    return out


async def describe(u: dict) -> str:
    """Что у человека сейчас — для /grant <кто>."""
    import billing
    import plans
    from database.billing import grant_log
    uid = u["user_id"]
    st = await billing.status(uid)
    lines = [f"👤 {who_text(u)}", f"Тариф: <b>{plans.NAMES[await plans.plan_of(uid)]}</b>"]
    lines.append(f"Подписка: до {fmt(st['paid_until'])}" if st["paid_until"] else "Подписка: нет")
    if st["gift"]:
        lines.append(f"Подарок группе: до {fmt(st['gift'])}")
    if st["unlimited"]:
        lines.append("Безлимит: " + (f"до {fmt(st['unlimited_until'])}" if st["unlimited_until"] else "навсегда"))
    log = await grant_log(uid, 6)
    if log:
        lines += ["", "<b>Последние выдачи:</b>"]
        for e in log:
            lines.append("• " + _log_line(e))
    return "\n".join(lines)


def _log_line(e: dict) -> str:
    from utils import esc
    day = (e["at"] or "")[:10]
    when = fmt(day) if day else ""
    src = {"manual": "вручную", "pay": "оплата"}.get(e["source"] or "", e["source"] or "")
    if e["kind"] == "sub":
        t = f"+{e['days']} дн. ({src}) → до {fmt(e['until'])}"
        if e["revoked"]:
            t = f"<s>{t}</s>"
    elif e["kind"] == "unlimited":
        t = "безлимит " + ("навсегда" if e["until"] == "forever" else f"до {fmt(e['until'])}")
    else:
        t = ("снят безлимит" if e["source"] == "unlimited" else
             f"сняты ручные дни → подписка до {fmt(e['until'])}")
    note = (e.get("note") or "").strip()
    if note:
        short = note if len(note) <= 60 else note[:59].rstrip() + "…"
        t += f" · <i>«{esc(short)}»</i>"
    return f"{when} — {t}"


HELP = ("<b>/grant</b> — выдать «Капибару+» вручную (только тебе):\n"
        "<code>/grant @ник</code> — что у человека сейчас\n"
        "<code>/grant @ник 3m</code> · <code>45d</code> · <code>1y</code> — продлить "
        "(месяц 30 дней, год 300: лето не считается; дни — после текущего срока)\n"
        "<code>/grant @ник unlimited</code> — безлимит навсегда, "
        "<code>/grant @ник безлимит 31.12.2027</code> — до дня\n"
        "<code>/grant @ник 3m Спасибо, что помог с расписанием!</code> — с припиской: всё после срока "
        "или даты уйдёт ему вместе с сообщением о выдаче (курсивом, «Приписка от Никиты: …»)\n"
        "<code>/grant @ник off</code> — снять ручное (безлимит и ручные дни; купленное остаётся), "
        "<code>off sub</code> / <code>off unlimited</code> — что-то одно\n"
        "Кто: <code>@ник</code>, Telegram id или id аккаунта приложения.")


def _tail(raw: str, n: int) -> str:
    """Текст после первых n слов — как написан (с переносами строк)."""
    parts = raw.strip().split(None, n)
    return parts[n].strip() if len(parts) > n else ""


async def command(bot, by: int, args: list[str] | str) -> str:
    """Разбор /grant → ответ Никите (HTML). Человеку пишет сам. args — слова
    или весь текст после «/grant» (так приписка сохранит переносы строк)."""
    import billing
    import plus_welcome
    raw = args if isinstance(args, str) else " ".join(args)
    words = raw.split()
    if not words:
        return HELP
    try:
        u = await find_user(words[0])
    except GrantError as e:
        return str(e)
    uid, rest = u["user_id"], [a.lower() for a in words[1:]]
    if not rest:
        return await describe(u)
    if rest[0] == "off":
        what = {"": "all", "sub": "sub", "подписка": "sub", "unlimited": "unlimited",
                "безлимит": "unlimited"}.get(rest[1] if len(rest) > 1 else "")
        if not what:
            return "Так: <code>/grant @ник off</code>, <code>off sub</code> или <code>off unlimited</code>."
        res = await off(uid, what, by)
        done = []
        if res["unlimited"]:
            done.append("безлимит снят")
        if res["sub"]:
            done.append(f"ручные дни сняты, подписка {'до ' + fmt(res['sub'][1]) if res['sub'][1] >= _today() else 'кончилась'}")
        head = ("Готово: " + ", ".join(done) + ".") if done else "Снимать нечего: ручных выдач нет."
        return head + "\n\n" + await describe(u)
    if rest[0] in UNLIMITED_WORDS:
        until, used = None, 2
        if len(rest) > 1 and (_DATE_LIKE.match(rest[1]) or parse_day(rest[1])):
            until, used = parse_day(rest[1]), 3
            if not until or until < _today():
                return "Дата — так: <code>/grant @ник unlimited 31.12.2027</code> (и не в прошлом)."
        note = _tail(raw, used)
        if len(note) > NOTE_MAX:
            return f"Приписка длинная ({len(note)} знаков) — до {NOTE_MAX}."
        await unlimited(uid, until, by, note or None)
        await billing.notify(bot, uid, plus_welcome.text(until, unlimited=True, note=note))
        await plus_welcome.mark(uid)
        return (f"Готово: безлимит {'до ' + fmt(until) if until else 'навсегда'}. "
                f"{_wrote(note)}\n\n" + await describe(u))
    if len(rest) > 1 and parse_term(f"{rest[0]} {rest[1]}"):       # «3 мес»
        days, used = parse_term(f"{rest[0]} {rest[1]}"), 3
    else:
        days, used = parse_term(rest[0]), 2
    if not days:
        return "Не понял срок. " + HELP
    note = _tail(raw, used)
    if len(note) > NOTE_MAX:
        return f"Приписка длинная ({len(note)} знаков) — до {NOTE_MAX}."
    until = await extend(uid, days, by, note or None)
    await billing.notify(bot, uid, plus_welcome.text(until, granted=True, note=note))
    await plus_welcome.mark(uid)
    return f"Готово: +{days} дн., «Капибара+» до {fmt(until)}. {_wrote(note)}\n\n" + await describe(u)


def _wrote(note: str) -> str:
    """Что ушло человеку — Никите видно, как выглядит приписка."""
    import plus_welcome
    return ("Ему написал с припиской:\n" + plus_welcome.note_line(note)) if note else "Ему написал."


def _today() -> str:
    from utils import today_msk
    return today_msk().isoformat()

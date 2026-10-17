"""Группы института (этап 1): группа человека, справочник групп, подписки."""

from contextvars import ContextVar

import aiosqlite

from database._conn import connect

# Группа того, чей запрос сейчас обрабатывается (WebApp — get_current_user,
# бот — GroupContextMiddleware). Функции базы без явного group_id берут её:
# так «Файлы», «ДЗ», заметки и контекст ИИ у человека из другой группы — его
# группы, без протаскивания group_id через каждый вызов. Нет запроса
# (рассылки, синк) — своя группа бота.
current_group: ContextVar[int | None] = ContextVar("current_group", default=None)
# И кто сам этот человек — для ИИ «только старостам на Ling» (gemini_solver.ai_main).
current_user: ContextVar[int | None] = ContextVar("current_user", default=None)


async def upsert_group(group_id: int, name: str, own: bool = False):
    async with connect() as db:
        await db.execute(
            "INSERT INTO groups (id, name, own) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name, own = MAX(own, excluded.own)",
            (group_id, name, 1 if own else 0))
        await db.commit()


async def get_group(group_id: int) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM groups WHERE id = ?", (group_id,))).fetchone()
        return dict(row) if row else None


async def get_user_group(user_id: int) -> int | None:
    async with connect() as db:
        row = await (await db.execute("SELECT group_id FROM users WHERE user_id = ?", (user_id,))).fetchone()
        return row[0] if row else None


async def set_user_group(user_id: int, group_id: int):
    async with connect() as db:
        await db.execute("UPDATE users SET group_id = ? WHERE user_id = ?", (group_id, user_id))
        await db.commit()


async def group_counts() -> list[dict]:
    """Группы и сколько в них людей — для /stats."""
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT u.group_id, COALESCE(g.name, ''), COUNT(*) FROM users u "
            "LEFT JOIN groups g ON g.id = u.group_id GROUP BY u.group_id ORDER BY COUNT(*) DESC")).fetchall()
    return [{"id": r[0], "name": r[1], "users": r[2]} for r in rows]


async def get_subscription(user_id: int) -> str | None:
    """До какой даты подписка (YYYY-MM-DD) или None."""
    async with connect() as db:
        row = await (await db.execute("SELECT until FROM subscriptions WHERE user_id = ?", (user_id,))).fetchone()
        return row[0] if row else None


async def set_subscription_until(user_id: int, until: str | None, source: str = "manual"):
    """until=None — снять подписку."""
    async with connect() as db:
        if until is None:
            await db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        else:
            await db.execute(
                "INSERT INTO subscriptions (user_id, until, source) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET until = excluded.until, source = excluded.source",
                (user_id, until, source))
        await db.commit()


# ── Видимость общих данных по группе (этап 1 (б)) ────────────────────────────
# Строки общих таблиц с group_id NULL — своей группы (всё, что было до этапа
# 1). Чужая группа видит только свои строки; копия бота на одну группу
# (HOME_GROUP_ID = 0) — всё, как раньше.

def home() -> int:
    from config import HOME_GROUP_ID
    return HOME_GROUP_ID


def scope_sql(alias: str = "") -> str:
    """Условие «строка этой группы» с одним параметром — группой зрителя."""
    col = f"{alias}." if alias else ""
    return f"COALESCE({col}group_id, {int(home())}) = ?"


def file_scope_sql(alias: str = "f") -> str:
    """Файл виден группе: свой или общий с ней (file_groups) — два параметра."""
    return (f"(COALESCE({alias}.group_id, {int(home())}) = ? OR EXISTS "
            f"(SELECT 1 FROM file_groups fg WHERE fg.file_id = {alias}.id AND fg.group_id = ?))")


async def viewer_group(user_id: int | None) -> int:
    """Группа, чьи общие данные видит человек. Не выбрал (только что пришёл —
    приложение и бот тут же спрашивают группу) — своя, как было до этапа 1.
    Своя группа — только участникам её чата в Telegram (members.py, владелец
    09.10): известно, что человек не в чате, — 0, данных своей группы нет."""
    if not home():
        return 0
    gid = await get_user_group(user_id) if user_id else None
    if gid and gid != home():
        return gid
    import members
    return 0 if user_id and await members.known(user_id) is False else home()


async def add_group_admin(group_id: int, user_id: int, added_by: int):
    async with connect() as db:
        await db.execute("INSERT OR IGNORE INTO group_admins (group_id, user_id, added_by) VALUES (?, ?, ?)",
                         (group_id, user_id, added_by))
        await db.commit()


async def remove_group_admin(group_id: int, user_id: int):
    async with connect() as db:
        await db.execute("DELETE FROM group_admins WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        await db.commit()


async def get_group_admins(group_id: int) -> list[int]:
    async with connect() as db:
        rows = await (await db.execute("SELECT user_id FROM group_admins WHERE group_id = ?", (group_id,))).fetchall()
        return [r[0] for r in rows]


async def is_group_admin(user_id: int, group_id: int) -> bool:
    async with connect() as db:
        row = await (await db.execute("SELECT 1 FROM group_admins WHERE group_id = ? AND user_id = ?",
                                      (group_id, user_id))).fetchone()
        return row is not None


def g_or_home(group_id: int | None) -> int:
    """Группа для запроса: явная; иначе — того, чей запрос (current_group);
    иначе своя (рассылки и синк своей группы)."""
    if group_id is not None:
        return group_id
    cur = current_group.get()
    return home() if cur is None else cur


def row_group(group_id: int | None) -> int:
    """Группа СТРОКИ базы (дедлайн, ДЗ, заметка): NULL — всегда своя группа.
    Не g_or_home: та подставляет группу запроса, и общий дедлайн УИБО-03-24
    для человека из другой группы считался «его» — староста чужой группы мог
    его править и удалять (ревью безопасности 09.10)."""
    return home() if group_id is None else group_id


async def enter(user_id: int) -> int:
    """Запомнить группу человека на время его запроса."""
    gid = await viewer_group(user_id)
    current_group.set(gid)
    current_user.set(user_id)
    return gid


def stored(group_id: int | None) -> int | None:
    """Что писать в group_id: своя — NULL (как всё до этапа 1), чужая — id."""
    return None if group_id in (None, home()) else group_id

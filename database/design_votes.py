"""Голос «какая тёмная лучше» (новый дизайн, шаг 9, Никита 18.11): кто был в
«Классике» с тёмной темой, пробует «Ночную тетрадь», сравнивает с прежней и
один раз отвечает. Пишет POST /api/design/vote, читает /stats — только счёт,
без имён. Один голос на человека, новый заменяет прежний; с удалением данных
уходит вместе с ним (колонка user_id, privacy.erase_user)."""

from database._conn import connect

CHOICES = ("new", "old")


async def vote(user_id: int, choice: str, at: str) -> None:
    """choice — «new» или «old»; at — время по Москве ISO."""
    if choice not in CHOICES:
        raise ValueError(choice)
    async with connect() as db:
        await db.execute("INSERT INTO design_votes (user_id, choice, at) VALUES (?, ?, ?) "
                         "ON CONFLICT(user_id) DO UPDATE SET choice = excluded.choice, at = excluded.at",
                         (user_id, choice, at))
        await db.commit()


async def counts() -> dict[str, int]:
    """{'new': N, 'old': M} — для /stats."""
    async with connect() as db:
        rows = await (await db.execute("SELECT choice, COUNT(*) FROM design_votes GROUP BY choice")).fetchall()
    got = {str(c): int(n) for c, n in rows}
    return {c: got.get(c, 0) for c in CHOICES}

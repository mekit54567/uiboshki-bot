"""Ачивки приложения на сервере (5.91): список — тот же, что в
app/lib/achievements/catalog.dart (тест test_achievements следит), ранги —
«Рассвет · Полдень · Сумерки · Полночь». Ловит их приложение, сервер хранит:
не пропадают при смене телефона, по ним открываются иконки (design/
app_icons.json, поле unlock) и — потом — дни подписки за закрытый ранг."""

from database._conn import connect

RANKS = {
    "dawn": ["lesson", "week_next", "goal", "sdo", "widget", "look", "ai", "summary", "remind", "teacher"],
    "noon": ["submit", "week5", "early", "streak", "plus", "found"],
    "dusk": ["auto", "clean", "month", "calm"],
    "midnight": ["t2222", "wave", "fri13", "secret", "one_of_us"],
}
IDS = {a for ids in RANKS.values() for a in ids}

# Не раньше запуска ачивок и не из будущего: приложение шлёт время телефона.
_MIN_MS = 1_760_000_000_000  # 09.10.2025


async def of_user(user_id: int) -> dict[str, int]:
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT ach_id, at FROM achievements WHERE user_id = ?", (user_id,))).fetchall()
    return {a: at for a, at in rows}


async def add(user_id: int, items: dict, now_ms: int) -> dict[str, int]:
    """Записать открытые: известные id, время — самое раннее из присланных
    и записанного. Возвращает всё, что есть у человека."""
    good = []
    for a, at in (items or {}).items():
        if a in IDS and isinstance(at, int) and not isinstance(at, bool):
            good.append((user_id, a, min(max(at, _MIN_MS), now_ms)))
    if good:
        async with connect() as db:
            await db.executemany(
                "INSERT INTO achievements (user_id, ach_id, at) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, ach_id) DO UPDATE SET at = MIN(at, excluded.at)", good)
            await db.commit()
    return await of_user(user_id)


async def rank_closed(user_id: int, rank: str) -> bool:
    """Все ачивки ранга открыты (для дней подписки за ранг)."""
    got = await of_user(user_id)
    return all(a in got for a in RANKS[rank])

"""
Вход в СДО у каждого студента свой: кука MoodleSession, которую человек
сам вставляет в WebApp (меню «Ещё» → СДО). Нужна, чтобы сдавать работы
из WebApp от своего имени (sdo_submit.py).

Кука в базе только зашифрованной (Fernet). Ключ — отдельный секрет на
хостинге (152-ФЗ): SDO_CRYPT_KEY (ключ Fernet) или SDO_CRYPT_PASSPHRASE
(фраза, из неё ключ через scrypt); если их нет — производный от BOT_TOKEN,
и /status об этом предупреждает. Утечка одной базы (бэкап) не раскрывает
чужие входы. Задали ключ — при запуске все записи перешифровываются
(rotate_all), старые ключи остаются запасными для расшифровки. В логи и
ответы значение не попадает.

Куки проверяются примерно раз в час и заодно держат сессию живой;
разлогиненная помечается expired, и человеку один раз приходит сообщение.
Проверки — вразнобой (keepalive_due, раз в минуту смотрит, чья очередь): у
каждого входа своё время; первые JITTER_CHECKS проверок — через случайные
50–59 мин, чтобы входы разошлись по часу и запросы в СДО не шли пачкой,
дальше ровно через 55.
"""

import hashlib
import logging
import random
import re
from datetime import datetime, timedelta, UTC

import httpx

from kapibara.features.sdo import net as sdo_net
from kapibara.core.config import SDO_BASE_URL, SDO_SESSION_COOKIE, is_starosta
# шифрование — общее для всех секретов в базе (kapibara/core/crypto); отсюда его брали раньше
from kapibara.core.crypto import decrypt, encrypt, key_source, needs_rotation  # noqa: F401
from kapibara.core.errors import NETWORK, aside

logger = logging.getLogger(__name__)

COOKIE_RE = re.compile(r"^[A-Za-z0-9,\-]{16,128}$")


def clean_cookie(raw: str) -> str | None:
    """Значение из поля ввода: «MoodleSession=abc», «abc;», с пробелами —
    всё сводим к самому значению. None — не похоже на куку."""
    value = (raw or "").strip().strip(";").strip()
    if "=" in value:
        value = value.split("=", 1)[1].strip()
    value = value.strip('"').strip()
    return value if COOKIE_RE.match(value) else None


def client_for(cookie: str, **kwargs) -> httpx.AsyncClient:
    return sdo_net.client(cookie, timeout=kwargs.pop("timeout", 30), **kwargs)


async def check(cookie: str) -> bool:
    """True — кука рабочая (СДО пускает на /my/). Сетевая ошибка —
    исключение: «СДО не отвечает» не значит «вход устарел»."""
    from kapibara.features.sdo.net import SdoSessionExpired, get_checked
    async with client_for(cookie) as client:
        try:
            await get_checked(client, f"{SDO_BASE_URL}/my/")
        except SdoSessionExpired:
            return False
    return True


async def cookie_for(user_id: int) -> str | None:
    """Рабочая кука человека. У старосты, если он свою не подключал, —
    общая из переменных хостинга (SDO_SESSION_COOKIE): это и есть его вход.
    Общая протухла — живой вход другого его аккаунта (backup_login)."""
    from database import get_sdo_session
    row = await get_sdo_session(user_id)
    if row and row["status"] == "ok":
        return decrypt(row["cookie_enc"])
    if not row and is_starosta(user_id):
        if SDO_SESSION_COOKIE and await shared_alive():
            return SDO_SESSION_COOKIE
        if backup := await backup_login():
            return backup[1]
        return SDO_SESSION_COOKIE or None
    return None


async def backup_login() -> tuple[int, str] | None:
    """Живой вход приложения, которым бот ходит в СДО за свою группу, когда
    общая кука с сервера протухла: сначала входы аккаунтов старосты (у Никиты
    их несколько — вошёл с одного, работают все), потом люди своей группы,
    согласные делиться дедлайнами. СДО лежал 10 часов (15–16.11), общая кука
    умерла, а вход, который Никита тут же сделал в приложении, синк не брал.
    → (user_id, кука) или None."""
    from database import get_group_donors, get_sdo_session
    from database.groups import home
    from kapibara.core.config import STAROSTA_IDS
    rows = [r for uid in STAROSTA_IDS if uid and (r := await get_sdo_session(uid)) and r["status"] == "ok"]
    rows += await get_group_donors(home())
    for r in rows:
        if cookie := decrypt(r["cookie_enc"]):
            return r["user_id"], cookie
    return None


async def status_for(user_id: int) -> dict:
    from database import get_sdo_session
    row = await get_sdo_session(user_id)
    if row:
        from kapibara.features.groups import groups
        g = await groups.of_user(user_id)
        return {"state": "ok" if row["status"] == "ok" else "expired", "checked_at": row["checked_at"],
                "share": bool(row.get("share")), "can_share": bool(g and not g["own"]),
                "group": g["name"] if g else ""}
    if is_starosta(user_id) and SDO_SESSION_COOKIE:
        # общая кука тоже протухает (ночной сбой СДО 16.11): раньше тут всегда
        # было «работает», а баллы говорили «устарел» — и подключить свой вход
        # было неоткуда. Теперь — как есть; свой вход приложения предлагают всегда.
        alive = await shared_alive() or bool(await backup_login())
        return {"state": "ok" if alive else "expired", "checked_at": None, "shared": True}
    return {"state": "off"}


# Общая кука старосты (SDO_SESSION_COOKIE) протухла — в настройках запоминаем
# её отпечаток, а не «да/нет»: поменяли куку на сервере — новая сразу считается
# живой, не дожидаясь часовой проверки.
SHARED_DEAD = "sdo:shared_dead"


def _fingerprint(cookie: str) -> str:
    return hashlib.sha256(cookie.encode()).hexdigest()[:16]


async def note_shared(alive: bool):
    """Чем кончилась проверка общей куки (keepalive, синк, запрос старосты)."""
    from database import set_setting
    if SDO_SESSION_COOKIE:
        await set_setting(SHARED_DEAD, "" if alive else _fingerprint(SDO_SESSION_COOKIE))


async def shared_alive() -> bool:
    from database import get_setting
    return bool(SDO_SESSION_COOKIE) and (await get_setting(SHARED_DEAD) or "") != _fingerprint(SDO_SESSION_COOKIE)


async def mark_expired(user_id: int):
    """СДО не пустил с кукой человека: свой вход — expired; своего нет, а это
    староста — значит, протухла общая кука (её и брали, cookie_for)."""
    from database import set_sdo_status
    if await set_sdo_status(user_id, "expired"):
        return
    if is_starosta(user_id) and SDO_SESSION_COOKIE:
        await note_shared(False)


JITTER_CHECKS = 3           # столько первых проверок — через случайные 50–59 мин
JITTER_RANGE = (50, 59)
STEADY_MINUTES = 55


def _utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")       # как datetime('now') в SQLite


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def next_interval(jitter_left: int) -> int:
    return random.randint(*JITTER_RANGE) if jitter_left > 0 else STEADY_MINUTES


def first_check_at(now: datetime | None = None) -> str:
    """Только что подключили (и проверили) — следующая проверка через 50–59 мин."""
    return _utc((now or _now()) + timedelta(minutes=random.randint(*JITTER_RANGE)))


# Как человек вошёл (sdo_sessions.via): page — страницей СДО в приложении на
# телефоне, silent — приложение само обновило протухший вход той же страницей
# в фоне (единый вход МИРЭА ещё помнил человека), paste — вставкой куки.
VIA = ("page", "silent", "paste")


def expired_text(via: str | None) -> str:
    """Вход вошедшего страницей приложение обновит само при следующем открытии,
    если единый вход МИРЭА его ещё помнит, — так и пишем, без «войди заново»."""
    if via in ("page", "silent"):
        return ("🎓 Вход в СДО устарел. Открой Капибару на телефоне — если МИРЭА тебя ещё "
                "помнит, вход обновится сам. Если нет — войди заново: СДО → Вход.")
    return ("🎓 Вход в СДО устарел — баллы и сдача работ в приложении пока не работают.\n"
            "Подключи заново: приложение → СДО → Вход.")


def expired_push(via: str | None) -> str:
    """Текст пуша под заголовком «Вход в СДО устарел» — что делать."""
    if via in ("page", "silent"):
        return "Открой Капибару — если МИРЭА тебя помнит, вход обновится сам"
    return "Баллы и сдача работ не работают. Подключи заново: СДО → Вход"


async def _check_one(row: dict, bot=None, now: datetime | None = None):
    from database import set_sdo_next_check, set_sdo_status, update_sdo_cookie
    uid, enc = row["user_id"], row["cookie_enc"]
    cookie = decrypt(enc)
    if cookie is None:
        # не расшифровалась — дело в ключе на сервере, а не во входе студента:
        # не помечаем протухшим и не пишем ему (иначе смена ключа «разлогинит» всех)
        logger.error(f"СДО keepalive {uid}: кука не расшифровывается — проверь SDO_CRYPT_KEY/PASSPHRASE")
        return
    if needs_rotation(enc):
        new_enc = encrypt(cookie)
        if await update_sdo_cookie(uid, new_enc, only_if=enc):   # на новый ключ
            enc = new_enc
    left = row.get("jitter_left")
    left = JITTER_CHECKS if left is None else left
    now = now or _now()
    try:
        alive = bool(cookie) and await check(cookie)
    except NETWORK as e:
        logger.info(f"СДО keepalive {uid}: {type(e).__name__}")
        await set_sdo_next_check(uid, _utc(now + timedelta(minutes=next_interval(left))), left)
        return
    # пока шла проверка, человек мог подключить новый вход — его статус не трогаем
    if not await set_sdo_status(uid, "ok" if alive else "expired", only_if=enc):
        return
    if alive:
        await set_sdo_next_check(uid, _utc(now + timedelta(minutes=next_interval(left))), max(0, left - 1))
        from kapibara.features.notifications import grade_alerts             # новые баллы — у каждого в его время (Никита 02.11)
        grade_alerts.check_soon(bot, uid, cookie, now)
    elif bot:
        with aside(logger, f"СДО: не смог сказать {uid}, что вход устарел", level=logging.INFO):
            from kapibara.features.notifications.delivery import deliver
            from kapibara.core.telegram import app_button
            await deliver(bot, uid, expired_text(row.get("via")), kind="sdo", tab="sdo",
                          title="Вход в СДО устарел", body=expired_push(row.get("via")), reply_markup=app_button("🎓 Подключить СДО", "sdo"))


async def keepalive_due(bot=None, now: datetime | None = None):
    """Раз в минуту (scheduler.py): проверить входы, чья очередь подошла.
    Вход без времени (подключён до этой версии) не проверяется сразу, а
    получает случайное место в ближайшем часе — после деплоя не все разом."""
    from database import get_sdo_sessions, set_sdo_next_check
    now = now or _now()
    for row in await get_sdo_sessions("ok"):
        due = row.get("next_check_at")
        if not due:
            left = row.get("jitter_left")
            await set_sdo_next_check(row["user_id"], _utc(now + timedelta(minutes=random.randint(1, STEADY_MINUTES))),
                                     JITTER_CHECKS if left is None else left)
        elif due <= _utc(now):
            await _check_one(row, bot, now)


async def rotate_all() -> dict:
    """Перешифровать все входы (и устаревшие) на основной ключ — при запуске,
    чтобы после SDO_CRYPT_KEY/фразы не ждать проверки каждого входа.
    → {"rotated": сколько, "unreadable": не расшифровались ни одним ключом}."""
    from database import get_sdo_sessions, update_sdo_cookie
    out = {"rotated": 0, "unreadable": 0}
    for status in ("ok", "expired"):
        for row in await get_sdo_sessions(status):
            enc = row["cookie_enc"]
            if not needs_rotation(enc):
                continue
            cookie = decrypt(enc)
            if cookie is None:
                out["unreadable"] += 1
            elif await update_sdo_cookie(row["user_id"], encrypt(cookie), only_if=enc):
                out["rotated"] += 1
    if out["rotated"] or out["unreadable"]:
        logger.info(f"СДО: перешифровано входов {out['rotated']}, не расшифровались {out['unreadable']}")
    return out


async def keepalive_all(bot=None):
    """Проверить все подключённые входы сразу (вручную/в тестах)."""
    from database import get_sdo_sessions
    for row in await get_sdo_sessions("ok"):
        await _check_one(row, bot)

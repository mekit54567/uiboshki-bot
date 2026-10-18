"""152-ФЗ (сервер в России, Amvera): согласие, «удалить все мои данные», срок
хранения. Тексты — legal_texts.py (страницы /consent и /privacy, JSON
/api/legal/<имя> — webapp/routes/legal.py).

Согласие (ст. 9) — отдельной галочкой, по умолчанию не стоит: общее (`pd`) —
при первом входе (бот — кнопка «Даю согласие», PWA и приложение — лист), на
вход в СДО (`sdo`) — своя галочка у поля куки, без неё сервер куку не берёт.
Поменял текст согласия по смыслу — подними VERSION: всех спросят заново.

Срок хранения: год без заходов — всё стирается той же erase_user; запросы
решалки — полгода.

«Удалить мои данные» (Никита 18.10) — вводом фразы ERASE_PHRASE руками.
Сразу — согласия, выход со всех устройств и из СДО, обработка встаёт
(blocked): ни рассылок, ни ИИ, ни событий. Полностью стирается через
ERASE_DAYS дней (purge); до этого староста может восстановить по заявке
(/undelete), без гарантии. Отказ от согласия до первого входа — сразу (erase)."""

import logging
import os

from config import STAROSTA_IDS

logger = logging.getLogger(__name__)

VERSION = "2"                  # 16.10: Amvera и «Капибара+» (касса, чек, приглашения)
DATE = "16.10.2026"
KINDS = ("pd", "sdo")
VIAS = ("bot", "pwa", "tg", "app")

INACTIVE_DAYS = 365
SOLVER_DAYS = 180
ERASE_DAYS = 7                 # «удалил по ошибке» — столько дней можно попросить восстановить
ERASE_PHRASE = "удалить мои данные"
ANSWER_DAYS = 10               # ответ на запрос о данных — рабочих дней (ст. 14 ч. 3, ст. 20)

# Кто оператор и как связаться — в текстах согласия и политики (legal_texts.py).
# ФИО, ИНН, почта и город — переменные окружения PD_FIO, PD_INN, PD_EMAIL,
# PD_CITY (задаёт Никита на хостинге); пока пусто — в текстах их нет.
FIO = os.getenv("PD_FIO", "").strip()
INN = os.getenv("PD_INN", "").strip()
EMAIL = os.getenv("PD_EMAIL", "").strip()
CITY = os.getenv("PD_CITY", "").strip()
OPERATOR = ", ".join(x for x in (
    f"самозанятый {FIO or 'Никита'}, разработчик сервиса «Капибара»",
    f"ИНН {INN}" if INN else "", f"г. {CITY}" if CITY else "") if x)
# Исполнитель в оферте — со статусом плательщика НПД: он нужен по смыслу
# договора (чек — из «Мой налог»). Тексты про персональные данные берут
# оператора выше, а не эту строку.


def contractor() -> str:
    return ", ".join(x for x in (
        FIO or "Никита, разработчик сервиса «Капибара»",
        "плательщик налога на профессиональный доход",
        f"ИНН {INN}" if INN else "") if x)


CONTACT = "Telegram @Partykq" + (f" или почта {EMAIL}" if EMAIL else "")
CONTACT_URL = "https://t.me/Partykq"


def backup_days() -> int:
    """Сколько живёт ночная копия базы: хранилище — 7 дней по кругу, Telegram —
    оператор удаляет старше 30 дней (Никита 18.10: Telegram — ненадолго, до S3)."""
    import s3_store
    return 7 if s3_store.configured() else 30


def backup_texts() -> dict:
    """Где резервные копии базы и как уходят запросы за границу — для
    legal_texts: своё хранилище в России (BACKUP_S3_*, s3_store.py) или файлом
    оператору в Telegram (ОАЭ); туннель Xray (XRAY_CONFIG, страна —
    PROXY_COUNTRY) или сеть хостинга. Копии — не дольше 30 дней (ст. 21 ч. 5)."""
    import s3_store
    if os.getenv("XRAY_CONFIG", "").strip() or os.getenv("OUT_PROXY", "").strip():
        country = os.getenv("PROXY_COUNTRY", "").strip()
        proxy = ("Запросы к Telegram и ИИ уходят с сервера через зашифрованный туннель на сервер оператора"
                 + (f" в {country}" if country else " за границей")
                 + ": содержимое там не хранится и не расшифровывается (HTTPS). СДО МИРЭА, VK и Яндекс — напрямую.")
    else:
        proxy = ("Запросы к Telegram и ИИ уходят с сервера через сеть хостинга Amvera в зашифрованном виде "
                 "(HTTPS): по пути их содержимое не видно и не хранится. СДО МИРЭА, VK и Яндекс — напрямую.")
    if s3_store.configured():
        return {
            "PROXY": proxy,
            "BACKUP_WHERE": "Раз в сутки делается резервная копия базы и ложится в хранилище в России "
                            f"({s3_store.provider()}). Хранятся копии за последние 7 дней, каждая новая "
                            "заменяет недельной давности, поэтому удалённое из базы уходит из копий за 7 дней.",
            "BACKUP_TO": f"{s3_store.provider()} (Россия) — хранение резервной копии базы, по поручению "
                         "оператора;",
            "BACKUP_ERASE": "когда копия сменится новой, не позже чем через 7 дней",
        }
    return {
        "PROXY": proxy,
        "BACKUP_WHERE": "Раз в сутки делается резервная копия базы и приходит оператору в Telegram "
                        "(Telegram FZ-LLC, ОАЭ). Копии старше 30 дней оператор удаляет вручную, поэтому "
                        "удалённое из базы может до 30 дней оставаться в копиях.",
        "BACKUP_TO": "Telegram FZ-LLC (ОАЭ) — хранение ночной резервной копии базы у оператора;",
        "BACKUP_ERASE": "не позже чем через 30 дней, когда оператор удаляет старые копии",
    }


def operator_missing() -> list[str]:
    """Каких данных оператора нет в текстах — предупреждение старосте в /status."""
    return [k for k, v in (("PD_FIO", FIO), ("PD_INN", INN), ("PD_EMAIL", EMAIL), ("PD_CITY", CITY)) if not v]

_seen: dict[int, str] = {}     # id → день последней отметки (пишем раз в день)
_given: set[tuple[int, str, str]] = set()   # (id, вид, версия) — уже дал, в базу не ходим


async def needs(user_id: int, kind: str = "pd") -> bool:
    from database.privacy import has_consent
    if (user_id, kind, VERSION) in _given:
        return False
    if await has_consent(user_id, kind, VERSION):
        _given.add((user_id, kind, VERSION))
        return False
    return True


async def blocked(user_id: int) -> bool:
    """Нельзя обрабатывать (кроме самого согласия, /privacy и /deleteme):
    согласия нет и человек новый. Без событий статистики, без имени и ника в
    базе, без рассылок. Кто был до согласий (users.legacy — пара своих),
    пользуется и без него (Никита, 11.10). Давал согласие прошлой версии
    текста — тоже: новую спросят один раз (ask_once), не блокируя (переезд
    16.10). Старосты — операторы."""
    if user_id in STAROSTA_IDS or not await needs(user_id):
        return False
    from database.privacy import has_any_consent, is_legacy
    if await erasing(user_id):       # попросил удалить — до полного стирания ничего не обрабатываем
        return True
    return not await is_legacy(user_id) and not await has_any_consent(user_id)


async def should_ask(user_id: int) -> bool:
    """Кто был до согласий или давал прошлую версию и ещё не видел просьбу
    этой версии (без отметки)."""
    if user_id in STAROSTA_IDS or not await needs(user_id):
        return False
    if await erasing(user_id):
        return False
    from database.privacy import asked_version
    return await asked_version(user_id) != VERSION


async def ask_once(user_id: int) -> bool:
    """Кто был до согласий: спросить один раз на версию текста — ботом или
    листом в приложении, что раньше. True — спросить сейчас (отметка уже в
    базе, после деплоя не повторится)."""
    if user_id in STAROSTA_IDS or not await needs(user_id):
        return False
    if await erasing(user_id):
        return False
    from database.privacy import mark_asked
    return await mark_asked(user_id, VERSION)


async def give(user_id: int, kind: str, via: str):
    from database.privacy import give_consent
    if kind not in KINDS:
        raise ValueError(kind)
    due = await erasing(user_id)
    if due:
        raise Erasing(erasing_text(due))
    await give_consent(user_id, kind, VERSION, via if via in VIAS else "pwa")
    _given.add((user_id, kind, VERSION))


async def seen(user_id: int):
    """Отметить заход (для срока хранения) — не чаще раза в день."""
    from datetime import date
    today = date.today().isoformat()
    if _seen.get(user_id) == today:
        return
    _seen[user_id] = today
    from database._conn import write_later
    from database.privacy import touch_seen
    await write_later(touch_seen(user_id))      # запрос этого не ждёт; ошибка — в лог


async def erase(user_id: int) -> dict:
    """Всё о человеке — из базы и кэшей. Из ночных копий базы — когда они
    сменятся (backup_texts, политика это говорит)."""
    from database.privacy import erase_user
    try:
        import apple_signin
        await apple_signin.revoke_for(user_id)    # вход через Apple — отозвать у Apple (их правило)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"отзыв входа Apple: {e}")
    from database.service import drop_events
    from database.users import forget_user
    drop_events(user_id)
    done = await erase_user(user_id, STAROSTA_IDS)
    forget_user(user_id)
    _seen.pop(user_id, None)
    _given.difference_update({g for g in _given if g[0] == user_id})
    try:
        import sdo_grades
        sdo_grades.forget(user_id)
    except Exception:
        pass
    logger.info(f"удалены данные человека: {sum(done.values())} строк")
    return done


def phrase_ok(text: str) -> bool:
    """Фраза подтверждения введена руками: регистр, «ё», пробелы, кавычки и
    точка в конце не важны."""
    t = " ".join((text or "").lower().replace("ё", "е").split()).strip(" .!«»\"'")
    return t == ERASE_PHRASE.replace("ё", "е")


async def erasing(user_id: int) -> str | None:
    """Попросил удалить данные: день полного стирания (ГГГГ-ММ-ДД) или None."""
    from database.privacy import erase_due
    return await erase_due(user_id)


def fmt_day(day: str) -> str:
    y, m, d = day.split("-")
    return f"{d}.{m}.{y}"


async def request_erase(user_id: int, bot=None) -> str:
    """«Удалить мои данные»: сразу — согласия, входы на устройствах и в СДО,
    пуши; обработка встаёт. Полностью — через ERASE_DAYS дней (purge).
    Старосте — сообщение с /undelete на случай заявки. Возвращает день."""
    from datetime import timedelta

    from database.privacy import request_erase as _request
    from utils import today_msk
    due = await erasing(user_id) or (today_msk() + timedelta(days=ERASE_DAYS)).isoformat()
    await _request(user_id, due)
    _given.difference_update({g for g in _given if g[0] == user_id})
    try:
        import sdo_grades
        sdo_grades.forget(user_id)
    except Exception:
        pass
    logger.info(f"запрос на удаление данных, полностью — {due}")
    if bot and STAROSTA_IDS:
        from database import get_user
        from utils import esc
        u = await get_user(user_id) or {}
        name = esc(u.get("full_name") or u.get("username") or "без имени")
        try:
            await bot.send_message(
                STAROSTA_IDS[0], f"🗑 {name} (<code>{user_id}</code>) удаляет свои данные: полностью — "
                f"{fmt_day(due)}. Попросит вернуть до этого — <code>/undelete {user_id}</code>.",
                parse_mode="HTML")
        except Exception as e:
            logger.info(f"удаление: старосте не ушло: {e}")
    return due


def erasing_text(due: str) -> str:
    """Что сказать тому, кто попросил удалить данные, — бот, API, приложение."""
    day = fmt_day(due)
    return (f"Твои данные будут удалены полностью {day}. До этой даты они только хранятся, никак "
            "не используются и никому не видны. Вход на всех устройствах и в СДО уже прекращён. "
            f"Повторный вход до {day} удаление не отменяет. Если данные удалены по ошибке, "
            f"напиши {CONTACT} до {day}: восстановить их можно только вручную и без гарантии. "
            f"После {day} данные восстановить нельзя: при новом входе аккаунт будет создан "
            "заново, без прежних данных. Из резервных копий базы данные удаляются в течение "
            f"{backup_days()} дней после полного удаления.")


class Erasing(Exception):
    """Попросил удалить данные — согласие и вход до полного стирания не берём."""


async def undo_erase(user_id: int) -> bool:
    """Восстановить по заявке (староста, /undelete): данные на месте, кроме
    входов и согласий — согласие спросят заново."""
    from database.privacy import cancel_erase
    return await cancel_erase(user_id)


async def purge():
    """Раз в сутки (scheduler): попросил удалить и прошло ERASE_DAYS — стереть
    полностью; год без заходов — тоже; старые запросы решалки."""
    from database.privacy import due_erasures, inactive_users, purge_solver_history
    from utils import today_msk
    for uid in await due_erasures(today_msk().isoformat()):
        await erase(uid)
    gone = [u for u in await inactive_users(INACTIVE_DAYS) if u not in STAROSTA_IDS]
    for uid in gone:
        await erase(uid)
    n = await purge_solver_history(SOLVER_DAYS)
    if gone or n:
        logger.info(f"срок хранения: людей {len(gone)}, запросов решалки {n}")

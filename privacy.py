"""152-ФЗ (сервер в России, Amvera): согласие, «удалить все мои данные», срок
хранения. Тексты — legal_texts.py (страницы /consent и /privacy, JSON
/api/legal/<имя> — webapp/routes/legal.py).

Согласие (ст. 9) — отдельной галочкой, по умолчанию не стоит: общее (`pd`) —
при первом входе (бот — кнопка «Даю согласие», PWA и приложение — лист), на
вход в СДО (`sdo`) — своя галочка у поля куки, без неё сервер куку не берёт.
Поменял текст согласия по смыслу — подними VERSION: всех спросят заново.

Срок хранения: год без заходов — всё стирается той же erase_user; запросы
решалки — полгода."""

import logging
import os

from config import STAROSTA_IDS

logger = logging.getLogger(__name__)

VERSION = "2"                  # 2 — сервер в России (Amvera), Ling среди получателей
DATE = "16.10.2026"
KINDS = ("pd", "sdo")
VIAS = ("bot", "pwa", "tg", "app")

INACTIVE_DAYS = 365
SOLVER_DAYS = 180
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
CONTACT = "Telegram @Partykq" + (f" или почта {EMAIL}" if EMAIL else "")
CONTACT_URL = "https://t.me/Partykq"


def backup_texts() -> dict:
    """Где резервные копии базы — для legal_texts: своё хранилище в России
    (BACKUP_S3_*, s3_store.py) или файлом оператору в Telegram (ОАЭ)."""
    import s3_store
    if s3_store.configured():
        return {
            "BACKUP_WHERE": "Раз в сутки делается резервная копия базы и ложится в хранилище в России "
                            f"({s3_store.provider()}). Копии за последние 7 дней сменяют друг друга сами, "
                            "копия на первое число месяца — через год, поэтому удалённое из базы может ещё "
                            "какое-то время оставаться в копиях.",
            "BACKUP_TO": f"{s3_store.provider()} (Россия) — хранение резервной копии базы, по поручению "
                         "оператора;",
            "BACKUP_ERASE": "когда копия сменится новой (ежедневные — за неделю, месячные — за год)",
        }
    return {
        "BACKUP_WHERE": "Раз в сутки делается резервная копия базы и приходит оператору в Telegram "
                        "(Telegram FZ-LLC, ОАЭ). Старые копии оператор удаляет вручную раз в месяц, поэтому "
                        "удалённое из базы может ещё какое-то время оставаться в копиях.",
        "BACKUP_TO": "Telegram FZ-LLC (ОАЭ) — хранение ночной резервной копии базы у оператора;",
        "BACKUP_ERASE": "когда оператор вручную удаляет старые копии, раз в месяц",
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
    return not await is_legacy(user_id) and not await has_any_consent(user_id)


async def should_ask(user_id: int) -> bool:
    """Кто был до согласий или давал прошлую версию и ещё не видел просьбу
    этой версии (без отметки)."""
    if user_id in STAROSTA_IDS or not await needs(user_id):
        return False
    from database.privacy import asked_version
    return await asked_version(user_id) != VERSION


async def ask_once(user_id: int) -> bool:
    """Кто был до согласий: спросить один раз на версию текста — ботом или
    листом в приложении, что раньше. True — спросить сейчас (отметка уже в
    базе, после деплоя не повторится)."""
    if user_id in STAROSTA_IDS or not await needs(user_id):
        return False
    from database.privacy import mark_asked
    return await mark_asked(user_id, VERSION)


async def give(user_id: int, kind: str, via: str):
    from database.privacy import give_consent
    if kind not in KINDS:
        raise ValueError(kind)
    await give_consent(user_id, kind, VERSION, via if via in VIAS else "pwa")
    _given.add((user_id, kind, VERSION))


async def seen(user_id: int):
    """Отметить заход (для срока хранения) — не чаще раза в день."""
    from datetime import date
    today = date.today().isoformat()
    if _seen.get(user_id) == today:
        return
    _seen[user_id] = today
    try:
        from database.privacy import touch_seen
        await touch_seen(user_id)
    except Exception as e:
        logger.info(f"last_seen: {e}")


async def erase(user_id: int) -> dict:
    """Всё о человеке — из базы и кэшей. Из ночных копий базы — когда они
    сменятся (backup_texts, политика это говорит)."""
    from database.privacy import erase_user
    done = await erase_user(user_id, STAROSTA_IDS)
    _seen.pop(user_id, None)
    _given.difference_update({g for g in _given if g[0] == user_id})
    try:
        import sdo_grades
        sdo_grades.forget(user_id)
    except Exception:
        pass
    logger.info(f"удалены данные человека: {sum(done.values())} строк")
    return done


async def purge():
    """Раз в сутки (scheduler): год без заходов — стереть; старые запросы решалки."""
    from database.privacy import inactive_users, purge_solver_history
    gone = [u for u in await inactive_users(INACTIVE_DAYS) if u not in STAROSTA_IDS]
    for uid in gone:
        await erase(uid)
    n = await purge_solver_history(SOLVER_DAYS)
    if gone or n:
        logger.info(f"срок хранения: людей {len(gone)}, запросов решалки {n}")

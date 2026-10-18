"""
Здоровье бота для старосты (/status): всё держится на куке СДО владельца и
бесплатных лимитах ИИ — пусть поломка видна раньше, чем о ней напишут в чат.

  • note(key, ok, detail) — «когда и чем кончилось» для синка СДО, проверки
    куки и бэкапа; лежит в settings (переживает перезапуск);
  • ErrorCounter — считает ошибки и предупреждения в логах за сутки по
    разделам (ИИ, СДО, расписание…), в памяти процесса;
  • report() — текст /status.
"""

import json
import logging
import math
import time
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

from config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)
STARTED = datetime.now(TZ)
DAY = 24 * 3600

# Раздел по имени логгера (модуля): первое совпадение по началу имени
AREAS = [("ai_solver", "ИИ"), ("gemini_solver", "ИИ"), ("lecture_summary", "ИИ"), ("handlers.solver", "ИИ"),
         ("webapp.routes.chat", "ИИ"), ("sdo", "СДО"), ("grade_alerts", "СДО"), ("webapp.routes.sdo", "СДО"),
         ("schedule", "Расписание"), ("mirea_schedule_api", "Расписание"), ("backup", "Бэкап")]


def area_of(name: str) -> str:
    return next((label for prefix, label in AREAS if name.startswith(prefix)), "Прочее")


class ErrorCounter(logging.Handler):
    """Ошибки (ERROR и выше) и предупреждения за последние сутки."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records: deque = deque(maxlen=2000)     # (время, уровень, раздел, текст)

    def emit(self, record):
        try:
            self.records.append((time.time(), record.levelno, area_of(record.name),
                                 record.getMessage()[:160]))
        except Exception:
            pass                                      # статистика ошибок сама не падает

    def last_day(self) -> list[tuple]:
        since = time.time() - DAY
        return [r for r in self.records if r[0] >= since]


counter = ErrorCounter()


def install():
    """Подключить счётчик к корневому логгеру (bot.py при запуске). Повторно — не дублирует."""
    root = logging.getLogger()
    if counter not in root.handlers:
        root.addHandler(counter)


# Всплеск ошибок — старосте сам, не дожидаясь /status: внешнего трекера
# ошибок нет, а узнать о поломке от одногруппников — поздно.
ALERT_MIN = 5              # ошибок (ERROR) за час — повод написать
ALERT_EVERY = 3 * 3600     # не чаще раза в три часа
_alerted_at = 0.0


def error_spike(now: float | None = None) -> str | None:
    """Текст тревоги, если за последний час ошибок ≥ ALERT_MIN и давно не
    писали; иначе None. Сама отметка «написали» — здесь же."""
    global _alerted_at
    now = now or time.time()
    errs = [r for r in counter.records if r[0] >= now - 3600 and r[1] >= logging.ERROR]
    if len(errs) < ALERT_MIN or now - _alerted_at < ALERT_EVERY:
        return None
    _alerted_at = now
    by_area: dict[str, int] = {}
    for r in errs:
        by_area[r[2]] = by_area.get(r[2], 0) + 1
    areas = " · ".join(f"{a} — {n}" for a, n in sorted(by_area.items(), key=lambda x: -x[1]))
    from utils import esc
    return (f"⚠️ <b>За час {len(errs)} ошибок</b>: {esc(areas)}\n"
            f"Последняя: <code>{esc(errs[-1][3])}</code>\nПодробнее — /status")


async def alert_errors(bot):
    """Раз в 15 минут (scheduler): всплеск ошибок — старосте."""
    from config import STAROSTA_ID
    text = error_spike()
    if text and STAROSTA_ID:
        try:
            await bot.send_message(STAROSTA_ID, text, parse_mode="HTML")
        except Exception as e:
            logging.getLogger(__name__).info(f"тревога об ошибках не ушла: {e}")


async def _idle_timeout() -> str:
    """Срок жизни сессии СДО без обращений (core_session_time_remaining): «2 ч», «1 ч 30 мин»."""
    from database import get_setting
    try:
        sec = int(await get_setting("sdo:idle_timeout") or 0)
    except ValueError:
        return ""
    if sec <= 0:
        return ""
    h, m = divmod(round(sec / 60), 60)
    return " ".join(x for x in (f"{h} ч" if h else "", f"{m} мин" if m else "") if x) or "меньше минуты"


async def note(key: str, ok: bool, detail: str = ""):
    """Запомнить, чем кончилась проверка (sdo_sync, sdo_cookie, backup)."""
    try:
        from database import set_setting
        await set_setting(f"health:{key}", json.dumps(
            {"at": datetime.now(TZ).isoformat(), "ok": ok, "detail": detail[:200]}, ensure_ascii=False))
    except Exception as e:
        logging.getLogger(__name__).info(f"health.note {key}: {e}")


async def _get(key: str) -> dict | None:
    from database import get_setting
    raw = await get_setting(f"health:{key}")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _when(iso: str, now: datetime) -> str:
    t = datetime.fromisoformat(iso).astimezone(TZ)
    if t.date() == now.date():
        return f"сегодня {t:%H:%M}"
    if (now.date() - t.date()).days == 1:
        return f"вчера {t:%H:%M}"
    return f"{t:%d.%m %H:%M}"


def _ago(seconds: float) -> str:
    h = int(seconds // 3600)
    return f"{h // 24} д {h % 24} ч" if h >= 24 else f"{h} ч {int(seconds % 3600 // 60)} мин" if h else f"{int(seconds // 60)} мин"


def _line(n: dict | None, title: str, now: datetime, never: str) -> str:
    from utils import esc
    if not n:
        return f"▫️ {title} — {never}"
    mark = "✅" if n["ok"] else "⚠️"
    detail = f": {esc(n['detail'])}" if n.get("detail") else ""
    return f"{mark} {title} — {_when(n['at'], now)}{detail}"


def version() -> str:
    """Последняя версия из CHANGELOG.md и changelog.d/ («v5.2.0 «Имя»»)."""
    import re

    from tools.changelog import full_text
    try:
        text = full_text()
        found = re.findall(r"^### (v\d+\.\d+\.\d+ «[^»]+»)", text, re.M)
        return found[-1] if found else ""
    except OSError:
        return ""


# Задержка цикла событий (16.10, Amvera: ответы бота по 45–146 с): раз в
# секунду спим 1 с и смотрим, на сколько проснулись позже. Большая задержка —
# цикл занят (тяжёлый код без to_thread или не хватает процессора), а не база.
_LAGS: deque = deque(maxlen=3600)       # (когда, задержка, с) — за последний час
LAG_WARN = 2.0


async def watch_loop(period: float = 1.0):
    import asyncio
    while True:
        t = time.monotonic()
        await asyncio.sleep(period)
        lag = time.monotonic() - t - period
        _LAGS.append((time.time(), lag))
        if lag >= LAG_WARN:
            logging.getLogger(__name__).warning(f"бот завис на {lag:.1f} с (цикл событий занят)")


def loop_lag(now: float | None = None) -> float:
    """Самая большая задержка за последний час, с."""
    now = now or time.time()
    return max((lag for t, lag in _LAGS if now - t <= 3600), default=0.0)


_SLOW: deque = deque(maxlen=500)       # (когда, путь, с) — запросы приложения дольше SLOW_REQ
SLOW_REQ = 5.0


def note_request(path: str, seconds: float, now: float | None = None) -> None:
    """Долгий запрос к API (webapp/server.py) — в «Сервер» у /status: какие
    разделы отвечают по 40–60 с (17.10 по метрикам Amvera были такие)."""
    if seconds >= SLOW_REQ:
        _SLOW.append((now or time.time(), path, seconds))
        logging.getLogger(__name__).info(f"долгий запрос {path}: {seconds:.1f} с")


def slow_requests(now: float | None = None, top: int = 3) -> tuple[int, list[tuple[str, float]]]:
    """(сколько долгих за час, самые долгие пути — по худшему разу)."""
    now = now or time.time()
    recent = [(p, s) for t, p, s in _SLOW if now - t <= 3600]
    worst: dict[str, float] = {}
    for p, s in recent:
        worst[p] = max(worst.get(p, 0.0), s)
    return len(recent), sorted(worst.items(), key=lambda x: -x[1])[:top]


async def db_probe() -> tuple[str, float, float]:
    """(режим журнала, чтение мс, запись мс) — свежим подключением, как у
    обработчиков: открыть базу + прочитать, открыть + записать в settings."""
    from database._conn import connect
    t = time.monotonic()
    async with connect() as db:
        mode = (await (await db.execute("PRAGMA journal_mode")).fetchone())[0]
        await (await db.execute("SELECT value FROM settings WHERE key='health:probe'")).fetchone()
    read = (time.monotonic() - t) * 1000
    t = time.monotonic()
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('health:probe', ?)",
                         (datetime.now(TZ).isoformat(),))
        await db.commit()
    return mode, read, (time.monotonic() - t) * 1000


async def report() -> str:
    from config import SDO_SESSION_COOKIE
    from database import get_sdo_sessions
    from schedule_parser import stale_label
    now = datetime.now(TZ)
    up = (now - STARTED).total_seconds()
    lines = [f"🩺 <b>Состояние бота</b> · {version()}",
             f"Работает {_ago(up)} (запущен {_when(STARTED.isoformat(), now)})", ""]
    import privacy
    if missing := privacy.operator_missing():      # тексты /consent и /privacy без оператора (152-ФЗ)
        lines += [f"⚠️ В согласии и политике нет данных оператора: задай {', '.join(missing)}", ""]
    import billing
    if billing.provider(configured_only=True) and billing.missing_requisites():
        lines += ["⚠️ Касса задана, но оплата «Капибары+» закрыта: в оферте нет реквизитов — задай "
                  + ", ".join(billing.missing_requisites()), ""]

    lines.append("<b>Сервер</b>")
    try:
        mode, read, write = await db_probe()
        warn = "⚠️ " if mode != "wal" or read > 300 or write > 300 else ""
        lines.append(f"{warn}База: {mode}, чтение {read:.0f} мс, запись {write:.0f} мс")
    except Exception as e:
        lines.append(f"⚠️ база: {type(e).__name__}: {e}")
    lag = loop_lag()
    lines.append(("⚠️ " if lag >= LAG_WARN else "") + f"Самое долгое зависание за час: {lag:.1f} с")
    n, worst = slow_requests()
    lines += [f"Долгих запросов (от {SLOW_REQ:.0f} с) за час: {n} — "
              + ", ".join(f"{p} {s:.0f} с" for p, s in worst) if n
              else f"Долгих запросов (от {SLOW_REQ:.0f} с) за час нет", ""]

    lines.append("<b>СДО</b>")
    if not SDO_SESSION_COOKIE:
        lines.append("⚠️ Кука СДО не задана (SDO_SESSION_COOKIE) — синк дедлайнов выключен")
    else:
        lines.append(_line(await _get("sdo_cookie"), "Кука жива", now, "ещё не проверялась после запуска"))
        if idle := await _idle_timeout():
            lines.append(f"Сессия СДО без запросов живёт {idle} (бот заходит раз в 55 мин)")
        lines.append(_line(await _get("sdo_sync"), "Синк дедлайнов", now, "ещё не было"))
    ok, expired = len(await get_sdo_sessions("ok")), len(await get_sdo_sessions("expired"))
    lines.append(f"Входы студентов: {ok} работают" + (f" · {expired} устарели" if expired else ""))
    import sdo_accounts
    if (ok or expired) and sdo_accounts.key_source() == "bot_token":   # 152-ФЗ: ключ отдельно от токена бота
        lines.append("⚠️ Входы зашифрованы ключом от BOT_TOKEN — задай на хостинге SDO_CRYPT_PASSPHRASE "
                     "(длинная фраза) или SDO_CRYPT_KEY")

    lines += ["", "<b>Расписание</b>"]
    stale = stale_label()
    lines.append(f"⚠️ Зеркало МИРЭА не отвечает — показываю расписание от {stale}" if stale
                 else "✅ Свежее")

    lines += ["", "<b>Поиск по смыслу</b>"]
    try:
        import semantic_index
        st = await semantic_index.stats()
        lines.append(f"Лекций в индексе: {st['files']}" + (f" · ждут {st['waiting']}" if st["waiting"] else "") +
                     f" · фрагментов {st['chunks']}, с векторами {st['embedded']}"
                     + ("" if st.get("provider", "gemini") == "gemini" else f" (своя модель {st['provider']})"))
        if not st["vectors"]:
            lines.append("⚠️ sqlite-vec не загрузился — ищу только по словам")
    except Exception as e:
        lines.append(f"⚠️ индекс недоступен: {type(e).__name__}")

    lines += ["", "<b>ИИ</b>"]
    try:
        import ai_quota
        import config
        import gemini_solver
        from utils import esc
        total, top = await ai_quota.summary()
        limit = f" · лимит {config.AI_DAILY_LIMIT} на человека" if config.AI_DAILY_LIMIT else " · дневного лимита нет"
        lines.append(f"Вопросов сегодня: {total}, у самого активного — {top}{limit}")
        if config.OPENROUTER_API_KEY and gemini_solver.AI_SPARE_MODEL:
            mode = await gemini_solver.ai_main()
            n = gemini_solver.answered
            lines.append(f"Ling ({esc(gemini_solver.AI_SPARE_MODEL)}) основная: {gemini_solver.MAIN_MODES[mode]}"
                         " · сменить — /aimain")
            if sum(n.values()):
                lines.append(f"С запуска ответили: Ling {n['ling']}, Gemini {n['gemini']}"
                             + (f" · Ling не смогла {n['ling_failed']}" if n["ling_failed"] else ""))
        rest, spare = gemini_solver.rest_status()
        if rest > 0:
            lines.append(f"⚠️ {esc(config.GEMINI_MODEL)} упёрлась в лимит — ещё {math.ceil(rest / 60)} мин отвечают "
                         f"запасные: {esc(', '.join(spare))}")
    except Exception as e:
        lines.append(f"⚠️ не узнал: {type(e).__name__}")

    lines += ["", "<b>Бэкап</b>", _line(await _get("backup"), "Копия базы", now, "ещё не было (каждую ночь в 04:40)")]

    errors = [r for r in counter.last_day() if r[1] >= logging.ERROR]
    warns = [r for r in counter.last_day() if r[1] < logging.ERROR]
    lines += ["", "<b>Ошибки за сутки</b>" + ("" if up >= DAY else " (с запуска)")]
    if not errors and not warns:
        lines.append("✅ Ни одной")
    else:
        from collections import Counter
        from utils import esc
        by_area = Counter(r[2] for r in errors)
        if errors:
            lines.append("❌ Ошибки: " + " · ".join(f"{a} {n}" for a, n in by_area.most_common()))
            t, _, area, text = errors[-1]
            lines.append(f"Последняя {datetime.fromtimestamp(t, TZ):%H:%M} ({area}): {esc(text)}")
        if warns:
            lines.append("⚠️ Предупреждения: " + " · ".join(
                f"{a} {n}" for a, n in Counter(r[2] for r in warns).most_common()))
    return "\n".join(lines)

"""СДО: свой вход студента, сдача работ, баллы БРС, экран задания и
подписанные ссылки /sdl на файлы из СДО."""

import logging
import re

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from kapibara.core.config import is_starosta
from webapp import deps
from webapp.deps import CurrentUser

from kapibara.core.errors import NETWORK, log_failure

logger = logging.getLogger(__name__)

EXPIRED = "вход в СДО устарел — подключи заново: вкладка СДО → Вход"
SDO_DOWN = "СДО сейчас не отвечает — попробуй позже"


async def _from_sdo(user_id: int, what: str, call):
    """Запрос в СДО входом человека — граница (ADR 0004) для всех экранов СДО:
    курса нет — 404, вход протух — 403 и экран «Подключить заново», СДО не
    ответил — 502 одной строкой в лог, баг у нас — 502 с traceback."""
    from kapibara.features.sdo.parser import SdoSessionExpired
    try:
        return await call
    except (KeyError, IndexError) as e:     # тоже LookupError, но это баг разбора, а не «курса нет»
        log_failure(logger, what, e)
        raise HTTPException(status_code=502, detail=SDO_DOWN) from e
    except LookupError:
        raise HTTPException(status_code=404, detail="курс не найден") from None
    except SdoSessionExpired:
        from database import set_sdo_status
        await set_sdo_status(user_id, "expired")
        raise HTTPException(status_code=403, detail=EXPIRED) from None
    except Exception as e:      # граница: человеку «не отвечает», в лог — сеть строкой, баг с traceback
        log_failure(logger, what, e)
        raise HTTPException(status_code=502, detail=SDO_DOWN) from e


_NO = object()      # «шаг не вышел» — отличить от None-ответа


async def _aside(what: str, call, default=None):
    """Необязательный шаг экрана СДО (история баллов, отметка «сдал»,
    посещения): не вышел — экран всё равно открывается, а баг виден в
    /status с traceback (раньше — строкой info, без следа)."""
    try:
        return await call()
    except Exception as e:      # граница шага: экран важнее, ошибка — в лог
        log_failure(logger, what, e)
        return default

router = APIRouter()


# ── СДО: свой вход и сдача работ (sdo_accounts.py, sdo_submit.py) ───────────

class SdoConnect(BaseModel):
    cookie: str
    agree: bool = False    # галочка «Даю согласие» у поля куки (152-ФЗ, privacy.py)
    via: str = ""          # page | silent | paste — от этого зависит, что бот напишет, когда вход устареет


class SdoFile(BaseModel):
    name: str
    data: str  # base64


class SdoSubmit(BaseModel):
    deadline_id: int = 0
    cmid: int = 0
    name: str = ""
    data: str = ""  # base64 — один файл (старый формат)
    files: list[SdoFile] = []
    replace: bool = False  # «Редактировать ответ»: новые файлы вместо прежних


class SdoRemove(BaseModel):
    cmid: int


@router.get("/api/sdo/status")
async def api_sdo_status(user: dict = CurrentUser):
    from kapibara.features.sdo.accounts import status_for
    return dict(await status_for(user["id"]), starosta=is_starosta(user["id"]))


@router.post("/api/sdo/connect")
async def api_sdo_connect(body: SdoConnect, user: dict = CurrentUser,
                          x_telegram_init_data: str = Header(default=""), x_app: str = Header(default="")):
    from kapibara.features.privacy import privacy
    from kapibara.features.sdo import accounts as sdo_accounts
    from database import save_sdo_session
    from kapibara.core import ratelimit
    if not body.agree and await privacy.needs(user["id"], "sdo"):
        raise HTTPException(status_code=400, detail="поставь галочку согласия на обработку данных из СДО")
    if not ratelimit.allow("sdo_connect", user["id"]):
        raise HTTPException(status_code=429, detail="слишком много попыток — попробуй через 10 минут")
    cookie = sdo_accounts.clean_cookie(body.cookie)
    if not cookie:
        raise HTTPException(status_code=400, detail="не похоже на MoodleSession — скопируй значение целиком")
    try:
        alive = await sdo_accounts.check(cookie)
    except NETWORK as e:
        log_failure(logger, "СДО: проверка куки", e)
        raise HTTPException(status_code=502, detail="СДО сейчас не отвечает — попробуй позже") from e
    if not alive:
        raise HTTPException(status_code=400, detail="СДО не пускает с этой кукой — войди на сайте заново и скопируй новую")
    if body.agree:
        from webapp.routes.legal import _via
        await privacy.give(user["id"], "sdo", _via(x_telegram_init_data, x_app))
    via = body.via if body.via in sdo_accounts.VIA else "paste"
    await save_sdo_session(user["id"], sdo_accounts.encrypt(cookie), sdo_accounts.first_check_at(), via)
    from kapibara.features.sdo import grades as sdo_grades
    sdo_grades.forget(user["id"])
    return await sdo_accounts.status_for(user["id"])


class SdoShare(BaseModel):
    share: bool


@router.post("/api/sdo/share")
async def api_sdo_share(body: SdoShare, user: dict = CurrentUser):
    """Делиться дедлайнами СДО с группой (этап 1 (в), group_sync.py): по
    этому входу бот берёт задания всей группы. Баллы и работы человека никто
    не видит — только список заданий и сроки."""
    from database import set_sdo_share
    from database.groups import home, viewer_group
    from kapibara.features.sdo.accounts import status_for
    # своя группа берёт задания по общему входу старосты; «делиться» тут создавало
    # дубли всех дедлайнов СДО (sdo:<группа>:<id> рядом с sdo:<id>) — ревью 09.10
    if body.share and await viewer_group(user["id"]) == home():
        raise HTTPException(status_code=400, detail="в этой группе задания из СДО и так приходят")
    if not await set_sdo_share(user["id"], body.share):
        raise HTTPException(status_code=400, detail="сначала подключи СДО")
    if body.share:
        from kapibara.core.tasks import spawn
        from kapibara.features.groups import sync as group_sync
        from database import get_user_group
        gid = await get_user_group(user["id"])
        if gid:
            spawn(group_sync.sync_group(gid), name="group_sync")     # задания группы — сразу, не ждать 6 ч
    return await status_for(user["id"])


@router.post("/api/sdo/disconnect")
async def api_sdo_disconnect(user: dict = CurrentUser):
    from database import delete_sdo_session
    from kapibara.features.sdo.accounts import status_for
    await delete_sdo_session(user["id"])
    from kapibara.features.sdo import grades as sdo_grades
    sdo_grades.forget(user["id"])
    return await status_for(user["id"])


@router.get("/api/sdo/submit-rules")
async def api_sdo_submit_rules(cmid: int = 0, deadline_id: int = 0, user: dict = CurrentUser):
    """Что принимает задание — показать в листе «Сдать» до выбора файлов:
    типы («только .zip»), сколько файлов и какой размер."""
    from kapibara.features.sdo import accounts as sdo_accounts
    from kapibara.features.sdo import submit as sdo_submit
    from database import get_deadline, set_sdo_status
    from kapibara.features.sdo.parser import SdoSessionExpired
    if not cmid:
        d = await get_deadline(deadline_id)
        if not d or not sdo_submit.can_submit(d):
            raise HTTPException(status_code=404, detail="это не задание из СДО")
        cmid = sdo_submit.cmid_of(d["description"])
    cookie = await sdo_accounts.cookie_for(user["id"])
    if not cookie:
        raise HTTPException(status_code=403, detail="сначала подключи СДО: вкладка СДО → Вход")
    try:
        return await sdo_submit.submission_rules(cookie, cmid)
    except SdoSessionExpired:
        await set_sdo_status(user["id"], "expired")
        raise HTTPException(status_code=403, detail="вход в СДО устарел — подключи заново: вкладка СДО → Вход") from None
    except sdo_submit.SubmitError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/api/sdo/submit")
async def api_sdo_submit(body: SdoSubmit, user: dict = CurrentUser):
    import base64
    from kapibara.features.sdo import accounts as sdo_accounts
    from kapibara.features.sdo import submit as sdo_submit
    from database import get_deadline, set_sdo_status
    from kapibara.features.sdo.parser import SdoSessionExpired
    from kapibara.core import ratelimit
    if not ratelimit.allow("submit", user["id"]):
        raise HTTPException(status_code=429, detail="слишком много сдач подряд — попробуй через 10 минут")
    if body.cmid:
        cmid = body.cmid     # из «Текущего контроля»: задание своего курса, сдаёт своим входом
    else:
        d = await get_deadline(body.deadline_id)
        if not d or not sdo_submit.can_submit(d):
            raise HTTPException(status_code=404, detail="это не задание из СДО")
        cmid = sdo_submit.cmid_of(d["description"])
    cookie = await sdo_accounts.cookie_for(user["id"])
    if not cookie:
        raise HTTPException(status_code=403, detail="сначала подключи СДО: вкладка СДО → Вход")
    items = body.files or [SdoFile(name=body.name, data=body.data)]
    # число и размер — до раскодирования: тело с сотней файлов по 20 МБ держало бы
    # в памяти гигабайты и роняло процесс (ревью безопасности 09.10)
    if len(items) > sdo_submit.MAX_FILES:
        raise HTTPException(status_code=400, detail=f"за раз — не больше {sdo_submit.MAX_FILES} файлов")
    if any(len(it.data) > sdo_submit.MAX_BYTES * 4 // 3 + 4 for it in items):
        raise HTTPException(status_code=413, detail="файл больше 20 МБ — СДО такой не примет")
    files = []
    try:
        for it in items:
            clean = re.sub(r'[\\/:*?"<>|]+', "_", it.name).strip() or "работа"
            files.append((clean[:120], base64.b64decode(it.data, validate=False)))
    except (ValueError, TypeError):     # binascii.Error — тоже ValueError
        raise HTTPException(status_code=400, detail="файл повреждён") from None
    try:
        result = await sdo_submit.submit_file(cookie, cmid, files=files, replace=body.replace)
    except SdoSessionExpired:
        await set_sdo_status(user["id"], "expired")
        raise HTTPException(status_code=403, detail="вход в СДО устарел — подключи заново: вкладка СДО → Вход") from None
    except sdo_submit.SdoUnavailable as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except sdo_submit.SubmitError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        # 3.3: что угодно ещё (обрыв, таймаут, странный ответ СДО) — не 500, а
        # понятный текст: файл мог и дойти, человек проверит в СДО
        log_failure(logger, f"СДО: сдача в задание {cmid} у {user['id']} упала", e)
        raise HTTPException(status_code=502, detail=sdo_submit.UNAVAILABLE) from e
    logger.info(f"СДО: {user['id']} сдал файл в задание {cmid}")
    from kapibara.features.sdo import grades as sdo_grades
    sdo_grades.forget(user["id"])    # статусы и баллы — заново
    from kapibara.features.sdo import done as sdo_done
    # приложение рисует «Сдано» только для submitted; черновик и непонятный
    # ответ СДО — другим экраном (аудит 21.10, R5)
    result = dict(result, state=sdo_done.submit_state(result.get("status")))
    if result["state"] == "submitted":   # ушло на проверку — дедлайн у себя сданным (черновик — нет)
        await _aside("отметка «сдал» после сдачи", lambda: sdo_done.mark(user["id"], [cmid]))
    return result


@router.post("/api/sdo/submission/remove")
async def api_sdo_remove_submission(body: SdoRemove, user: dict = CurrentUser):
    """«Удалить ответ» на задание — своим входом, как кнопка в СДО (пока ответ
    не оценён и срок не прошёл — иначе СДО сам не даст)."""
    from kapibara.core import ratelimit
    from kapibara.features.sdo import accounts as sdo_accounts
    from kapibara.features.sdo import grades as sdo_grades
    from kapibara.features.sdo import submit as sdo_submit
    from database import set_sdo_status
    from kapibara.features.sdo.parser import SdoSessionExpired
    if not ratelimit.allow("submit", user["id"]):
        raise HTTPException(status_code=429, detail="слишком много действий подряд — попробуй через 10 минут")
    cookie = await sdo_accounts.cookie_for(user["id"])
    if not cookie:
        raise HTTPException(status_code=403, detail="сначала подключи СДО: вкладка СДО → Вход")
    try:
        result = await sdo_submit.remove_submission(cookie, body.cmid)
    except SdoSessionExpired:
        await set_sdo_status(user["id"], "expired")
        raise HTTPException(status_code=403, detail="вход в СДО устарел — подключи заново: вкладка СДО → Вход") from None
    except sdo_submit.SubmitError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info(f"СДО: {user['id']} удалил ответ в задании {body.cmid}")
    sdo_grades.forget(user["id"])
    return result


# ── Баллы БРС из СДО (sdo_grades.py) ─────────────────────────────────────────

async def _sdo_cookie(user_id: int) -> str:
    from kapibara.features.sdo.accounts import cookie_for
    cookie = await cookie_for(user_id)
    if not cookie:
        raise HTTPException(status_code=403, detail="подключи СДО, чтобы видеть свои баллы")
    return cookie


@router.get("/api/sdo/grades")
async def api_sdo_grades(fresh: bool = False, user: dict = CurrentUser):
    from kapibara.features.sdo import grades as sdo_grades
    cookie = await _sdo_cookie(user["id"])
    from kapibara.core import ratelimit
    if fresh and not ratelimit.allow("sdo_fresh", user["id"]):
        fresh = False              # «обновить» чаще 3 раз за 5 минут — из кэша, СДО не долбим
    data = await _from_sdo(user["id"], "Баллы СДО", sdo_grades.overview(user["id"], cookie, fresh=fresh))
    from kapibara.features.sdo import history as sdo_history          # точка истории баллов на сегодня (график на экране предмета)
    await _aside("история баллов", lambda: sdo_history.record(user["id"], data.get("courses") or []))
    from kapibara.features.sdo import goal as sdo_goal                 # свои цели по предметам («4» вместо ближайшей «3»)
    return {**data, "goals": await sdo_goal.get_goals(user["id"])}


@router.get("/api/sdo/grades/{course_id}")
async def api_sdo_course(course_id: int, user: dict = CurrentUser):
    from kapibara.features.sdo import grades as sdo_grades
    cookie = await _sdo_cookie(user["id"])
    data = await _from_sdo(user["id"], f"Баллы СДО, курс {course_id}", sdo_grades.course_detail(user["id"], cookie, course_id))
    from kapibara.features.sdo import history as sdo_history
    history = await _aside("история баллов", lambda: sdo_history.series(user["id"], course_id, data.get("score")), _NO)
    if history is not _NO:
        data = {**data, "history": history}
    from kapibara.features.sdo import done as sdo_done             # зачтено или ждёт оценки — дедлайн у себя сданным
    await _aside("отметка «сдал» по журналу", lambda: sdo_done.mark(user["id"], sdo_done.finished(data)))
    from kapibara.features.schedule import attendance           # посещения лекций из баллов за посещаемость
    att = await _aside("посещения", lambda: attendance.for_course(user["id"], data), _NO)
    if att is not _NO:
        data = {**data, "attendance": att}
    return {**data, "goal": await _goal(user["id"], data)}


async def _goal(user_id: int, course: dict) -> dict:
    """Цель по предмету: сколько не хватает, откуда взять, правило 75 % (sdo_goal.py)."""
    from kapibara.features.sdo import goal as sdo_goal
    goals = await sdo_goal.get_goals(user_id)
    modes = await sdo_goal.get_modes(user_id)
    cid = str(course["id"])
    return sdo_goal.plan(course, course.get("attendance"), goals.get(cid), modes.get(cid))


class Goal(BaseModel):
    label: str | None = None     # «зачёт», «3», «4», «5»; None — снять свою цель
    mode: str | None = None      # "auto" — автомат, "exam" — с экзаменом; None — не менять


@router.post("/api/sdo/goal/{course_id}")
async def api_sdo_goal(course_id: int, body: Goal, user: dict = CurrentUser):
    """Своя цель по предмету — только для подсчёта в боте, на СДО не влияет."""
    from kapibara.features.schedule import attendance
    from kapibara.features.sdo import goal as sdo_goal
    from kapibara.features.sdo import grades as sdo_grades
    cookie = await _sdo_cookie(user["id"])
    course = await _from_sdo(user["id"], f"СДО: курс {course_id}",
                             sdo_grades.course_detail(user["id"], cookie, course_id, stale_ok=True))
    if body.label is not None and body.label not in [m["label"] for m in course.get("marks") or []]:
        raise HTTPException(status_code=400, detail="такой оценки у предмета нет")
    if body.mode is not None and body.mode not in sdo_goal.MODES:
        raise HTTPException(status_code=400, detail="счёт цели — auto или exam")
    if body.mode is not None:
        await sdo_goal.set_mode(user["id"], course_id, body.mode)
        if body.label is not None:
            await sdo_goal.set_goal(user["id"], course_id, body.label)
    else:
        await sdo_goal.set_goal(user["id"], course_id, body.label)
    att = await _aside("посещения", lambda: attendance.for_course(user["id"], course))
    return await _goal(user["id"], {**course, "attendance": att})


class AttendanceMark(BaseModel):
    day: str
    mark: str | None = None      # "ok" — был, "excused" — уважительная, None — снять


@router.post("/api/sdo/attendance/{course_id}")
async def api_attendance_mark(course_id: int, body: AttendanceMark, user: dict = CurrentUser):
    """Своя отметка для лекции до начала истории посещаемости: какие именно
    лекции засчитаны, по баллам не видно — человек отмечает сам, но не больше,
    чем показывают баллы. Только для показа в боте, на СДО не влияет."""
    from kapibara.features.schedule import attendance
    from kapibara.features.sdo import grades as sdo_grades
    from database import get_attendance_marks, set_attendance_mark
    cookie = await _sdo_cookie(user["id"])
    course = await _from_sdo(user["id"], f"СДО: курс {course_id}",
                             sdo_grades.course_detail(user["id"], cookie, course_id, stale_ok=True))
    blank = await attendance.for_course(user["id"], course, manual={})
    marks = await get_attendance_marks(user["id"], course_id)
    why = attendance.check_mark(blank, marks, body.day, body.mark)
    if why:
        raise HTTPException(status_code=400, detail=why)
    await set_attendance_mark(user["id"], course_id, body.day, body.mark)
    return await attendance.for_course(user["id"], course)


# ── Задание СДО: описание, файлы преподавателя, сдача ────────────────────────
# Файлы из СДО лежат за входом студента (pluginfile.php), а Telegram скачивает
# по обычной ссылке — даём подписанную на 10 минут: /sdl/<токен>/<имя>.

def _sdl_token(user_id: int, path: str, exp: int) -> str:
    import base64
    import hashlib
    import hmac
    payload = base64.urlsafe_b64encode(f"{user_id}|{exp}|{path}".encode()).decode().rstrip("=")
    sig = hmac.new(deps.BOT_TOKEN.encode(), f"sdl:{payload}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def _sdl_parse(token: str) -> tuple[int, str] | None:
    import base64
    import hashlib
    import hmac
    import time
    payload, _, sig = token.partition(".")
    good = hmac.new(deps.BOT_TOKEN.encode(), f"sdl:{payload}".encode(), hashlib.sha256).hexdigest()[:32]
    if not sig or not hmac.compare_digest(sig, good):
        return None
    try:
        uid, exp, path = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().split("|", 2)
    except ValueError:      # не base64, не UTF-8 или не три части — подпись чужая
        return None
    if int(exp) < time.time() or not path.startswith("/pluginfile.php/"):
        return None
    return int(uid), path


@router.get("/api/sdo/task/{cmid}")
async def api_sdo_task(cmid: int, request: Request, module: str = "assign", user: dict = CurrentUser):
    import time
    from urllib.parse import quote, urlparse
    from kapibara.features.sdo import grades as sdo_grades
    if module not in ("assign", "quiz"):
        raise HTTPException(status_code=400, detail="неизвестный тип работы")
    cookie = await _sdo_cookie(user["id"])
    task = await _from_sdo(user["id"], f"Задание СДО {cmid}", sdo_grades.task_detail(cookie, cmid, module))
    base = (deps.WEBAPP_URL or str(request.base_url)).rstrip("/")
    exp = int(time.time()) + 600
    for f in task["files"] + task["mine"]:
        path = urlparse(f.pop("url")).path
        f["dl"] = f"{base}/sdl/{_sdl_token(user['id'], path, exp)}/{quote(f['name'], safe='')}"
    return task


@router.get("/sdl/{token}/{name}")
async def sdo_download(token: str, name: str):
    """Файл из СДО входом того, кому выдана ссылка (через Telegram.WebApp.downloadFile)."""
    import mimetypes
    from urllib.parse import quote
    from kapibara.features.sdo.accounts import client_for, cookie_for
    from kapibara.features.sdo.net import SdoSessionExpired, get_checked
    from kapibara.core.config import SDO_BASE_URL
    parsed = _sdl_parse(token)
    if not parsed:
        raise HTTPException(403, "Ссылка устарела — нажми «📥» ещё раз")
    uid, path = parsed
    cookie = await cookie_for(uid)
    if not cookie:
        raise HTTPException(403, "Вход в СДО не подключён")
    try:
        async with client_for(cookie, timeout=60) as client:
            resp = await get_checked(client, SDO_BASE_URL + path + "?forcedownload=1")
    except SdoSessionExpired:
        raise HTTPException(403, "Вход в СДО устарел") from None
    if resp.status_code != 200 or len(resp.content) > 50 * 1024 * 1024:
        raise HTTPException(404, "Файл не скачался из СДО")
    return Response(resp.content, media_type=resp.headers.get("content-type") or mimetypes.guess_type(name)[0] or "application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}"})

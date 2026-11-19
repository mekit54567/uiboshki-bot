"""Комментарии к ответу на задание СДО (Moodle, assignsubmission_comments) —
строка «Комментарии к ответу» на странице задания (Никита 18.11: «как в СДО,
только красивее; чтобы можно было написать комментарий»).

Moodle рисует их скриптом: на странице задания — вызов
M.core_comment.init(Y, {client_id, itemid, courseid, contextid, component,
commentarea…}), а список и новый комментарий ходят через
/comment/comment_ajax.php (action=get / add, sesskey). Делаем те же запросы
входом студента. Наружу отдаём только автора, время и текст — без client_id
и прочих внутренних номеров.
"""

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

from kapibara.core.config import SDO_BASE_URL
from kapibara.features.sdo import net as sdo_net

logger = logging.getLogger(__name__)

MAX_TEXT = 2000
_INIT = re.compile(r"M\.core_comment\.init\(\s*Y\s*,\s*(\{[^{}]*\})")
_SESSKEY = re.compile(r"\"sesskey\"\s*:\s*\"([A-Za-z0-9]+)\"")
_KEYS = ("client_id", "itemid", "courseid", "contextid", "component", "commentarea")


class CommentError(Exception):
    """Понятный текст для приложения: почему комментарий не ушёл."""


def comment_options(html: str) -> dict | None:
    """Настройки комментариев к ответу со страницы задания; нет — None."""
    for m in _INIT.finditer(html or ""):
        try:
            o = json.loads(m.group(1))
        except ValueError:
            continue
        if not isinstance(o, dict):
            continue
        if o.get("commentarea") != "submission_comments" and o.get("component") != "assignsubmission_comments":
            continue
        opts = {k: str(o.get(k) if o.get(k) is not None else "") for k in _KEYS}
        if opts["client_id"] and opts["itemid"] and opts["contextid"]:
            return opts
    return None


def sesskey_of(html: str) -> str:
    m = _SESSKEY.search(html or "")
    if m:
        return m.group(1)
    el = BeautifulSoup(html or "", "html.parser").find("input", attrs={"name": "sesskey"})
    return str(el.get("value", "")) if el else ""


def _text(content: str) -> str:
    """HTML комментария → текст с переносами строк."""
    soup = BeautifulSoup(content or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all(["p", "div", "li"]):
        p.insert_after("\n")
    lines = [re.sub(r"[ \t\xa0]+", " ", x).strip() for x in soup.get_text().split("\n")]
    return "\n".join(x for x in lines if x)[:MAX_TEXT]


def clean(item: dict) -> dict:
    """Комментарий из ответа Moodle → {author, time, at, text}."""
    at = item.get("timecreated")
    return {
        "author": re.sub(r"\s+", " ", str(item.get("fullname") or "")).strip(),
        "time": re.sub(r"\s+", " ", str(item.get("time") or "")).strip(),
        "at": int(at) if isinstance(at, (int, float)) or (isinstance(at, str) and at.isdigit()) else 0,
        "text": _text(str(item.get("content") or "")),
    }


async def _ajax(client: httpx.AsyncClient, opts: dict, sesskey: str, action: str, **extra) -> dict:
    data = {
        "sesskey": sesskey, "action": action, "client_id": opts["client_id"], "itemid": opts["itemid"],
        "area": opts["commentarea"] or "submission_comments", "courseid": opts["courseid"],
        "contextid": opts["contextid"], "component": opts["component"] or "assignsubmission_comments",
        **extra,
    }
    resp = await client.post(f"{SDO_BASE_URL}/comment/comment_ajax.php", data=data)
    if "/login/index.php" in str(resp.url):
        raise sdo_net.SdoSessionExpired("вход устарел")
    try:
        res = resp.json()
    except ValueError:
        raise CommentError("СДО ответило не так, как ждали — открой комментарии на сайте") from None
    if not isinstance(res, dict):
        raise CommentError("СДО ответило не так, как ждали — открой комментарии на сайте")
    if res.get("error"):
        raise CommentError("СДО не дало: " + str(res["error"])[:200])
    return res


def _shape(res: dict) -> dict:
    items = [clean(x) for x in (res.get("list") or []) if isinstance(x, dict)]
    items.sort(key=lambda c: c["at"])          # старые сверху, как переписка
    count = res.get("count")
    return {"count": int(count) if isinstance(count, int) else len(items), "items": items, "can_post": True}


async def fetch(client: httpx.AsyncClient, html: str) -> dict | None:
    """Комментарии к ответу по уже открытой странице задания; на странице их нет — None."""
    opts = comment_options(html)
    sesskey = sesskey_of(html)
    if not opts or not sesskey:
        return None
    return _shape(await _ajax(client, opts, sesskey, "get", page="0"))


async def add(cookie: str, cmid: int, text: str) -> dict:
    """Написать комментарий к своему ответу в задании cmid → комментарии заново."""
    text = (text or "").strip()
    if not text:
        raise CommentError("пустой комментарий")
    if len(text) > MAX_TEXT:
        raise CommentError(f"комментарий длиннее {MAX_TEXT} знаков")
    url = f"{SDO_BASE_URL}/mod/assign/view.php?id={cmid}"
    async with sdo_net.client(cookie) as client:
        try:
            html = (await sdo_net.get_checked(client, url)).text
            opts = comment_options(html)
            sesskey = sesskey_of(html)
            if not opts or not sesskey:
                raise CommentError("в этом задании комментарии к ответу закрыты")
            await _ajax(client, opts, sesskey, "add", content=text)
            return _shape(await _ajax(client, opts, sesskey, "get", page="0"))
        except httpx.HTTPError:
            raise CommentError("СДО не ответило — комментарий, возможно, не дошёл; проверь на сайте") from None

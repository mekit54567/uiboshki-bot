"""
Файлы курсов СДО (Moodle) → «Файлы» бота, по предметам и типам, с текстом
для ИИ. Просьба владельца: «давай зальём все файлы, разберись с парсером —
там и файлы, и дедлайны, чтобы ИИ ловил контекст».

Та же кука MoodleSession, что и у синка дедлайнов (sdo_parser.py). Из
облачной сессии разработки СДО недоступен, с Railway — доступен, поэтому
сначала пробный прогон (/sdofiles): что нашлось, куда ляжет, без
сохранения. Выгрузка — только по кнопке старосты.

Откуда что берётся (стандартные страницы Moodle, без API-токенов):
- курсы — AJAX core_course_get_enrolled_courses_by_timeline_classification
  (им же рисуется «Мои курсы»), sesskey — со страницы /my/; если AJAX
  недоступен — ссылки на курсы в профиле (/user/profile.php);
- материалы курса — /course/resources.php?id=… (таблица «раздел —
  название» по всем файлам и папкам курса);
- содержимое папки — ссылки pluginfile.php на /mod/folder/view.php;
- сам файл — /mod/resource/view.php?id=…&redirect=1 (Moodle отдаёт
  редирект на pluginfile.php).

Файл в Telegram попадает так: бот отправляет его старосте без звука,
запоминает file_id и сразу удаляет сообщение (file_id остаётся рабочим).
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from config import SDO_BASE_URL
from file_categories import detect_category
from sdo_parser import SdoSessionExpired

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 45 * 1024 * 1024   # sendDocument бота — до 50 МБ
SEND_PAUSE = 1.1                    # не упираться в лимиты Telegram на отправку


@dataclass
class SdoFile:
    course_id: int
    subject: str
    title: str
    category: str
    source: str                     # "sdo:<cmid>" или "sdo:<cmid>:<имя в папке>"
    url: str                        # resource/view.php?...&redirect=1 или pluginfile.php
    file_name: str = ""             # у ресурса узнаём только при скачивании


@dataclass
class SdoCourse:
    id: int
    name: str
    subject: str
    files: list[SdoFile] = field(default_factory=list)
    error: str = ""
    old: bool = False               # курс прошлого семестра — не выгружаем


def make_client(cookie: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(cookies={"MoodleSession": cookie}, follow_redirects=True, timeout=60)


def _logged_out(resp: httpx.Response) -> bool:
    return "/login/index.php" in str(resp.url)


async def _get_html(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(url)
    if _logged_out(resp):
        raise SdoSessionExpired(f"СДО попросил войти заново ({url})")
    resp.raise_for_status()
    return resp.text


# ── курсы ────────────────────────────────────────────────────────────────────

_COURSE_LINK = re.compile(r"/course/view\.php\?id=(\d+)")
_PROFILE_COURSE_LINK = re.compile(r"/user/view\.php\?id=\d+&(?:amp;)?course=(\d+)")


def parse_sesskey(html: str) -> str | None:
    m = re.search(r'"sesskey":"([^"]+)"', html)
    return m.group(1) if m else None


def parse_course_links(html: str) -> list[dict]:
    """Запасной путь: курсы по ссылкам на странице (профиль, меню)."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        m = _COURSE_LINK.search(a["href"]) or _PROFILE_COURSE_LINK.search(a["href"])
        name = a.get_text(" ", strip=True)
        if m and name and int(m.group(1)) > 1:   # id=1 — главная сайта
            found.setdefault(int(m.group(1)), name)
    return [{"id": i, "name": n} for i, n in found.items()]


async def list_courses(client: httpx.AsyncClient) -> list[dict]:
    html = await _get_html(client, f"{SDO_BASE_URL}/my/")
    sesskey = parse_sesskey(html)
    if sesskey:
        for classification in ("inprogress", "all"):
            method = "core_course_get_enrolled_courses_by_timeline_classification"
            try:
                resp = await client.post(
                    f"{SDO_BASE_URL}/lib/ajax/service.php?sesskey={sesskey}&info={method}",
                    json=[{"index": 0, "methodname": method, "args": {
                        "offset": 0, "limit": 0, "classification": classification, "sort": "fullname"}}],
                )
                data = resp.json()[0]
            except Exception as e:
                logger.info(f"sdo_files: AJAX курсов не ответил: {e}")
                break
            if data.get("error"):
                logger.info(f"sdo_files: AJAX курсов: {data.get('exception')}")
                break
            courses = [{"id": c["id"], "name": c.get("fullname") or c.get("shortname") or str(c["id"])}
                       for c in data["data"]["courses"]]
            if courses:
                return courses
    return parse_course_links(await _get_html(client, f"{SDO_BASE_URL}/user/profile.php"))


# ── предмет по названию курса ────────────────────────────────────────────────

_COURSE_NOISE = re.compile(
    r"\[[^\]]*\]|\([^)]*\)|\b(?:экзамен|зач[её]т|диф\w*|курсов\w+|кп|кр|семестр|осень|весна)\b|\d{2,4}[-/.]\d{2,4}",
    re.I,
)


def clean_course_name(name: str) -> str:
    """«Архитектура_Экзамен [I.26-27]» → «Архитектура»."""
    text = _COURSE_NOISE.sub(" ", name.replace("_", " "))
    return re.sub(r"\s+", " ", text).strip(" .,-—:") or name.strip()


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[а-яёa-z]{3,}", text.lower().replace("ё", "е"))
            if w not in {"для", "and", "the", "при", "основы"}}


def match_subject(course_name: str, subjects: list[str]) -> str:
    """Предмет из расписания группы, похожий на курс СДО (чтобы файлы и
    решалка жили под одним названием), иначе — очищенное имя курса."""
    clean = clean_course_name(course_name)
    course_stems = _stems(clean)
    best, best_score = None, 0.0
    for subject in subjects:
        subj_stems = _stems(subject)
        if not subj_stems or not course_stems:
            continue
        common = len(course_stems & subj_stems)
        score = common / min(len(course_stems), len(subj_stems))
        if common and score > best_score:
            best, best_score = subject, score
    return best if best and best_score >= 0.6 else clean


# ── материалы курса ──────────────────────────────────────────────────────────

_MOD_LINK = re.compile(r"/mod/(resource|folder)/view\.php\?id=(\d+)")


def _link_text(a) -> str:
    for hidden in a.select(".accesshide, .sr-only"):
        hidden.decompose()                      # «Лекция 1 Файл» → «Лекция 1»
    return re.sub(r"\s+", " ", a.get_text(" ", strip=True))


def parse_course_resources(html: str) -> list[dict]:
    """[{kind, cmid, title, section}] со страницы resources.php (раздел — в
    первой ячейке строки и только у первой строки раздела) или со страницы
    курса (раздел — ближайший li.section)."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen, section = [], set(), ""
    for a in soup.find_all("a", href=True):
        m = _MOD_LINK.search(a["href"])
        if not m:
            continue
        row = a.find_parent("tr")
        if row:
            first = row.find(["td", "th"])
            if first and first is not a.find_parent(["td", "th"]) and first.get_text(strip=True):
                section = first.get_text(" ", strip=True)
        else:
            sec = a.find_parent("li", class_="section")
            if sec:
                name = sec.get("data-sectionname") or (sec.select_one(".sectionname") or sec).get_text(" ", strip=True)
                section = name if len(name) < 120 else ""
        cmid = int(m.group(2))
        title = _link_text(a)
        if cmid in seen or not title:
            continue
        seen.add(cmid)
        out.append({"kind": m.group(1), "cmid": cmid, "title": title, "section": section})
    return out


def parse_folder_files(html: str) -> list[dict]:
    """[{url, name}] — файлы внутри папки."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.select('a[href*="/pluginfile.php/"]'):
        url = a["href"].split("?")[0]
        if "/mod_folder/" not in url or url in seen:
            continue
        seen.add(url)
        name = _link_text(a) or unquote(url.rsplit("/", 1)[-1])
        out.append({"url": url + "?forcedownload=1", "name": name})
    return out


def _category(*candidates: str) -> str:
    for text in candidates:
        cat = detect_category(text)
        if cat != "other":
            return cat
    return "other"


def _title_from_name(name: str) -> str:
    from handlers.files import title_from_filename
    return title_from_filename(name)


async def scan_course(client: httpx.AsyncClient, course: dict, subject: str) -> SdoCourse:
    result = SdoCourse(id=course["id"], name=course["name"], subject=subject)
    try:
        items = parse_course_resources(
            await _get_html(client, f"{SDO_BASE_URL}/course/resources.php?id={course['id']}"))
        if not items:   # у курса без «Ресурсов» (или на старой теме) — сама страница курса
            items = parse_course_resources(
                await _get_html(client, f"{SDO_BASE_URL}/course/view.php?id={course['id']}"))
        for it in items:
            if it["kind"] == "resource":
                result.files.append(SdoFile(
                    course_id=course["id"], subject=subject, title=it["title"][:120],
                    category=_category(it["title"], it["section"]),
                    source=f"sdo:{it['cmid']}",
                    url=f"{SDO_BASE_URL}/mod/resource/view.php?id={it['cmid']}&redirect=1",
                ))
                continue
            folder_html = await _get_html(client, f"{SDO_BASE_URL}/mod/folder/view.php?id={it['cmid']}")
            for f in parse_folder_files(folder_html):
                title = _title_from_name(f["name"])
                if len(title) <= 3 or title.isdigit():   # «1.pdf» в папке «Лекции» → «Лекции 1»
                    title = f"{it['title']} {title}"
                result.files.append(SdoFile(
                    course_id=course["id"], subject=subject, title=title[:120],
                    category=_category(f["name"], it["title"], it["section"]),
                    source=f"sdo:{it['cmid']}:{f['name']}", url=f["url"], file_name=f["name"],
                ))
    except SdoSessionExpired:
        raise
    except Exception as e:
        logger.warning(f"sdo_files: курс {course['id']} не прочитался: {e}")
        result.error = str(e) or type(e).__name__
    return result


async def scan(client: httpx.AsyncClient, subjects: list[str]) -> list[SdoCourse]:
    from sdo_parser import is_old_semester
    courses = await list_courses(client)
    out = []
    for c in courses:
        if is_old_semester(c["name"]):   # «…[II.25-26]» осенью — прошлый семестр, владельцу не нужен
            out.append(SdoCourse(id=c["id"], name=c["name"], subject="", old=True))
            continue
        out.append(await scan_course(client, c, match_subject(c["name"], subjects)))
    return out


# ── скачивание и выгрузка ────────────────────────────────────────────────────

def _file_name_from(resp: httpx.Response) -> str:
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)"?', cd, re.I)
    if m:
        return unquote(m.group(1).strip())
    return unquote(urlparse(str(resp.url)).path.rsplit("/", 1)[-1]) or "файл"


class NotAFile(Exception):
    """Ресурс открылся страницей, а не файлом."""


class TooBig(Exception):
    """Больше, чем бот может отправить в Telegram."""


async def download(client: httpx.AsyncClient, f: SdoFile) -> tuple[bytes, str]:
    async with client.stream("GET", f.url) as resp:
        if _logged_out(resp):
            raise SdoSessionExpired("СДО попросил войти заново")
        resp.raise_for_status()
        if "text/html" in resp.headers.get("content-type", "") and "pluginfile.php" not in str(resp.url):
            raise NotAFile(str(resp.url))
        if int(resp.headers.get("content-length") or 0) > MAX_FILE_BYTES:
            raise TooBig()
        data = b""
        async for chunk in resp.aiter_bytes():
            data += chunk
            if len(data) > MAX_FILE_BYTES:
                raise TooBig()
        return data, f.file_name or _file_name_from(resp)


async def import_files(bot, chat_id: int, client: httpx.AsyncClient, files: list[SdoFile],
                       progress=None) -> dict:
    """Выгружает файлы, которых ещё нет в боте (по source). progress(done,
    total) — чтобы обновлять сообщение старосте."""
    from aiogram.types import BufferedInputFile

    from database import add_file, get_file_sources, save_file_text
    from file_text import extract_text

    known = await get_file_sources()
    todo = [f for f in files if f.source not in known]
    stats = {"added": 0, "with_text": 0, "skipped": len(files) - len(todo),
             "failed": 0, "too_big": 0, "not_file": 0}
    for i, f in enumerate(todo, 1):
        try:
            data, name = await download(client, f)
            msg = await bot.send_document(chat_id, BufferedInputFile(data, filename=name),
                                          disable_notification=True)
            tg_file_id = msg.document.file_id if msg.document else None
            try:
                await bot.delete_message(chat_id, msg.message_id)
            except Exception:
                pass
            if not tg_file_id:
                stats["failed"] += 1
                continue
            fid = await add_file(f.title, f.subject, tg_file_id, name, 0, category=f.category, source=f.source)
            stats["added"] += 1
            text = await asyncio.to_thread(extract_text, data, name)
            if text.strip():
                await save_file_text(fid, text)
                stats["with_text"] += 1
            await asyncio.sleep(SEND_PAUSE)
        except SdoSessionExpired:
            stats["expired"] = True
            break
        except TooBig:
            stats["too_big"] += 1
        except NotAFile:
            stats["not_file"] += 1
        except Exception as e:
            logger.warning(f"sdo_files: {f.source} не выгрузился: {e}")
            stats["failed"] += 1
        finally:
            if progress:
                await progress(i, len(todo))
    return stats

"""
Сдача файла в задание СДО (Moodle, mod_assign) от имени студента — так же,
как это делает браузер:

1. GET view.php?id=<cmid>&action=editsubmission — форма ответа: sesskey,
   черновая область файлов (files_filemanager = draft itemid), настройки
   файлового менеджера (client_id, context, id репозитория «Загрузить файл»).
2. POST repository/repository_ajax.php?action=upload — файл в черновик.
   Если файл с таким именем уже есть — action=overwrite, как кнопка
   «Перезаписать» в браузере.
3. POST view.php — сохранить ответ (все поля формы как есть + submitbutton).
4. Если в задании нужно отдельно «Отправить на проверку» — action=submit
   и подтверждение (галочку «это моя работа» человек ставит в WebApp:
   экран «Файл уйдёт преподавателю от твоего имени»).

«Редактировать ответ» (владелец 09.10, 3.3) — тот же путь, но перед загрузкой
черновая область очищается от прежних файлов (draftfiles_ajax.php dir/delete):
новые файлы заменяют старые. «Удалить ответ» — action=removesubmissionconfirm
и POST формы подтверждения (action=removesubmission, sesskey), как кнопка
«Продолжить» в браузере.

Ошибки — SubmitError с понятным текстом для WebApp.
"""

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

import sdo_net
from config import SDO_BASE_URL

logger = logging.getLogger(__name__)

MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 3            # за раз из WebApp (владелец: «до трёх файлов»)
UPLOAD_TIMEOUT = 120     # с на загрузку одного файла: PDF в пару МБ СДО принимает долго (3.3)
# СДО МИРЭА не открылось до сдачи (Никита 18.10: ошибку — там, где не прошло действие)
DOWN = "Сейчас СДО МИРЭА недоступно — попробуй чуть позже"
UNAVAILABLE = "СДО не ответило вовремя — файл, возможно, не дошёл; проверь в СДО и попробуй ещё раз"
CMID_RE = re.compile(r"/mod/(assign|quiz)/view\.php\?(?:[^#\s\"']*&)?id=(\d+)")


class SubmitError(Exception):
    pass


class SdoUnavailable(SubmitError):
    """СДО не ответило или оборвало связь посреди сдачи — файл мог и дойти."""


class NoForm(SubmitError):
    """На странице сдачи нет формы с файлами — причину ищем на странице задания."""


def cmid_of(url: str, quiz: bool = False) -> int | None:
    """Номер задания (cmid) из ссылки mod/assign; quiz=True — и тестов (для
    отметки «сдал», sdo_done; сдавать файлом можно только assign)."""
    for m in CMID_RE.finditer(url or ""):
        if m.group(1) == "assign" or quiz:
            return int(m.group(2))
    return None


def _notice(soup: BeautifulSoup) -> str:
    """Текст ошибки Moodle со страницы (почему не даёт сдать). Плашки внутри
    <noscript> («JavaScript отключен…») — на каждой странице Moodle, живой
    тест 01.10: её показывали вместо настоящей причины."""
    for el in soup.find_all("noscript"):
        el.decompose()
    for sel in (".alert-danger", ".alert-warning", ".errormessage", ".box.errorbox", ".alert",
                "#id_error_files_filemanager", ".invalid-feedback", ".form-control-feedback"):
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(" ", strip=True)[:200]
    return ""


def form_fields(form) -> dict:
    """Поля формы так, как их отправил бы браузер (без кнопок)."""
    data = {}
    for el in form.find_all(["input", "textarea", "select"]):
        name = el.get("name")
        if not name or el.has_attr("disabled"):
            continue
        if el.name == "textarea":
            data[name] = el.get_text()
        elif el.name == "select":
            opt = el.find("option", selected=True) or el.find("option")
            data[name] = opt.get("value", opt.get_text()) if opt else ""
        else:
            kind = (el.get("type") or "text").lower()
            if kind in ("submit", "button", "image", "reset", "file"):
                continue
            if kind in ("checkbox", "radio") and not el.has_attr("checked"):
                continue
            data[name] = el.get("value", "")
    return data


def parse_edit_page(html: str) -> dict:
    """Форма ответа на странице editsubmission → всё, что нужно для загрузки."""
    soup = BeautifulSoup(html, "html.parser")
    area = soup.find("input", attrs={"name": "files_filemanager"})
    if not area:
        if soup.find(attrs={"name": re.compile(r"^onlinetext")}):
            raise SubmitError("в этом задании ответ пишется текстом на сайте, файл не прикрепить")
        raise NoForm(_notice(soup))
    form = area.find_parent("form")
    fields = form_fields(form)
    repo_id = None
    for block in re.findall(r"\{[^{}]*\"type\":\"upload\"[^{}]*\}", html):
        m = re.search(r"\"id\":\"?(\d+)", block)
        if m:
            repo_id = m.group(1)
            break
    itemid = area.get("value", "")
    opts = filemanager_options(html, itemid)
    ctx = (opts.get("context") or {}).get("id") if isinstance(opts.get("context"), dict) else None
    if not ctx:
        m = re.search(r"\"context\":\{\"id\":\"?(\d+)", html) or re.search(r"\"contextid\":\"?(\d+)", html)
        ctx = m and m.group(1)
    client = opts.get("client_id")
    if not client:
        m = re.search(r"\"client_id\":\"([0-9a-z]+)\"", html)
        client = m.group(1) if m else ""
    accepted, labels = accepted_types(opts, soup)
    if not (repo_id and ctx and fields.get("sesskey")):
        raise SubmitError("не разобрал форму сдачи в СДО — сдай на сайте")
    return {
        "action": form.get("action") or f"{SDO_BASE_URL}/mod/assign/view.php",
        "fields": fields,
        "itemid": itemid,
        "sesskey": fields["sesskey"],
        "repo_id": repo_id,
        "ctx_id": str(ctx),
        "client_id": str(client),
        "maxbytes": _int(opts.get("maxbytes")),
        "maxfiles": _int(opts.get("maxfiles")),
        "accepted": accepted,
        "labels": labels,
    }


def _int(v) -> int:
    try:
        return max(0, int(v))          # -1 и 0 у Moodle — «без своего ограничения»
    except (TypeError, ValueError):
        return 0


def filemanager_options(html: str, itemid: str) -> dict:
    """Настройки файлового менеджера ответа — M.form_filemanager.init(Y, {…})
    с itemid поля files_filemanager. Только они: у редактора «ответ текстом»
    свои настройки со списком картинок (.gif … .svgz) и своими лимитами —
    живой случай 04.10: бот брал их и не пускал .docx в задание без
    ограничений. Не нашли — {} (тогда ничего не запрещаем, решает СДО)."""
    dec, found = json.JSONDecoder(), []
    for m in re.finditer(r"M\.form_filemanager\.init\(\s*Y\s*,\s*", html):
        try:
            obj, _ = dec.raw_decode(html, m.end())
        except ValueError:
            continue
        if isinstance(obj, dict):
            found.append(obj)
    for obj in found:
        if str(obj.get("itemid")) == str(itemid):
            return obj
    return found[0] if len(found) == 1 else {}


def accepted_types(opts: dict, soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    """Какие файлы принимает задание — из настроек файлового менеджера ответа и
    подписи СДО под полем файлов («Допустимые типы файлов: Архив (ZIP) .zip»).
    → ([".zip"], ["Архив (ZIP)"]); пустой список — любые. Живой случай 02.10:
    задание брало только ZIP, а бот молча пытался грузить PDF и Word."""
    exts: list[str] = []
    has = "accepted_types" in opts
    if has:
        raw = opts["accepted_types"]
        raw = raw if isinstance(raw, list) else [raw]
        exts = [e.strip().lower() for e in raw if isinstance(e, str) and e.strip().startswith(".")]
        if any(isinstance(e, str) and e.strip() == "*" for e in raw):
            exts = []
    labels = []
    for li in soup.select(".form-filetypes-descriptions li"):
        small = li.find("small")
        tail = small.get_text(" ", strip=True) if small else ""
        if small:
            small.extract()
        name = li.get_text(" ", strip=True)
        if name:
            labels.append(name)
        if not has:        # нет настроек файлового менеджера — расширения из подписи
            exts += [e.lower() for e in re.findall(r"\.[0-9A-Za-z]+", tail)]
    return sorted(set(exts), key=exts.index), labels


def ext_ok(name: str, accepted: list[str]) -> bool:
    return not accepted or any(name.lower().endswith(e) for e in accepted)


def only_text(accepted: list[str]) -> str:
    """«СДО примет здесь только .zip — упакуй работу в ZIP-архив»."""
    text = "СДО примет здесь только " + ", ".join(accepted)
    if accepted == [".zip"]:
        text += " — упакуй работу в ZIP-архив"
    return text


async def submission_rules(cookie: str, cmid: int) -> dict:
    """Что принимает задание — до выбора файлов: {"accepted", "labels",
    "maxfiles", "maxbytes"} или {"closed": почему нельзя сдать}."""
    from sdo_parser import get_checked
    url = f"{SDO_BASE_URL}/mod/assign/view.php?id={cmid}"
    async with sdo_net.client(cookie) as client:
        try:
            resp = await get_checked(client, url + "&action=editsubmission")
            try:
                page = parse_edit_page(resp.text)
            except NoForm as e:
                view = await get_checked(client, url)
                why = str(e) or submission_summary(view.text)
                return {"closed": "СДО не даёт прикрепить файл" + (f": {why}" if why else " — сдача закрыта или срок вышел")}
            except SubmitError as e:
                return {"closed": str(e)}
        except httpx.HTTPError:
            raise SdoUnavailable(DOWN)
    return {k: page[k] for k in ("accepted", "labels", "maxfiles", "maxbytes")}


STATUS_ROWS = ("Состояние ответа", "Оставшееся время", "Последний срок", "Срок сдачи",
               "Submission status", "Time remaining")


def submission_summary(html: str) -> str:
    """Строки таблицы статуса задания: «Состояние ответа: Нет ответа · Оставшееся
    время: Задание просрочено на 5 дн.» — чтобы было видно, почему не сдать."""
    soup = BeautifulSoup(html, "html.parser")
    parts = []
    for row in soup.select("table tr"):
        th, td = row.find("th"), row.find("td")
        if not (th and td):
            continue
        name = th.get_text(" ", strip=True)
        if any(name.startswith(k) for k in STATUS_ROWS):
            parts.append(f"{name}: {td.get_text(' ', strip=True)}")
    return " · ".join(parts)[:300]


def status_text(html: str) -> str:
    """Статус ответа на странице задания: «Отправлено для оценивания» и т.п."""
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one("td.submissionstatussubmitted, td.submissionstatusdraft, "
                         "[class*=submissionstatussubmitted], [class*=submissionstatusdraft]")
    return el.get_text(" ", strip=True) if el else ""


async def _upload(client: httpx.AsyncClient, page: dict, name: str, data: bytes):
    base = {
        "sesskey": page["sesskey"], "repo_id": page["repo_id"], "itemid": page["itemid"],
        "ctx_id": page["ctx_id"], "client_id": page["client_id"], "env": "filemanager",
        "savepath": "/", "title": name, "author": "", "license": "unknown",
        "maxbytes": str(page["maxbytes"] or -1), "areamaxbytes": "-1",
    }
    resp = await client.post(f"{SDO_BASE_URL}/repository/repository_ajax.php?action=upload",
                             data=base, files={"repo_upload_file": (name, data)}, timeout=UPLOAD_TIMEOUT)
    try:
        res = resp.json()
    except ValueError:
        raise SubmitError("СДО не принял файл (ответ не JSON)")
    if isinstance(res, dict) and res.get("error"):
        raise SubmitError("СДО не принял файл: " + str(res["error"])[:200])
    if isinstance(res, dict) and res.get("event") == "fileexists":
        new, old = res.get("newfile") or {}, res.get("existingfile") or {}
        resp = await client.post(f"{SDO_BASE_URL}/repository/repository_ajax.php?action=overwrite", data={
            "sesskey": page["sesskey"], "client_id": page["client_id"], "itemid": page["itemid"],
            "existingfilename": old.get("filename", name), "existingfilepath": old.get("filepath", "/"),
            "newfilename": new.get("filename", ""), "newfilepath": new.get("filepath", "/"),
        })
        try:
            res = resp.json()
        except ValueError:
            res = {}
        if isinstance(res, dict) and res.get("error"):
            raise SubmitError("не вышло заменить старый файл: " + str(res["error"])[:200])


async def _clear_draft(client: httpx.AsyncClient, page: dict):
    """Убрать из черновой области ответа прежние файлы: Moodle кладёт туда уже
    сданные файлы, и без этого новые добавились бы к старым."""
    base = {"sesskey": page["sesskey"], "client_id": page["client_id"], "itemid": page["itemid"]}
    resp = await client.post(f"{SDO_BASE_URL}/repository/draftfiles_ajax.php?action=dir",
                             data=dict(base, filepath="/"))
    try:
        listing = resp.json()
    except ValueError:
        listing = None
    if not isinstance(listing, dict) or not isinstance(listing.get("list"), list):
        raise SubmitError("СДО не показал прежние файлы ответа — замени их на сайте")
    for f in listing["list"]:
        if not isinstance(f, dict):
            continue
        resp = await client.post(f"{SDO_BASE_URL}/repository/draftfiles_ajax.php?action=delete", data=dict(
            base, filepath=f.get("filepath") or "/", filename=f.get("filename") or "."))
        try:
            res = resp.json()
        except ValueError:
            res = None
        if res is False or (isinstance(res, dict) and res.get("error")):
            raise SubmitError(f"не вышло убрать старый файл «{f.get('filename', '')}» — замени на сайте")


async def submit_file(cookie: str, cmid: int, name: str = "", data: bytes = b"",
                      files: list[tuple[str, bytes]] | None = None, replace: bool = False) -> dict:
    """Загрузить файл(ы) в задание cmid одним ответом (до MAX_FILES за раз, но
    не больше, чем разрешает задание); replace — прежние файлы ответа убрать
    («Редактировать ответ»). → {"status": текст статуса в СДО, "url": ...}"""
    from sdo_parser import SdoSessionExpired, get_checked
    files = files or [(name, data)]
    if not files or any(not d for _, d in files):
        raise SubmitError("пустой файл")
    if len(files) > MAX_FILES:
        raise SubmitError(f"за раз — не больше {MAX_FILES} файлов")
    if any(len(d) > MAX_BYTES for _, d in files):
        raise SubmitError("файл больше 20 МБ")
    url = f"{SDO_BASE_URL}/mod/assign/view.php?id={cmid}"
    async with sdo_net.client(cookie, timeout=60) as client:
        try:
            resp = await get_checked(client, url + "&action=editsubmission")
            try:
                page = parse_edit_page(resp.text)
            except NoForm as e:
                view = await get_checked(client, url)
                why = str(e) or submission_summary(view.text)
                logger.warning(f"СДО: нет формы сдачи в задании {cmid} (итоговый URL {resp.url}): {why}")
                raise SubmitError("СДО не даёт прикрепить файл"
                                  + (f": {why}" if why else " — сдача закрыта или срок вышел. Проверь задание на сайте"))
            if page["maxbytes"] > 0 and any(len(d) > page["maxbytes"] for _, d in files):
                raise SubmitError(f"в этом задании файл не больше {page['maxbytes'] // (1024 * 1024) or 1} МБ")
            if page["maxfiles"] > 0 and len(files) > page["maxfiles"]:
                raise SubmitError(f"в этом задании можно прикрепить не больше {page['maxfiles']} файл(ов)")
            bad = [n for n, _ in files if not ext_ok(n, page["accepted"])]
            if bad:
                raise SubmitError(f"«{bad[0]}» не подойдёт: {only_text(page['accepted'])}")
            if replace:
                await _clear_draft(client, page)
            for fname, fdata in files:
                await _upload(client, page, fname, fdata)
            form = dict(page["fields"], submitbutton="Сохранить")
            resp = await client.post(page["action"], data=form)
            if "/login/index.php" in str(resp.url):
                raise SdoSessionExpired("вход устарел")
            soup = BeautifulSoup(resp.text, "html.parser")
            if soup.find("input", attrs={"name": "files_filemanager"}):
                raise SubmitError("СДО не сохранил ответ: " + (_notice(soup) or "проверь задание на сайте"))
            # Черновики: ответ надо ещё «Отправить на проверку»
            if soup.find("input", attrs={"name": "action", "value": "submit"}) or "action=submit" in resp.text:
                resp = await get_checked(client, url + "&action=submit")
                confirm = BeautifulSoup(resp.text, "html.parser").find(
                    "input", attrs={"name": "action", "value": "confirmsubmit"})
                if confirm:
                    form = form_fields(confirm.find_parent("form"))
                    box = confirm.find_parent("form").find("input", attrs={"name": "submissionstatement"})
                    if box is not None:
                        form["submissionstatement"] = box.get("value") or "1"
                    form["submitbutton"] = "Продолжить"
                    resp = await client.post(f"{SDO_BASE_URL}/mod/assign/view.php", data=form)
            resp = await get_checked(client, url)
        except httpx.HTTPError as e:
            logger.warning(f"СДО: сдача в задание {cmid} оборвалась: {type(e).__name__}")
            raise SdoUnavailable(UNAVAILABLE)
    return {"status": status_text(resp.text), "url": url}


async def remove_submission(cookie: str, cmid: int) -> dict:
    """«Удалить ответ» в задании cmid: страница подтверждения → её форма
    (action=removesubmission, sesskey). → {"status": состояние ответа после}."""
    from sdo_grades import parse_assign_page
    from sdo_parser import SdoSessionExpired, get_checked
    url = f"{SDO_BASE_URL}/mod/assign/view.php?id={cmid}"
    async with sdo_net.client(cookie) as client:
        try:
            resp = await get_checked(client, url + "&action=removesubmissionconfirm")
            soup = BeautifulSoup(resp.text, "html.parser")
            btn = soup.find("input", attrs={"name": "action", "value": "removesubmission"})
            if not btn or not btn.find_parent("form"):
                why = _notice(soup)
                raise SubmitError("СДО не даёт удалить ответ" + (f": {why}" if why else
                                                               " — ответ уже оценён или срок прошёл"))
            form = btn.find_parent("form")
            fields = form_fields(form)
            if not fields.get("sesskey"):
                raise SubmitError("не разобрал подтверждение в СДО — удали ответ на сайте")
            resp = await client.post(form.get("action") or f"{SDO_BASE_URL}/mod/assign/view.php", data=fields)
            if "/login/index.php" in str(resp.url):
                raise SdoSessionExpired("вход устарел")
            view = await get_checked(client, url)
        except httpx.HTTPError:
            raise SdoUnavailable(DOWN)
    page = parse_assign_page(view.text)
    if page["submitted"] or "action=removesubmissionconfirm" in view.text:
        raise SubmitError("СДО не удалил ответ: " + (_notice(BeautifulSoup(resp.text, "html.parser"))
                                                     or "проверь задание на сайте"))
    return {"status": page["status"], "url": url}


def can_submit(deadline: dict) -> bool:
    return cmid_of(deadline.get("description") or "") is not None and bool(deadline.get("external_id"))


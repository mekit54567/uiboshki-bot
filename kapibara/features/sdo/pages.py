"""Разбор страниц заданий и тестов СДО (Moodle): статус ответа, сроки,
проходной балл, время теста, описание и файлы преподавателя.

Чистые функции HTML → dict, без сети и базы. Жили в sdo/grades, но их зовут
и сдача работ (sdo/submit), и время тестов (deadlines/quiz_time), а grades
сам зовёт обоих — выходил клубок (03.11). Снаружи можно и из sdo.grades."""
import re

from bs4 import BeautifulSoup


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _activity_dates(soup) -> dict:
    """{подпись без двоеточия, строчными: дата} из [data-region="activity-dates"].
    «Закрыто c:» у МИРЭА пишут латинской «c» — подпись режем до «закрыт…»."""
    out: dict[str, str] = {}
    box = soup.find(attrs={"data-region": "activity-dates"})
    for div in (box.find_all("div") if box else []):
        strong = div.find("strong")
        if not strong:
            continue
        label = _clean(strong.get_text(" ")).rstrip(":").strip().lower()
        value = _clean(div.get_text(" "))[len(_clean(strong.get_text(" "))):].strip()
        if label.startswith("закрыто"):
            label = "закрыто"
        out.setdefault(label, value)
    return out


_TL = re.compile(r"Ограничение по времени\s*:?\s*((?:\d+(?:[.,]\d+)?\s*(?:дн|час|ч|мин|сек)\w*\.?\s*)+)", re.I)
_TL_PART = re.compile(r"(\d+(?:[.,]\d+)?)\s*(дн|час|ч|мин|сек)", re.I)
_TL_UNIT = {"дн": 1440, "час": 60, "ч": 60, "мин": 1, "сек": 1 / 60}


def parse_time_limit(text: str) -> int | None:
    """«Ограничение по времени: 1 час 30 мин.» → 90 (минуты); нет строки — None."""
    m = _TL.search(text or "")
    if not m:
        return None
    total = sum(float(n.replace(",", ".")) * _TL_UNIT[u.lower()] for n, u in _TL_PART.findall(m.group(1)))
    return max(1, int(round(total))) if total > 0 else None


def parse_assign_page(html: str) -> dict:
    """Строки таблицы статуса на странице задания/теста."""
    soup = BeautifulSoup(html, "html.parser")
    rows = {}
    for tr in soup.find_all("tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            rows[_clean(th.get_text(" ")).lower()] = _clean(td.get_text(" "))
    text = _clean(soup.get_text(" "))
    pass_m = re.search(r"Проходн\w+ (?:балл|оценка)\s*:?\s*(\d+(?:[.,]\d+)?)", text)
    status = next((v for k, v in rows.items() if k.startswith("состояние ответа")), "")
    due = next((v for k, v in rows.items() if k.startswith(("срок сдачи", "последний срок"))), "")
    if not due:
        m = re.search(r"Срок сдачи\s*:?\s*([^.]*?\d{4},\s*\d{1,2}:\d{2})", text)
        due = m.group(1) if m else ""
    if not due:
        # тест: «Тест будет закрыт: среда, 15 октября 2026, 23:59»
        m = re.search(r"(?:будет закрыт|закрывается|закрыт)\w*\s*:?\s*([^.]*?\d{4},\s*\d{1,2}:\d{2})", text)
        due = m.group(1) if m else ""
    opens = ""
    m = re.search(r"Открыва\w+\s*:?\s*([^.]*?\d{4},\s*\d{1,2}:\d{2})", text)
    if m:
        opens = m.group(1)
    # блок дат Moodle 4 («Открыто с:», «Открывается:», «Срок сдачи:», «Закрывается:»,
    # «Закрыто c:» — у МИРЭА с латинской «c») — точнее поиска по всему тексту
    dates = _activity_dates(soup)
    due = dates.get("срок сдачи") or dates.get("закрывается") or due
    opens = dates.get("открывается") or opens
    closed = dates.get("закрыто", "")
    unavailable = "этот тест недоступен" in text.lower()      # тест ещё не открыт
    # «Ограничение по времени: 30 мин.» (у тестов) — показываем в списке работ
    # и в «Сдать» (quiz_time.py); «1 час 30 мин.» — сумма частей
    time_limit = parse_time_limit(text)
    low = status.lower()
    draft = "черновик" in low or "draft" in low
    # «Оценено» / «Оценено в» в блоке «Отзыв» — кто и когда поставил оценку
    graded_by = next((v for k, v in rows.items() if k == "оценено"), "")
    graded_at = next((v for k, v in rows.items() if k == "оценено в"), "")
    # «Отзыв в виде комментария» в блоке оценки — что написал преподаватель
    feedback = ""
    for tr in soup.find_all("tr"):
        th, td = tr.find("th"), tr.find("td")
        key = _clean(th.get_text(" ")).lower() if th else ""
        if td and "коммент" in key and ("отзыв" in key or "feedback" in key):
            for br in td.find_all("br"):
                br.replace_with("\n")
            parts = [_clean(el.get_text(" ")) for el in td.find_all(["p", "li", "div"]) if not el.find(["p", "li", "div"])]
            feedback = "\n".join(x for x in parts if x) or _clean(td.get_text(" "))
            break
    return {
        "pass": float(pass_m.group(1).replace(",", ".")) if pass_m else None,
        "status": status,
        # «Черновик (не отправлено)» — тоже со словом «отправлен», но не сдано
        "submitted": not draft and ("для оценивания" in low or "for grading" in low or (
            any(k in low for k in ("отправлен", "submitted")) and not any(k in low for k in ("не отправ", "not submitted"))
            and "не " not in low[:4])),
        "draft": draft,
        "offline": "вне сайта" in low,
        "remaining": next((v for k, v in rows.items() if k.startswith("оставшееся время")), ""),
        "due": due, "opens": opens, "closed": closed, "unavailable": unavailable,
        "time_limit": time_limit, "feedback": feedback[:3000],
        # блок теста со сведениями (попытки, проходная, время) — без строки про
        # время у такого теста ограничения нет (quiz_time.learned)
        "quiz_info": bool(soup.find(class_="quizinfo")),
        "graded_by": graded_by, "graded_at": graded_at,
        "can_submit": bool(soup.find(None, {"name": "action", "value": "editsubmission"})
                           or "action=editsubmission" in html),
    }


_PLUGINFILE = re.compile(r"/pluginfile\.php/")


def _file_name(a) -> str:
    from urllib.parse import unquote, urlparse
    text = _clean(a.get_text(" "))
    if text and "." in text[-6:]:
        return text
    return unquote(urlparse(a["href"]).path.rsplit("/", 1)[-1]) or text or "файл"


def parse_task_page(html: str) -> dict:
    """Страница задания: название, описание (текстом), файлы преподавателя
    (introattachment и вложенные в описание) и свои уже сданные файлы."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find(None, {"role": "main"}) or soup
    # В Moodle 4 описание и файлы задания — в шапке активности (activity-header),
    # она стоит в #region-main ПЕРЕД <div role="main">, а не внутри него.
    region = soup.find(id="region-main") or main
    title_el = main.find(["h2", "h1"]) or soup.find(["h1", "h2"])
    teacher: list[dict] = []
    mine: list[dict] = []
    seen: set[str] = set()
    for a in region.find_all("a", href=_PLUGINFILE):
        href = str(a["href"]).split("?")[0]
        if href in seen:
            continue
        seen.add(href)
        item = {"name": _file_name(a), "url": href}
        (mine if "assignsubmission_file" in href else teacher).append(item)
    intro = region.find(class_=re.compile(r"activity-description")) or region.find(id="intro")
    text = ""
    if intro:
        for a in intro.find_all("a", href=_PLUGINFILE):
            (a.find_parent("li") or a).decompose()
        for br in intro.find_all("br"):
            br.replace_with("\n")
        blocks = [_clean(el.get_text(" ")) for el in intro.find_all(["p", "li", "div"]) if not el.find(["p", "li", "div"])]
        text = "\n".join(b for b in blocks if b) or _clean(intro.get_text(" "))
    out = parse_assign_page(html)
    out.update(title=_clean(title_el.get_text(" ")) if title_el else "", description=text[:3000],
               files=teacher, mine=mine)
    # «Редактировать ответ» / «Удалить ответ» (владелец 09.10, 3.3): ответ уже
    # есть, ещё не оценён, и СДО показывает эти кнопки (срок не прошёл)
    answered = out["submitted"] or out["draft"] or bool(mine)
    grading = next((_clean(td.get_text(" ")).lower() for tr in soup.find_all("tr")
                    if (th := tr.find("th")) and (td := tr.find("td"))
                    and _clean(th.get_text(" ")).lower().startswith("состояние оценивания")), "")
    graded = bool(out["graded_at"]) or (grading.startswith("оценено") and "не оценено" not in grading)
    out["can_edit"] = out["can_submit"] and answered and not graded
    out["can_remove"] = answered and not graded and bool(
        soup.find(None, {"name": "action", "value": "removesubmissionconfirm"})
        or "action=removesubmissionconfirm" in html)
    return out


def parse_quiz_page(html: str) -> dict:
    """Страница теста (разведка 07.10): попытки, лучшая оценка, проходная, открыт
    ли сейчас. Пройти тест можно только на сайте — бот лишь показывает."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find(id="region-main") or soup
    info = [_clean(p.get_text(" ")) for p in (main.find(class_="quizinfo") or soup.new_tag("div")).find_all("p")]
    allowed = next((int(m.group(1)) for t in info if (m := re.match(r"Разрешено попыток:\s*(\d+)", t))), None)
    pass_text = next((t.split(":", 1)[1].strip() for t in info if t.startswith("Проходн")), "")
    attempts = []
    for table in main.find_all("table", class_=re.compile(r"quizreviewsummary")):
        rows = {_clean(th.get_text(" ")).lower(): _clean(td.get_text(" "))
                for tr in table.find_all("tr") if (th := tr.find("th")) and (td := tr.find("td"))}
        attempts.append({"state": rows.get("состояние", ""), "grade": rows.get("оценка", ""),
                         "points": rows.get("баллы", ""), "finished": rows.get("завершен", "")})
    fb = main.find(id="feedback")
    best = ""
    if fb and (m := re.search(r"итоговая оценка[^:]*:\s*([\d.,]+\s*/\s*[\d.,]+)", _clean(fb.get_text(" ")))):
        best = m.group(1).replace(" ", "")
    text = _clean(main.get_text(" ")).lower()
    return {"quiz": True, "attempts_allowed": allowed, "attempts": attempts, "best": best, "pass_text": pass_text,
            "open_now": bool(main.find(class_="quizstartbuttondiv")), "no_more": "больше нет попыток" in text}

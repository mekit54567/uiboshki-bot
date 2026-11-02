"""
Баллы БРС из СДО: страница «Оценки» каждого курса (отчёт по пользователю,
/grade/report/user/index.php?id=<курс>), входом самого студента.

Как устроен журнал курса в СДО МИРЭА (скрин владельца, 01.10):
  • верхний уровень — категории БРС: «Текущий контроль 0–45», «Посещаемость
    0–20», «Семестровый контроль 0–40», «Трудовая деятельность 0–5»,
    «Достижения 0–10», иногда доп. балл; «Сумма баллов 0–130»; «Оценка за
    промежуточную аттестацию» (Не зачтено–Зачтено или 2–5);
  • ниже — раскрытые категории («Текущий контроль», «Самостоятельная работа»)
    с работами: задания и тесты со своим диапазоном (0–8, 0–12, …).

Работа «зачтена», если балл не ниже проходного (Moodle помечает такие
ячейки классами gradepass/gradefail; порог виден и на странице задания —
«Проходной балл»). Без порога — зачтена любая выставленная оценка. Для БРС
нужно зачесть ≥ 75% работ текущего контроля (владелец).

Разбор — по классам и тексту строк, без привязки к точной вёрстке: тема СДО
может отличаться, а курсы преподаватели настраивают по-разному.
"""

import asyncio
import logging
import math
import re
import time
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from config import SDO_BASE_URL

logger = logging.getLogger(__name__)

PASS_SHARE = 0.75           # доля зачтённых работ текущего контроля для БРС
CACHE_SECONDS = 10 * 60
# Экран предмета ждёт страницы работ (порог, статус, срок) не дольше этого:
# 19.10 СДО отвечал медленно, и экран с целью грузился 76–100 с. Не успевшие
# страницы — из прошлого раза или без порога; такой ответ не кэшируется.
PAGES_BUDGET = 20
EXAM_MARKS = ((40, "3"), (60, "4"), (80, "5"))
CREDIT_MARKS = ((40, "зачёт"),)

_cache: dict[tuple, tuple[float, object]] = {}
# Страницы заданий (порог «зачтено», вердикт) — для подсчёта в списке
# предметов тем же правилом, что на экране предмета (Б4). Порог меняется
# редко: держим дольше баллов и не стираем после сдачи.
PAGES_SECONDS = 6 * 3600
_pages: dict[tuple[int, int], tuple[float, dict]] = {}

_RANGE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*[–—-]\s*(-?\d+(?:[.,]\d+)?)")
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")
_MOD = re.compile(r"/mod/(\w+)/view\.php\?id=(\d+)")


def _num(text: str) -> float | None:
    m = _NUM.search(text or "")
    return float(m.group(0).replace(",", ".")) if m else None


def _level(el) -> int:
    for c in el.get("class") or []:
        m = re.fullmatch(r"level(\d+)", c)
        if m:
            return int(m.group(1))
    return 0


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _blank(text: str) -> bool:
    """Оценки нет: пусто, любое тире («-», «–», «—») или «Не оценено» / «Нет
    оценки». Закрытый тест показывал «—», бот считал его оценённым и красил
    «ниже порога» (владелец, 06.10)."""
    t = (text or "").strip().lower()
    if not t or not t.strip("-–—‒ "):
        return True
    # не число и не слово шкалы («Зачтено», «Отлично»…) — служебная надпись журнала
    # у закрытого теста; раньше она шла за «зачтено» и «Зачтено работ» было 3 вместо 2
    return _num(t) is None and not any(w in t for w in _SCALE)


_SCALE = ("зачт", "удовл", "хорош", "отлич", "неуд")


def _activity_dates(soup) -> dict:
    """{подпись без двоеточия, строчными: дата} из [data-region="activity-dates"].
    «Закрыто c:» у МИРЭА пишут латинской «c» — подпись режем до «закрыт…»."""
    out = {}
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


def is_tk(name: str) -> bool:
    return "текущ" in (name or "").lower()


def parse_report(html: str) -> dict:
    """Журнал курса → {"items": [...], "categories": [...]}.

    item: name, kind (подпись над названием: «ЗАДАНИЕ», «ТЕСТ», «ВЫЧИСЛЯЕМАЯ
    ОЦЕНКА»…), module/cmid (если это работа), grade (число или None), text
    (как написано: «5,0», «Не зачтено», «-»), max, passed (True/False/None),
    level, category (имя ближайшей раскрытой категории или "")."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=re.compile(r"user-grade|generaltable")) or soup
    items, categories, stack = [], [], []   # stack: (level, name)
    for tr in table.find_all("tr"):
        head = tr.find(["th", "td"], class_=re.compile(r"column-itemname"))
        if head is None:
            continue
        level = _level(head)
        grade_td = tr.find("td", class_=re.compile(r"column-grade"))
        range_td = tr.find("td", class_=re.compile(r"column-range"))
        if grade_td is None and range_td is None:
            # заголовок категории: «Текущий контроль», «Самостоятельная работа»
            name = _clean(head.get_text(" "))
            if not name:
                continue
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, name))
            categories.append({"name": name, "level": level})
            continue
        while stack and stack[-1][0] >= level:
            stack.pop()
        link = head.find("a", href=_MOD)
        kind_el = head.find(class_=re.compile(r"text-uppercase|dimmed_text|small"))
        kind = _clean(kind_el.get_text(" ")) if kind_el else ""
        name = _clean((link or head).get_text(" "))
        if kind and name.startswith(kind) and not link:
            name = name[len(kind):].strip()
        text = _clean(grade_td.get_text(" ")) if grade_td else ""
        rng = _RANGE.search(range_td.get_text(" ") if range_td else "")
        classes = " ".join(grade_td.get("class") or []) if grade_td else ""
        passed = True if "gradepass" in classes else (False if "gradefail" in classes else None)
        blank = _blank(text)
        grade = None if blank else _num(text)
        if blank:
            passed = None       # «-» с классом gradefail у закрытого теста — не «не зачтено»
        elif grade is None and passed is None:
            # оценка шкалой: «Зачтено» / «Не зачтено» — числа нет, но работа оценена
            low = text.lower()
            passed = not low.startswith(("не ", "неуд"))
        m = _MOD.search(link["href"]) if link else None
        items.append({
            "name": name, "kind": kind.capitalize(),
            "module": m.group(1) if m else "", "cmid": int(m.group(2)) if m else None,
            "url": link["href"] if link else "",
            "grade": grade, "graded": not blank,
            "text": "" if blank else text,
            "max": float(rng.group(2).replace(",", ".")) if rng else None,
            "passed": passed, "level": level,
            "category": stack[-1][1] if stack else "",
        })
    return {"items": items, "categories": categories}


_MARK_WORD_RE = re.compile(r"\(?\s*(?:не)?удовлетворительно\s*\)?|\(?\s*хорошо\s*\)?|\(?\s*отлично\s*\)?", re.I)


def short_final(text: str) -> str:
    """«2 (неудовлетворительно)» → «2»: при цифре слово не нужно (Никита
    12.10). Без цифры («Не зачтено», «отлично») — как есть."""
    t = (text or "").strip()
    if not re.search(r"\d", t) or not _MARK_WORD_RE.search(t):
        return t
    rest = _MARK_WORD_RE.sub(" ", t).strip(" -—–,;:()")
    return re.sub(r"\s+", " ", rest) if re.fullmatch(r"[\d.,\s]+", rest) else t


def summarize(report: dict, course_name: str = "") -> dict:
    """Сводка курса для экрана «Баллы»: сумма, категории БРС, итог, работы
    текущего контроля и сколько из них зачтено."""
    items = report["items"]
    total = next((i for i in items if "сумма" in i["name"].lower()), None)
    final = next((i for i in items if "аттестац" in i["name"].lower() or "итог" in i["name"].lower()), None)
    top = min((i["level"] for i in items if not i["cmid"]), default=0)
    cats = [i for i in items if i["level"] == top and not i["cmid"] and i is not total and i is not final
            and i["max"] and "итог" not in i["name"].lower()]
    works = order_works([i for i in items if i["cmid"] and (is_tk(i["category"]) or not any(is_tk(c["name"]) for c in report["categories"]))])
    for w in works:
        if w["passed"] is None and w["grade"] is not None:
            w["passed"] = True     # порога нет — зачтена любая выставленная оценка
        w["graded"] = w.get("graded", w["grade"] is not None)
    tk_cat = next((c for c in cats if is_tk(c["name"])), None)
    if tk_cat and tk_cat["grade"] is None and works:
        # «Текущий контроль» ещё не посчитан («-») — сумма выставленных работ
        tk_cat["grade"] = sum(w["grade"] or 0 for w in works) or None
    total_max = (total or {}).get("max") or sum(c["max"] for c in cats) or 130
    score = (total or {}).get("grade")
    if score is None:
        score = sum(c["grade"] or 0 for c in cats)
    final_text = short_final((final or {}).get("text", ""))
    lower = (course_name + " " + ((final or {}).get("text") or "")).lower()
    # «Дифференцированный зачёт» — по нему ставят 3/4/5, это не простой зачёт
    credit = "зач" in lower and "экзам" not in course_name.lower() and "диф" not in lower
    marks = CREDIT_MARKS if credit else EXAM_MARKS
    passed = sum(1 for w in works if w["passed"])
    graded = sum(1 for w in works if w["graded"])
    works_need = max(0, math.ceil(len(works) * PASS_SHARE) - passed)
    goal = next((p for p, _ in marks if score < p), None)
    return {
        "kind": "credit" if credit else "exam",
        "score": round(score, 2), "max": total_max, "final": final_text,
        "marks": [{"at": p, "label": l} for p, l in marks],
        "closed": score >= marks[0][0],
        # «на автомат»: баллов на зачёт/«3» и зачтено ≥ 75 % работ ТК (правило БРС)
        "auto": score >= marks[0][0] and not works_need,
        "works_need": works_need,
        "need": round(goal - score, 2) if goal is not None else 0,
        "need_label": next((l for p, l in marks if score < p), ""),
        # set — выставлено ли вообще («-» у преподавателя, который ещё ничего не внёс, ≠ 0)
        "categories": [{"name": c["name"], "score": c["grade"] or 0, "max": c["max"], "tk": is_tk(c["name"]),
                        "set": c["grade"] is not None} for c in cats],
        "works": [{"name": w["name"], "kind": w["kind"], "module": w["module"], "cmid": w["cmid"],
                   "grade": w["grade"], "graded": w["graded"], "max": w["max"], "passed": w["passed"]} for w in works],
        "works_total": len(works), "works_passed": passed, "works_graded": graded,
        "pass_share": PASS_SHARE,
    }


# ── страница задания: порог, статус, срок ────────────────────────────────────

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
    due = next((v for k, v in rows.items() if k.startswith("срок сдачи") or k.startswith("последний срок")), "")
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
        "can_submit": bool(soup.find(attrs={"name": "action", "value": "editsubmission"})
                           or "action=editsubmission" in html),
    }


GRACE_DAYS = 15     # срок прошёл, оценки нет — столько дней ждём (могли сдать на паре)
STALE_DAYS = 180    # дата закрытия старше полугода — осталась от копии курса прошлого года


def feedback_verdict(text: str) -> str:
    """У части заданий оценка не предусмотрена («Не оценено» навсегда), вердикт —
    комментарием преподавателя: «зачет» → ok, «не принято» → low (разведка 07.10)."""
    t = (text or "").lower().replace("ё", "е")
    if not t:
        return ""
    if re.search(r"не\s*(принят|зач|засчит)|незач|доработ|передела|исправ", t):
        return "low"
    if re.search(r"зач[её]?т|принят|засчит", t):
        return "ok"
    return ""
_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря")


def parse_due(text: str) -> datetime | None:
    """«среда, 9 октября 2026, 23:59» → datetime (время МСК, без зоны)."""
    m = re.search(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})(?:\D+(\d{1,2}):(\d{2}))?", (text or "").lower())
    if not m or m.group(2) not in _MONTHS:
        return None
    return datetime(int(m.group(3)), _MONTHS.index(m.group(2)) + 1, int(m.group(1)),
                    int(m.group(4) or 23), int(m.group(5) or 59))


def _now_msk() -> datetime:
    from datetime import timezone
    return datetime.now(timezone(timedelta(hours=3))).replace(tzinfo=None)


def work_status(w: dict, page: dict | None, now: datetime | None = None) -> str:
    """ok — зачтено; low — оценка ниже порога; wait — сдано, ждёт оценки;
    todo — можно сдавать; offline — сдаётся на занятии; soon — ещё закрыто;
    late — срок прошёл, оценки нет, ждём GRACE_DAYS (могли сдать на паре);
    miss — срок прошёл давно, ответа и оценки нет."""
    page = page or {}
    now = now or _now_msk()
    quiz = w.get("module") == "quiz"
    closed_quiz = quiz and (page.get("opens") or page.get("unavailable")) and not page.get("submitted")
    if (w["grade"] is not None or w.get("graded")) and not closed_quiz:
        return "ok" if w["passed"] else "low"
    verdict = feedback_verdict(page.get("feedback", ""))
    if verdict:
        return verdict          # оценки у задания нет вовсе, вердикт — комментарием («зачет» / «не принято»)
    if page.get("submitted"):
        return "wait"
    if quiz and page.get("unavailable"):
        return "soon"           # «В настоящее время этот тест недоступен» — ещё не открыт
    closed = parse_due(page.get("closed", ""))
    if quiz and closed and closed < now:
        # «Закрыто c: 25 декабря 2024» в курсе 2026 года — даты остались от копии
        # курса: тест ещё не настроен, а не пропущен
        return "soon" if now - closed > timedelta(days=STALE_DAYS) else "miss"
    due = parse_due(page.get("due", ""))
    overdue = (due is not None and due < now) or "просроч" in (page.get("remaining") or "").lower()
    if not overdue:
        if page.get("offline"):
            return "offline"
        return "soon" if page.get("opens") else "todo"   # тест ещё не открыт — не «ниже порога»
    if w.get("module") == "quiz":
        return "miss"           # тест не пройден в срок — на паре его не сдают
    if due is not None and now - due > timedelta(days=GRACE_DAYS):
        return "miss"
    return "late"


def order_works(works: list[dict]) -> list[dict]:
    """Порядок работ ТК (владелец, 06.10): одноимённые с номером — строго по
    номеру («Практическая работа №1, 2, 3», в журнале бывало 1, 3, 2), они
    занимают те же места; тест встаёт между ними по своему сроку (или дате
    открытия); остальное — как в журнале."""
    num = re.compile(r"^(.*?)\s*(?:№\s*)?(\d+)\s*$")
    out = list(works)
    fams: dict[str, list[int]] = {}
    for i, w in enumerate(out):
        m = num.match(w.get("name") or "")
        if m:
            fams.setdefault(m.group(1).strip().lower(), []).append(i)
    for idx in fams.values():
        ordered = sorted((out[i] for i in idx), key=lambda w: int(num.match(w["name"]).group(2)))
        for i, w in zip(idx, ordered):
            out[i] = w

    def when(w):
        return parse_due(w.get("due") or "") or parse_due(w.get("opens") or "")

    tests = [w for w in out if w.get("module") == "quiz" and not num.match(w.get("name") or "") and when(w)]
    for t in tests:
        out.remove(t)
        at = next((i for i, w in enumerate(out) if when(w) and when(w) > when(t)), len(out))
        out.insert(at, t)
    return out


def with_pass(w: dict, page: dict | None) -> dict:
    """Оценка ниже проходного балла со страницы задания — не зачтено,
    хотя журнал красит её как выставленную («4 из 8» при пороге 5)."""
    p = page or {}
    if w["grade"] is not None and p.get("pass") is not None and w["passed"] is True and w["grade"] < p["pass"]:
        return dict(w, passed=False)
    return w


def recount(s: dict, pages: list[dict | None]) -> dict:
    """Одно правило «зачтено» для списка предметов и экрана предмета (Б4):
    статус ok из work_status — с проходным баллом и вердиктом со страницы
    задания, а без страницы — по оценке журнала. Отсюда же works_need и
    «автомат»."""
    works = [with_pass(w, p) for w, p in zip(s["works"], pages)]
    passed = sum(1 for w, p in zip(works, pages) if work_status(w, p) == "ok")
    need = max(0, math.ceil(len(works) * PASS_SHARE) - passed)
    first = s["marks"][0]["at"] if s.get("marks") else 0
    return dict(s, works=works, works_passed=passed, works_need=need, auto=s["score"] >= first and not need)


def known_page(user_id: int, cmid: int) -> dict | None:
    hit = _pages.get((user_id, cmid))
    return hit[1] if hit and time.time() - hit[0] < PAGES_SECONDS else None


# ── загрузка из СДО ──────────────────────────────────────────────────────────

def _cached(key):
    hit = _cache.get(key)
    return hit[1] if hit and time.time() - hit[0] < CACHE_SECONDS else None


def _store(key, value):
    _cache[key] = (time.time(), value)
    return value


def forget(user_id: int):
    for k in [k for k in _cache if k[1] == user_id]:
        _cache.pop(k, None)


async def _report(client: httpx.AsyncClient, course_id: int) -> dict:
    from sdo_parser import get_checked
    resp = await get_checked(client, f"{SDO_BASE_URL}/grade/report/user/index.php?id={course_id}")
    return parse_report(resp.text)


async def this_semester_courses(client: httpx.AsyncClient) -> list[dict]:
    from schedule_parser import get_group_subjects
    from sdo_files import clean_course_name, list_courses
    from sdo_parser import KEEP_COURSES, SEMESTER_WINDOW, is_old_semester, off_schedule
    subjects = await get_group_subjects(**SEMESTER_WINDOW)
    out = []
    for c in await list_courses(client):
        name = c["name"]
        if is_old_semester(name) or off_schedule(name, subjects) or any(k in name.lower() for k in KEEP_COURSES):
            continue
        out.append({"id": c["id"], "name": name, "title": clean_course_name(name)})
    return out


_inflight: dict[int, asyncio.Future] = {}


async def overview(user_id: int, cookie: str, fresh: bool = False) -> dict:
    """Все предметы семестра со сводкой баллов. Кэш на 10 минут.

    16.10 (Amvera): приложение на старте спрашивало баллы трижды разом — 12
    соединений к СДО, часть не открылась, и неполный список (4 предмета)
    лёг в кэш на 10 минут. Теперь одновременные запросы одного человека
    ждут один общий, а не открывшийся предмет пробуем ещё раз; не вышло —
    отдаём что есть, но в кэш не кладём."""
    key = ("all", user_id)
    if not fresh and (hit := _cached(key)):
        return hit
    if (running := _inflight.get(user_id)) is not None:
        return await asyncio.shield(running)
    fut = asyncio.get_running_loop().create_future()
    _inflight[user_id] = fut
    try:
        result = await _overview(user_id, cookie, fresh)
    except asyncio.CancelledError:
        fut.cancel()
        raise
    except Exception as e:
        fut.set_exception(e)
        fut.exception()                # чтобы без ждущих не было «exception never retrieved»
        raise
    else:
        fut.set_result(result)
        return result
    finally:
        _inflight.pop(user_id, None)


async def _overview(user_id: int, cookie: str, fresh: bool) -> dict:
    key = ("all", user_id)
    if fresh:                  # «обновить» — и экраны предметов тоже, иначе там до 10 минут старое
        for k in [k for k in _cache if k[0] == "detail" and k[1] == user_id]:
            _cache.pop(k, None)
    from sdo_files import make_client
    failed = object()
    async with make_client(cookie) as client:
        courses = await this_semester_courses(client)
        sem = asyncio.Semaphore(4)

        async def one(c, retry=False):
            async with sem:
                try:
                    rep = await _report(client, c["id"])
                except httpx.HTTPError as e:
                    logger.info(f"Баллы СДО: курс {c['id']} не открылся{' (повтор)' if retry else ''}: "
                                f"{type(e).__name__}")
                    return failed
            s = summarize(rep, c["name"])
            if not s["categories"] and not s["works"]:
                return None      # курс без журнала БРС («Учебный отдел» и т.п.)
            s = recount(s, [known_page(user_id, w["cmid"]) for w in s["works"]])
            _store(("course", user_id, c["id"]), (c, s))
            return dict(s, id=c["id"], name=c["name"], title=c["title"])

        got = list(await asyncio.gather(*(one(c) for c in courses)))
        for i, c in enumerate(courses):           # повтор по одному, не залпом
            if got[i] is failed:
                got[i] = await one(c, retry=True)
    partial = any(x is failed for x in got)
    items = [x for x in got if x and x is not failed]
    items.sort(key=lambda x: (x["closed"], x["need"] if not x["closed"] else -x["score"]))
    data = {"courses": items, "updated": int(time.time())}
    if partial:
        if not items:          # ни одного предмета — это «СДО не отвечает», а не пустой семестр
            raise httpx.ConnectError("СДО не отдал ни одного журнала")
        return data            # неполный список — показать, но не запоминать
    return _store(key, data)


async def course_detail(user_id: int, cookie: str, course_id: int, stale_ok: bool = False) -> dict:
    """Предмет подробно + по каждой работе текущего контроля страница задания
    (порог, статус, срок) — для экрана «Текущий контроль».

    19.10: смена цели шла по 15 с — экран предмета ещё грузился из медленного
    СДО, а каждое нажатие начинало ту же загрузку заново. Теперь одновременные
    запросы ждут одну загрузку, а действиям (цель, отметка посещения) хватает
    прошлой загрузки любой давности (stale_ok) — баллы им не нужны свежими."""
    key = ("detail", user_id, course_id)
    if hit := _cached(key):
        return hit
    if stale_ok and (old := _cache.get(key)):
        return old[1]
    if (running := _inflight_detail.get(key)) is not None:
        return await asyncio.shield(running)
    fut = asyncio.get_running_loop().create_future()
    _inflight_detail[key] = fut
    try:
        result = await _course_detail(user_id, cookie, course_id)
    except asyncio.CancelledError:
        fut.cancel()
        raise
    except BaseException as e:
        fut.set_exception(e)
        fut.exception()
        raise
    else:
        fut.set_result(result)
        return result
    finally:
        _inflight_detail.pop(key, None)


_inflight_detail: dict[tuple, asyncio.Future] = {}


async def _course_detail(user_id: int, cookie: str, course_id: int) -> dict:
    key = ("detail", user_id, course_id)
    from sdo_files import make_client
    async with make_client(cookie) as client:
        base = _cached(("course", user_id, course_id))
        if base:
            course, s = base
        else:
            course = next((c for c in await this_semester_courses(client) if c["id"] == course_id), None)
            if not course:
                raise LookupError("курс не найден")
            s = summarize(await _report(client, course_id), course["name"])
        sem = asyncio.Semaphore(5)

        async def page(w):
            if w["module"] not in ("assign", "quiz"):
                return None
            async with sem:
                try:
                    from sdo_parser import get_checked
                    r = await get_checked(client, f"{SDO_BASE_URL}/mod/{w['module']}/view.php?id={w['cmid']}")
                    return parse_assign_page(r.text)
                except httpx.HTTPError:
                    return None

        tasks = [asyncio.ensure_future(page(w)) for w in s["works"]]
        if tasks:
            await asyncio.wait(tasks, timeout=PAGES_BUDGET)
        late = [t for t in tasks if not t.done()]
        for t in late:
            t.cancel()
        if late:
            await asyncio.gather(*late, return_exceptions=True)
            logger.info(f"предмет {course_id}: {len(late)} из {len(tasks)} страниц работ не успели за {PAGES_BUDGET} с")
        # не успевшую страницу берём из прошлого раза (если была) — лучше старый порог, чем никакого
        pages = [t.result() if t.done() and not t.cancelled() else (_pages.get((user_id, w["cmid"])) or (0, None))[1]
                 for t, w in zip(tasks, s["works"])]
    for t, w, p in zip(tasks, s["works"], pages):
        if p is not None and t.done() and not t.cancelled():
            _pages[(user_id, w["cmid"])] = (time.time(), p)
    import quiz_time        # время тестов — одно на всех, видно в «Сдать»
    await quiz_time.remember({w["cmid"]: p for w, p in zip(s["works"], pages) if w["module"] == "quiz"})
    s = recount(s, pages)
    works = []
    for w, p in zip(s["works"], pages):
        p = p or {}
        works.append(dict(w, pass_mark=p.get("pass"), status=work_status(w, p), due=p.get("due", ""),
                          opens=p.get("opens", ""), remaining=p.get("remaining", ""), time_limit=p.get("time_limit"),
                          can_submit=bool(p.get("can_submit")) and w["module"] == "assign",
                          url=f"{SDO_BASE_URL}/mod/{w['module']}/view.php?id={w['cmid']}"))
    works = order_works(works)
    out = dict(s, id=course_id, name=course["name"], title=course["title"], works=works)
    # список предметов из кэша — те же «зачтено X из Y», что здесь (Б4)
    if hit := _cached(("all", user_id)):
        for c in hit["courses"]:
            if c["id"] == course_id:
                c.update({k: s[k] for k in ("works_passed", "works_need", "auto")})
    if late:
        return out                  # не всё успели — в кэш не кладём, следующий заход доберёт
    return _store(key, out)


# ── задание целиком: описание, файлы преподавателя ───────────────────────────

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
    main = soup.find(attrs={"role": "main"}) or soup
    # В Moodle 4 описание и файлы задания — в шапке активности (activity-header),
    # она стоит в #region-main ПЕРЕД <div role="main">, а не внутри него.
    region = soup.find(id="region-main") or main
    title_el = main.find(["h2", "h1"]) or soup.find(["h1", "h2"])
    teacher, mine, seen = [], [], set()
    for a in region.find_all("a", href=_PLUGINFILE):
        href = a["href"].split("?")[0]
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
    grading = next((_clean(tr.find("td").get_text(" ")).lower() for tr in soup.find_all("tr")
                    if tr.find("th") and tr.find("td")
                    and _clean(tr.find("th").get_text(" ")).lower().startswith("состояние оценивания")), "")
    graded = bool(out["graded_at"]) or (grading.startswith("оценено") and "не оценено" not in grading)
    out["can_edit"] = out["can_submit"] and answered and not graded
    out["can_remove"] = answered and not graded and bool(
        soup.find(attrs={"name": "action", "value": "removesubmissionconfirm"})
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
        rows = {_clean(tr.find("th").get_text(" ")).lower(): _clean(tr.find("td").get_text(" "))
                for tr in table.find_all("tr") if tr.find("th") and tr.find("td")}
        attempts.append({"state": rows.get("состояние", ""), "grade": rows.get("оценка", ""),
                         "points": rows.get("баллы", ""), "finished": rows.get("завершен", "")})
    fb = main.find(id="feedback")
    best = ""
    if fb and (m := re.search(r"итоговая оценка[^:]*:\s*([\d.,]+\s*/\s*[\d.,]+)", _clean(fb.get_text(" ")))):
        best = m.group(1).replace(" ", "")
    text = _clean(main.get_text(" ")).lower()
    return {"quiz": True, "attempts_allowed": allowed, "attempts": attempts, "best": best, "pass_text": pass_text,
            "open_now": bool(main.find(class_="quizstartbuttondiv")), "no_more": "больше нет попыток" in text}


async def task_detail(cookie: str, cmid: int, module: str = "assign") -> dict:
    from sdo_files import make_client
    from sdo_parser import get_checked
    import sdo_submit
    url = f"{SDO_BASE_URL}/mod/{module}/view.php?id={cmid}"
    async with make_client(cookie) as client:
        html = (await get_checked(client, url)).text
        page = parse_task_page(html)
        page["maxfiles"] = 0
        if module == "quiz":
            page.update(parse_quiz_page(html), can_submit=False)
            import quiz_time
            await quiz_time.remember({cmid: page})
        if page["can_submit"]:
            try:
                edit = sdo_submit.parse_edit_page((await get_checked(client, url + "&action=editsubmission")).text)
                page["maxfiles"] = edit["maxfiles"]
                page["maxbytes"] = edit["maxbytes"]
            except sdo_submit.SubmitError:
                page["can_submit"] = page["can_edit"] = False
    page.update(cmid=cmid, url=url, limit=min(sdo_submit.MAX_FILES, page["maxfiles"] or sdo_submit.MAX_FILES))
    return page

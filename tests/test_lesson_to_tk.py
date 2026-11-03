"""Нажал на пару на главной → её текущий контроль в СДО: название пары из
расписания сопоставляется с курсом СДО (js/sdo.js: matchCourse)."""
import json
import re
import subprocess
from pathlib import Path

JS = (Path(__file__).parent.parent / "webapp/static/js/sdo.js").read_text()


def _match(title, courses):
    fns = "".join(re.search(rf"function {n}\(.*?\n}}\n", JS, re.S).group(0) for n in ("courseWords", "matchCourse"))
    code = fns + f"const r = matchCourse({json.dumps(title)}, {json.dumps(courses)}); console.log(JSON.stringify(r ? r.id : null));"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


COURSES = [
    {"id": 1, "title": "Анализ и диагностика финансово-хозяйственной деятельности предприятия"},
    {"id": 2, "title": "Основы бизнес-анализа в ИТ-сфере [II.25-26]"},
    {"id": 3, "title": "Моделирование бизнес-процессов"},
    {"id": 4, "title": "Объектно-ориентированный анализ и программирование"},
]


def test_match_course_by_words():
    assert _match("Основы бизнес-анализа в ИТ-сфере", COURSES) == 2       # метка семестра не мешает
    assert _match("Моделирование бизнес-процессов", COURSES) == 3          # не путает с «бизнес-анализом»
    assert _match("Объектно-ориентированный анализ и программирование", COURSES) == 4
    assert _match("Анализ и диагностика финансово-хозяйственной деятельности предприятия", COURSES) == 1
    assert _match("Физическая культура и спорт", COURSES) is None          # нет журнала — не угадываем


def test_own_lessons_tappable_search_not():
    home = (Path(__file__).parent.parent / "webapp/static/js/home.js").read_text()
    search = (Path(__file__).parent.parent / "webapp/static/js/search.js").read_text()
    assert "lessonRow(l, !!l.status, true)" in home          # «Эта неделя» — нажимается
    assert "lessonRow(l, true)" in home and "lessonRow(l, true, true)" not in home   # «Сегодня» — нет
    assert "lessonRow(l, !!l.status)" in search    # чужое расписание — без перехода в свой СДО


def test_week_lessons_show_sdo_score():
    home = (Path(__file__).parent.parent / "webapp/static/js/home.js").read_text()
    sdo = (Path(__file__).parent.parent / "webapp/static/js/sdo.js").read_text()
    assert "(tap ? lessonScore(l.title) : '')" in home        # только у своих пар недели
    fn = re.search(r"function lessonScore\(.*?\n}\n", sdo, re.S).group(0)
    code = ("function fmtNum(x){return String(x)}" + "".join(
        re.search(rf"function {n}\(.*?\n}}\n", sdo, re.S).group(0) for n in ("courseWords", "matchCourse")) + fn +
        "let sdoData = {{courses: {}}};".format(json.dumps([{**c, "score": 41, "max": 60, "closed": c["id"] == 3} for c in COURSES])) +
        "console.log(JSON.stringify([lessonScore('Моделирование бизнес-процессов'), lessonScore('Физкультура')]))")
    out = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)
    assert "41/60" in out[0] and "ok" in out[0] and out[1] == ""

"""Карточка задания (Никита 18.11: «как в СДО, только красивее»): строки
таблицы задания (максимум, проходной, состояние оценивания, последнее
изменение, «Комментарии (N)») и комментарии к ответу — список и новый."""
from urllib.parse import parse_qs

import httpx
import pytest

from kapibara.features.sdo import comments as sdo_comments
from kapibara.features.sdo import grades as sdo_grades

COOKIE = "c00k1e"
INIT = ('<script>M.cfg = {"wwwroot":"https:\\/\\/online-edu.mirea.ru","sesskey":"SK777","themerev":"1"};</script>'
        '<script>Y.use("core_comment", function(Y) { M.core_comment.init(Y, {"client_id":"6a1b2c3d4e5f",'
        '"commentarea":"submission_comments","itemid":"98765","page":0,"courseid":"321","contextid":"4567",'
        '"component":"assignsubmission_comments","notoggle":false,"autostart":false}); });</script>')

# страница с телефона Никиты 18.11 (аудиторная контрольная, сдаётся вне сайта)
VIEW = """<div role="main"><h2>Аудиторная контрольная работа №3</h2>
<div data-region="activity-dates"><div><strong>Открыто с:</strong> понедельник, 9 ноября 2026, 00:00</div>
<div><strong>Срок сдачи:</strong> четверг, 26 ноября 2026, 00:00</div></div>
<div class="activity-description"><p>письменная работа в аудитории по темам 5, 6</p></div>
<h3>Состояние ответа</h3><table class="generaltable">
<tr><th>Максимальная оценка</th><td>15,0</td></tr>
<tr><th>Проходной балл</th><td>5,0</td></tr>
<tr><th>Состояние ответа на задание</th><td>Ответ на задание должен быть представлен вне сайта</td></tr>
<tr><th>Состояние оценивания</th><td>Не оценено</td></tr>
<tr><th>Оставшееся время</th><td>6 дн. 22 час. осталось</td></tr>
<tr><th>Последнее изменение</th><td>-</td></tr>
<tr><th>Комментарии к ответу</th><td><a href="#" class="comment-link"><span>Комментарии (2)</span></a></td></tr>
</table></div>""" + INIT

GRADED = """<div role="main"><h2>Практика 4</h2><table>
<tr><th>Состояние ответа на задание</th><td class="submissionstatussubmitted">Отправлено для оценивания</td></tr>
<tr><th>Состояние оценивания</th><td>Оценено</td></tr>
<tr><th>Последнее изменение</th><td>вторник, 10 ноября 2026, 21:14</td></tr></table>
<h3>Отзыв</h3><table><tr><th>Оценка</th><td>12,00 / 15,00</td></tr>
<tr><th>Оценено в</th><td>среда, 11 ноября 2026, 10:02</td></tr></table></div>"""

LIST = {"list": [
    {"id": 2, "content": "<div class=\"no-overflow\"><p>Принято, молодец</p></div>", "fullname": "Иванова Анна Петровна",
     "time": "среда, 11 ноября 2026, 10:05", "timecreated": 1794380700, "delete": False},
    {"id": 1, "content": "<p>Здравствуйте!<br>Прикрепил скан</p>", "fullname": "Никита  Курашкин",
     "time": "вторник, 10 ноября 2026, 21:15", "timecreated": 1794334500, "delete": True},
], "count": 2, "pagination": "", "client_id": "6a1b2c3d4e5f"}


def test_card_rows_like_sdo():
    t = sdo_grades.parse_task_page(VIEW)
    assert t["max_grade"] == 15.0 and t["pass"] == 5.0
    assert t["grading"] == "Не оценено"
    assert t["modified"] == ""                      # «-» в СДО — изменений не было
    assert t["comments_count"] == 2
    assert t["offline"] and t["remaining"] == "6 дн. 22 час. осталось"
    assert t["opened"].startswith("понедельник, 9 ноября") and not t["opens"] and t["due"].startswith("четверг, 26 ноября")
    assert t["description"] == "письменная работа в аудитории по темам 5, 6"


def test_card_grade_and_modified():
    t = sdo_grades.parse_task_page(GRADED)
    assert t["grade"] == 12.0 and t["grading"] == "Оценено"
    assert t["modified"] == "вторник, 10 ноября 2026, 21:14"
    assert t["comments_count"] is None and t["max_grade"] is None


def test_comment_options_only_submission_comments():
    o = sdo_comments.comment_options(VIEW)
    assert o == {"client_id": "6a1b2c3d4e5f", "itemid": "98765", "courseid": "321", "contextid": "4567",
                 "component": "assignsubmission_comments", "commentarea": "submission_comments"}
    assert sdo_comments.sesskey_of(VIEW) == "SK777"
    other = INIT.replace("submission_comments", "page_comments").replace("assignsubmission_comments", "block_comments")
    assert sdo_comments.comment_options(other) is None          # чужая область — не наша
    assert sdo_comments.comment_options("<html></html>") is None


def test_comments_clean_and_order():
    out = sdo_comments._shape(LIST)
    assert out["count"] == 2 and out["can_post"]
    first, second = out["items"]
    assert first["author"] == "Никита Курашкин" and first["text"] == "Здравствуйте!\nПрикрепил скан"   # старые сверху
    assert second["text"] == "Принято, молодец" and second["time"].startswith("среда")
    assert set(first) == {"author", "time", "at", "text"}       # без внутренних номеров Moodle


class Moodle:
    def __init__(self, error=None):
        self.calls, self.added, self.error = [], [], error

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append((request.method, url))
        if "comment_ajax.php" in url:
            form = parse_qs(request.content.decode())
            assert form["sesskey"] == ["SK777"] and form["client_id"] == ["6a1b2c3d4e5f"]
            assert form["itemid"] == ["98765"] and form["contextid"] == ["4567"] and form["area"] == ["submission_comments"]
            if self.error:
                return httpx.Response(200, json={"error": self.error})
            if form["action"] == ["add"]:
                self.added.append(form["content"][0])
                return httpx.Response(200, json={"id": 3, "content": form["content"][0], "count": 3})
            items = LIST["list"] + [{"id": 3, "content": f"<p>{t}</p>", "fullname": "Никита Курашкин",
                                     "time": "сейчас", "timecreated": 1794400000} for t in self.added]
            return httpx.Response(200, json={"list": items, "count": len(items)})
        if "mod/assign/view.php" in url:
            return httpx.Response(200, text=VIEW)
        return httpx.Response(404)


@pytest.fixture
def moodle(monkeypatch):
    fake = Moodle()
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: real(*a, transport=httpx.MockTransport(fake), **kw))
    return fake


@pytest.mark.asyncio
async def test_add_comment_then_list(moodle):
    out = await sdo_comments.add(COOKIE, 4242, "  Добрый день, файл во вложении  ")
    assert moodle.added == ["Добрый день, файл во вложении"]
    assert out["count"] == 3 and out["items"][-1]["text"] == "Добрый день, файл во вложении"


@pytest.mark.asyncio
async def test_add_comment_errors(moodle):
    with pytest.raises(sdo_comments.CommentError):
        await sdo_comments.add(COOKIE, 4242, "   ")
    with pytest.raises(sdo_comments.CommentError):
        await sdo_comments.add(COOKIE, 4242, "x" * (sdo_comments.MAX_TEXT + 1))
    moodle.error = "Нет прав комментировать"
    with pytest.raises(sdo_comments.CommentError, match="Нет прав"):
        await sdo_comments.add(COOKIE, 4242, "привет")
    assert not moodle.added


@pytest.mark.asyncio
async def test_task_detail_brings_comments(moodle):
    t = await sdo_grades.task_detail(COOKIE, 4242)
    assert t["comments"]["count"] == 2 and len(t["comments"]["items"]) == 2


@pytest.mark.asyncio
async def test_task_detail_survives_comment_failure(moodle):
    moodle.error = "что-то сломалось"
    t = await sdo_grades.task_detail(COOKIE, 4242)
    assert t["comments"] is None and t["title"] == "Аудиторная контрольная работа №3"

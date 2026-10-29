"""Пуши с сутью в заголовке (Никита 25.10: «смысл от такого пуша? человеку
смысла ноль»): заголовок — главное, текст — одна-две строки, что делать."""
from datetime import date, datetime, timedelta

import pytest

from utils import TZ

TODAY = date(2026, 10, 5)          # понедельник


def _ev(h, m, summary="ЛК Анализ данных", room="А-1 (В-78)", teacher="Иванов Иван Иванович"):
    t = datetime(2026, 10, 5, h, m, tzinfo=TZ)
    return {"summary": summary, "location": room, "teacher": teacher,
            "time_start": t, "time_end": t + timedelta(minutes=90)}


def test_morning():
    import scheduler
    events = [_ev(10, 40, "ПР ООП", "И-201 (МП-1)"), _ev(9, 0)]
    title, body = scheduler.morning_push(events, "В-78", {"weather": True, "campus": True},
                                         "☁️ +3°, пасмурно, ощущается +1° · куртка")
    assert title == "Сегодня: 2 пары с 09:00, В-78, МП-1"
    assert body == "Первая — Анализ данных, лекция · А-1 (В-78) · ☁️ +3°, пасмурно, ощущается +1°"
    title, body = scheduler.morning_push(events, "В-78", {"weather": False, "campus": False}, "☁️")
    assert title == "Сегодня: 2 пары с 09:00" and "☁️" not in body
    assert scheduler.morning_push([], "В-78", {"weather": False}, "") == ("Сегодня пар нет", "Отдыхай")


def test_lesson():
    import scheduler
    assert scheduler.lesson_push(_ev(9, 0), 15) == ("Через 15 мин: Анализ данных",
                                                    "А-1 (В-78) · лекция · Иванов И. И.")


def test_deadlines():
    import scheduler
    one = [{"subject": "Практика 2 · Анализ данных (Экз)", "due_date": "2026-10-06", "due_time": "23:59"}]
    assert scheduler.deadlines_push(one, TODAY) == ("Завтра до 23:59: Практика 2", "Анализ данных (Экз)")
    many = one + [{"subject": "Лаба 3", "due_date": "2026-10-05"}, {"subject": "Эссе", "due_date": "2026-10-08"}]
    title, body = scheduler.deadlines_push(many, TODAY)
    assert title == "3 срока за 3 дня, ближайший сегодня"
    assert body == "Лаба 3 — сегодня; Практика 2 — завтра до 23:59; Эссе — в чт"


def test_new_tasks():
    import new_tasks
    task = {"subject": "Практика 3 · Анализ данных", "due_date": "2026-10-08", "due_time": "23:59"}
    assert new_tasks.headline([task], today=TODAY) == ("Новое задание: Практика 3",
                                                       "Анализ данных · сдать в чт до 23:59")
    moved = dict(task, was="2026-10-06")
    assert new_tasks.headline([], [moved], today=TODAY) == (
        "Перенесли срок: Практика 3", "Анализ данных · теперь в чт до 23:59, было 6 октября")
    title, body = new_tasks.headline([task, dict(task, subject="Тест 1")], [moved], today=TODAY)
    assert title == "В СДО новое: 2 задания, 1 перенос"
    assert body.startswith("Практика 3 — в чт до 23:59; Тест 1")


def test_grades():
    import grade_alerts
    one = [({"name": "Моделирование"}, 34.0, 39.0)]
    assert grade_alerts.headline(one) == ("Моделирование: +5", "Было 34, стало 39")
    two = one + [({"name": "ООП"}, 50.0, 48.5)]
    assert grade_alerts.headline(two) == ("Новые баллы по 2 предметам",
                                          "Моделирование +5 (39) · ООП -1.5 (48.5)")


def test_quiz():
    import quiz_alerts
    now = datetime(2026, 10, 5, 12, 0, tzinfo=TZ)
    d = {"subject": "Тест 2 · ООП", "due_date": "2026-10-05", "due_time": "12:30"}
    assert quiz_alerts.push_head(d, "r30", 30, 20, now) == ("Через 30 мин закрывается тест",
                                                            "Тест 2 · ООП · 20 мин на попытку")
    assert quiz_alerts.push_head(d, "open", 0, None, now) == ("Открыли тест: Тест 2", "ООП · сдать сегодня до 12:30")


@pytest.mark.asyncio
async def test_deliver_uses_own_title_and_body(db, monkeypatch):
    import delivery
    import webpush
    from database.push import save_push_sub
    from tests.test_delivery_push import _browser
    _, p256dh, auth = _browser()
    await save_push_sub(1, "https://push.example/a", p256dh, auth)
    got = []

    async def send(sub, data, ttl=3600):
        got.append(data)
        return 201

    monkeypatch.setattr(webpush, "send", send)
    await delivery.push(1, "weekly", "🗓 <b>Неделя 9</b>\nПн — 5 пар", "today",
                        title="Неделя 9: 21 пара, свободен вт", body="Сдать: Практика 2, пн 23:59")
    assert got[0]["title"] == "Неделя 9: 21 пара, свободен вт" and got[0]["body"] == "Сдать: Практика 2, пн 23:59"


def test_every_kind_has_title():
    """Пуш без своего заголовка по виду — был «Капибара» (изменения расписания, вход в СДО)."""
    import delivery
    assert {"lessons", "sdo"} <= set(delivery.TITLES)

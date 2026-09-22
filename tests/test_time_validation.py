"""
Строгая валидация времени дедлайна (handlers.deadlines.parse_due_time).
Граничные случаи — то, что реально ловит регрессии вроде "22.61 проходило".
"""
import pytest
from handlers.deadlines import parse_due_time


@pytest.mark.parametrize("raw,expected", [
    ("22.61", (False, None)),
    ("22.60", (False, None)),
    ("22.59", (True, "22:59")),
    ("25:10", (False, None)),
    ("24:00", (False, None)),
    ("9:5",   (False, None)),
    ("09:30", (True, "09:30")),
    ("9:30",  (True, "09:30")),
    ("0:00",  (True, "00:00")),
    ("23:59", (True, "23:59")),
    ("-",     (True, None)),
    ("–",     (True, None)),
    ("abc",   (False, None)),
    ("12:60", (False, None)),
    ("12.5",  (False, None)),
    ("",      (False, None)),
])
def test_parse_due_time(raw, expected):
    assert parse_due_time(raw) == expected

"""
Ответ решалки в Telegram: Markdown модели -> HTML (md_to_tg_html_chunks).

Поймано живым тестом бота в Telegram: ответ уходил с parse_mode="Markdown"
(старый Markdown Telegram), и в "f'(x) = 3 * x^2 * ln(x)" пропадали знаки
умножения, жирный растекался на пол-ответа, а "### 3. Итог" выводились как
есть.
"""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, Chat, User, Update

from tests.test_deadlines_routing import FakeSession
from utils import md_to_tg_html_chunks

USER = User(id=222, is_bot=False, first_name="Alice")
CHAT = Chat(id=222, type="private")

GEMINI_ANSWER = (
    "Привет! 👋\n\n"
    "### 1. Краткий ответ\n"
    "f'(x) = 3 * x^2 * ln(x) + x^2, **f'(e) = 4 * e^2**\n\n"
    "---\n\n"
    "### 2. Решение\n"
    "* правило: (u * v)' = u' * v + u * v'\n"
    "* при x < 1 логарифм *отрицательный*"
)


# ── конвертер ────────────────────────────────────────────────────────────────

def test_multiplication_asterisks_survive():
    html = md_to_tg_html_chunks("f'(x) = 3 * x^2 * ln(x) + x^2, а 2*3 = 6")[0]
    assert html == "f'(x) = 3 * x^2 * ln(x) + x^2, а 2*3 = 6"


def test_headings_bold_rules_bullets_italic():
    html = md_to_tg_html_chunks(GEMINI_ANSWER)[0]
    assert "<b>1. Краткий ответ</b>" in html
    assert "###" not in html
    assert "<b>f'(e) = 4 * e^2</b>" in html
    assert "──────────" in html and "---" not in html
    assert "• правило: (u * v)' = u' * v + u * v'" in html
    assert "<i>отрицательный</i>" in html
    assert "x &lt; 1" in html


def test_code_is_escaped_and_not_formatted():
    html = md_to_tg_html_chunks("Код `a<b` и\n```python\nif a < b:\n    print('**x**')\n```\nконец")[0]
    assert "<code>a&lt;b</code>" in html
    assert "<pre>if a &lt; b:\n    print('**x**')</pre>" in html
    assert html.endswith("конец")


def test_unclosed_fence_and_stray_backtick():
    assert md_to_tg_html_chunks("```\nx < 1")[0] == "<pre>x &lt; 1</pre>"
    assert md_to_tg_html_chunks("один ` бэктик")[0] == "один ` бэктик"


def test_long_answer_split_keeps_code_block_in_each_chunk():
    code = "\n".join(f"line {i} < {i + 1}" for i in range(400))
    chunks = md_to_tg_html_chunks(f"Начало\n```\n{code}\n```\nКонец", limit=1000)
    assert len(chunks) > 1
    for chunk in chunks:
        # каждый кусок сам по себе валиден: <pre> открыт и закрыт внутри
        assert chunk.count("<pre>") == chunk.count("</pre>")
    assert chunks[0].startswith("Начало")
    assert chunks[-1].endswith("Конец")


def test_bold_and_italic_never_cross():
    html = md_to_tg_html_chunks("**a *b** c*")[0]
    assert html == "<b>a *b</b> c*"


# ── через настоящий Dispatcher ───────────────────────────────────────────────

class RecordingSession(FakeSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sent = []  # (text, parse_mode)

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        if name == "SendMessage":
            self.sent.append((method.text, method.parse_mode))
        if name == "DeleteMessage":
            return True
        return await super().make_request(bot, method, timeout)


@pytest.fixture
def bot():
    return Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=RecordingSession())


@pytest.fixture
def dp():
    from handlers.solver import router as solver_router
    d = Dispatcher(storage=MemoryStorage())
    d.include_router(solver_router)
    yield d
    solver_router._parent_router = None


async def _feed(dp, bot, text):
    msg = Message(message_id=int(time.time() * 1000) % 1000000, date=0, chat=CHAT, from_user=USER, text=text)
    await dp.feed_update(bot, Update(update_id=int(time.time() * 1000000) % 10**9, message=msg))


@pytest.mark.asyncio
async def test_solve_answer_goes_out_as_html(db, dp, bot, monkeypatch):
    import handlers.solver as solver

    async def fake_solve_text(task, subject="", backend="gemini"):
        return GEMINI_ANSWER

    monkeypatch.setattr(solver, "solve_text", fake_solve_text)

    await _feed(dp, bot, "/solve")
    await _feed(dp, bot, "Математика")
    bot.session.sent.clear()
    await _feed(dp, bot, "Найди производную x^3 * ln(x)")

    answers = [(t, pm) for t, pm in bot.session.sent if "Краткий ответ" in t]
    assert len(answers) == 1
    text, parse_mode = answers[0]
    assert parse_mode == "HTML"
    assert "3 * x^2 * ln(x)" in text
    assert "<b>1. Краткий ответ</b>" in text

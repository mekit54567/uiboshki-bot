"""Капибара отвечает в чате своей группы на тег (handlers/group_talk.py, 11.11)."""
import pytest

from kapibara.core import config
from kapibara.features.ai import group_talk

CHAT = -100777


class FakeMsg:
    def __init__(self, text, chat_id=CHAT, uid=5, reply_to=None, bot=False):
        self.text, self.replies = text, []
        self.chat = type("C", (), {"id": chat_id, "type": "supergroup"})()
        self.from_user = type("U", (), {"id": uid, "is_bot": bot})()
        self.reply_to_message = reply_to

    async def reply(self, text):
        self.replies.append(text)


class FakeBot:
    id = 42

    async def me(self):
        return type("M", (), {"id": 42, "username": "UiboshkiBot"})()


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    group_talk.reset()
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(config, "GROUP_CHAT_ID", CHAT)
    monkeypatch.setattr(config, "BOT_USERNAME", "UiboshkiBot")
    monkeypatch.delenv("GROUP_TALK_MODELS", raising=False)
    monkeypatch.delenv("GROUP_TALK", raising=False)


async def _talk(msg, monkeypatch, reply="Я Капибара!"):
    from handlers import group_talk as h

    async def fake(q):
        return reply
    monkeypatch.setattr(group_talk, "answer", fake)
    await h.talk(msg, FakeBot())


@pytest.mark.asyncio
async def test_answers_on_tag(monkeypatch):
    m = FakeMsg("@UiboshkiBot ты кто?")
    await _talk(m, monkeypatch)
    assert m.replies == ["Я Капибара!"]


@pytest.mark.asyncio
async def test_silent_without_tag_and_in_other_chat(monkeypatch):
    for m in (FakeMsg("всем привет"), FakeMsg("@UiboshkiBot привет", chat_id=-1), FakeMsg("@UiboshkiBot", bot=True)):
        await _talk(m, monkeypatch)
        assert m.replies == []


@pytest.mark.asyncio
async def test_answers_on_reply_to_bot(monkeypatch):
    prev = type("P", (), {"from_user": type("U", (), {"id": 42})()})()
    m = FakeMsg("а что ещё умеешь?", reply_to=prev)
    await _talk(m, monkeypatch)
    assert len(m.replies) == 1


@pytest.mark.asyncio
async def test_user_pause_and_daily_limit(monkeypatch):
    a = FakeMsg("@UiboshkiBot раз")
    b = FakeMsg("@UiboshkiBot два")
    await _talk(a, monkeypatch)
    await _talk(b, monkeypatch)
    assert len(a.replies) == 1 and b.replies == []        # второй раз подряд — молча
    monkeypatch.setattr(group_talk, "DAILY", 1)
    c = FakeMsg("@UiboshkiBot три", uid=6)
    await _talk(c, monkeypatch)
    assert "выговорилась" in c.replies[0]


@pytest.mark.asyncio
async def test_disabled_without_key(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    m = FakeMsg("@UiboshkiBot привет")
    await _talk(m, monkeypatch)
    assert m.replies == []


@pytest.mark.asyncio
async def test_fallback_chain_and_failure(monkeypatch):
    tried = []

    async def ask(model, q):
        tried.append(model)
        if model != "nvidia/nemotron-3.5-lightning:free":
            raise group_talk.TalkError("429")
        return "ок"
    monkeypatch.setattr(group_talk, "_ask", ask)
    assert await group_talk.answer("@UiboshkiBot привет") == "ок"
    assert tried[0] == "nvidia/nemotron-3-ultra-550b-a55b:free" and len(tried) == 3

    async def bad(model, q):
        raise group_talk.TalkError("down")
    monkeypatch.setattr(group_talk, "_ask", bad)
    from handlers import group_talk as h
    m = FakeMsg("@UiboshkiBot привет", uid=9)
    await h.talk(m, FakeBot())
    assert "позже" in m.replies[0]


def test_tidy_cleans_doubles_json_and_leaks():
    assert group_talk.tidy("Ты это в зеркале репетировал, да? Смешно.Ты это в зеркале репетировал, да? Смешно.") == \
        "Ты это в зеркале репетировал, да? Смешно."
    assert group_talk.tidy('{   "response": "Тебе показалось." }') == "Тебе показалось."
    assert group_talk.leaked("Ты бот и приложение «Капибара — учёба МИРЭА»") and not group_talk.leaked("Привет!")


@pytest.mark.asyncio
async def test_leaked_answer_is_skipped(monkeypatch):
    class R:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "Два режима, выбирай по тому, как к тебе обратились."}}]}

    class C:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return R()
    monkeypatch.setattr(group_talk.net, "client", lambda **kw: C())
    with pytest.raises(group_talk.TalkError):
        await group_talk._ask("m", "привет")


def test_helpers():
    assert group_talk.clean_question("@uiboshkibot  как дела?") == "как дела?"
    assert group_talk.tidy("<think>думаю</think>Привет!") == "Привет!"
    assert len(group_talk.tidy("Предложение. " * 200)) <= group_talk.MAX_ANSWER
    p = group_talk.persona()
    assert "Капибара" in p and "Капибару+" in p and "ничего не выдумывай" in p
    assert config.APPSTORE_URL in p
    assert "Grok" in p and "мат" in p and "Запрещено" in p     # два режима: обычный и жёсткий ответ на подкол


@pytest.mark.asyncio
async def test_intro_once_with_text_when_no_video(db, monkeypatch):
    from handlers import group_talk as h
    monkeypatch.setattr(group_talk, "INTRO_VIDEO", "/nonexistent.mp4")
    sent = []

    class B:
        async def send_message(self, chat_id, text, **kw):
            sent.append(text)
    assert await h.send_intro(B(), CHAT) is True
    assert await h.send_intro(B(), CHAT) is False          # второй раз — нет
    assert await h.send_intro(B(), CHAT, force=True) is True
    assert len(sent) == 2 and "Капибара" in sent[0]


@pytest.mark.asyncio
async def test_talktest_report(monkeypatch):
    async def ans(q):
        return "ответ"
    monkeypatch.setattr(group_talk, "answer", ans)
    rep = await group_talk.run_test(pause=0)
    assert rep.count("→ ответ") == len(group_talk.TEST_QUESTIONS) >= 25

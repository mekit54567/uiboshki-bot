"""Имя группы и бота — из переменных (GROUP_NAME, BOT_USERNAME): страница
приложения, промпты ИИ и подсказки бота подхватывают их, а не «УИБО-03-24»."""
import config


def test_index_page_uses_config(monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    monkeypatch.setattr(config, "GROUP_NAME", "КМБО-01-25</script>")
    monkeypatch.setattr(config, "BOT_USERNAME", "otherbot")
    html = TestClient(server.app).get("/").text
    assert "УИБО-03-24" not in html.split("<script>window.APP_CONFIG")[0]
    assert "КМБО-01-25&lt;/script&gt;" in html                         # в разметке — экранировано
    assert 'window.APP_CONFIG = {"group": "КМБО-01-25<\\/script>", "bot": "otherbot", "channel": "", "contact": "", "guide": ""}' in html
    assert html.index("window.APP_CONFIG") < html.index('src="js/core.js')


def test_index_page_passes_channel_and_contact(monkeypatch):
    # плитки «Канал бота» и «Написать нам» в меню «Ещё» (дизайн-ревью, п. 18)
    from fastapi.testclient import TestClient
    import webapp.server as server
    monkeypatch.setattr(config, "CHANNEL_URL", "https://t.me/uiboshki_news")
    monkeypatch.setattr(config, "CONTACT_URL", "https://t.me/Partykq</script>")
    html = TestClient(server.app).get("/").text
    cfg = html.split("window.APP_CONFIG = ", 1)[1].split(";</script>", 1)[0]
    assert '"channel": "https://t.me/uiboshki_news"' in cfg
    assert '"contact": "https://t.me/Partykq<\\/script>"' in cfg       # не закрывает <script>


def test_prompts_use_group(monkeypatch):
    # группа — из профиля человека (контекст группы), а не GROUP_NAME сервера:
    # живой тест 20.10 — «полезен вам, студентам УИБО-03-24» человеку другой группы
    import ai_solver
    import config
    monkeypatch.setattr(config, "GROUP_NAME", "КМБО-01-25")
    p = ai_solver.build_system_prompt("Матан")
    assert "КМБО-01-25" not in p and "УИБО" not in p and "Матан" in p and "контексту группы" in p


def test_no_hardcoded_group_in_code():
    import pathlib
    root = pathlib.Path(__file__).parent.parent
    for f in ("ai_solver.py", "gemini_solver.py", "group_context.py", "bot.py", "handlers/start.py",
              "handlers/schedule.py", "handlers/inline.py", "webapp/static/js/home.js"):
        assert "УИБО-03-24" not in (root / f).read_text(encoding="utf-8"), f

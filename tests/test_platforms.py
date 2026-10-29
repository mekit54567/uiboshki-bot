"""Капибара везде (владелец, 09.10): про PWA (uiboshki.ru/app) и приложение
рассказываем во всех местах, где бот представляется."""
import bot
from handlers.start import HELP_TEXT, start_text


def test_bot_description_mentions_pwa():
    assert "uiboshki.ru/app" in bot.BOT_DESCRIPTION
    assert "uiboshki.ru" in bot.BOT_SHORT_DESCRIPTION and len(bot.BOT_SHORT_DESCRIPTION) <= 120


def test_start_and_help_mention_pwa():
    assert "uiboshki.ru/app" in start_text("Аня") and "Ещё → Установить" in start_text("Аня")
    assert "uiboshki.ru/app" in HELP_TEXT and "VK" in HELP_TEXT


def test_rustore_everywhere():
    """Android-приложение в RuStore (27.10.2026) — в /start, /help, /app, описании бота,
    на сайте, в «Установить» Mini App и в /api/meta (links.rustore)."""
    import config
    from pathlib import Path
    from handlers.start import help_text
    url = config.RUSTORE_URL
    assert url.endswith("/ru.uiboshki.app")
    assert url in start_text("Аня") and url in help_text()
    assert "RuStore" in bot.BOT_DESCRIPTION
    root = Path(__file__).resolve().parents[1]
    assert url in (root / "webapp/static/site/index.html").read_text(encoding="utf-8")
    assert url in (root / "webapp/static/js/more.js").read_text(encoding="utf-8")


def test_news_channel_everywhere(monkeypatch):
    """Открытый канал Капибары (LOGIN_CHANNEL, Никита 19.10) — в /start, /help и
    описании бота; не задан — строки нет. Имя бота — «Капибара МИРЭА»."""
    import config
    from handlers.start import help_text
    monkeypatch.setattr(config, "LOGIN_CHANNEL", "")
    assert "Новости Капибары" not in start_text("Аня") + help_text() + bot.bot_description("УИБО-03-24")
    monkeypatch.setattr(config, "LOGIN_CHANNEL", "@kapibara_mirea")
    for text in (start_text("Аня"), help_text(), bot.bot_description("УИБО-03-24")):
        assert "Новости Капибары — @kapibara_mirea" in text
    assert len(bot.bot_description("УИБО-03-24")) <= 512                   # предел Telegram
    assert bot.BOT_NAME == "Капибара МИРЭА"


def test_start_not_one_group_bot(monkeypatch):
    """Бот — для любой группы МИРЭА (Никита 29.10: «Я бот группы УИБО…» — уже не так):
    представляется Капибарой, группа человека — строкой «Твоя группа», если выбрана."""
    text = start_text("Аня")
    assert "бот группы" not in text and "Капибара" in text and "Твоя группа" not in text
    assert "Твоя группа — <b>ИКБО-01-23</b>" in start_text("Аня", "ИКБО-01-23")


def test_appstore_only_when_live(monkeypatch):
    """App Store — только когда задан APPSTORE_URL (приложение вышло), до этого — молчим."""
    import config
    from handlers.start import help_text, stores_line
    monkeypatch.setattr(config, "LOGIN_CHANNEL", "")
    monkeypatch.setattr(config, "APPSTORE_URL", "")
    assert "App Store" not in start_text("Аня") + help_text() + stores_line() + bot.bot_description("УИБО-03-24")
    url = "https://apps.apple.com/ru/app/id123"
    monkeypatch.setattr(config, "APPSTORE_URL", url)
    for text in (start_text("Аня"), help_text(), stores_line()):
        assert url in text and config.RUSTORE_URL in text
    assert "App Store" in bot.bot_description("УИБО-03-24") and len(bot.bot_description("УИБО-03-24")) <= 512

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

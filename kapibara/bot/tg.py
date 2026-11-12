"""Узкие геттеры для событий Telegram в обработчиках.

aiogram честно говорит, что у события многое может не быть: `message.from_user`
— None у постов каналов, `callback.message` — `InaccessibleMessage` (сообщение
удалено или старше 48 часов) или None (кнопка из inline-режима),
`message.text` — None у фото, `message.bot` — None вне диспетчера. В наших
обработчиках этих случаев почти нет, но проверка типов (mypy) их видит —
сотни мест. Вместо `assert` и `# type: ignore` в каждом — функции здесь: одна
проверка, одно понятное поведение.

    from kapibara.bot.tg import data_of, msg, sender
    if not is_starosta(sender(message).id): ...
    await msg(callback).edit_text(...)

Решение про устаревшее сообщение одно на весь бот (ADR 0004): `msg()`
бросает `StaleMessage`; внутри `cosmetic(...)` она глотается как ожидаемая, а
на верхнем уровне её ловит `stale_message` (bot.py) — человеку «сообщение
устарело», старосте алерт не уходит, в лог одна строка.
"""
import logging

from aiogram import Bot
from aiogram.types import CallbackQuery, ChatMemberUpdated, ErrorEvent, InaccessibleMessage, Message, User

from kapibara.core.errors import StaleMessage
from kapibara.core.telegram import cosmetic

logger = logging.getLogger(__name__)

STALE_TEXT = "Это сообщение устарело — вызови команду заново"


def sender(event: Message | CallbackQuery) -> User:
    """Кто прислал. У сообщений в личке и в группе отправитель есть всегда."""
    user = event.from_user
    if user is None:
        raise RuntimeError(f"{type(event).__name__} без отправителя")
    return user


def msg(callback: CallbackQuery) -> Message:
    """Сообщение, под которым нажали кнопку. Нет доступа — `StaleMessage`."""
    m = callback.message
    if m is None or isinstance(m, InaccessibleMessage):   # не «not Message»: тесты подсовывают заглушки
        raise StaleMessage(type(m).__name__)
    return m


def text_of(message: Message) -> str:
    """Текст сообщения; у фото, файла, стикера — пустая строка (подпись не берём)."""
    return message.text or ""


def data_of(callback: CallbackQuery) -> str:
    """Данные кнопки; у игровых кнопок их нет — пустая строка."""
    return callback.data or ""


def bot_of(event: Message | CallbackQuery | ChatMemberUpdated) -> Bot:
    """Бот, через которого пришло событие (в диспетчере он есть всегда)."""
    bot = event.bot
    if bot is None:
        raise RuntimeError(f"{type(event).__name__} без бота: событие не из диспетчера")
    return bot


async def stale_message(event: ErrorEvent) -> None:
    """Ошибка `StaleMessage` из обработчика кнопки: ответить человеку, без алерта."""
    logger.info(f"кнопка под устаревшим сообщением: {event.exception}")
    callback = event.update.callback_query
    if callback is not None:
        with cosmetic("tg.stale_message: ответ на кнопку"):
            await callback.answer(STALE_TEXT, show_alert=True)

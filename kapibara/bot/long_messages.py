"""
Длинные сообщения — частями. Живой тест: одногруппник открыл бота, и
сразу «TelegramBadRequest: message is too long». После синка СДО дедлайнов
стало 32, у каждого описание и ссылка — список перевалил за лимит Telegram
(4096 символов). Так же могло упасть расписание преподавателя на 2 недели и
всё, что вырастет потом.

Вместо того чтобы резать в каждом хендлере, — одна прослойка на все
sendMessage бота: текст длиннее лимита уходит несколькими сообщениями,
разрезанный по строкам (строки в наших HTML-текстах закрывают свои теги
сами), клавиатура — у последнего куска.
"""

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.methods import SendMessage

LIMIT = 4000   # с запасом до 4096: HTML-сущности Telegram считает после разбора


def split_text(text: str, limit: int = LIMIT) -> list[str]:
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:              # одна строка сама длиннее лимита — режем её
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{cur}\n{line}" if cur else line
        if len(candidate) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = candidate
    if cur or not chunks:
        chunks.append(cur)
    return [c for c in chunks if c.strip()] or [text[:limit]]


class SplitLongMessages(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        if isinstance(method, SendMessage) and method.text and len(method.text) > LIMIT:
            *head, last = split_text(method.text)
            for chunk in head:
                await make_request(bot, method.model_copy(update={"text": chunk, "reply_markup": None}))
            method = method.model_copy(update={"text": last})
        return await make_request(bot, method)

"""
Единое место для всех клавиатур бота и набора текстов кнопок меню.

Раньше MAIN_KB/ACTIONS_KB/CANCEL_KB и наборы "текстов кнопок, которые не надо
путать с вводом пользователя" были продублированы в start.py, deadlines.py,
files.py, solver.py — с расхождениями (например, в solver.py не хватало
части кнопок). Из-за этого можно было словить баг: пользователь на середине
FSM-диалога (ввод дедлайна, выбор предмета для решателя и т.д.) нажимает
кнопку меню — а она воспринимается как обычный текстовый ввод и улетает
в базу как значение поля.

MENU_BUTTON_TEXTS — источник правды для всех текстов кнопок. Используется
в middleware.py, который сбрасывает активное FSM-состояние при нажатии любой
из этих кнопок, поэтому больше не нужно вручную дублировать проверку в
каждом хендлере.
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def webapp_keyboard(text: str = "🚀 Открыть приложение") -> InlineKeyboardMarkup | None:
    """Кнопка запуска Mini App. Возвращает None, если WEBAPP_URL не настроен —
    Telegram не даёт зарегистрировать WebAppInfo с пустым/не-https url, поэтому
    вызывающий код должен сам проверить на None перед показом кнопки."""
    from aiogram.types import WebAppInfo
    from config import WEBAPP_URL
    if not WEBAPP_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, web_app=WebAppInfo(url=WEBAPP_URL))]
    ])


MAIN_KB = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📅 Сегодня"),    KeyboardButton(text="📆 Неделя"),     KeyboardButton(text="🌅 Завтра")],
    [KeyboardButton(text="⏭ Следующая"),   KeyboardButton(text="📋 Дедлайны"),   KeyboardButton(text="🤖 Решить")],
    [KeyboardButton(text="📁 Файлы"),       KeyboardButton(text="📝 ДЗ"),         KeyboardButton(text="🌤 Погода")],
    [KeyboardButton(text="🗣 Подслушано"),  KeyboardButton(text="🏆 Рейтинг"),    KeyboardButton(text="⚙️ Настройки")],
    [KeyboardButton(text="⋯ Действия")],
], resize_keyboard=True)

CANCEL_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)

STOP_DIALOG_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🛑 Завершить диалог")]],
    resize_keyboard=True
)

ACTIONS_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="➕ Дедлайн",             callback_data="act:add_deadline"),
     InlineKeyboardButton(text="📤 Загрузить файлы",     callback_data="act:upload")],
    [InlineKeyboardButton(text="📆 След. неделя",        callback_data="act:nextweek"),
     InlineKeyboardButton(text="🔍 Чужое расписание",    callback_data="act:lookup")],
    [InlineKeyboardButton(text="📖 Решить по лекциям",   callback_data="act:solve_lectures"),
     InlineKeyboardButton(text="📜 История решений",     callback_data="act:history")],
    [InlineKeyboardButton(text="🗳 Голосование",         callback_data="act:vote"),
     InlineKeyboardButton(text="🗣 Подслушано",          callback_data="act:feed")],
    [InlineKeyboardButton(text="❓ Вопрос старосте",      callback_data="act:anon"),
     InlineKeyboardButton(text="➕ ДЗ (староста)",        callback_data="act:add_hw")],
    [InlineKeyboardButton(text="🐋 Через DeepSeek",      callback_data="act:solve_ds"),
     InlineKeyboardButton(text="⚙️ Настройки",           callback_data="act:settings")],
])

# Все тексты, которые появляются хоть на одной клавиатуре бота (reply-кнопки).
# Если пользователь прислал именно такой текст во время активного FSM-состояния —
# это почти всегда означает "я хочу перейти в другой раздел", а не "вот моё значение".
MENU_BUTTON_TEXTS = {
    "📅 Сегодня", "📆 Неделя", "🌅 Завтра", "⏭ Следующая",
    "📆 След. неделя", "📋 Дедлайны", "➕ Дедлайн", "🤖 Решить",
    "📁 Файлы", "📝 ДЗ", "🌤 Погода", "🏆 Рейтинг", "⚙️ Настройки",
    "⋯ Действия", "❌ Отмена", "🛑 Завершить диалог",
    "🗳 Голосование", "❓ Вопрос анон", "🔔 Подписка", "🗣 Подслушано",
}

"""Переехал в kapibara/bot/long_messages.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.bot.long_messages as _m

sys.modules[__name__] = _m

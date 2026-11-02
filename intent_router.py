"""Переехал в kapibara/bot/intent_router.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.bot.intent_router as _m

sys.modules[__name__] = _m

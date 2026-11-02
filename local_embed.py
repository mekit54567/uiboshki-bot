"""Переехал в kapibara/features/ai/local_embed.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.features.ai.local_embed as _m

sys.modules[__name__] = _m

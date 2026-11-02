"""Переехал в kapibara/features/schedule/format.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.features.schedule.format as _m

sys.modules[__name__] = _m

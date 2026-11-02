"""Переехал в kapibara/features/schedule/mirea_api.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.features.schedule.mirea_api as _m

sys.modules[__name__] = _m

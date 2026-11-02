"""Переехал в kapibara/features/notifications/evening_digest.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.features.notifications.evening_digest as _m

sys.modules[__name__] = _m

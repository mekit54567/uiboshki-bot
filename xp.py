"""Переехал в kapibara/features/social/xp.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.features.social.xp as _m

sys.modules[__name__] = _m

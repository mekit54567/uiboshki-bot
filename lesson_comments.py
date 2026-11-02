"""Переехал в kapibara/features/social/comments.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.features.social.comments as _m

sys.modules[__name__] = _m

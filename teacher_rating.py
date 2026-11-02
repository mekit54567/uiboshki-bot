"""Переехал в kapibara/features/social/teacher_rating.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.features.social.teacher_rating as _m

sys.modules[__name__] = _m

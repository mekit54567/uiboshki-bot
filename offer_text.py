"""Переехал в kapibara/features/privacy/offer_text.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.features.privacy.offer_text as _m

sys.modules[__name__] = _m

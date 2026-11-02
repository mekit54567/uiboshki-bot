"""Переехал в kapibara/features/identity/login_channel.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.features.identity.login_channel as _m

sys.modules[__name__] = _m

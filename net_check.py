"""Переехал в kapibara/ops/net_check.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.ops.net_check as _m

sys.modules[__name__] = _m

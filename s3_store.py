"""Переехал в kapibara/ops/s3_store.py — здесь переадресация на тот же
модуль (docs/adr/0003-safe-moves.md). Убирается, когда импорты перепишем."""
import sys

import kapibara.ops.s3_store as _m

sys.modules[__name__] = _m

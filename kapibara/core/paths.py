"""Пути проекта. Файлы данных (pulse_lab_kit/, assets/, roadmap.json…) лежат в
корне репозитория, а модули переезжают глубже в kapibara/ — поэтому путь
считаем от корня, а не от файла модуля (docs/adr/0003-safe-moves.md)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

"""Этап 2 (д): дизайн-токены — один источник для веба и Flutter."""
import re

from tools import tokens


def test_tokens_complete_and_css_fresh():
    t = tokens.load()
    # «Кампус» и «Библиотека» — темы приложения из «Оформления» (5.79)
    # «Тетрадь» и «Ночная тетрадь» по брендбуку v1 — paper и night (11.11)
    assert set(t["themes"]) == {"depth", "notebook", "campus", "library", "paper", "night"} and t["fonts"]["default"] in t["fonts"]
    keys = set(t["themes"]["depth"])
    for name, theme in t["themes"].items():
        assert set(theme) == keys, f"у тем один набор цветов: {name}"
    for theme in t["themes"].values():
        for k, v in theme.items():
            if k != "label":
                assert re.fullmatch(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", v), (k, v)
    assert tokens.CSS.read_text(encoding="utf-8") == tokens.css(t), "запусти python tools/tokens.py"


def test_dart_output():
    d = tokens.dart(tokens.load())
    assert "class ThemeDepth" in d and "static const bg = Color(0xFF141823);" in d
    assert "static const card = Color(0x13FFFFFF);" in d                       # #RRGGBBAA → 0xAARRGGBB

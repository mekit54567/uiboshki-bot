"""
gemini_solver._fit_context_budget: обрезка контекста лекций под лимит токенов
Gemini. Чистая функция, без сети — но именно тут раньше был реальный баг
(найден независимым ревью): если ПЕРВАЯ лекция сама больше бюджета, функция
возвращала её целиком с truncated=False, что рисковало отправить запрос
больше лимита без предупреждения.
"""
from gemini_solver import _fit_context_budget


def _lecture(name: str, size: int) -> str:
    return f"=== {name} ===\n" + ("x" * size)


def test_fits_under_budget_untouched():
    context = _lecture("Лекция 1", 100)
    fitted, truncated = _fit_context_budget(context, max_chars=1000)
    assert fitted == context
    assert truncated is False


def test_drops_latest_lectures_that_dont_fit():
    context = "\n\n".join([_lecture("Лекция 1", 100), _lecture("Лекция 2", 100), _lecture("Лекция 3", 100)])
    fitted, truncated = _fit_context_budget(context, max_chars=250)
    assert "Лекция 1" in fitted
    assert "Лекция 3" not in fitted
    assert truncated is True


def test_single_oversized_first_lecture_is_still_truncated():
    context = _lecture("Гигантская лекция", 5000)
    fitted, truncated = _fit_context_budget(context, max_chars=1000)
    assert len(fitted) == 1000
    assert truncated is True, "регрессия: первая лекция больше бюджета должна резаться, а не уходить целиком"

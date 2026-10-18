"""Чат бота в Telegram ищет куски лекций по смыслу, как приложение (5.94):
в ИИ уходят ~16 тыс. символов вместо целых лекций; «объясни 3 лекцию» и
пустой индекс — по-старому, целыми лекциями. Под ответом — откуда куски."""
import pytest

import semantic_search
from handlers import solver

HIT = {"file_id": 7, "title": "Лекция 5. Оценка бизнеса", "subject": "Экономика", "page_from": 12,
       "page_to": 12, "kind": "слайд", "text": "Дисконтирование денежных потоков…"}


@pytest.fixture
def index(monkeypatch):
    calls = []

    async def ready():
        return True

    async def search(query, subject="", k=semantic_search.TOP):
        calls.append((query, subject))
        return [HIT]

    async def whole(subject):
        return "=== Лекция 5 ===\nцелая лекция " * 10

    monkeypatch.setattr(semantic_search, "ready", ready)
    monkeypatch.setattr(semantic_search, "search", search)
    monkeypatch.setattr(solver, "get_subject_lecture_context", whole)
    return calls


@pytest.mark.asyncio
async def test_bot_uses_chunks_not_whole_lectures(index):
    data = {"has_lectures": True, "subject": "Экономика"}
    ctx = await solver._lectures_for(data, "как дисконтируют денежные потоки")
    assert ctx.startswith("=== [1] Экономика: Лекция 5. Оценка бизнеса · слайд 12 ===")
    assert index == [("как дисконтируют денежные потоки", "Экономика")]
    assert "целая лекция" in await solver._lectures_for(data, "объясни 5 лекцию")   # по номеру — целиком
    assert await solver._lectures_for({"has_lectures": False}, "вопрос") == ""


@pytest.mark.asyncio
async def test_bot_falls_back_when_index_empty(index, monkeypatch):
    async def empty():
        return False
    monkeypatch.setattr(semantic_search, "ready", empty)
    ctx = await solver._lectures_for({"has_lectures": True, "subject": "Экономика"}, "вопрос про потоки")
    assert "целая лекция" in ctx and not index


def test_sources_line_only_for_cited_chunks():
    ctx, _ = semantic_search.build_context([HIT, {**HIT, "file_id": 8, "title": "Лекция 6", "page_from": 3,
                                                 "page_to": 4}])
    out = solver.with_sources("Потоки дисконтируют [1].", ctx)
    assert out.endswith("📚 [1] Лекция 5. Оценка бизнеса · слайд 12")
    assert solver.with_sources("Без ссылок.", ctx) == "Без ссылок."
    assert solver.with_sources("Ответ [1].", "=== Лекция 5 ===\nтекст") == "Ответ [1]."      # целые лекции — без строки


def test_sources_line_title_up_to_40_by_word():
    # робот 18.10: название резалось до 28 знаков посреди слова
    long = "Лекция 5. Оценка стоимости бизнеса доходным подходом"
    ctx, _ = semantic_search.build_context([{**HIT, "title": long}])
    out = solver.with_sources("Ответ [1].", ctx)
    assert out.endswith("📚 [1] Лекция 5. Оценка стоимости бизнеса… · слайд 12")
    assert semantic_search.short_title("Лекция 5. Оценка бизнеса") == "Лекция 5. Оценка бизнеса"
    assert semantic_search.short_title("Аааааааааааааааааааааааааааааааааа", 10) == "Ааааааааа…"   # без пробела — как было

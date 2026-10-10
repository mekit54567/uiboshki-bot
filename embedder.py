"""
Чем считать векторы для поиска по смыслу: Gemini (как было) или своя модель
на сервере (local_embed.py) — для переезда в Россию, где Google не отвечает.

`EMBED_PROVIDER` — `gemini` (по умолчанию) или ключ модели из
local_embed.MODELS (`rubert-mini-frida`, можно с приставкой `local:`).
У каждой модели свои векторы в индексе (своя таблица vec0): переключение
туда и обратно мгновенное, пересчитывать заново не надо.
`EMBED_PRECOMPUTE` — модель, векторы которой фоном считаются заранее, пока
поиск идёт на другой (например, на Railway до переезда).
"""

import os

import local_embed

GEMINI = "gemini"


class EmbedError(RuntimeError):
    pass


def _key(raw: str | None) -> str:
    raw = (raw or "").strip().lower()
    if raw.startswith("local:"):
        raw = raw[len("local:"):]
    return raw if raw in local_embed.MODELS else GEMINI


def provider() -> str:
    return _key(os.getenv("EMBED_PROVIDER", GEMINI))


def precompute() -> str | None:
    """Модель для фонового пересчёта заранее (не та, что сейчас ищет)."""
    raw = os.getenv("EMBED_PRECOMPUTE", "")
    p = _key(raw)
    return p if raw.strip() and p != provider() else None


def dims(p: str) -> int:
    if p == GEMINI:
        from config import GEMINI_EMBED_DIMS
        return GEMINI_EMBED_DIMS
    return local_embed.MODELS[p]["dims"]


def vec_table(p: str) -> str:
    """Таблица векторов модели в индексе (у Gemini — прежняя vec_chunks)."""
    return "vec_chunks" if p == GEMINI else "vec_" + p.replace("-", "_")


def done_table(p: str) -> str | None:
    """Какие куски уже с векторами этой модели (у Gemini — колонка chunks.embedded)."""
    return None if p == GEMINI else "emb_" + p.replace("-", "_")


def min_sim(p: str, gemini_default: float) -> float:
    return gemini_default if p == GEMINI else local_embed.MODELS[p]["min_sim"]


async def embed(texts: list[str], *, query: bool = False, titles: list[str] | None = None,
                p: str | None = None) -> list[list[float]]:
    """Векторы единичной длины. Куски лекций — с названием файла (так точнее)."""
    p = p or provider()
    if p == GEMINI:
        import gemini_solver
        try:
            return await gemini_solver.embed(texts, "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT", titles=titles)
        except gemini_solver.GeminiError as e:
            raise EmbedError(str(e)) from e
    if titles and not query:
        texts = [f"{t}\n{x}" if t else x for t, x in zip(titles, texts)]
    try:
        return await local_embed.embed(p, texts, query=query)
    except Exception as e:
        raise EmbedError(f"своя модель {p}: {type(e).__name__}: {e}") from e

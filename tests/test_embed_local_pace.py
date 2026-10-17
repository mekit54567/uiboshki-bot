"""Своя модель векторов не отнимает процессор у ответов (17.10, Amvera: проход
раз в 20 минут — троттлинг CPU до 90%, ответы по 10–60 с): пачки по
LOCAL_BATCH, после каждой отдых втрое дольше счёта, проход ограничен по
времени. Gemini — как было: пачки по 64 без отдыха."""
import pytest

import semantic_index as si
from tests.test_semantic_search import embed  # noqa: F401 — фикстура


async def _fill(db, n):
    fid = await db.add_file("Лекция 1", "Анализ данных", "tg1", "л1.txt", 1)
    await db.save_file_text(fid, "текст")
    await si.index_file(fid, None, "л1.txt", text="\n\n".join(f"кусок {i} про анализ " * 60 for i in range(n)))


@pytest.mark.asyncio
async def test_local_model_rests_between_small_batches(db, embed, monkeypatch):  # noqa: F811
    import embedder
    import local_embed
    await _fill(db, 40)
    sizes, sleeps, clock = [], [], [0.0]

    async def fake_local(key, texts, query=False):
        sizes.append(len(texts))
        clock[0] += 2.0                      # счёт пачки — 2 с
        return [[1.0] + [0.0] * 311 for _ in texts]

    async def no_download(key):
        return ""

    async def fake_sleep(s):
        sleeps.append(s)
        clock[0] += s

    monkeypatch.setenv("EMBED_PROVIDER", "rubert-mini-frida")
    monkeypatch.setattr(local_embed, "embed", fake_local)
    monkeypatch.setattr(local_embed, "download", no_download)
    monkeypatch.setattr(si.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(si.time, "monotonic", lambda: clock[0])
    assert embedder.provider() == "rubert-mini-frida"

    done = await si.embed_pending(pause=0)
    assert done > si.LOCAL_BATCH and max(sizes) <= si.LOCAL_BATCH
    assert sleeps and all(s == pytest.approx(si.LOCAL_REST * 2.0) for s in sleeps)

    # проход ограничен по времени: 2 с счёта + 6 с отдыха на пачку
    monkeypatch.setattr(si, "LOCAL_BUDGET", 20)
    await _fill(db, 40)
    sizes.clear()
    await si.embed_pending(pause=0)
    assert len(sizes) == 3                   # 0, 8, 16 с — дальше бюджет кончился


@pytest.mark.asyncio
async def test_gemini_keeps_big_batches_without_rest(db, embed, monkeypatch):  # noqa: F811
    await _fill(db, 10)
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(si.asyncio, "sleep", fake_sleep)
    assert await si.embed_pending(pause=0) > 0
    assert sleeps == []

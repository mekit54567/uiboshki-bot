"""/embedtest (embed_bench.py): вопросы к кускам лекций, место нужного куска
у каждой модели, порог «про лекции», отчёт. Сеть подменена."""
import json

import pytest

import embed_bench
import semantic_index as si
from tests.test_semantic_search import fake_vec, embed  # noqa: F401 — фикстура


@pytest.mark.asyncio
async def test_embedtest_report(db, embed, monkeypatch):  # noqa: F811
    import gemini_solver
    import local_embed
    topics = ["дисконт npv прибыль", "регресс коэффициент", "баланс актив"] * 2
    for i, t in enumerate(topics):
        fid = await db.add_file(f"Лекция {i}", "Анализ данных", f"tg{i}", f"л{i}.txt", 1)
        await db.save_file_text(fid, "текст")
        await si.index_file(fid, None, f"л{i}.txt", text="\n\n".join(f"{t} подробно " * 40 for _ in range(4)))
    await si.embed_pending(pause=0)

    async def fake_text(history, system, **kw):
        n = int(history[0]["content"].split("ровно ")[1].split()[0])
        return json.dumps(["как считать прибыль проекта"] * n, ensure_ascii=False)

    async def fake_local(key, texts, query=False):
        return [fake_vec(t) for t in texts]

    async def no_download(key):
        return ""

    monkeypatch.setattr(gemini_solver, "generate_text", fake_text)
    monkeypatch.setattr(local_embed, "embed", fake_local)
    monkeypatch.setattr(local_embed, "download", no_download)
    monkeypatch.setattr(embed_bench, "TARGETS", 10)
    text = await embed_bench.run(["rubert-tiny-turbo"])
    assert "<b>gemini</b>: R@1" in text and "<b>rubert-tiny-turbo</b>: R@1" in text
    assert "мс на кусок" in text and "порог" in text and "«как считать прибыль проекта»" in text


def test_score_ranks_and_threshold():
    q = [[1, 0], [0, 1]]
    hay = [[1, 0], [0.6, 0.8], [0, 1]]
    r = embed_bench._score(q, hay, [10, 11, 12], [10, 11], [[0.7, 0.7]])
    assert r["r1"] == 0.5 and r["r5"] == 1.0 and r["mrr"] == pytest.approx(0.75)

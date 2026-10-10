"""
/embedtest у старосты: какая своя модель векторов заменит Gemini (переезд в
Россию, PLAN.md). Прогон — на сервере бота, на настоящих лекциях группы.

1. Из индекса берутся куски лекций: TARGETS «целей» (не больше двух с файла)
   и до POOL остальных — «стог».
2. Gemini пишет к каждой цели вопрос студента своими словами (без редких
   слов из текста — иначе это проверка поиска по словам, а не по смыслу).
3. Каждая модель (Gemini — уже посчитанные векторы индекса, свои — по
   local_embed.MODELS) кодирует стог и вопросы; для каждого вопроса — на
   каком месте нужный кусок: R@1, R@5, MRR.
4. Порог «это про лекции»: лучший косинус у настоящих вопросов против
   посторонних фраз («привет», «посоветуй фильм») — середина между ними.
5. Память (+МБ к процессу) и скорость (мс на кусок) своих моделей.

Платное — только один запрос к Gemini за вопросами (бесплатный лимит).
"""

import asyncio
import json
import logging
import os
import random
import re
import tempfile
import time
from html import escape

logger = logging.getLogger(__name__)

TARGETS = 40
POOL = 600
OFFTOPIC = ["привет", "спасибо большое", "как дела?", "какая завтра погода", "посоветуй фильм на вечер",
            "во сколько завтра первая пара", "скинь расписание", "кто сегодня дежурный", "хочу пиццу",
            "что ты умеешь"]
_lock = asyncio.Lock()


def _rss_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


async def _sample() -> tuple[list[tuple], list[tuple]]:
    """(цели, стог): [(id, текст, название файла)]; цели входят в стог."""
    import semantic_index as si
    async with si.open_index() as db:
        rows = await (await db.execute(
            "SELECT c.id, c.text, COALESCE(f.title, ''), c.file_id FROM chunks c JOIN m.files f ON f.id = c.file_id "
            "WHERE length(c.text) >= 200")).fetchall()
    rng = random.Random(len(rows))
    rng.shuffle(rows)
    targets, per_file = [], {}
    for r in rows:
        if len(r[1]) >= 450 and per_file.get(r[3], 0) < 2:
            targets.append(r[:3])
            per_file[r[3]] = per_file.get(r[3], 0) + 1
            if len(targets) == TARGETS:
                break
    ids = {t[0] for t in targets}
    hay = targets + [r[:3] for r in rows if r[0] not in ids][:POOL - len(targets)]
    return targets, hay


async def _questions(targets: list[tuple]) -> list[str]:
    import gemini_solver
    blocks = "\n\n".join(f"[{i}] {t[1][:900]}" for i, t in enumerate(targets, 1))
    prompt = (
        "Ниже — фрагменты лекций. К каждому напиши один вопрос, который мог бы задать студент, "
        "чтобы найти именно этот фрагмент: 6–15 слов, по-русски, своими словами — не копируй "
        "термины и редкие слова из фрагмента, перефразируй. Ответ — только JSON-массив строк "
        f"по порядку, ровно {len(targets)} штук.\n\n{blocks}")
    text = await gemini_solver.generate_text([{"role": "user", "content": prompt}],
                                             "Ты готовишь тест для поиска по лекциям.",
                                             temperature=0.4, max_output_tokens=8192, timeout=120, fallback=False)
    m = re.search(r"\[.*\]", text, re.S)
    qs = json.loads(m.group(0)) if m else []
    if len(qs) != len(targets):
        raise RuntimeError(f"Gemini дал {len(qs)} вопросов вместо {len(targets)}")
    return [str(q) for q in qs]


def _score(qv, hv, hay_ids: list[int], target_ids: list[int], off_v) -> dict:
    import numpy as np
    sims = np.asarray(qv, dtype=np.float32) @ np.asarray(hv, dtype=np.float32).T
    pos = {cid: i for i, cid in enumerate(hay_ids)}
    ranks = []
    for qi, cid in enumerate(target_ids):
        mine = sims[qi, pos[cid]]
        ranks.append(int((sims[qi] > mine).sum()) + 1)
    best_q = sims.max(1)
    best_off = (np.asarray(off_v, dtype=np.float32) @ np.asarray(hv, dtype=np.float32).T).max(1)
    lo_q, hi_off = float(np.percentile(best_q, 10)), float(best_off.max())
    n = len(ranks)
    return {"r1": sum(r == 1 for r in ranks) / n, "r5": sum(r <= 5 for r in ranks) / n,
            "mrr": sum(1 / r for r in ranks) / n, "q10": lo_q, "off_max": hi_off,
            "thr": round((lo_q + hi_off) / 2, 2)}


async def _gemini_run(hay, targets, questions) -> dict:
    import embedder
    import semantic_index as si
    ids = [h[0] for h in hay]
    async with si.open_index() as db:
        rows = await (await db.execute(
            f"SELECT rowid, embedding FROM vec_chunks WHERE rowid IN ({','.join('?' * len(ids))})", ids)).fetchall()
    have = {r[0]: si.unpack(r[1]) for r in rows}
    missing = [h for h in hay if h[0] not in have]
    for i in range(0, len(missing), 64):
        part = missing[i:i + 64]
        for h, v in zip(part, await embedder.embed([h[1] for h in part], titles=[h[2] for h in part], p="gemini")):
            have[h[0]] = v
    qv = await embedder.embed(questions, query=True, p="gemini")
    off = await embedder.embed(OFFTOPIC, query=True, p="gemini")
    return _score(qv, [have[i] for i in ids], ids, [t[0] for t in targets], off)


async def _local_run(key: str, hay, targets, questions) -> dict:
    import local_embed
    await local_embed.download(key)
    local_embed.unload_idle(idle=-1)
    before = _rss_mb()
    docs = [f"{h[2]}\n{h[1]}" if h[2] else h[1] for h in hay]
    started = time.monotonic()
    hv = await local_embed.embed(key, docs)
    per = (time.monotonic() - started) / len(docs) * 1000
    qv = await local_embed.embed(key, questions, query=True)
    off = await local_embed.embed(key, OFFTOPIC, query=True)
    res = _score(qv, hv, [h[0] for h in hay], [t[0] for t in targets], off)
    res.update(ms=round(per), mb=round(_rss_mb() - before))
    local_embed.unload_idle(idle=-1)
    return res


async def run(keys: list[str] | None = None) -> str:
    import local_embed
    keys = keys or list(local_embed.MODELS)
    targets, hay = await _sample()
    if len(targets) < 10:
        return "Мало лекций в индексе для теста — нужно хотя бы 10 кусков."
    questions = await _questions(targets)
    results = {}
    try:
        results["gemini"] = await _gemini_run(hay, targets, questions)
    except Exception as e:
        results["gemini"] = {"error": f"{type(e).__name__}: {e}"}
    # модели — во временную папку, если своя не задана (на Railway том маленький)
    own_dir = os.environ.get("EMBED_DIR")
    if not own_dir:
        os.environ["EMBED_DIR"] = os.path.join(tempfile.gettempdir(), "uiboshki-models")
    try:
        for key in keys:
            try:
                results[key] = await _local_run(key, hay, targets, questions)
            except Exception as e:
                logger.warning(f"embedtest {key}: {type(e).__name__}: {e}")
                results[key] = {"error": f"{type(e).__name__}: {e}"}
    finally:
        if not own_dir:
            os.environ.pop("EMBED_DIR", None)
    logger.info(f"embedtest: {json.dumps(results, ensure_ascii=False)}")
    return report(results, len(targets), len(hay), questions[:3])


def report(results: dict, n_targets: int, n_hay: int, examples: list[str]) -> str:
    lines = ["<b>Свои векторы против Gemini</b>",
             f"{n_targets} вопросов к кускам лекций, искали среди {n_hay} кусков.", ""]
    for key, r in results.items():
        if "error" in r:
            lines.append(f"🔴 {key}: {escape(r['error'][:200])}")
            continue
        speed = f" · {r['ms']} мс на кусок · +{r['mb']} МБ" if "ms" in r else ""
        lines.append(f"<b>{key}</b>: R@1 {r['r1']:.0%} · R@5 {r['r5']:.0%} · MRR {r['mrr']:.2f}{speed}")
        lines.append(f"   порог «про лекции» ≈ {r['thr']} (вопросы от {r['q10']:.2f}, посторонние до {r['off_max']:.2f})")
    lines += ["", "Примеры вопросов: " + " · ".join(f"«{escape(q)}»" for q in examples)]
    return "\n".join(lines)

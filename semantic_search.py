"""
Поиск по смыслу в лекциях группы — гибридный (индекс — semantic_index.py).

Вопрос ищется двумя путями сразу:
  • по словам — FTS5, ранжирование BM25 (с расшифровкой сокращений и
    любыми окончаниями из lecture_picker: «дисконт*»);
  • по смыслу — вектор вопроса (Gemini или своя модель, embedder.py) против векторов
    кусков в sqlite-vec: «почему нельзя просто сложить прибыль за годы»
    находит «дисконтирование» и «NPV», хотя этих слов в вопросе нет.

Два списка сливаются по Reciprocal Rank Fusion — важно место в списке, а не
сырые числа (BM25 и косинус несравнимы): score = Σ 1 / (K + место). Потом
MMR (Maximal Marginal Relevance) выбирает самые подходящие, но разные куски —
чтобы три соседних слайда про одно не вытеснили остальное, и не больше
PER_FILE кусков из одного файла.

ИИ получает куски с номерами [1], [2]… и ссылается на них в ответе, а под
ответом — «Лекция 5 · слайд 12»: нажал — открылась нужная страница.
"""

import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)

RRF_K = 60            # классическая константа RRF: сглаживает разницу верхних мест
POOL = 40             # сколько кандидатов берёт каждый путь
TOP = 10              # сколько кусков уходит ИИ
PER_FILE = 3
MMR_LAMBDA = 0.72     # 1 — только релевантность, 0 — только разнообразие
VEC_MIN_SIM = 0.55    # без выбранного предмета: «по смыслу» ниже — не про лекции (подстроить по живым)
CONTEXT_CHARS = 16_000

_qcache: "OrderedDict[str, list[float] | None]" = OrderedDict()


def fts_query(query: str) -> str:
    """Запрос FTS5: основы слов вопроса (и расшифровок сокращений) с любым
    окончанием — «"дисконт"* OR "проект"*». Пусто — путь по словам пропускаем."""
    from lecture_picker import _stems, expand
    words = sorted(w for w in _stems(expand(query)) if len(w) >= 3 and '"' not in w)
    return " OR ".join(f'"{w}"*' for w in words[:24])


async def _query_vec(query: str, p: str) -> list[float] | None:
    """Вектор вопроса моделью p (embedder.py); одинаковые вопросы не тратят
    лимит Gemini (кэш)."""
    key = f"{p}\n{query.strip().lower()}"
    if key in _qcache:
        _qcache.move_to_end(key)
        return _qcache[key]
    import embedder
    try:
        (vec,) = await embedder.embed([query], query=True, p=p)
    except embedder.EmbedError as e:
        logger.info(f"поиск по смыслу без вектора вопроса: {e}")
        return None
    _qcache[key] = vec
    while len(_qcache) > 256:
        _qcache.popitem(last=False)
    return vec


def rrf(*ranked: list[int]) -> dict[int, float]:
    """Reciprocal Rank Fusion: id → Σ 1/(K + место) по всем спискам."""
    out: dict[int, float] = {}
    for lst in ranked:
        for place, cid in enumerate(lst, 1):
            out[cid] = out.get(cid, 0.0) + 1.0 / (RRF_K + place)
    return out


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))       # векторы уже единичные


def mmr(cands: list[dict], k: int = TOP, lam: float = MMR_LAMBDA, per_file: int = PER_FILE) -> list[dict]:
    """Жадный MMR: каждый следующий кусок — max(λ·релевантность −
    (1−λ)·похожесть на уже взятые). Похожесть — косинус векторов, а у
    кусков без вектора — доля общих основ слов."""
    from lecture_picker import _stems
    if not cands:
        return []
    top = max(c["score"] for c in cands) or 1.0
    for c in cands:
        c.setdefault("_stems", _stems(c["text"]))

    def sim(a, b):
        if a.get("vec") and b.get("vec"):
            return _cos(a["vec"], b["vec"])
        sa, sb = a["_stems"], b["_stems"]
        return len(sa & sb) / (len(sa | sb) or 1)

    picked, per = [], {}
    pool = list(cands)
    while pool and len(picked) < k:
        best = max(pool, key=lambda c: lam * c["score"] / top
                   - (1 - lam) * max((sim(c, p) for p in picked), default=0.0))
        pool.remove(best)
        if per.get(best["file_id"], 0) >= per_file:
            continue
        per[best["file_id"]] = per.get(best["file_id"], 0) + 1
        picked.append(best)
    return picked


async def ready() -> bool:
    """Есть ли что искать (индекс наполняется фоном после деплоя)."""
    from semantic_index import open_index
    try:
        async with open_index() as db:
            return (await (await db.execute("SELECT 1 FROM chunks LIMIT 1")).fetchone()) is not None
    except Exception as e:
        logger.info(f"индекс поиска недоступен: {e}")
        return False


async def search(query: str, subject: str = "", k: int = TOP) -> list[dict]:
    """Гибридный поиск: [{id, file_id, title, subject, page_from, page_to, kind,
    text, score, lex, sem, sim}] — лучшие и разные куски. lex/sem — место в
    списке «по словам» / «по смыслу» (None — не нашёлся этим путём)."""
    import embedder
    import semantic_index as si
    from semantic_index import open_index, unpack
    p = embedder.provider()
    vt = embedder.vec_table(p)
    query = (query or "").strip()
    if not query:
        return []
    subj_sql, subj_args = (" AND f.subject = ?", [subject]) if subject else ("", [])
    # только лекции группы того, кто спрашивает (этап 1 (б); current_group)
    from database.groups import file_scope_sql, g_or_home
    g = g_or_home(None)
    subj_sql += " AND " + file_scope_sql("f")
    subj_args = [*subj_args, g, g]
    async with open_index() as db:
        lex: list[int] = []
        q = fts_query(query)
        if q:
            try:
                rows = await (await db.execute(
                    "SELECT c.id FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid "
                    "JOIN m.files f ON f.id = c.file_id WHERE chunks_fts MATCH ?" + subj_sql +
                    " ORDER BY bm25(chunks_fts) LIMIT ?", [q, *subj_args, POOL])).fetchall()
                lex = [r[0] for r in rows]
            except Exception as e:
                logger.info(f"поиск по словам: {e}")
        sem: list[int] = []
        sims: dict[int, float] = {}
        vecs: dict[int, list[float]] = {}
        if await si.has_vectors(db, p):
            qv = await _query_vec(query, p)
            if qv:
                rows = await (await db.execute(
                    f"SELECT rowid, distance, embedding FROM {vt} WHERE embedding MATCH ? AND k = ? "
                    "ORDER BY distance", (si._pack(qv), POOL * (4 if subject else 1)))).fetchall()
                ids = [r[0] for r in rows]
                if ids:
                    ok = {r[0] for r in await (await db.execute(
                        f"SELECT c.id FROM chunks c JOIN m.files f ON f.id = c.file_id "
                        f"WHERE c.id IN ({','.join('?' * len(ids))})" + subj_sql, [*ids, *subj_args])).fetchall()}
                    for cid, dist, blob in rows:
                        if cid in ok and len(sem) < POOL:
                            sem.append(cid)
                            sims[cid] = 1.0 - dist
                            vecs[cid] = unpack(blob)
        fused = rrf(lex, sem)
        if not subject:
            # без предмета не тянем лекции к «привет» и «спасибо»: нужен
            # хоть один кусок, найденный по словам или достаточно близкий по смыслу
            thr = embedder.min_sim(p, VEC_MIN_SIM)
            fused = {c: s for c, s in fused.items() if c in lex or sims.get(c, 0) >= thr}
        if sims:
            logger.info(f"поиск по смыслу: лучший косинус {max(sims.values()):.3f} · «{query[:60]}»")
        best = sorted(fused, key=fused.get, reverse=True)[:POOL]
        if not best:
            return []
        rows = await (await db.execute(
            "SELECT c.id, c.file_id, c.page_from, c.page_to, c.kind, c.text, f.title, COALESCE(f.subject, '') "
            f"FROM chunks c JOIN m.files f ON f.id = c.file_id WHERE c.id IN ({','.join('?' * len(best))})",
            best)).fetchall()
        missing = [r[0] for r in rows if r[0] not in vecs]
        if missing and await si.has_vectors(db, p):
            for cid, blob in await (await db.execute(
                    f"SELECT rowid, embedding FROM {vt} WHERE rowid IN ({','.join('?' * len(missing))})",
                    missing)).fetchall():
                vecs[cid] = unpack(blob)
    lex_pos = {c: i for i, c in enumerate(lex, 1)}
    sem_pos = {c: i for i, c in enumerate(sem, 1)}
    cands = [{"id": r[0], "file_id": r[1], "page_from": r[2], "page_to": r[3], "kind": r[4], "text": r[5],
              "title": r[6], "subject": r[7], "score": fused[r[0]], "lex": lex_pos.get(r[0]),
              "sem": sem_pos.get(r[0]), "sim": round(sims[r[0]], 3) if r[0] in sims else None,
              "vec": vecs.get(r[0])} for r in rows]
    cands.sort(key=lambda c: c["score"], reverse=True)
    picked = mmr(cands, k)
    for c in picked:
        c.pop("vec", None)
        c.pop("_stems", None)
    return picked


def place(h: dict) -> str:
    """«слайд 12», «слайды 3–4», «стр. 7», «часть 2»."""
    a, b, kind = h["page_from"], h["page_to"], h["kind"]
    if kind == "слайд":
        return f"слайд {a}" if a == b else f"слайды {a}–{b}"
    if a == b:
        return f"{kind} {a}"
    return f"{kind} {a}–{b}"


def short_title(title: str, limit: int = 28) -> str:
    t = (title or "").strip()
    return t if len(t) <= limit else t[:limit - 1].rstrip() + "…"


def build_context(hits: list[dict], limit: int = CONTEXT_CHARS) -> tuple[str, list[dict]]:
    """Куски для ИИ с номерами [n] — и источники для чипов под ответом."""
    blocks, sources, used = [], [], 0
    for h in hits:
        if used + len(h["text"]) > limit and blocks:
            break
        n = len(blocks) + 1
        where = place(h)
        blocks.append(f"=== [{n}] {h['subject'] or 'Без предмета'}: {h['title']} · {where} ===\n{h['text']}")
        sources.append({"n": n, "id": h["file_id"], "title": h["title"], "page": h["page_from"],
                        "kind": h["kind"], "label": f"{short_title(h['title'])} · {where}"})
        used += len(h["text"])
    return "\n\n".join(blocks), sources

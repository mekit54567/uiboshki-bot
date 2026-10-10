"""
Сверка своих векторов (local_embed.py, numpy) с sentence-transformers на
настоящих моделях + память и скорость. Запускается в GitHub Actions
(embed-check.yml): там есть доступ к Hugging Face и можно поставить torch.

    EMBED_DIR=/tmp/models python tools/embed_check.py [ключ ...]

Падает, если косинус между нашим вектором и эталонным ниже 0.999.
"""

import asyncio
import gc
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import local_embed  # noqa: E402

TEXTS = [
    "Дисконтирование денежных потоков: будущие доходы проекта приводятся к текущему моменту по ставке дисконта, "
    "учитывающей риск и стоимость капитала. NPV — сумма дисконтированных потоков минус начальные инвестиции.",
    "Лекция 3. Бизнес-процессы предприятия: нотация BPMN, пулы и дорожки, события, шлюзы. Пример — процесс "
    "закупки: заявка, согласование, выбор поставщика, договор, поставка и оплата.",
    "почему нельзя просто сложить прибыль за годы",
    "Как посчитать точку безубыточности?",
    "Налоговая нагрузка организации зависит от режима налогообложения: ОСНО, УСН, патент. " * 6,
]


def rss_mb() -> float:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0


async def check(key: str) -> bool:
    from sentence_transformers import SentenceTransformer
    spec = local_embed.MODELS[key]
    await local_embed.download(key)
    gc.collect()
    before = rss_mb()
    t0 = time.monotonic()
    enc = local_embed.Encoder(local_embed.model_dir(key))
    load_s = time.monotonic() - t0
    loaded = rss_mb()
    long_texts = [TEXTS[0] * 3] * 32            # ~1100 символов, как кусок индекса
    t0 = time.monotonic()
    enc.encode(long_texts)
    per = (time.monotonic() - t0) / len(long_texts) * 1000
    peak = rss_mb()
    ok = True
    for prefix in (spec["doc"], spec["query"]):
        texts = [prefix + t for t in TEXTS]
        ours = enc.encode(texts)
        ref = SentenceTransformer(spec["repo"], device="cpu").encode(texts, prompt="", normalize_embeddings=True)
        cos = (ours * ref).sum(1)
        print(f"  {key} «{prefix}»: косинус с эталоном min {cos.min():.6f}")
        ok &= bool(cos.min() > 0.999)
    print(f"  {key}: длина {ours.shape[1]}, загрузка {load_s:.1f} с, память +{loaded - before:.0f} МБ "
          f"(после пачки +{peak - before:.0f} МБ), {per:.0f} мс на кусок · {'OK' if ok else 'РАСХОЖДЕНИЕ'}")
    del enc
    return ok


async def main(keys: list[str]) -> int:
    os.environ.setdefault("EMBED_DIR", "/tmp/models")
    bad = [k for k in keys if not await check(k)]
    if bad:
        print("Не совпали с эталоном:", ", ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or list(local_embed.MODELS))))

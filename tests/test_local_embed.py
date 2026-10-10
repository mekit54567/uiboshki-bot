"""
Свои векторы на numpy (local_embed.py) на крошечной случайной модели BERT /
XLM-R: формат safetensors, пачки с паддингом дают те же векторы, что и по
одному, длина вектора единичная, пулинг CLS/mean из 1_Pooling. Сверка с
настоящими моделями и sentence-transformers — в CI (embed-check.yml).
"""
import json
import os

import numpy as np
import pytest

import local_embed

pytest.importorskip("tokenizers")

WORDS = ["лекция", "дисконтирование", "проект", "прибыль", "ставка", "риск", "##а", "##и", "налог", "баланс"]


def _make_model(folder, *, roberta=False, cls=False, layers=2, hidden=16, heads=4, inter=32):
    from tokenizers import Tokenizer
    from tokenizers.models import WordPiece
    from tokenizers.normalizers import BertNormalizer
    from tokenizers.pre_tokenizers import BertPreTokenizer
    from tokenizers.processors import TemplateProcessing
    special = ["[PAD]", "[UNK]", "[CLS]", "[SEP]"] if not roberta else ["<s>", "<pad>", "</s>", "<unk>"]
    vocab = {t: i for i, t in enumerate(special + WORDS)}
    unk = "[UNK]" if not roberta else "<unk>"
    tok = Tokenizer(WordPiece(vocab, unk_token=unk))
    tok.normalizer = BertNormalizer(lowercase=True)
    tok.pre_tokenizer = BertPreTokenizer()
    cls_t, sep_t = ("[CLS]", "[SEP]") if not roberta else ("<s>", "</s>")
    tok.post_processor = TemplateProcessing(single=f"{cls_t} $A {sep_t}", special_tokens=[(cls_t, vocab[cls_t]), (sep_t, vocab[sep_t])])
    os.makedirs(os.path.join(folder, "1_Pooling"), exist_ok=True)
    tok.save(os.path.join(folder, "tokenizer.json"))
    pad = 1 if roberta else 0
    cfg = {"model_type": "xlm-roberta" if roberta else "bert", "hidden_size": hidden, "num_attention_heads": heads,
           "num_hidden_layers": layers, "intermediate_size": inter, "max_position_embeddings": 40,
           "layer_norm_eps": 1e-12, "hidden_act": "gelu", "pad_token_id": pad, "vocab_size": len(vocab)}
    with open(os.path.join(folder, "config.json"), "w") as f:
        json.dump(cfg, f)
    with open(os.path.join(folder, "1_Pooling", "config.json"), "w") as f:
        json.dump({"pooling_mode_cls_token": cls, "pooling_mode_mean_tokens": not cls}, f)
    rng = np.random.default_rng(1)

    def r(*shape):
        return rng.normal(0, 0.3, shape).astype(np.float32)
    pre = "roberta." if roberta else ""
    t = {f"{pre}embeddings.word_embeddings.weight": r(len(vocab), hidden),
         f"{pre}embeddings.position_embeddings.weight": r(40, hidden),
         f"{pre}embeddings.token_type_embeddings.weight": r(1 if roberta else 2, hidden),
         f"{pre}embeddings.LayerNorm.weight": 1 + r(hidden), f"{pre}embeddings.LayerNorm.bias": r(hidden)}
    for i in range(layers):
        p = f"{pre}encoder.layer.{i}."
        for name, (o, n) in {"attention.self.query": (hidden, hidden), "attention.self.key": (hidden, hidden),
                             "attention.self.value": (hidden, hidden), "attention.output.dense": (hidden, hidden),
                             "intermediate.dense": (inter, hidden), "output.dense": (hidden, inter)}.items():
            t[p + name + ".weight"], t[p + name + ".bias"] = r(o, n), r(o)
        for ln in ("attention.output.LayerNorm", "output.LayerNorm"):
            t[p + ln + ".weight"], t[p + ln + ".bias"] = 1 + r(hidden), r(hidden)
    local_embed.write_safetensors(os.path.join(folder, "model.safetensors"), t)
    return folder


@pytest.mark.parametrize("roberta,cls", [(False, False), (False, True), (True, False)])
def test_batch_equals_single(tmp_path, roberta, cls):
    enc = local_embed.Encoder(_make_model(str(tmp_path), roberta=roberta, cls=cls))
    texts = ["лекция", "дисконтирование проекта и ставка риска налог баланс прибыль", "прибыль", "ставка налог"]
    together = enc.encode(texts)
    alone = np.vstack([enc.encode([t]) for t in texts])
    assert together.shape == (4, 16)
    assert np.allclose(np.linalg.norm(together, axis=1), 1, atol=1e-5)
    assert np.allclose(together, alone, atol=1e-5)       # паддинг не влияет
    assert not np.allclose(together[0], together[2])


def test_small_attention_budget_same_result(tmp_path, monkeypatch):
    enc = local_embed.Encoder(_make_model(str(tmp_path)))
    texts = ["лекция", "ставка налог", "прибыль риск баланс проект", "налог"]
    big = enc.encode(texts)
    monkeypatch.setattr(local_embed, "ATTN_BUDGET", 1)    # по одному тексту в пачке
    assert np.allclose(enc.encode(texts), big, atol=1e-5)


def test_erf_precision():
    import math
    xs = np.linspace(-4, 4, 81)
    assert max(abs(local_embed._erf(xs) - np.array([math.erf(x) for x in xs]))) < 2e-7


async def test_embed_prefix_and_unload(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBED_DIR", str(tmp_path))
    key = "rubert-mini-frida"
    _make_model(local_embed.model_dir(key))
    monkeypatch.setitem(local_embed.MODELS, key, {**local_embed.MODELS[key], "query": "риск ", "doc": "баланс "})
    q = await local_embed.embed(key, ["ставка"], query=True)
    d = await local_embed.embed(key, ["ставка"])
    assert len(q[0]) == 16 and q != d                     # приставки запроса и документа разные
    assert key in local_embed._models
    assert local_embed.unload_idle(idle=-1) == [key] and key not in local_embed._models

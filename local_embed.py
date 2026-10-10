"""
Свои векторы для поиска по смыслу — модель считает на сервере бота, без
Gemini (переезд в Россию: Google не отвечает российским адресам, PLAN.md).

Без torch и onnxruntime: небольшие модели семейства BERT (rubert-tiny,
FRIDA-mini, multilingual-e5) прямо на numpy — веса из model.safetensors
с Hugging Face, токенизатор — tokenizers. Файл весов открывается через
memmap: в памяти — слои (десятки МБ), а таблица слов читается с диска по
нужным строкам. Модель грузится при первом запросе и выгружается после
простоя (IDLE_UNLOAD).

Какая модель — `EMBED_PROVIDER=local:<ключ>` (embedder.py), ключи — MODELS.
Файлы кладутся в `EMBED_DIR` (по умолчанию models/ рядом с базой), качаются
с `EMBED_HF_BASE` (по умолчанию huggingface.co; можно зеркало).
Сверка с sentence-transformers — .github/workflows/embed-check.yml.
"""

import asyncio
import json
import logging
import os
import struct
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)

# ключ → репозиторий и приставки запроса/документа (как у авторов модели);
# min_sim — порог «это про лекции» без выбранного предмета (semantic_search)
MODELS = {
    "rubert-tiny-turbo": {"repo": "sergeyzh/rubert-tiny-turbo", "dims": 312, "query": "", "doc": "", "min_sim": 0.55},
    "rubert-mini-frida": {"repo": "sergeyzh/rubert-mini-frida", "dims": 312, "query": "search_query: ",
                          "doc": "search_document: ", "min_sim": 0.55},
    "e5-small": {"repo": "intfloat/multilingual-e5-small", "dims": 384, "query": "query: ", "doc": "passage: ",
                 "min_sim": 0.80},
}
FILES = ("config.json", "tokenizer.json", "model.safetensors")
OPTIONAL = ("1_Pooling/config.json",)
MAX_TOKENS = 512
IDLE_UNLOAD = 600               # сек без запросов — модель выгружается
ATTN_BUDGET = 48 * 1024 * 1024  # байт на матрицу внимания пачки — держит пик памяти


class EmbedUnavailable(RuntimeError):
    pass


def model_dir(key: str) -> str:
    root = os.getenv("EMBED_DIR")
    if not root:
        import database
        root = os.path.join(os.path.dirname(os.path.abspath(database.DATABASE_PATH)), "models")
    return os.path.join(root, MODELS[key]["repo"].replace("/", "__"))


# ── загрузка файлов ───────────────────────────────────────────────────────────

async def download(key: str) -> str:
    """Скачать файлы модели, если их ещё нет. → папка модели."""
    import net
    base = (os.getenv("EMBED_HF_BASE") or "https://huggingface.co").rstrip("/")
    repo, folder = MODELS[key]["repo"], model_dir(key)
    for name in FILES + OPTIONAL:
        path = os.path.join(folder, name)
        if os.path.exists(path):
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        url = f"{base}/{repo}/resolve/main/{name}"
        tmp = path + ".part"
        async with net.client(timeout=120, follow_redirects=True) as c:
            async with c.stream("GET", url) as resp:
                if resp.status_code == 404 and name in OPTIONAL:
                    continue
                if resp.status_code != 200:
                    raise EmbedUnavailable(f"{repo}/{name}: HTTP {resp.status_code}")
                with open(tmp, "wb") as f:
                    async for part in resp.aiter_bytes(1 << 20):
                        f.write(part)
        os.replace(tmp, path)
        logger.info(f"модель векторов: скачан {repo}/{name} ({os.path.getsize(path) // 1024} КБ)")
    return folder


# ── safetensors без библиотеки: заголовок JSON + сырые массивы ───────────────

_DTYPES = {"F32": np.float32, "F16": np.float16}


def read_safetensors(path: str) -> dict[str, np.ndarray]:
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(n))
    mm = np.memmap(path, dtype=np.uint8, mode="r", offset=8 + n)
    out = {}
    for name, info in header.items():
        if name == "__metadata__":
            continue
        if info["dtype"] not in _DTYPES:
            raise EmbedUnavailable(f"тип весов {info['dtype']} не поддержан")
        s, e = info["data_offsets"]
        out[name] = mm[s:e].view(_DTYPES[info["dtype"]]).reshape(info["shape"])
    return out


def write_safetensors(path: str, tensors: dict[str, np.ndarray]):
    """Для тестов: записать веса в формате safetensors."""
    header, blobs, off = {}, [], 0
    for name, arr in tensors.items():
        arr = np.ascontiguousarray(arr, dtype=np.float32)
        header[name] = {"dtype": "F32", "shape": list(arr.shape), "data_offsets": [off, off + arr.nbytes]}
        blobs.append(arr.tobytes())
        off += arr.nbytes
    raw = json.dumps(header).encode()
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(raw)) + raw + b"".join(blobs))


# ── сама модель ───────────────────────────────────────────────────────────────

def _erf(x: np.ndarray) -> np.ndarray:
    # Абрамовиц — Стиган 7.1.26: погрешность < 1.5e-7 — для GELU хватает
    s = np.sign(x)
    a = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * a)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-a * a)
    return s * y


def _gelu(x: np.ndarray) -> np.ndarray:
    return 0.5 * x * (1.0 + _erf(x / np.float32(np.sqrt(2.0))))


def _ln(x: np.ndarray, w: np.ndarray, b: np.ndarray, eps: float) -> np.ndarray:
    mu = x.mean(-1, keepdims=True)
    var = ((x - mu) ** 2).mean(-1, keepdims=True)
    return (x - mu) / np.sqrt(var + eps) * w + b


class Encoder:
    """BERT / XLM-RoBERTa энкодер на numpy + пулинг как у sentence-transformers."""

    def __init__(self, folder: str):
        from tokenizers import Tokenizer
        with open(os.path.join(folder, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        pool_path = os.path.join(folder, "1_Pooling", "config.json")
        pool = {}
        if os.path.exists(pool_path):
            with open(pool_path, encoding="utf-8") as f:
                pool = json.load(f)
        self.pooling = "cls" if pool.get("pooling_mode_cls_token") else "mean"
        self.heads = cfg["num_attention_heads"]
        self.eps = float(cfg.get("layer_norm_eps", 1e-12))
        self.roberta = cfg.get("model_type", "bert") in ("xlm-roberta", "roberta")
        self.pad_id = int(cfg.get("pad_token_id", 0) or 0)
        self.max_tokens = min(MAX_TOKENS, int(cfg.get("max_position_embeddings", MAX_TOKENS)) - (self.pad_id + 1 if self.roberta else 0))
        if cfg.get("hidden_act", "gelu") not in ("gelu", "gelu_new", "gelu_python"):
            raise EmbedUnavailable(f"функция активации {cfg.get('hidden_act')} не поддержана")

        raw = read_safetensors(os.path.join(folder, "model.safetensors"))
        w = {}
        for name, arr in raw.items():
            for prefix in ("bert.", "roberta.", "model."):
                if name.startswith(prefix):
                    name = name[len(prefix):]
            w[name.replace(".gamma", ".weight").replace(".beta", ".bias")] = arr

        def f32(name):
            return np.ascontiguousarray(w[name], dtype=np.float32)

        self.word = w["embeddings.word_embeddings.weight"]          # memmap: строки читаются по нужде
        self.pos = f32("embeddings.position_embeddings.weight")
        self.tok_type = f32("embeddings.token_type_embeddings.weight")[0]
        self.emb_ln = (f32("embeddings.LayerNorm.weight"), f32("embeddings.LayerNorm.bias"))
        self.layers = []
        for i in range(cfg["num_hidden_layers"]):
            p = f"encoder.layer.{i}."

            def lin(name, p=p):
                return np.ascontiguousarray(f32(p + name + ".weight").T), f32(p + name + ".bias")
            self.layers.append({
                "q": lin("attention.self.query"), "k": lin("attention.self.key"), "v": lin("attention.self.value"),
                "o": lin("attention.output.dense"),
                "ln1": (f32(p + "attention.output.LayerNorm.weight"), f32(p + "attention.output.LayerNorm.bias")),
                "i": lin("intermediate.dense"), "out": lin("output.dense"),
                "ln2": (f32(p + "output.LayerNorm.weight"), f32(p + "output.LayerNorm.bias")),
            })
        self.dims = self.pos.shape[1]
        self.tok = Tokenizer.from_file(os.path.join(folder, "tokenizer.json"))
        self.tok.no_padding()
        self.tok.enable_truncation(max_length=self.max_tokens)

    def _forward(self, ids: np.ndarray, mask: np.ndarray) -> np.ndarray:
        B, T = ids.shape
        if self.roberta:          # позиции XLM-R: с pad_id + 1, паддинг — pad_id
            pos = (np.cumsum(mask, axis=1) * mask) + self.pad_id
        else:
            pos = np.broadcast_to(np.arange(T), (B, T))
        x = np.asarray(self.word[ids.reshape(-1)], dtype=np.float32).reshape(B, T, -1) + self.pos[pos] + self.tok_type
        x = _ln(x, *self.emb_ln, self.eps)
        H = self.heads
        d = x.shape[-1] // H
        add_mask = ((1.0 - mask[:, None, None, :]) * np.float32(-1e9)).astype(np.float32)
        scale = np.float32(1.0 / np.sqrt(d))
        for L in self.layers:
            def proj(name, inp=x, L=L):
                W, b = L[name]
                return (inp @ W + b).reshape(B, T, H, d).transpose(0, 2, 1, 3)
            q, k, v = proj("q"), proj("k"), proj("v")
            s = (q @ k.transpose(0, 1, 3, 2)) * scale + add_mask
            s -= s.max(-1, keepdims=True)
            np.exp(s, out=s)
            s /= s.sum(-1, keepdims=True)
            ctx = (s @ v).transpose(0, 2, 1, 3).reshape(B, T, H * d)
            W, b = L["o"]
            x = _ln(x + ctx @ W + b, *L["ln1"], self.eps)
            W, b = L["i"]
            inter = _gelu(x @ W + b)
            W, b = L["out"]
            x = _ln(x + inter @ W + b, *L["ln2"], self.eps)
        if self.pooling == "cls":
            out = x[:, 0]
        else:
            m = mask[:, :, None].astype(np.float32)
            out = (x * m).sum(1) / np.maximum(m.sum(1), 1e-9)
        return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)

    def encode(self, texts: list[str]) -> np.ndarray:
        encs = self.tok.encode_batch(texts)
        lens = [len(e.ids) for e in encs]
        order = sorted(range(len(texts)), key=lambda i: -lens[i])     # длинные первыми
        out = np.zeros((len(texts), self.dims), dtype=np.float32)
        i = 0
        while i < len(order):
            T = lens[order[i]]          # самый длинный в пачке
            # размер пачки — чтобы матрица внимания влезла в ATTN_BUDGET
            n = max(1, ATTN_BUDGET // max(1, self.heads * T * T * 4))
            batch = order[i:i + n]
            ids = np.full((len(batch), T), self.pad_id, dtype=np.int64)
            mask = np.zeros((len(batch), T), dtype=np.int64)
            for r, j in enumerate(batch):
                ids[r, :lens[j]] = encs[j].ids
                mask[r, :lens[j]] = 1
            out[batch] = self._forward(ids, mask)
            i += len(batch)
        return out


# ── загрузка, выгрузка после простоя ──────────────────────────────────────────

_models: dict[str, Encoder] = {}
_used: dict[str, float] = {}
_lock = threading.Lock()


def _get(key: str) -> Encoder:
    if key not in _models:
        started = time.monotonic()
        _models[key] = Encoder(model_dir(key))
        logger.info(f"модель векторов {key}: загружена за {time.monotonic() - started:.1f} с")
    _used[key] = time.monotonic()
    return _models[key]


def unload_idle(idle: float = IDLE_UNLOAD) -> list[str]:
    """Выгрузить модели без запросов дольше idle секунд (scheduler)."""
    gone = []
    if not _lock.acquire(blocking=False):      # модель сейчас считает — не простой
        return gone
    try:
        for key in list(_models):
            if time.monotonic() - _used.get(key, 0) > idle:
                del _models[key]
                gone.append(key)
    finally:
        _lock.release()
    if gone:
        import gc
        gc.collect()
        logger.info(f"модель векторов выгружена после простоя: {', '.join(gone)}")
    return gone


def _encode_sync(key: str, texts: list[str]) -> list[list[float]]:
    with _lock:
        return _get(key).encode(texts).tolist()


async def embed(key: str, texts: list[str], query: bool = False) -> list[list[float]]:
    """Векторы (единичной длины) — запросу с приставкой запроса, кускам — документа."""
    if key not in MODELS:
        raise EmbedUnavailable(f"неизвестная модель векторов {key}")
    await download(key)
    prefix = MODELS[key]["query" if query else "doc"]
    return await asyncio.to_thread(_encode_sync, key, [prefix + t for t in texts])


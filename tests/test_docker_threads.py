"""16.10, Amvera: своя модель векторов на numpy запускала поток OpenBLAS на
каждое ядро машины при доле одного ядра у контейнера — бот и приложение
отвечали по полминуты. В образе потоки — по одному."""
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parent.parent / "Dockerfile"


def test_blas_threads_limited():
    text = DOCKERFILE.read_text()
    for var in ("OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1", "MKL_NUM_THREADS=1"):
        assert var in text, var

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

import numpy as np


@lru_cache
def _fastembed(model_name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name)


def embed_texts(model_name: str, texts: Sequence[str]) -> list[list[float]]:
    """Embed texts using fastembed (ONNX); avoids a heavy PyTorch stack in many environments."""
    if not texts:
        return []
    model = _fastembed(model_name)
    out: list[list[float]] = []
    for vec in model.embed(list(texts)):
        if isinstance(vec, np.ndarray):
            out.append(vec.astype(np.float32).tolist())
        else:
            out.append(list(vec))
    return out


def embed_query(model_name: str, text: str) -> list[float]:
    out = embed_texts(model_name, [text])
    return out[0] if out else []

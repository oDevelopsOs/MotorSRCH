from __future__ import annotations

import numpy as np

from . import settings

_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.EMBED_MODEL)
    return _model


def embed_text(text: str) -> np.ndarray:
    m = get_model()
    return m.encode(
        text[:4000],
        normalize_embeddings=True,
        show_progress_bar=False,
    )

from __future__ import annotations

import logging
from typing import Any

from sentence_transformers import CrossEncoder

from . import settings

log = logging.getLogger("investsearch.rerank")
_ce: CrossEncoder | None = None


def get_cross_encoder() -> CrossEncoder:
    global _ce
    if _ce is None:
        _ce = CrossEncoder(settings.RERANK_MODEL)
    return _ce


def rerank_results(
    query: str,
    results: list[dict[str, Any]],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    if not settings.ENABLE_RERANK or not results:
        return results
    n = top_n or settings.RERANK_TOP_N
    chunk = results[:n]
    rest = results[n:]
    try:
        ce = get_cross_encoder()
        pairs: list[tuple[str, str]] = []
        for r in chunk:
            title = str(r.get("title") or "")
            summary = str(r.get("summary") or "")[:1500]
            text = f"{title}\n{summary}".strip()
            pairs.append((query[:2000], text))
        scores = ce.predict(pairs)
        scored = list(zip(scores, chunk, strict=True))
        scored.sort(key=lambda x: float(x[0]), reverse=True)
        reranked: list[dict[str, Any]] = []
        for score, row in scored:
            row = dict(row)
            row["rerank_score"] = float(score)
            reranked.append(row)
        return reranked + rest
    except Exception as e:
        log.warning("rerank skipped: %s", e)
        return results

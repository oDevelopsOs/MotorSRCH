from __future__ import annotations

import hashlib
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from .. import settings
from .types import NormalizedHit

log = logging.getLogger("investsearch.searxng")


def _base_url() -> str:
    return (settings.SEARXNG_URL or "").strip().rstrip("/")


def _rows_to_hits(rows: list[dict], lim: int) -> list[NormalizedHit]:
    hits: list[NormalizedHit] = []
    for row in rows[:lim]:
        url_s = str(row.get("url") or "").strip()
        if not url_s:
            continue
        title = str(row.get("title") or url_s)[:2000]
        snippet = str(row.get("content") or "")[:2000]
        h = hashlib.sha256(url_s.encode("utf-8")).hexdigest()[:20]
        hid = f"searxng:{h}"
        dom = urlparse(url_s).netloc or None
        extra: dict[str, Any] = {
            "searxng_weighted_score": row.get("_weighted_score"),
            "sq_weight": row.get("sq_weight"),
        }
        eng = row.get("engine")
        if eng:
            extra["engine"] = eng
        hits.append(
            NormalizedHit(
                id=hid,
                source="searxng",
                title=title,
                snippet=snippet,
                url=url_s,
                published_at=None,
                domain=dom,
                extra=extra,
            )
        )
    return hits


async def searxng_raw_json(query: str) -> dict[str, Any]:
    """Respuesta JSON cruda de SearXNG (`/search?format=json`) — una sola petición (p. ej. /brain)."""
    base = _base_url()
    if not base:
        return {}
    url = f"{base}/search"
    params = {"q": query[:500], "format": "json"}
    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
        r = await client.get(
            url,
            params=params,
            headers={"User-Agent": "InvestSearch/1.0 (motor; +https://localhost)"},
        )
        r.raise_for_status()
        return r.json()


async def fetch_searxng(query: str, limit: int | None = None) -> list[NormalizedHit]:
    if not settings.ENABLE_SEARXNG:
        return []
    if not _base_url():
        return []
    lim = limit if limit is not None else settings.SEARXNG_MAX_RESULTS

    if settings.ENABLE_SEARXNG_DECOMPOSITION:
        try:
            from ..query_decomposer import parallel_search

            rows = await parallel_search(query, max_results=lim)
            return _rows_to_hits(rows, lim)
        except Exception as e:
            log.warning("searxng decomposition: %s", e)
            return []

    try:
        data = await searxng_raw_json(query)
    except Exception as e:
        log.warning("searxng: %s", e)
        return []

    results = data.get("results") or []
    rows: list[dict] = []
    for item in results[:lim]:
        if not isinstance(item, dict):
            continue
        url_s = str(item.get("url") or "").strip()
        if not url_s:
            continue
        rows.append(
            {
                "url": url_s,
                "title": str(item.get("title") or ""),
                "content": str(
                    item.get("content")
                    or item.get("content_highlighted")
                    or item.get("snippet")
                    or ""
                ),
                "engine": item.get("engine", ""),
                "score": float(item.get("score") or 0.5),
                "sq_weight": 1.0,
                "_weighted_score": float(item.get("score") or 0.5),
            }
        )
    return _rows_to_hits(rows, lim)

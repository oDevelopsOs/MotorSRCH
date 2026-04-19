from __future__ import annotations

import logging

import httpx

from .. import settings
from .types import NormalizedHit

log = logging.getLogger("investsearch.openalex")


async def fetch_openalex(query: str, limit: int = 8) -> list[NormalizedHit]:
    if not settings.ENABLE_OPENALEX:
        return []
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            r = await client.get(
                "https://api.openalex.org/works",
                params={"search": query[:400], "per_page": min(limit, 25)},
                headers={"User-Agent": "InvestSearch/1.0 (motor; +https://localhost)"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("openalex: %s", e)
        return []

    out: list[NormalizedHit] = []
    for w in data.get("results") or []:
        wid = str(w.get("id") or "").split("/")[-1]
        title = (w.get("display_name") or w.get("title") or "").strip() or wid
        abst = (w.get("abstract_inverted_index") or None)
        snippet = ""
        if isinstance(abst, dict):
            # Reconstruct a short preview from inverted index keys order is unknown; skip heavy rebuild
            snippet = title
        if not snippet:
            snippet = (w.get("abstract") or title)[:500]
        oa_url = ""
        boa = w.get("best_oa_location") or {}
        if isinstance(boa, dict):
            oa_url = str(boa.get("landing_page_url") or boa.get("pdf_url") or "")
        if not oa_url:
            oa_url = str(w.get("id") or "")
        pub = w.get("publication_date")
        pub_s = str(pub) if pub else None
        oid = f"openalex:{wid}"
        out.append(
            NormalizedHit(
                id=oid,
                source="openalex",
                title=title[:500],
                snippet=snippet[:2000],
                url=oa_url or f"https://openalex.org/{wid}",
                published_at=pub_s,
                domain="openalex.org",
                extra={"openalex": w.get("id")},
            )
        )
    return out

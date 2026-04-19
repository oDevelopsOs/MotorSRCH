from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from .. import settings
from .types import NormalizedHit

log = logging.getLogger("investsearch.wikipedia")


async def fetch_wikipedia(query: str, limit: int = 5) -> list[NormalizedHit]:
    if not settings.ENABLE_WIKIPEDIA:
        return []
    q = quote(query[:300], safe="")
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&srlimit={min(limit, 10)}&format=json"
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            r = await client.get(
                url,
                headers={"User-Agent": "InvestSearch/1.0 (motor; +https://localhost)"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("wikipedia: %s", e)
        return []

    hits: list[NormalizedHit] = []
    for item in (data.get("query") or {}).get("search") or []:
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
        safe = quote(title.replace(" ", "_"), safe="")
        page_url = f"https://en.wikipedia.org/wiki/{safe}"
        hits.append(
            NormalizedHit(
                id=f"wikipedia:{title}",
                source="wikipedia",
                title=title,
                snippet=snippet[:2000],
                url=page_url,
                published_at=None,
                domain="wikipedia.org",
            )
        )
    return hits

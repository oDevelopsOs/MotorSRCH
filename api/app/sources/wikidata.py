from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from .. import settings
from .types import NormalizedHit

log = logging.getLogger("investsearch.wikidata")


async def fetch_wikidata(query: str, limit: int = 5) -> list[NormalizedHit]:
    if not settings.ENABLE_WIKIDATA:
        return []
    q = quote(query[:200], safe="")
    url = (
        "https://www.wikidata.org/w/api.php?"
        f"action=wbsearchentities&search={q}&language=en&limit={min(limit, 10)}&format=json"
    )
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            r = await client.get(
                url,
                headers={"User-Agent": "InvestSearch/1.0 (motor; +https://localhost)"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("wikidata search: %s", e)
        return []

    search_res = data.get("search") or []
    if not search_res:
        return []

    ids = [str(x.get("id")) for x in search_res if x.get("id")]
    if not ids:
        return []

    ids_param = "|".join(ids[:10])
    desc_url = (
        "https://www.wikidata.org/w/api.php?"
        f"action=wbgetentities&ids={quote(ids_param, safe='|')}&props=descriptions|labels&languages=en&format=json"
    )
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            r2 = await client.get(
                desc_url,
                headers={"User-Agent": "InvestSearch/1.0 (motor; +https://localhost)"},
            )
            r2.raise_for_status()
            ent_data = r2.json()
    except Exception as e:
        log.warning("wikidata entities: %s", e)
        ent_data = {"entities": {}}

    entities = ent_data.get("entities") or {}
    out: list[NormalizedHit] = []
    for eid in ids:
        ent = entities.get(eid) or {}
        labels = ent.get("labels") or {}
        descs = ent.get("descriptions") or {}
        label = (labels.get("en") or {}).get("value") or eid
        desc = (descs.get("en") or {}).get("value") or ""
        snippet = desc or label
        url_e = f"https://www.wikidata.org/wiki/{eid}"
        out.append(
            NormalizedHit(
                id=f"wikidata:{eid}",
                source="wikidata",
                title=label[:500],
                snippet=snippet[:2000],
                url=url_e,
                published_at=None,
                domain="wikidata.org",
                extra={"wikidata_id": eid},
            )
        )
    return out

from __future__ import annotations

from . import settings

# Aligned with processor/app/trust.py; extended for external APIs used en /resolve
SOURCE_TRUST: dict[str, float] = {
    "sec.gov": 1.0,
    "reuters.com": 0.95,
    "ft.com": 0.93,
    "bloomberg.com": 0.93,
    "wsj.com": 0.90,
    "investopedia.com": 0.75,
    "federalreserve.gov": 0.95,
    "wikipedia.org": 0.88,
    "wikidata.org": 0.90,
    "openalex.org": 0.88,
}


def trust_for_domain(domain: str) -> float:
    if not domain:
        return 0.5
    d = domain.lower().strip()
    for k, v in SOURCE_TRUST.items():
        if k in d or d.endswith(k):
            return v
    return 0.5


def trust_for_source_key(source: str) -> float:
    """Trust prior for logical source names (openalex, wikipedia, wikidata, meilisearch)."""
    s = source.lower().strip()
    if s in ("wikipedia",):
        return SOURCE_TRUST.get("wikipedia.org", 0.88)
    if s in ("wikidata",):
        return SOURCE_TRUST.get("wikidata.org", 0.90)
    if s in ("openalex",):
        return SOURCE_TRUST.get("openalex.org", 0.88)
    if s in ("searxng",):
        if (
            settings.SEARXNG_AS_PRIMARY
            and settings.ENABLE_SEARXNG
            and settings.SEARXNG_URL
        ):
            return 0.78
        return 0.58
    return 0.5

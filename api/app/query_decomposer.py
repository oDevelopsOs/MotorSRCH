"""
Descomposición determinista de consultas → varias peticiones SearXNG (categorías / motores)
en paralelo, con fusión por URL y score ponderado por sub-query.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

from . import settings

log = logging.getLogger("investsearch.query_decomposer")

SEARXNG_USER_AGENT = "InvestSearch/1.0 (motor; +https://localhost)"


@dataclass
class SubQuery:
    text: str
    categories: list[str]
    engines: list[str] = field(default_factory=list)
    weight: float = 1.0


def _base_url() -> str:
    return (settings.SEARXNG_URL or "").strip().rstrip("/")


def decompose(query: str) -> list[SubQuery]:
    """Descompone la consulta en sub-queries (sin LLM)."""
    q = query.strip()
    ql = q.lower()
    sub_queries: list[SubQuery] = []

    sub_queries.append(
        SubQuery(text=q, categories=["general"], engines=[], weight=1.0)
    )

    TIME_WORDS = {
        "today",
        "yesterday",
        "latest",
        "recent",
        "breaking",
        "now",
        "2024",
        "2025",
        "2026",
    }
    NEWS_WORDS = {
        "news",
        "headlines",
        "report",
        "announced",
        "breaking",
        "fed",
        "fomc",
    }
    if any(w in ql for w in TIME_WORDS) or any(w in ql for w in NEWS_WORDS):
        sub_queries.append(
            SubQuery(text=q, categories=["news"], engines=[], weight=0.9)
        )

    ACADEMIC_WORDS = {
        "research",
        "study",
        "paper",
        "model",
        "theory",
        "methodology",
        "analysis",
        "algorithm",
        "framework",
        "literature",
        "doi",
        "journal",
    }
    if any(w in ql for w in ACADEMIC_WORDS):
        sub_queries.append(
            SubQuery(
                text=q,
                categories=["science"],
                engines=[
                    "semantic scholar",
                    "arxiv",
                    "openalex",
                ],
                weight=0.95,
            )
        )

    TECH_WORDS = {
        "code",
        "api",
        "library",
        "github",
        "python",
        "golang",
        "docker",
        "kubernetes",
        "sql",
        "algorithm",
        "implementation",
        "npm",
        "stackoverflow",
    }
    if any(w in ql for w in TECH_WORDS):
        sub_queries.append(
            SubQuery(
                text=q,
                categories=["it"],
                engines=["github", "stackoverflow"],
                weight=0.85,
            )
        )

    if _looks_financial(ql):
        enriched = _enrich_financial_query(q)
        if enriched != q:
            sub_queries.append(
                SubQuery(
                    text=enriched,
                    categories=["general", "news"],
                    engines=[],
                    weight=0.8,
                )
            )

    return sub_queries


def _looks_financial(q: str) -> bool:
    fin = {
        "revenue",
        "earnings",
        "profit",
        "margin",
        "stock",
        "share",
        "market cap",
        "dividend",
        "eps",
        "ebitda",
        "ipo",
        "bond",
        "yield",
        "tsla",
        "nasdaq",
    }
    return any(w in q for w in fin)


def _enrich_financial_query(query: str) -> str:
    enrichments = {
        "revenue": "annual revenue financial results",
        "earnings": "quarterly earnings report",
        "stock": "stock market performance",
        "profit": "net income profit margin",
    }
    ql = query.lower()
    for keyword, addition in enrichments.items():
        if keyword in ql and addition not in ql:
            return f"{query} {addition}"
    return query


async def fetch_sub_query(
    client: httpx.AsyncClient,
    sub: SubQuery,
    max_results: int,
    timeout: float,
) -> list[dict]:
    params: dict[str, str | int] = {
        "q": sub.text[:500],
        "categories": ",".join(sub.categories),
        "format": "json",
        "pageno": 1,
    }
    if sub.engines:
        params["engines"] = ",".join(sub.engines)

    base = _base_url()
    if not base:
        return []
    try:
        resp = await client.get(
            f"{base}/search",
            params=params,
            headers={"User-Agent": SEARXNG_USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.debug("searxng sub-query: %s", e)
        return []

    results = data.get("results") or []
    out: list[dict] = []
    for r in results[:max_results]:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or "").strip()
        if not url:
            continue
        score = float(r.get("score") or 0.5)
        out.append(
            {
                "url": url,
                "title": str(r.get("title") or ""),
                "content": str(
                    r.get("content")
                    or r.get("content_highlighted")
                    or r.get("snippet")
                    or ""
                ),
                "engine": r.get("engine", ""),
                "score": score,
                "sq_weight": sub.weight,
                "_weighted_score": score * sub.weight,
            }
        )
    return out


async def parallel_search(query: str, max_results: int | None = None) -> list[dict]:
    """
    Descompone la query, lanza sub-búsquedas en paralelo, deduplica por URL,
    ordena por score ponderado.
    """
    if not _base_url():
        return []

    subs = decompose(query)
    per_sq = max(5, (max_results or settings.SEARXNG_MAX_RESULTS) // max(1, len(subs)))
    per_sq = min(per_sq, 15)
    timeout = float(settings.SEARXNG_SUBQUERY_TIMEOUT)

    async with httpx.AsyncClient() as client:
        tasks = [fetch_sub_query(client, sq, per_sq, timeout) for sq in subs]
        all_results = await asyncio.gather(*tasks)

    seen: set[str] = set()
    flat: list[dict] = []
    for results in all_results:
        for r in results:
            u = r.get("url") or ""
            if u and u not in seen:
                seen.add(u)
                flat.append(r)

    flat.sort(key=lambda x: float(x.get("_weighted_score") or 0.0), reverse=True)
    lim = max_results if max_results is not None else settings.SEARXNG_MAX_RESULTS
    return flat[:lim]

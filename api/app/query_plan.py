from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from . import settings


class QueryType(str, Enum):
    FACTUAL = "factual"
    FINANCIAL = "financial"
    ACADEMIC = "academic"
    NEWS = "news"
    ANALYTICAL = "analytical"
    COMPARATIVE = "comparative"
    DEFINITION = "definition"


@dataclass
class QueryPlan:
    query_type: QueryType
    sources: list[str]
    needs_fresh: bool
    entities: list[str]
    time_range: str | None
    ambiguous: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["query_type"] = self.query_type.value
        return d


TICKER_PATTERN = re.compile(r"\b([A-Z]{1,5})\b")
MACRO_KEYWORDS = frozenset(
    {
        "fed",
        "inflation",
        "gdp",
        "cpi",
        "interest rate",
        "recession",
        "yield",
        "fomc",
        "macro",
        "unemployment",
    }
)
ACADEMIC_KEYWORDS = frozenset(
    {
        "study",
        "research",
        "paper",
        "methodology",
        "theory",
        "model",
        "literature",
        "journal",
        "doi",
    }
)
DEFINITION_KEYWORDS = frozenset(
    {
        "what is",
        "what are",
        "define",
        "definition",
        "meaning",
        "explanation",
        "how does",
        "qué es",
        "definición",
    }
)
NEWS_KEYWORDS = frozenset(
    {
        "latest",
        "news",
        "today",
        "breaking",
        "yesterday",
        "this week",
    }
)


def _extract_tickers(q: str) -> list[str]:
    return list(dict.fromkeys(TICKER_PATTERN.findall(q)))


def _apply_searxng_primary(sources: list[str]) -> list[str]:
    """
    Si SearXNG es la fuente web principal, no llamamos a APIs públicas directas
    (Wikipedia / OpenAlex / Wikidata): el descubrimiento pasa por SearXNG + índice local.
    """
    if not (
        settings.SEARXNG_AS_PRIMARY
        and settings.ENABLE_SEARXNG
        and settings.SEARXNG_URL
    ):
        return sources
    drop = frozenset({"wikipedia", "openalex", "wikidata"})
    out = [s for s in sources if s not in drop]
    if "searxng" not in out:
        out.append("searxng")
    return out


def fast_route(query: str) -> QueryPlan:
    q = query.strip()
    ql = q.lower()
    tickers = _extract_tickers(q)

    sources: list[str] = ["meilisearch", "qdrant"]
    needs_fresh = False
    qtype = QueryType.FACTUAL
    time_range: str | None = None

    if any(kw in ql for kw in DEFINITION_KEYWORDS):
        qtype = QueryType.DEFINITION
        sources.extend(["wikipedia", "wikidata"])
    elif any(kw in ql for kw in ACADEMIC_KEYWORDS):
        qtype = QueryType.ACADEMIC
        sources.extend(["openalex", "wikipedia"])
    elif any(kw in ql for kw in NEWS_KEYWORDS):
        qtype = QueryType.NEWS
        needs_fresh = True
        sources.extend(["wikipedia"])
    elif any(kw in ql for kw in MACRO_KEYWORDS):
        qtype = QueryType.FINANCIAL
        sources.extend(["wikidata", "wikipedia"])
    elif tickers:
        qtype = QueryType.FINANCIAL
        sources.extend(["openalex", "wikidata"])
    elif " vs " in ql or " versus " in ql or " compared to " in ql:
        qtype = QueryType.COMPARATIVE
        sources.extend(["wikipedia", "wikidata", "openalex"])
    elif any(x in ql for x in ("why ", "how will", "outlook", "forecast")):
        qtype = QueryType.ANALYTICAL
        sources.extend(["wikipedia", "openalex"])
    else:
        qtype = QueryType.FACTUAL
        sources.extend(["wikipedia", "openalex"])

    # De-duplicate preserving order
    seen: set[str] = set()
    uniq_sources: list[str] = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            uniq_sources.append(s)

    if settings.ENABLE_SEARXNG and settings.SEARXNG_URL:
        if "searxng" not in uniq_sources:
            uniq_sources.append("searxng")

    uniq_sources = _apply_searxng_primary(uniq_sources)

    ambiguous = _is_ambiguous(q, ql, tickers, qtype)
    return QueryPlan(
        query_type=qtype,
        sources=uniq_sources,
        needs_fresh=needs_fresh,
        entities=tickers,
        time_range=time_range,
        ambiguous=ambiguous,
    )


def _is_ambiguous(q: str, ql: str, tickers: list[str], qtype: QueryType) -> bool:
    if len(q) > 120:
        return True
    if q.count("?") >= 2:
        return True
    if not tickers and qtype == QueryType.FACTUAL and len(q.split()) <= 2:
        return True
    return False


async def plan_with_ollama_if_needed(query: str, base: QueryPlan) -> QueryPlan:
    """Optionally refine plan via Ollama JSON when enabled and query looks ambiguous."""
    if not settings.USE_OLLAMA_FOR_PLAN or not base.ambiguous:
        return base
    try:
        from .ollama_client import ollama_complete

        if (
            settings.SEARXNG_AS_PRIMARY
            and settings.ENABLE_SEARXNG
            and settings.SEARXNG_URL
        ):
            src_hint = '["meilisearch","qdrant","searxng"]'
        else:
            src_hint = '["meilisearch","qdrant","wikipedia","wikidata","openalex","searxng"]'

        prompt = f"""Analyze this search query and return ONLY valid JSON (no markdown):
{{
  "type": "factual|financial|academic|news|analytical|comparative|definition",
  "sources": {src_hint},
  "needs_fresh": true or false,
  "entities": ["TICKER_OR_NAME"],
  "time_range": "2023" or null
}}
Query: "{query}"
"""
        raw = await ollama_complete(
            prompt,
            model=settings.OLLAMA_MODEL,
            max_tokens=400,
            temperature=0.1,
            timeout=settings.OLLAMA_PLAN_TIMEOUT,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        qt = QueryType(data.get("type", base.query_type.value))
        src = data.get("sources") or base.sources
        src = _apply_searxng_primary(list(dict.fromkeys(src)))
        nf = bool(data.get("needs_fresh", base.needs_fresh))
        ent = data.get("entities") or base.entities
        tr = data.get("time_range")
        return QueryPlan(
            query_type=qt,
            sources=src,
            needs_fresh=nf,
            entities=list(ent) if isinstance(ent, list) else base.entities,
            time_range=tr if isinstance(tr, str) or tr is None else base.time_range,
            ambiguous=False,
        )
    except Exception:
        return base


def cache_ttl_seconds(plan: QueryPlan) -> int:
    """Adaptive Redis TTL by query type and freshness (PLAN_DE_TRABAJO1)."""
    if plan.needs_fresh or plan.query_type == QueryType.NEWS:
        return settings.CACHE_TTL_NEWS
    if plan.query_type == QueryType.DEFINITION:
        return settings.CACHE_TTL_DEFINITION
    if plan.query_type in (QueryType.ACADEMIC, QueryType.FINANCIAL):
        return settings.CACHE_TTL_STABLE
    return settings.SEARCH_CACHE_TTL

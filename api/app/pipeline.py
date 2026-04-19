from __future__ import annotations

import asyncio
import time
from typing import Any

from meilisearch import Client as MeiliClient
from qdrant_client import QdrantClient

from . import settings
from .fusion import (
    build_id_registry,
    multi_rrf,
    weighted_fusion_scores,
)
from .query_plan import QueryPlan, fast_route, plan_with_ollama_if_needed
from .rerank import rerank_results
from .sources import fetch_openalex, fetch_searxng, fetch_wikipedia, fetch_wikidata
from .sources.types import NormalizedHit
from .brain_client import (
    BrainMisconfigured,
    firecrawl_agent_sync,
    openperplex_collect_sse,
    vane_search_get,
)
from .synthesis import synthesize_answer


def build_meili_filter(
    ticker: str | None,
    lang: str | None,
    from_date: str | None,
) -> str | None:
    parts: list[str] = []
    if ticker:
        parts.append(f'tickers = "{ticker}"')
    if lang:
        parts.append(f'language = "{lang}"')
    if from_date:
        parts.append(f"published_at >= {from_date}")
    if not parts:
        return None
    return " AND ".join(parts)


async def gather_external(plan: QueryPlan, q: str) -> list[NormalizedHit]:
    hits: list[NormalizedHit] = []
    tasks: list[Any] = []

    searxng_primary = (
        settings.SEARXNG_AS_PRIMARY
        and settings.ENABLE_SEARXNG
        and settings.SEARXNG_URL
    )
    if searxng_primary and "searxng" in plan.sources:
        res = await fetch_searxng(q)
        return res if isinstance(res, list) else []

    if "openalex" in plan.sources:
        tasks.append(fetch_openalex(q))
    if "wikipedia" in plan.sources:
        tasks.append(fetch_wikipedia(q))
    if "wikidata" in plan.sources:
        tasks.append(fetch_wikidata(q))
    if "searxng" in plan.sources:
        tasks.append(fetch_searxng(q))

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
        if isinstance(res, Exception):
            continue
        if isinstance(res, list):
            hits.extend(res)
    return hits


async def run_resolve(
    q: str,
    *,
    meili: MeiliClient,
    qdrant: QdrantClient,
    embed_query,
    ticker: str | None,
    lang: str | None,
    from_date: str | None,
    limit: int,
    plan: QueryPlan | None = None,
    brain_boost: str | None = None,
    brain_max_wait_sec: float | None = None,
    openperplex_date_context: str = "",
    openperplex_stored_location: str = "",
    openperplex_pro_mode: bool = False,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    if plan is None:
        plan = fast_route(q)
        plan = await plan_with_ollama_if_needed(q, plan)

    filt = build_meili_filter(ticker, lang, from_date)
    idx = meili.index("documents")
    search_params: dict[str, Any] = {
        "limit": limit * 2,
        "attributesToRetrieve": [
            "id",
            "title",
            "summary",
            "score",
            "url",
            "source_domain",
            "published_at",
            "tickers",
            "sentiment",
            "language",
        ],
    }
    if filt:
        search_params["filter"] = filt

    meili_res = idx.search(q, search_params)
    meili_hits = meili_res.get("hits") or []
    meili_ids = [str(h.get("id")) for h in meili_hits if h.get("id")]

    vec = embed_query(q)
    qdrant_ids: list[str] = []
    try:
        qr = qdrant.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=vec,
            limit=limit * 2,
            with_payload=False,
        )
        qdrant_ids = [str(p.id) for p in qr.points]
    except Exception:
        qdrant_ids = []

    external = await gather_external(plan, q)
    ext_openalex = [h.id for h in external if h.source == "openalex"]
    ext_wiki = [h.id for h in external if h.source == "wikipedia"]
    ext_wd = [h.id for h in external if h.source == "wikidata"]
    ext_searx = [h.id for h in external if h.source == "searxng"]

    ranked_lists: list[list[str]] = [meili_ids, qdrant_ids]
    searxng_primary = (
        settings.SEARXNG_AS_PRIMARY
        and settings.ENABLE_SEARXNG
        and settings.SEARXNG_URL
    )
    if ext_searx and searxng_primary:
        ranked_lists.append(ext_searx)
    if ext_openalex:
        ranked_lists.append(ext_openalex)
    if ext_wiki:
        ranked_lists.append(ext_wiki)
    if ext_wd:
        ranked_lists.append(ext_wd)
    if ext_searx and not searxng_primary:
        ranked_lists.append(ext_searx)

    rrf_scores = multi_rrf(ranked_lists, settings.RRF_K)
    registry = build_id_registry(meili_hits, external)
    for cid in rrf_scores:
        if cid not in registry:
            registry[cid] = {
                "id": cid,
                "title": "",
                "summary": "",
                "url": "",
                "published_at": None,
                "source_domain": "",
            }
    fused = weighted_fusion_scores(
        rrf_scores,
        registry,
        needs_fresh=plan.needs_fresh,
    )

    sorted_ids = sorted(fused.keys(), key=lambda x: fused[x], reverse=True)

    results: list[dict[str, Any]] = []
    for doc_id in sorted_ids[: max(limit * 2, limit)]:
        row = registry.get(doc_id)
        if row:
            row = dict(row)
            row["fusion_score"] = round(float(fused.get(doc_id, 0.0)), 6)
            results.append(row)
        else:
            results.append(
                {
                    "id": doc_id,
                    "fusion_score": round(float(fused.get(doc_id, 0.0)), 6),
                }
            )

    results = results[:limit]
    results = rerank_results(q, results)

    synth: dict[str, Any] = {}
    if settings.ENABLE_SYNTHESIS:
        synth = await synthesize_answer(q, results)

    brain_boost_out: dict[str, Any] | None = None
    if brain_boost:
        wait = brain_max_wait_sec if brain_max_wait_sec is not None else settings.BRAIN_BOOST_MAX_WAIT
        src = brain_boost.strip().lower()
        if src == "firecrawl_agent":
            try:
                raw = await firecrawl_agent_sync(
                    prompt=q,
                    max_wait_sec=float(wait),
                    poll_interval_sec=2.0,
                )
                brain_boost_out = {"source": "firecrawl_agent", "data": raw}
            except BrainMisconfigured as e:
                brain_boost_out = {"source": "firecrawl_agent", "skipped": str(e)}
            except Exception as e:
                brain_boost_out = {"source": "firecrawl_agent", "error": str(e)[:1200]}
        elif src == "openperplex":
            try:
                sse = await openperplex_collect_sse(
                    query=q,
                    date_context=openperplex_date_context,
                    stored_location=openperplex_stored_location,
                    pro_mode=openperplex_pro_mode,
                )
                brain_boost_out = {
                    "source": "openperplex",
                    "sse_text": sse[:80_000],
                    "truncated": len(sse) > 80_000,
                }
            except BrainMisconfigured as e:
                brain_boost_out = {"source": "openperplex", "skipped": str(e)}
            except Exception as e:
                brain_boost_out = {"source": "openperplex", "error": str(e)[:1200]}
        elif src == "vane":
            try:
                data = await vane_search_get(q)
                brain_boost_out = {"source": "vane", "data": data}
            except BrainMisconfigured as e:
                brain_boost_out = {"source": "vane", "skipped": str(e)}
            except Exception as e:
                brain_boost_out = {"source": "vane", "error": str(e)[:1200]}
        else:
            brain_boost_out = {"source": brain_boost, "skipped": "valor brain_boost no reconocido"}

    ms = (time.perf_counter() - t0) * 1000.0
    out: dict[str, Any] = {
        "query": q,
        "plan": plan.to_dict(),
        "total": len(results),
        "results": results,
        "search_time_ms": round(ms, 2),
        "cached": False,
    }
    if synth:
        out["synthesis"] = synth
    if brain_boost_out is not None:
        out["brain_boost"] = brain_boost_out
    return out

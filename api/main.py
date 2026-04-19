from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

import numpy as np
import redis
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from meilisearch import Client as MeiliClient
from qdrant_client import QdrantClient

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

from app import settings
from app.brain import router as brain_router
from app.fusion import multi_rrf
from app.pipeline import run_resolve
from app.query_plan import cache_ttl_seconds, fast_route, plan_with_ollama_if_needed

app = FastAPI(title="InvestSearch API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(brain_router)

_meili: MeiliClient | None = None
_qdrant: QdrantClient | None = None
_embed: "SentenceTransformer | None" = None
_redis: redis.Redis | None = None


def get_meili() -> MeiliClient:
    global _meili
    if _meili is None:
        _meili = MeiliClient(settings.MEILI_URL, settings.MEILI_MASTER_KEY or None)
    return _meili


def get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(url=settings.QDRANT_URL)
    return _qdrant


def get_embed() -> "SentenceTransformer":
    global _embed
    if _embed is None:
        from sentence_transformers import SentenceTransformer

        _embed = SentenceTransformer(settings.EMBED_MODEL)
    return _embed


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def embed_query(q: str) -> list[float]:
    m = get_embed()
    v = m.encode(q[:4000], normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(v).tolist()


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/search")
async def search(
    q: str = Query(..., min_length=2, max_length=500),
    ticker: str | None = None,
    lang: str | None = None,
    from_date: str | None = None,
    limit: int = Query(default=20, le=100),
    include_plan: bool = Query(default=False),
) -> dict[str, Any]:
    t0 = time.perf_counter()
    plan_obj = fast_route(q)
    if include_plan:
        plan_obj = await plan_with_ollama_if_needed(q, plan_obj)
    ttl = cache_ttl_seconds(plan_obj)

    cache_key = hashlib.sha256(
        json.dumps(
            {
                "q": q,
                "ticker": ticker,
                "lang": lang,
                "from_date": from_date,
                "limit": limit,
                "include_plan": include_plan,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    rkey = f"search:{cache_key}"
    try:
        cached = get_redis().get(rkey)
        if cached:
            out = json.loads(cached)
            out["search_time_ms"] = 0.0
            out["cached"] = True
            return out
    except Exception:
        pass

    filt = build_meili_filter(ticker, lang, from_date)
    idx = get_meili().index("documents")

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

    vec = embed_query(q)
    qdrant_ids: list[str] = []
    try:
        qr = get_qdrant().search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=vec,
            limit=limit * 2,
            with_payload=False,
        )
        qdrant_ids = [str(p.id) for p in qr.points]
    except Exception:
        qdrant_ids = []

    meili_ids = [str(h.get("id")) for h in meili_hits if h.get("id")]
    rrf_scores = multi_rrf([meili_ids, qdrant_ids], settings.RRF_K)
    fused_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:limit]

    by_id = {str(h.get("id")): h for h in meili_hits}
    results: list[dict[str, Any]] = []
    for doc_id in fused_ids:
        hit = by_id.get(doc_id)
        if hit:
            results.append(hit)
        else:
            results.append({"id": doc_id})

    ms = (time.perf_counter() - t0) * 1000.0
    out: dict[str, Any] = {
        "query": q,
        "total": len(results),
        "results": results,
        "search_time_ms": round(ms, 2),
        "cached": False,
    }
    if include_plan:
        out["plan"] = plan_obj.to_dict()
    try:
        get_redis().setex(rkey, ttl, json.dumps(out))
    except Exception:
        pass
    return out


@app.get("/resolve")
async def resolve(
    q: str = Query(..., min_length=2, max_length=500),
    ticker: str | None = None,
    lang: str | None = None,
    from_date: str | None = None,
    limit: int = Query(default=20, le=100),
    brain_boost: str | None = Query(
        None,
        description="Opcional: firecrawl_agent | openperplex | vane — mezcla con motor remoto",
    ),
    brain_max_wait_sec: float | None = Query(
        None,
        ge=10,
        le=600,
        description="Timeout polling Agent Firecrawl (por defecto BRAIN_BOOST_MAX_WAIT)",
    ),
    openperplex_date_context: str = Query(""),
    openperplex_stored_location: str = Query(""),
    openperplex_pro_mode: bool = Query(False),
) -> dict[str, Any]:
    t0 = time.perf_counter()
    plan_for_ttl = fast_route(q)
    plan_for_ttl = await plan_with_ollama_if_needed(q, plan_for_ttl)
    ttl = cache_ttl_seconds(plan_for_ttl)

    cache_key = hashlib.sha256(
        json.dumps(
            {
                "endpoint": "resolve",
                "q": q,
                "ticker": ticker,
                "lang": lang,
                "from_date": from_date,
                "limit": limit,
                "synth": settings.ENABLE_SYNTHESIS,
                "rerank": settings.ENABLE_RERANK,
                "brain_boost": brain_boost,
                "brain_max_wait_sec": brain_max_wait_sec,
                "openperplex_date_context": openperplex_date_context,
                "openperplex_stored_location": openperplex_stored_location,
                "openperplex_pro_mode": openperplex_pro_mode,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    rkey = f"resolve:{cache_key}"
    try:
        cached = get_redis().get(rkey)
        if cached:
            out = json.loads(cached)
            out["search_time_ms"] = 0.0
            out["cached"] = True
            return out
    except Exception:
        pass

    out = await run_resolve(
        q,
        meili=get_meili(),
        qdrant=get_qdrant(),
        embed_query=embed_query,
        ticker=ticker,
        lang=lang,
        from_date=from_date,
        limit=limit,
        plan=plan_for_ttl,
        brain_boost=brain_boost,
        brain_max_wait_sec=brain_max_wait_sec,
        openperplex_date_context=openperplex_date_context,
        openperplex_stored_location=openperplex_stored_location,
        openperplex_pro_mode=openperplex_pro_mode,
    )
    ms = (time.perf_counter() - t0) * 1000.0
    out["search_time_ms"] = round(ms, 2)
    try:
        get_redis().setex(rkey, ttl, json.dumps(out))
    except Exception:
        pass
    return out

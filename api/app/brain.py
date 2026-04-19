"""Rutas HTTP para Firecrawl Agent, OpenPerplex, Vane y SearXNG. Lógica remota compartida: `brain_client.py`; SearXNG en `sources/searxng.py`."""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app import settings
from app.brain_client import (
    BrainMisconfigured,
    firecrawl_agent_get,
    firecrawl_agent_start,
    firecrawl_agent_sync,
    vane_search_get,
)
from app.sources.searxng import searxng_raw_json

router = APIRouter(prefix="/brain", tags=["brain"])


class FirecrawlAgentStartBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    prompt: str = Field(..., min_length=1, max_length=10000)
    urls: list[str] | None = None
    schema_: dict[str, Any] | None = Field(None, alias="schema")
    maxCredits: float | None = None
    strictConstrainToURLs: bool | None = None
    model: str | None = Field(None, description="spark-1-mini | spark-1-pro")


class FirecrawlAgentSyncBody(FirecrawlAgentStartBody):
    poll_interval_sec: float = Field(2.0, ge=0.5, le=30)
    max_wait_sec: float = Field(120.0, ge=5, le=600)


def _http_exc(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.text[:2000],
        )
    return HTTPException(status_code=502, detail=str(exc)[:2000])


@router.post("/firecrawl/agent")
async def firecrawl_agent_start_route(body: FirecrawlAgentStartBody) -> dict[str, Any]:
    try:
        return await firecrawl_agent_start(
            prompt=body.prompt,
            urls=body.urls,
            schema=body.schema_,
            max_credits=body.maxCredits,
            strict_constrain_to_urls=body.strictConstrainToURLs,
            model=body.model,
        )
    except BrainMisconfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        raise _http_exc(e) from e


@router.get("/firecrawl/agent/{job_id}")
async def firecrawl_agent_status_route(job_id: str) -> dict[str, Any]:
    try:
        return await firecrawl_agent_get(job_id)
    except BrainMisconfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        raise _http_exc(e) from e


@router.post("/firecrawl/agent/sync")
async def firecrawl_agent_sync_route(body: FirecrawlAgentSyncBody) -> dict[str, Any]:
    try:
        out = await firecrawl_agent_sync(
            prompt=body.prompt,
            urls=body.urls,
            schema=body.schema_,
            max_credits=body.maxCredits,
            strict_constrain_to_urls=body.strictConstrainToURLs,
            model=body.model,
            poll_interval_sec=body.poll_interval_sec,
            max_wait_sec=body.max_wait_sec,
        )
    except BrainMisconfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        raise _http_exc(e) from e

    if out.get("_error") == "failed":
        raise HTTPException(status_code=502, detail=out.get("error") or str(out))
    if out.get("_error") == "timeout":
        raise HTTPException(status_code=504, detail=out)
    if out.get("_error") == "sin id en respuesta start":
        raise HTTPException(status_code=502, detail=out)
    return out


@router.get("/openperplex/search")
async def openperplex_search_proxy(
    query: str = Query(..., min_length=1),
    date_context: str = Query(default=""),
    stored_location: str = Query(default=""),
    pro_mode: bool = Query(default=False),
):
    if not settings.OPENPERPLEX_URL:
        raise HTTPException(status_code=503, detail="OPENPERPLEX_URL no configurada")

    base = settings.OPENPERPLEX_URL.rstrip("/")
    url = f"{base}/search"
    params = {
        "query": query,
        "date_context": date_context,
        "stored_location": stored_location,
        "pro_mode": pro_mode,
    }

    async def stream():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, params=params) as r:
                if r.status_code >= 400:
                    body = await r.aread()
                    yield f"data: {json.dumps({'type': 'error', 'data': body.decode(errors='replace')[:500]})}\n\n"
                    return
                async for chunk in r.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/vane/search")
async def vane_search_proxy(q: str = Query(..., min_length=1)):
    try:
        return await vane_search_get(q)
    except BrainMisconfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        raise _http_exc(e) from e


@router.get("/searxng/search")
async def searxng_search_proxy(q: str = Query(..., min_length=1)):
    if not settings.ENABLE_SEARXNG or not settings.SEARXNG_URL:
        raise HTTPException(
            status_code=503,
            detail="SearXNG no configurado (ENABLE_SEARXNG=1 y SEARXNG_URL)",
        )
    try:
        return await searxng_raw_json(q)
    except httpx.HTTPStatusError as e:
        raise _http_exc(e) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:2000]) from e

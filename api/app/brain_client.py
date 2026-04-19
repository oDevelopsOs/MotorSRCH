"""
Clientes HTTP reutilizables para Firecrawl Agent, OpenPerplex y Vane.
Usados por `brain` router y por `pipeline.run_resolve` (brain_boost).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from app import settings


class BrainMisconfigured(RuntimeError):
    """Falta API key o URL necesaria."""


def _fc_base() -> str:
    return settings.FIRECRAWL_AGENT_BASE_URL.rstrip("/")


def fc_auth_headers() -> dict[str, str]:
    if not settings.FIRECRAWL_AGENT_API_KEY:
        raise BrainMisconfigured("FIRECRAWL_AGENT_API_KEY no configurada")
    return {
        "Authorization": f"Bearer {settings.FIRECRAWL_AGENT_API_KEY}",
        "Content-Type": "application/json",
    }


async def firecrawl_agent_start(
    *,
    prompt: str,
    urls: list[str] | None = None,
    schema: dict[str, Any] | None = None,
    max_credits: float | None = None,
    strict_constrain_to_urls: bool | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"prompt": prompt}
    if urls:
        payload["urls"] = urls
    if schema is not None:
        payload["schema"] = schema
    if max_credits is not None:
        payload["maxCredits"] = max_credits
    if strict_constrain_to_urls is not None:
        payload["strictConstrainToURLs"] = strict_constrain_to_urls
    if model:
        payload["model"] = model

    url = f"{_fc_base()}/v2/agent"
    async with httpx.AsyncClient(timeout=settings.BRAIN_HTTP_TIMEOUT) as client:
        r = await client.post(url, json=payload, headers=fc_auth_headers())
    r.raise_for_status()
    return r.json()


async def firecrawl_agent_get(job_id: str) -> dict[str, Any]:
    url = f"{_fc_base()}/v2/agent/{job_id}"
    async with httpx.AsyncClient(timeout=settings.BRAIN_HTTP_TIMEOUT) as client:
        r = await client.get(url, headers=fc_auth_headers())
    r.raise_for_status()
    return r.json()


async def firecrawl_agent_sync(
    *,
    prompt: str,
    urls: list[str] | None = None,
    schema: dict[str, Any] | None = None,
    max_credits: float | None = None,
    strict_constrain_to_urls: bool | None = None,
    model: str | None = None,
    poll_interval_sec: float = 2.0,
    max_wait_sec: float = 120.0,
) -> dict[str, Any]:
    """POST /v2/agent y poll hasta completed/failed."""
    start = await firecrawl_agent_start(
        prompt=prompt,
        urls=urls,
        schema=schema,
        max_credits=max_credits,
        strict_constrain_to_urls=strict_constrain_to_urls,
        model=model,
    )
    job_id = start.get("id")
    if not job_id:
        return {"_error": "sin id en respuesta start", "raw": start}

    deadline = time.monotonic() + max_wait_sec
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = await firecrawl_agent_get(job_id)
        st = last.get("status")
        if st == "completed":
            return last
        if st == "failed":
            return {"_error": "failed", **last}
        await asyncio.sleep(poll_interval_sec)

    return {"_error": "timeout", "last": last}


async def openperplex_collect_sse(
    *,
    query: str,
    date_context: str = "",
    stored_location: str = "",
    pro_mode: bool = False,
    max_bytes: int = 2_000_000,
) -> str:
    if not settings.OPENPERPLEX_URL:
        raise BrainMisconfigured("OPENPERPLEX_URL no configurada")

    base = settings.OPENPERPLEX_URL.rstrip("/")
    url = f"{base}/search"
    params = {
        "query": query,
        "date_context": date_context,
        "stored_location": stored_location,
        "pro_mode": pro_mode,
    }
    buf = bytearray()
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET", url, params=params) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                buf.extend(chunk)
                if len(buf) >= max_bytes:
                    break
    return buf.decode("utf-8", errors="replace")


async def vane_search_get(q: str) -> Any:
    if not settings.VANE_API_URL:
        raise BrainMisconfigured("VANE_API_URL no configurada")

    base = settings.VANE_API_URL.rstrip("/")
    path = settings.VANE_SEARCH_PATH.lstrip("/")
    url = f"{base}/{path}"
    async with httpx.AsyncClient(timeout=settings.BRAIN_HTTP_TIMEOUT) as client:
        r = await client.get(url, params={"q": q})
    r.raise_for_status()
    try:
        return r.json()
    except json.JSONDecodeError:
        return {"raw": r.text[:8000]}

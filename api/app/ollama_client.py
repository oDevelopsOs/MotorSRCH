from __future__ import annotations

import httpx

from . import settings


async def ollama_complete(
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 1000,
    temperature: float = 0.1,
    timeout: float | None = None,
) -> str:
    m = model or settings.OLLAMA_MODEL
    url = f"{settings.OLLAMA_URL.rstrip('/')}/api/generate"
    t = timeout if timeout is not None else settings.OLLAMA_HTTP_TIMEOUT
    async with httpx.AsyncClient(timeout=t) as client:
        resp = await client.post(
            url,
            json={
                "model": m,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": temperature},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("response", ""))

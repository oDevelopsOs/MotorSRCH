"""HTTP bridge: Camoufox (Playwright) → JSON para el crawler Go."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from camoufox.async_api import AsyncCamoufox
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


def _token_ok(header: str | None) -> bool:
    expected = (os.getenv("CAMOUFOX_BRIDGE_TOKEN") or "").strip()
    if not expected:
        return True
    if not header or header != f"Bearer {expected}":
        return False
    return True


@asynccontextmanager
async def _lifespan(app: FastAPI):
    headless = os.getenv("CAMOUFOX_HEADLESS", "1").strip().lower() not in ("0", "false", "no")
    async with AsyncCamoufox(headless=headless) as browser:
        app.state.browser = browser
        yield


app = FastAPI(title="Camoufox bridge", lifespan=_lifespan)


class FetchBody(BaseModel):
    url: str = Field(..., min_length=8, max_length=8000)
    timeout_ms: int = Field(120_000, ge=5_000, le=300_000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/fetch")
async def fetch_page(
    body: FetchBody,
    authorization: str | None = Header(default=None),
) -> dict:
    if not _token_ok(authorization):
        raise HTTPException(status_code=401, detail="unauthorized")
    browser = app.state.browser
    page = await browser.new_page()
    try:
        await page.goto(
            body.url,
            wait_until="domcontentloaded",
            timeout=body.timeout_ms,
        )
        title = (await page.title()) or ""
        html = await page.content()
        return {"ok": True, "html": html, "title": title.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:2000], "html": "", "title": ""}
    finally:
        await page.close()

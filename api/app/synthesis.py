from __future__ import annotations

from typing import Any

from . import settings
from .ollama_client import ollama_complete


async def synthesize_answer(
    query: str,
    contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Produce a short answer with citations from top contexts."""
    if not settings.ENABLE_SYNTHESIS or not contexts:
        return {"answer": "", "citations": [], "provider": "none"}

    lines: list[str] = []
    cites: list[dict[str, str]] = []
    for i, c in enumerate(contexts[: settings.SYNTHESIS_MAX_CONTEXT_DOCS], start=1):
        title = str(c.get("title") or "")
        summary = str(c.get("summary") or "")[:1200]
        url = str(c.get("url") or "")
        src = str(c.get("source") or c.get("source_domain") or "")
        lines.append(f"[{i}] {title}\n{summary}\nURL: {url}\nSource: {src}")
        if url:
            cites.append({"ref": str(i), "title": title, "url": url})

    prompt = f"""You are a research assistant. Answer the user question using ONLY the numbered sources below.
If the sources are insufficient, say what is missing. End with a "Sources:" line listing ref numbers used.

Question: {query}

Sources:
{chr(10).join(lines)}

Answer (concise, factual):"""

    provider = settings.SYNTHESIS_PROVIDER.lower().strip()
    if provider == "groq" and settings.GROQ_API_KEY:
        try:
            from groq import AsyncGroq

            client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            resp = await client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=900,
                temperature=0.1,
            )
            text = resp.choices[0].message.content or ""
            return {"answer": text.strip(), "citations": cites, "provider": "groq"}
        except Exception:
            pass

    text = await ollama_complete(
        prompt,
        model=settings.OLLAMA_MODEL,
        max_tokens=900,
        temperature=0.1,
    )
    return {"answer": text.strip(), "citations": cites, "provider": "ollama"}

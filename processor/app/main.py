from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2
import trafilatura
from fastapi import FastAPI, Request, Response
from langdetect import detect
from meilisearch import Client as MeiliClient
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from trafilatura import extract_metadata

from . import settings
from .embeddings import embed_text
from .enrich import enrich_document, translate_to_english
from .minhash_dedup import SemanticDedup
from .scoring import calculate_score
from .trust import trust_for_domain

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("processor")

app = FastAPI(title="Motor F1 Processor")

_semantic: SemanticDedup | None = None
_meili: MeiliClient | None = None
_qdrant: QdrantClient | None = None


def get_semantic() -> SemanticDedup:
    global _semantic
    if _semantic is None:
        _semantic = SemanticDedup()
    return _semantic


def meili() -> MeiliClient:
    global _meili
    if _meili is None:
        _meili = MeiliClient(settings.MEILI_URL, settings.MEILI_MASTER_KEY or None)
    return _meili


def qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(url=settings.QDRANT_URL)
    return _qdrant


@app.on_event("startup")
def startup() -> None:
    try:
        meili().create_index("documents", {"primaryKey": "id"})
    except Exception:
        pass
    configure_meili()
    configure_qdrant()


def configure_meili() -> None:
    idx = meili().index("documents")
    try:
        idx.update_ranking_rules(
            ["words", "typo", "attribute", "sort", "exactness"]
        )
        idx.update_searchable_attributes(
            ["title", "summary", "entities.tickers", "entities.companies", "content"]
        )
        idx.update_filterable_attributes(
            ["ticker", "tickers", "source_domain", "sentiment", "language", "published_at"]
        )
        idx.update_sortable_attributes(["score", "published_at"])
    except Exception as e:
        log.warning("meili settings: %s", e)


def configure_qdrant() -> None:
    if not settings.ENABLE_EMBEDDINGS:
        return
    qc = qdrant()
    cols = [c.name for c in qc.get_collections().collections]
    if settings.QDRANT_COLLECTION in cols:
        return
    qc.recreate_collection(
        collection_name=settings.QDRANT_COLLECTION,
        vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
    )


def html_to_parts(html: str, url: str) -> tuple[str, str | None, datetime | None]:
    text = trafilatura.extract(html) or ""
    meta = extract_metadata(html)
    title = meta.title if meta else None
    pub: datetime | None = None
    if meta and meta.date:
        try:
            pub = datetime.fromisoformat(meta.date.replace("Z", "+00:00"))
        except ValueError:
            pub = None
    return text, title, pub


def pg_conn():
    return psycopg2.connect(settings.DATABASE_URL)


def upsert_source(cur, domain: str) -> str:
    trust = trust_for_domain(domain)
    cur.execute(
        """
        INSERT INTO sources (domain, name, trust_score, language)
        VALUES (%s, %s, %s, 'en')
        ON CONFLICT (domain) DO UPDATE SET last_crawl = NOW()
        RETURNING id::text
        """,
        (domain, domain, trust),
    )
    row = cur.fetchone()
    return row[0]


def url_exists(cur, url: str) -> bool:
    cur.execute("SELECT 1 FROM documents WHERE url = %s LIMIT 1", (url,))
    return cur.fetchone() is not None


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/internal/ingest")
async def ingest(request: Request) -> Response:
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return Response(status_code=400)

    try:
        process_raw_page(payload)
    except Exception as e:
        log.exception("ingest failed: %s", e)
        return Response(status_code=500)

    return Response(status_code=200)


def process_raw_page(msg: dict[str, Any]) -> None:
    doc_id = str(msg.get("id") or uuid.uuid4())
    url = str(msg.get("url") or "")
    html = str(msg.get("html") or "")
    domain = str(msg.get("domain") or "")
    title_hint = str(msg.get("title") or "")

    if not url or not html:
        return

    text, title_meta, pub_meta = html_to_parts(html, url)
    title = title_meta or title_hint or ""
    if len(text) < 80:
        log.info("skip short text: %s", url)
        return

    chash = hash_text(text)

    with pg_conn() as conn:
        with conn.cursor() as cur:
            if url_exists(cur, url):
                log.info("dedup url: %s", url)
                return
            cur.execute(
                "SELECT 1 FROM documents WHERE content_hash = %s LIMIT 1",
                (chash,),
            )
            if cur.fetchone():
                log.info("dedup hash: %s", url)
                return

    if settings.ENABLE_MINHASH and get_semantic().should_skip_duplicate(text, doc_id):
        log.info("dedup minhash: %s", url)
        return

    lang = "en"
    try:
        lang = detect(text[:2000]) or "en"
    except Exception:
        pass

    work_text = text
    if settings.ENABLE_TRANSLATION and lang[:2] not in ("en",):
        try:
            work_text = translate_to_english(text[:2000], lang)
        except Exception as e:
            log.warning("translate: %s", e)

    entities = enrich_document(work_text, settings.ENABLE_FINBERT)
    tickers: list[str] = list(entities.get("tickers") or [])
    first_ticker = tickers[0] if tickers else None

    published_at = pub_meta or datetime.now(timezone.utc)

    row_doc: dict[str, Any] = {
        "title": title,
        "summary": work_text[:500],
        "content": work_text[:50_000],
        "url": url,
        "source_domain": domain,
        "domain": domain,
        "published_at": published_at.isoformat(),
        "entities": {
            "tickers": tickers,
            "companies": entities.get("companies", []),
        },
        "ticker": first_ticker,
        "tickers": tickers,
        "sentiment": entities.get("sentiment", "neutral"),
        "language": lang,
    }
    score = calculate_score({**row_doc, "published_at": published_at})
    row_doc["score"] = score

    meili_doc = {"id": doc_id, **row_doc}
    meili().index("documents").add_documents([meili_doc], primary_key="id")

    if settings.ENABLE_EMBEDDINGS:
        vec = embed_text(work_text).tolist()
        qdrant().upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=[
                PointStruct(
                    id=doc_id,
                    vector=vec,
                    payload={
                        "url": url,
                        "title": title,
                        "score": score,
                    },
                )
            ],
        )

    with pg_conn() as conn:
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                sid = upsert_source(cur, domain)
                cur.execute(
                    """
                    INSERT INTO documents (
                        id, url, source_id, title, content_hash, language, published_at,
                        score, tickers, sentiment, sentiment_score, meili_id, qdrant_id
                    )
                    VALUES (
                        %s::uuid, %s, %s::uuid, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s::uuid
                    )
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (
                        doc_id,
                        url,
                        sid,
                        title,
                        chash,
                        lang,
                        published_at,
                        score,
                        tickers,
                        entities.get("sentiment"),
                        entities.get("sentiment_score"),
                        doc_id,
                        doc_id,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


@app.get("/debug/meili-stats")
def meili_stats() -> dict[str, Any]:
    try:
        return meili().index("documents").get_stats()
    except Exception as e:
        return {"error": str(e)}

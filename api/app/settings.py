from __future__ import annotations

import os


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


MEILI_URL = os.getenv("MEILI_URL", "http://localhost:7700")
MEILI_MASTER_KEY = os.getenv("MEILI_MASTER_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "documents")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
RRF_K = int(os.getenv("RRF_K", "60"))

SEARCH_CACHE_TTL = int(os.getenv("SEARCH_CACHE_TTL", "120"))
CACHE_TTL_NEWS = int(os.getenv("CACHE_TTL_NEWS", "300"))
CACHE_TTL_DEFINITION = int(os.getenv("CACHE_TTL_DEFINITION", "86400"))
CACHE_TTL_STABLE = int(os.getenv("CACHE_TTL_STABLE", "14400"))

# Fusion weights (phase 3)
FUSION_TRUST_WEIGHT = env_float("FUSION_TRUST_WEIGHT", 0.35)
FUSION_RECENCY_WEIGHT = env_float("FUSION_RECENCY_WEIGHT", 0.25)
# Remaining weight implicitly on normalized RRF

# Ollama (plan + synthesis)
OLLAMA_URL = os.getenv("OLLAMA_URL") or "http://localhost:11434"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
USE_OLLAMA_FOR_PLAN = env_bool("USE_OLLAMA_FOR_PLAN", False)
OLLAMA_PLAN_TIMEOUT = float(os.getenv("OLLAMA_PLAN_TIMEOUT", "15"))
OLLAMA_HTTP_TIMEOUT = float(os.getenv("OLLAMA_HTTP_TIMEOUT", "120"))

# Groq (optional synthesis)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")

# External HTTP sources
HTTP_TIMEOUT = float(os.getenv("SOURCE_HTTP_TIMEOUT", "8"))
ENABLE_OPENALEX = env_bool("ENABLE_OPENALEX", True)
ENABLE_WIKIPEDIA = env_bool("ENABLE_WIKIPEDIA", True)
ENABLE_WIKIDATA = env_bool("ENABLE_WIKIDATA", True)

# SearXNG (meta-búsqueda agregada; servicio opcional en compose perfil `searxng`)
ENABLE_SEARXNG = env_bool("ENABLE_SEARXNG", False)
SEARXNG_URL = os.getenv("SEARXNG_URL", "").strip()
SEARXNG_MAX_RESULTS = int(os.getenv("SEARXNG_MAX_RESULTS", "15"))
# Varias peticiones /search en paralelo (categorías + motores); desactivar = una sola petición tipo antigua
ENABLE_SEARXNG_DECOMPOSITION = env_bool("ENABLE_SEARXNG_DECOMPOSITION", True)
SEARXNG_SUBQUERY_TIMEOUT = float(os.getenv("SEARXNG_SUBQUERY_TIMEOUT", "8"))
# Sin Wikipedia/OpenAlex/Wikidata directos: solo índice local + SearXNG (motores agregados + scrapers vía crawl)
SEARXNG_AS_PRIMARY = env_bool("SEARXNG_AS_PRIMARY", True)

# Rerank
ENABLE_RERANK = env_bool("ENABLE_RERANK", False)
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "24"))

# Synthesis
ENABLE_SYNTHESIS = env_bool("ENABLE_SYNTHESIS", False)
SYNTHESIS_PROVIDER = os.getenv("SYNTHESIS_PROVIDER", "ollama")  # ollama | groq
SYNTHESIS_MAX_CONTEXT_DOCS = int(os.getenv("SYNTHESIS_MAX_CONTEXT_DOCS", "5"))

# Firecrawl Agent (API cloud v2 — no soportado en self-host igual que cloud)
FIRECRAWL_AGENT_BASE_URL = os.getenv("FIRECRAWL_AGENT_BASE_URL", "https://api.firecrawl.dev")
FIRECRAWL_AGENT_API_KEY = os.getenv("FIRECRAWL_AGENT_API_KEY", "")

# OpenPerplex backend (microservicio aparte)
OPENPERPLEX_URL = os.getenv("OPENPERPLEX_URL", "")

# Vane API (solo HTTP; no usamos su UI)
VANE_API_URL = os.getenv("VANE_API_URL", "")
VANE_SEARCH_PATH = os.getenv("VANE_SEARCH_PATH", "api/search")

# Clientes HTTP “brain”
BRAIN_HTTP_TIMEOUT = float(os.getenv("BRAIN_HTTP_TIMEOUT", "120"))
BRAIN_BOOST_MAX_WAIT = float(os.getenv("BRAIN_BOOST_MAX_WAIT", "90"))

# CORS
_origins = os.getenv("CORS_ORIGINS", "*")
if _origins == "*":
    ALLOW_ORIGINS = ["*"]
else:
    ALLOW_ORIGINS = [o.strip() for o in _origins.split(",") if o.strip()]

import os


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


MEILI_URL = os.getenv("MEILI_URL", "http://localhost:7700")
MEILI_MASTER_KEY = os.getenv("MEILI_MASTER_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "")

ENABLE_EMBEDDINGS = env_bool("ENABLE_EMBEDDINGS", True)
ENABLE_FINBERT = env_bool("ENABLE_FINBERT", False)
ENABLE_TRANSLATION = env_bool("ENABLE_TRANSLATION", False)
ENABLE_MINHASH = env_bool("ENABLE_MINHASH", True)

QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "documents")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
NLLB_MODEL = os.getenv("NLLB_MODEL", "facebook/nllb-200-distilled-600M")

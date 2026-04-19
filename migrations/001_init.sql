-- Registro de fuentes
CREATE TABLE sources (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain      TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    language    TEXT DEFAULT 'en',
    trust_score FLOAT DEFAULT 0.5,
    crawl_freq  INTERVAL DEFAULT '1 hour',
    last_crawl  TIMESTAMPTZ,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Documentos procesados
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             TEXT UNIQUE NOT NULL,
    source_id       UUID REFERENCES sources(id),
    title           TEXT,
    content_hash    TEXT,
    language        TEXT,
    published_at    TIMESTAMPTZ,
    indexed_at      TIMESTAMPTZ DEFAULT NOW(),
    score           FLOAT DEFAULT 0.5,
    tickers         TEXT[],
    sentiment       TEXT,
    sentiment_score FLOAT,
    meili_id        TEXT,
    qdrant_id       UUID
);

CREATE INDEX idx_documents_tickers ON documents USING GIN(tickers);
CREATE INDEX idx_documents_published ON documents (published_at DESC);
CREATE INDEX idx_documents_score ON documents (score DESC);

-- Estadísticas de crawling
CREATE TABLE crawl_stats (
    id          BIGSERIAL PRIMARY KEY,
    source_id   UUID REFERENCES sources(id),
    crawled_at  TIMESTAMPTZ DEFAULT NOW(),
    pages_found INT DEFAULT 0,
    pages_new   INT DEFAULT 0,
    errors      INT DEFAULT 0,
    duration_ms INT
);

# Motor de búsqueda F1 — arquitectura completa a $0

> **Filosofía:** Lo que la Fórmula 1 hace con presupuesto limitado — ingeniería de élite, cero desperdicio, máximo rendimiento de cada componente. Todo open source. Todo self-hosted. Todo gratis.

---

## Infraestructura base — Oracle Cloud Always Free

El núcleo de todo. Oracle ofrece esto **para siempre, sin tarjeta de crédito requerida después del registro:**

| Recurso | Especificación | Coste |
|---|---|---|
| CPU | 4 vCPU ARM (Ampere A1) | $0 |
| RAM | 24 GB | $0 |
| Almacenamiento | 200 GB SSD | $0 |
| Ancho de banda | 10 TB/mes salida | $0 |
| IPs públicas | 2 | $0 |
| **Total** | **Servidor de producción real** | **$0/mes** |

**Servicios complementarios gratuitos:**

- **Supabase free** → PostgreSQL 500 MB (metadata, source registry)
- **Fly.io free tier** → 3 VMs pequeñas para workers distribuidos
- **GitHub Actions** → 2.000 minutos/mes CI/CD
- **Cloudflare free** → DNS, CDN, DDoS protection para la API pública
- **Redis Cloud free** → 30 MB Redis (query cache, rate limiter state)

---

## Stack tecnológico — decisiones y por qué

### Crawler — Go (Colly), no Python

```
Python Scrapy:    ~200 req/s por worker
Go Colly:       ~10.000 req/s por worker
```

Go usa goroutines nativas para I/O concurrente. Con los 4 CPUs de Oracle, un crawler Go satura el ancho de banda antes de saturar la CPU. Python con el GIL no puede hacer esto.

**Librerías Go:**

```
github.com/gocolly/colly/v2      — crawler principal
github.com/go-redis/redis/v8     — frontier + bloom filter
github.com/PuerkitoBio/goquery   — parsing HTML (jQuery-style)
github.com/temoto/robotstxt      — respeto robots.txt
```

### Message Queue — NSQ, no Kafka

```
Kafka:   JVM + Zookeeper + 2 GB RAM solo para arrancar
NSQ:     binario único, 50 MB RAM, 0 dependencias
```

NSQ es perfecto para esta escala. Cuando el negocio crezca a multi-servidor se reemplaza con Redpanda, pero NSQ arranca en 2 segundos y nunca falla.

**Topics NSQ:**

```
raw_pages      → páginas crudas del crawler
translated     → páginas con traducción aplicada
enriched       → con NER, sentiment, embeddings
indexed        → confirmación de indexación
dead_letter    → errores para reintento
```

### Search — Meilisearch + Qdrant, no Elasticsearch

```
Elasticsearch:   4-8 GB RAM heap mínimo útil
Meilisearch:     200 MB RAM, Rust, latencia <50ms
Qdrant:          vector DB más rápido del mercado, también Rust
```

Juntos hacen **búsqueda híbrida** (full-text + semántica) con Reciprocal Rank Fusion — mejor calidad de resultados que Elastic a un décimo del consumo de recursos.

### Embeddings — BGE-M3 (multilingüe, CPU)

BGE-M3 de BAAI es el modelo de embeddings open source más capaz para búsqueda multilingüe. Cubre inglés, chino, ruso y 100 idiomas más. Con cuantización INT8 corre en CPU con ~50 docs/segundo — suficiente para el volumen inicial.

### Traducción — NLLB-200 de Meta (self-hosted)

NLLB-200 (No Language Left Behind) de Meta soporta 200 idiomas. Con cuantización INT8 cabe en los 24 GB de Oracle. Traduce mandarín y ruso a inglés antes de indexar, lo que permite búsqueda cross-lingüe sin APIs de pago.

---

## Capa anti-bot — evasión open source

### FlareSolverr

Proxy open source que usa un browser real (Chrome headless) para resolver Cloudflare. Expone una API REST simple. Se despliega como contenedor Docker.

```bash
docker run -d \
  --name=flaresolverr \
  -p 8191:8191 \
  -e LOG_LEVEL=info \
  ghcr.io/flaresolverr/flaresolverr:latest
```

Uso desde el crawler:

```go
resp, _ := http.Post("http://localhost:8191/v1", "application/json",
    strings.NewReader(`{
        "cmd": "request.get",
        "url": "https://sitio-con-cloudflare.com/datos",
        "maxTimeout": 60000
    }`))
```

### curl-impersonate

Imita exactamente los TLS fingerprints (JA3) de Chrome 120 y Firefox 120. Para la mayoría de sitios que detectan bots por fingerprint TLS, esto los hace invisibles.

```bash
# Instalación
git clone https://github.com/lwthiker/curl-impersonate
cd curl-impersonate && make chrome

# Uso — idéntico a curl normal
curl_chrome120 https://sitio-protegido.com/api/datos
```

### Playwright con stealth plugin

Para páginas con JavaScript complejo y anti-bot sofisticado:

```python
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def crawl_js_heavy(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await stealth_async(page)  # <- hace el browser invisible como bot
        await page.goto(url)
        content = await page.content()
        await browser.close()
        return content
```

### Rotación de User-Agents y headers

```go
var userAgents = []string{
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

func randomUA() string {
    return userAgents[rand.Intn(len(userAgents))]
}
```

### Tor como proxy gratuito

Para sitios que bloquean IPs de datacenter, Tor proporciona IPs residenciales gratuitas (velocidad limitada pero funcional para crawling selectivo):

```bash
# Instalar Tor
apt install tor

# Usar como proxy SOCKS5
curl --socks5 127.0.0.1:9050 https://sitio-que-bloquea-datacenter.com
```

---

## Pipeline de procesamiento IA

### 1. Deduplicación — MinHash LSH

Antes de procesar nada, eliminar duplicados. MinHash Locally Sensitive Hashing detecta documentos similares (no solo idénticos) en O(1).

```python
from datasketch import MinHash, MinHashLSH

lsh = MinHashLSH(threshold=0.8, num_perm=128)

def is_duplicate(text: str, doc_id: str) -> bool:
    m = MinHash(num_perm=128)
    for word in text.lower().split():
        m.update(word.encode('utf8'))
    
    result = lsh.query(m)
    if result:
        return True  # es duplicado
    
    lsh.insert(doc_id, m)
    return False
```

### 2. NER financiero — FinBERT + spaCy

Extraer entidades financieras: tickers, empresas, eventos, fechas de earnings.

```python
from transformers import pipeline
import spacy

# FinBERT para sentiment financiero
sentiment = pipeline(
    "text-classification",
    model="ProsusAI/finbert",
    device=-1  # CPU
)

# spaCy para NER general
nlp = spacy.load("en_core_web_sm")

def enrich_document(text: str) -> dict:
    doc = nlp(text)
    
    entities = {
        "companies": [e.text for e in doc.ents if e.label_ == "ORG"],
        "locations": [e.text for e in doc.ents if e.label_ == "GPE"],
        "dates":     [e.text for e in doc.ents if e.label_ == "DATE"],
    }
    
    # Extraer tickers (patrón $TSLA, $AAPL, etc.)
    tickers = re.findall(r'\$([A-Z]{1,5})\b', text)
    entities["tickers"] = list(set(tickers))
    
    # Sentiment
    sent = sentiment(text[:512])[0]
    entities["sentiment"] = sent["label"]
    entities["sentiment_score"] = sent["score"]
    
    return entities
```

### 3. Embeddings — BGE-M3

```python
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("BAAI/bge-m3")

def embed_document(text: str) -> np.ndarray:
    # Truncar a 8192 tokens (capacidad de BGE-M3)
    return model.encode(
        text[:4000],
        normalize_embeddings=True,  # para cosine similarity
        show_progress_bar=False
    )
```

### 4. Traducción — NLLB-200 cuantizado

```python
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
import torch

tokenizer = AutoTokenizer.from_pretrained("facebook/nllb-200-distilled-600M")
model = AutoModelForSeq2SeqLM.from_pretrained(
    "facebook/nllb-200-distilled-600M",
    load_in_8bit=True  # cuantización INT8: cabe en 24GB con todo lo demás
)

def translate_to_english(text: str, source_lang: str) -> str:
    lang_codes = {
        "zh": "zho_Hans",  # Chino simplificado
        "ru": "rus_Cyrl",  # Ruso
        "ar": "arb_Arab",  # Árabe
    }
    
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    
    translated = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.lang_code_to_id["eng_Latn"],
        max_length=512
    )
    
    return tokenizer.batch_decode(translated, skip_special_tokens=True)[0]
```

### 5. Scoring de calidad

```python
from datetime import datetime, timezone

def calculate_score(doc: dict) -> float:
    # Frescura (decay exponencial)
    age_hours = (datetime.now(timezone.utc) - doc["published_at"]).total_seconds() / 3600
    freshness = 1.0 / (1.0 + age_hours / 24)  # media vida = 24 horas
    
    # Credibilidad de fuente (pre-definida por dominio)
    source_scores = {
        "sec.gov": 1.0,
        "reuters.com": 0.95,
        "ft.com": 0.93,
        "bloomberg.com": 0.93,
        "wsj.com": 0.90,
    }
    source_trust = source_scores.get(doc["domain"], 0.5)
    
    # Score final ponderado
    return (freshness * 0.4) + (source_trust * 0.6)
```

---

## Almacenamiento e indexación

### Meilisearch — configuración óptima

```bash
# Docker
docker run -d \
  --name meilisearch \
  -p 7700:7700 \
  -v $(pwd)/meili_data:/meili_data \
  -e MEILI_MASTER_KEY="tu_clave_secreta" \
  getmeili/meilisearch:latest
```

```python
import meilisearch

client = meilisearch.Client("http://localhost:7700", "tu_clave_secreta")
index = client.index("documents")

# Configuración de ranking para dominio financiero
index.update_ranking_rules([
    "words",
    "typo",
    "attribute",      # campos importantes pesan más
    "sort",
    "exactness"
])

index.update_searchable_attributes([
    "title",          # peso máximo
    "summary",
    "entities.tickers",
    "entities.companies",
    "content"         # peso mínimo (bulk)
])

index.update_filterable_attributes([
    "ticker",
    "source_domain",
    "sentiment",
    "language",
    "published_at"
])

index.update_sortable_attributes(["score", "published_at"])
```

### Qdrant — configuración óptima

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, HnswConfigDiff

client = QdrantClient(host="localhost", port=6333)

client.recreate_collection(
    collection_name="documents",
    vectors_config=VectorParams(
        size=1024,          # dimensión BGE-M3
        distance=Distance.COSINE
    ),
    hnsw_config=HnswConfigDiff(
        m=16,               # conexiones por nodo (calidad vs velocidad)
        ef_construct=100,   # calidad del índice
        full_scan_threshold=10000
    ),
    on_disk_payload=True    # payload en disco, vectores en RAM
)
```

### Búsqueda híbrida con RRF Fusion

```python
async def hybrid_search(query: str, limit: int = 20) -> list:
    # Búsqueda full-text (BM25)
    meili_results = index.search(query, {
        "limit": limit * 2,
        "attributesToRetrieve": ["id", "title", "summary", "score"]
    })
    
    # Búsqueda vectorial (semántica)
    query_vector = embed_document(query)
    qdrant_results = qdrant.search(
        collection_name="documents",
        query_vector=query_vector.tolist(),
        limit=limit * 2
    )
    
    # Reciprocal Rank Fusion (RRF)
    rrf_scores = {}
    k = 60  # constante RRF estándar
    
    for rank, hit in enumerate(meili_results["hits"]):
        rrf_scores[hit["id"]] = rrf_scores.get(hit["id"], 0) + 1 / (k + rank + 1)
    
    for rank, hit in enumerate(qdrant_results):
        rrf_scores[hit.id] = rrf_scores.get(hit.id, 0) + 1 / (k + rank + 1)
    
    # Ordenar por RRF score
    sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)
    
    return sorted_ids[:limit]
```

---

## Query layer — NGiNX + API

### NGiNX como reverse proxy + cache

```nginx
upstream search_api {
    least_conn;                         # balanceo por conexiones activas
    server 127.0.0.1:8000 weight=1;
    server 127.0.0.1:8001 weight=1;
    keepalive 32;
}

proxy_cache_path /var/cache/nginx
    levels=1:2
    keys_zone=search_cache:10m
    max_size=2g
    inactive=10m;

server {
    listen 443 ssl http2;
    server_name api.tudominio.com;

    # Rate limiting por IP
    limit_req_zone $binary_remote_addr zone=api:10m rate=30r/m;
    limit_req zone=api burst=10 nodelay;

    location /search {
        proxy_pass http://search_api;
        proxy_cache search_cache;
        proxy_cache_key "$request_uri";
        proxy_cache_valid 200 2m;       # cache de resultados 2 minutos
        proxy_cache_use_stale updating; # sirve caché mientras refresca
        
        add_header X-Cache-Status $upstream_cache_status;
    }
}
```

### API FastAPI

```python
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import asyncio

app = FastAPI(title="InvestSearch API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://investplatform.com"],
    allow_methods=["GET"],
)

@app.get("/search")
async def search(
    q: str = Query(..., min_length=2, max_length=500),
    ticker: str | None = None,
    lang: str | None = None,
    from_date: str | None = None,
    limit: int = Query(default=20, le=100)
):
    results = await hybrid_search(q, limit=limit)
    return {
        "query": q,
        "total": len(results),
        "results": results,
        "search_time_ms": ...,
    }
```

---

## Orden de construcción — sprint por sprint

### Sprint 1 — semana 1: el núcleo que funciona

1. Crear cuenta Oracle Cloud, provisionar VM ARM 24GB
2. Instalar Docker + Docker Compose
3. Levantar Meilisearch + Redis
4. Escribir crawler Colly básico (100 fuentes web abiertas)
5. Indexar en Meilisearch y probar búsqueda

**Resultado:** buscador funcional sobre noticias financieras

### Sprint 2 — semana 2: el crawler invisible

1. Desplegar FlareSolverr como contenedor
2. Integrar curl-impersonate en el crawler Go
3. Implementar Bloom filter para dedup de URLs (no repetir crawls)
4. Implementar rate limiting adaptativo por dominio
5. Añadir Tor para dominios que bloquean datacenter IPs

**Resultado:** crawler que evita bots y no repite trabajo

### Sprint 3 — semana 3: semántica

1. Desplegar Qdrant
2. Descargar y cuantizar BGE-M3 a INT8
3. Generar embeddings en el pipeline NSQ
4. Implementar búsqueda híbrida con RRF fusion

**Resultado:** resultados relevantes semánticamente, no solo por keyword

### Sprint 4 — semana 4: inteligencia financiera

1. Integrar FinBERT para sentiment por ticker
2. Descargar y cuantizar NLLB-200-distilled-600M
3. Pipeline de traducción para contenido no inglés
4. Scoring de frescura + credibilidad de fuente
5. PostgreSQL (Supabase) para source registry

**Resultado:** resultados rankeados por relevancia financiera real

### Sprint 5 — semana 5: producción

1. Configurar NGiNX con cache y rate limiting
2. API FastAPI con filtros por ticker, fecha, idioma
3. Redis query cache para búsquedas repetidas
4. Cloudflare DNS + DDoS protection (gratis)
5. GitHub Actions para deploy automático

**Resultado:** API de producción lista para InvestPlatform

---

## Fuentes a crawlear — mapa completo

### Internet abierto — alta prioridad

| Fuente | Tipo | Método |
|---|---|---|
| SEC EDGAR | Filings US | API oficial (gratis, sin límite) |
| FRED (Fed Reserve) | Datos macro | API oficial gratis |
| Alpha Vantage | Precios, noticias | API gratis (25 req/día) |
| Yahoo Finance | Precios, noticias | Scraping (no API oficial) |
| Reuters | Noticias | RSS + scraping |
| Financial Times | Noticias | RSS públicos |
| Wall Street Journal | Noticias | RSS + scraping selectivo |
| Bloomberg | Artículos públicos | Scraping (Cloudflare → FlareSolverr) |
| Seeking Alpha | Análisis | Scraping (anti-bot → curl-impersonate) |
| Investopedia | Definiciones | Scraping libre |
| Macrotrends | Datos históricos | Scraping |
| Simply Wall St | Análisis | Scraping |

### Social / comunidades

| Fuente | Tipo | Método |
|---|---|---|
| Reddit r/investing, r/stocks | Sentiment | Reddit API (gratis, limitada) |
| StockTwits | Sentiment tickers | API pública |
| Telegram canales financieros | Alpha | MTProto / Telethon (gratis) |
| Twitter/X | Sentiment | API básica gratis (limitada) |

### Internet chino — desde datacenter (lo que no bloquea)

| Fuente | Tipo | Accessible |
|---|---|---|
| Xinhua English | Noticias | Sí |
| China Daily | Noticias | Sí |
| CGTN | Noticias | Sí |
| Shanghai Stock Exchange | Datos A-shares | API pública parcial |
| Shenzhen Stock Exchange | Datos | API pública parcial |

### Internet ruso — desde datacenter (lo que no bloquea)

| Fuente | Tipo | Accessible |
|---|---|---|
| MOEX API | Datos bolsa | API oficial, gratis |
| cbr.ru (Banco Central) | Política monetaria | Acceso abierto |
| RBC English | Noticias | Acceso abierto |

---

## Arquitectura de datos — esquema PostgreSQL

```sql
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
    content_hash    TEXT,                    -- para dedup exacto
    language        TEXT,
    published_at    TIMESTAMPTZ,
    indexed_at      TIMESTAMPTZ DEFAULT NOW(),
    score           FLOAT DEFAULT 0.5,
    tickers         TEXT[],                  -- ['TSLA', 'AAPL']
    sentiment       TEXT,                    -- 'positive' | 'negative' | 'neutral'
    sentiment_score FLOAT,
    meili_id        TEXT,                    -- ID en Meilisearch
    qdrant_id       UUID                     -- ID en Qdrant
);

CREATE INDEX idx_documents_tickers ON documents USING GIN(tickers);
CREATE INDEX idx_documents_published ON documents(published_at DESC);
CREATE INDEX idx_documents_score ON documents(score DESC);

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
```

---

## docker-compose.yml — todo el stack

```yaml
version: '3.9'

services:

  # Message queue
  nsqd:
    image: nsqio/nsq
    command: /nsqd --lookupd-tcp-address=nsqlookupd:4160
    ports: ["4150:4150", "4151:4151"]
    restart: unless-stopped

  nsqlookupd:
    image: nsqio/nsq
    command: /nsqlookupd
    ports: ["4160:4160", "4161:4161"]
    restart: unless-stopped

  # Full-text search
  meilisearch:
    image: getmeili/meilisearch:latest
    ports: ["7700:7700"]
    environment:
      MEILI_MASTER_KEY: ${MEILI_KEY}
    volumes: ["./data/meili:/meili_data"]
    restart: unless-stopped

  # Vector search
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333", "6334:6334"]
    volumes: ["./data/qdrant:/qdrant/storage"]
    restart: unless-stopped

  # Cache + frontier
  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
    ports: ["6379:6379"]
    volumes: ["./data/redis:/data"]
    restart: unless-stopped

  # Anti-bot proxy
  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    ports: ["8191:8191"]
    environment:
      LOG_LEVEL: warn
    restart: unless-stopped

  # API principal
  api:
    build: ./api
    ports: ["8000:8000"]
    environment:
      MEILI_URL: http://meilisearch:7700
      QDRANT_URL: http://qdrant:6333
      REDIS_URL: redis://redis:6379
      DATABASE_URL: ${SUPABASE_URL}
    depends_on: [meilisearch, qdrant, redis]
    restart: unless-stopped

  # Crawler Go
  crawler:
    build: ./crawler
    environment:
      NSQ_URL: nsqd:4150
      REDIS_URL: redis://redis:6379
      FLARESOLVERR_URL: http://flaresolverr:8191
    depends_on: [nsqd, redis, flaresolverr]
    restart: unless-stopped

  # Worker procesamiento IA
  processor:
    build: ./processor
    environment:
      NSQ_URL: nsqd:4150
      MEILI_URL: http://meilisearch:7700
      QDRANT_URL: http://qdrant:6333
    depends_on: [nsqd, meilisearch, qdrant]
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 16G     # BGE-M3 + NLLB-200 cuantizados

volumes:
  data:
```

---

## Métricas objetivo — lo que "espectacular" significa en números

| Métrica | Objetivo mes 1 | Objetivo mes 6 |
|---|---|---|
| Páginas indexadas | 1 M | 50 M |
| Fuentes activas | 200 | 2.000 |
| Latencia búsqueda p50 | < 100 ms | < 50 ms |
| Latencia búsqueda p99 | < 500 ms | < 200 ms |
| Freshness (noticias) | < 15 min | < 5 min |
| Idiomas soportados | 3 (EN, ZH, RU) | 10+ |
| Coste mensual | $0 | $0 |

---

## Lo que viene después — cuando haya ingresos

En cuanto InvestPlatform genere los primeros €500/mes, la reinversión correcta es:

1. **€4/mes** → Hetzner CAX21 (ARM, 4 vCPU, 8 GB) para crawlers adicionales
2. **€15/mes** → Bright Data 1 GB CN residencial (desbloquea Eastmoney, Sina Finance)
3. **€20/mes** → Hetzner CAX31 para procesamiento IA dedicado

Por €39/mes el sistema se convierte en algo que ningún competidor con presupuesto normal puede igualar porque la base de ingeniería es F1 desde el día uno.

---

*Generado para InvestPlatform · arquitectura v1.0 · abril 2026*
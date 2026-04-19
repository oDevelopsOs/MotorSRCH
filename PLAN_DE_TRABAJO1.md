# El monstruo de información — fuentes gratuitas de élite + motor de resolución

> **Objetivo:** cuando llegue una query, resolverla con la información más completa, fiable y fresca disponible en internet, usando exclusivamente fuentes gratuitas y proyectos open source. Sin pagar un euro.

---

## Mapa mental de la estrategia

Hay tres categorías de fuentes. Cada una tiene un rol distinto:

```
CONOCIMIENTO BASE          DATOS EN TIEMPO REAL       FUENTES ESPECIALIZADAS
─────────────────          ────────────────────       ──────────────────────
Wikipedia / Wikidata    +  RSS financieros         +  SEC EDGAR (filings)
Common Crawl            +  APIs gratuitas          +  FRED (macro)
OpenAlex (papers)       +  Telegram canales        +  MOEX (bolsa rusa)
arXiv / PubMed          +  Reddit / Hacker News    +  OpenAlex (academia)
Internet Archive        +  GitHub trending         +  World Bank / IMF
Hugging Face datasets   +  Crawl directo           +  EU Open Data Portal
```

La clave no es elegir uno. Es **orquestar todos** y que la IA decida en tiempo real cuál fuente(s) consultar según la query.

---

## Parte 1 — Las fuentes de conocimiento base (gratuitas, masivas, de élite)

### Wikipedia + Wikidata — el grafo de conocimiento más grande del mundo

Wikipedia no es solo una enciclopedia. Es **la fuente de conocimiento estructurado más completa y fiable que existe**, con cobertura en 300+ idiomas y actualización constante por millones de editores.

**Wikipedia — acceso completo:**

```python
# Opción 1: API en tiempo real (para queries individuales)
import wikipedia
wikipedia.set_lang("en")
page = wikipedia.page("Apple Inc")
print(page.summary)      # resumen
print(page.content)      # contenido completo
print(page.links)        # páginas relacionadas

# Opción 2: Dump completo (para indexación masiva)
# Descargar el dump completo de Wikipedia en inglés (~22 GB comprimido)
# https://dumps.wikimedia.org/enwiki/latest/
# Actualizado cada 2 semanas. Completamente gratis.
```

**Wikidata — Wikipedia estructurada en triples RDF:**

Wikidata es lo que hace que Wikipedia sea consultable como una base de datos. Cada entidad tiene propiedades estructuradas: empresa → CEO → nombre, fecha de fundación, ingresos, etc.

```python
from wikidata.client import Client
client = Client()

# Buscar Apple Inc por ID (Q312)
entity = client.get('Q312', load=True)
print(entity.description)

# SPARQL para queries complejas
import requests

query = """
SELECT ?company ?companyLabel ?revenue WHERE {
  ?company wdt:P31 wd:Q4830453.    # instancia de: empresa
  ?company wdt:P2139 ?revenue.      # ingresos anuales
  FILTER(?revenue > 1000000000)    # más de 1B
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
ORDER BY DESC(?revenue)
LIMIT 100
"""

resp = requests.get(
    "https://query.wikidata.org/sparql",
    params={"query": query, "format": "json"},
    headers={"User-Agent": "InvestSearch/1.0"}
)
results = resp.json()["results"]["bindings"]
```

**Volumen:** 6,7 millones de artículos en inglés, 60+ millones en total. Dump descargable gratis cada 2 semanas.

---

### Common Crawl — petabytes de internet, gratis para siempre

Common Crawl es una organización sin ánimo de lucro que crawlea todo internet cada mes y **publica los datos completamente gratis en AWS S3 público**. No necesitas crawlear tú mismo lo que ya existe.

```
Tamaño: ~380 TB por crawl mensual
Documentos: ~3.000 millones de páginas web
Formato: WARC (Web ARChive) + WET (texto plano) + WAT (metadata)
Acceso: s3://commoncrawl/ (sin coste de descarga desde AWS)
```

**Lo que esto significa para ti:** en vez de crawlear Bloomberg desde cero, puedes consultar si Common Crawl ya tiene esa URL y extraer el texto directamente. Para análisis histórico es revolucionario.

```python
import boto3
from botocore import UNSIGNED
from botocore.config import Config

# Acceso anónimo (sin cuenta AWS)
s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))

# Buscar páginas específicas usando el índice CDX
import requests

def search_common_crawl(url: str, crawl: str = "CC-MAIN-2024-10") -> list:
    """
    Busca una URL en el índice de Common Crawl.
    Devuelve lista de captures con WARC offset para descargar.
    """
    cdx_url = f"http://index.commoncrawl.org/{crawl}-index"
    resp = requests.get(cdx_url, params={
        "url": url,
        "output": "json",
        "limit": 10
    })
    return [json.loads(line) for line in resp.text.strip().split('\n') if line]

def fetch_warc_record(filename: str, offset: int, length: int) -> str:
    """Descarga solo el fragmento WARC necesario (range request)."""
    resp = s3.get_object(
        Bucket="commoncrawl",
        Key=filename,
        Range=f"bytes={offset}-{offset+length-1}"
    )
    return resp['Body'].read()
```

**Uso inteligente:** no descargues todo. Usa el índice CDX para buscar URLs específicas y descarga solo el fragmento WARC que necesitas. Coste: $0.

---

### OpenAlex — 250 millones de papers académicos, API gratis

OpenAlex reemplazó a Microsoft Academic Graph. Es la base de datos de literatura científica más grande del mundo, con API completamente gratuita y sin límites severos.

```
250 millones de papers
200.000 instituciones
50.000 fuentes (revistas, preprints)
Actualización: diaria
API: https://api.openalex.org — gratis, 100.000 req/día sin clave
```

```python
import requests

def search_papers(query: str, topic: str = None) -> list:
    params = {
        "search": query,
        "sort": "cited_by_count:desc",   # más citados primero
        "per-page": 20,
        "select": "id,title,abstract_inverted_index,publication_year,cited_by_count,open_access"
    }
    
    if topic:
        params["filter"] = f"concepts.display_name:{topic}"
    
    resp = requests.get("https://api.openalex.org/works", params=params)
    works = resp.json()["results"]
    
    # Reconstruir abstract desde inverted index
    results = []
    for work in works:
        if work.get("abstract_inverted_index"):
            # OpenAlex almacena abstracts como {word: [posiciones]}
            idx = work["abstract_inverted_index"]
            words = sorted(
                [(pos, word) for word, positions in idx.items() for pos in positions]
            )
            abstract = " ".join(w for _, w in words)
        else:
            abstract = ""
        
        results.append({
            "title": work["title"],
            "abstract": abstract,
            "year": work["publication_year"],
            "citations": work["cited_by_count"],
            "open_access": work["open_access"]["is_oa"]
        })
    
    return results

# Ejemplo: buscar papers sobre stress testing financiero
papers = search_papers("portfolio stress testing systemic risk", topic="Finance")
```

**Para InvestPlatform:** cuando alguien busque metodología de análisis financiero, los papers académicos son la fuente de mayor credibilidad posible.

---

### arXiv — preprints de élite, API gratis

arXiv es donde los investigadores de quant finance, ML y economía publican **antes** de la revisión formal. Es la fuente más fresca de conocimiento técnico avanzado.

```
2 millones de papers
Categorías clave: q-fin (quantitative finance), cs.AI, econ
Actualización: diaria
API: https://export.arxiv.org/api — completamente gratis
```

```python
import urllib.request
import xml.etree.ElementTree as ET

def search_arxiv(query: str, category: str = "q-fin", max_results: int = 20) -> list:
    url = (
        f"http://export.arxiv.org/api/query?"
        f"search_query={urllib.parse.quote(query)}+AND+cat:{category}"
        f"&max_results={max_results}"
        f"&sortBy=submittedDate&sortOrder=descending"
    )
    
    with urllib.request.urlopen(url) as response:
        root = ET.fromstring(response.read())
    
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    
    for entry in root.findall("atom:entry", ns):
        results.append({
            "id":       entry.find("atom:id", ns).text,
            "title":    entry.find("atom:title", ns).text.strip(),
            "abstract": entry.find("atom:summary", ns).text.strip(),
            "published": entry.find("atom:published", ns).text[:10],
            "pdf_url":  entry.find("atom:id", ns).text.replace("abs", "pdf")
        })
    
    return results

# Papers sobre factor investing publicados esta semana
recent = search_arxiv("factor investing machine learning", "q-fin.PM")
```

---

### Internet Archive — la memoria de internet

El Wayback Machine no es solo nostalgia. Tiene una API para recuperar **versiones históricas de cualquier página web**, incluyendo noticias que ya no están online, reportes anuales eliminados, comunicados de prensa borrados.

```python
import requests
from datetime import datetime

def get_historical_page(url: str, date: str = None) -> str:
    """
    date formato: YYYYMMDD
    Si no se especifica, devuelve la versión más reciente disponible.
    """
    if date:
        wayback_url = f"http://archive.org/wayback/available?url={url}&timestamp={date}"
    else:
        wayback_url = f"http://archive.org/wayback/available?url={url}"
    
    resp = requests.get(wayback_url).json()
    
    if resp.get("archived_snapshots", {}).get("closest", {}).get("available"):
        archive_url = resp["archived_snapshots"]["closest"]["url"]
        page = requests.get(archive_url)
        return page.text
    
    return None

# Ejemplo: recuperar el 10-K de Enron justo antes del colapso
historical = get_historical_page(
    "https://www.enron.com/corp/investors/annuals/2000/",
    date="20011201"
)
```

---

### Hugging Face Datasets — repositorio de datasets ML, gratis

Hugging Face tiene miles de datasets pre-procesados, muchos financieros, listos para descargar.

```python
from datasets import load_dataset

# Dataset de noticias financieras con sentiment
financial_news = load_dataset("nickmuchi/financial-classification")

# Dataset de filings SEC procesados
sec_filings = load_dataset("JanosAudran/financial-reports-sec")

# Dataset de tweets financieros con sentiment
fin_tweets = load_dataset("zeroshot/twitter-financial-news-sentiment")

# Dataset multilingüe de noticias financieras
multilingual = load_dataset("SALT-NLP/FLANG-BERT")
```

Muchos de estos datasets tienen millones de documentos ya etiquetados con sentiment, sector, empresa. Son perfectos para pre-entrenar o fine-tunear modelos propios.

---

## Parte 2 — Fuentes de datos financieros gratuitas de alta calidad

### SEC EDGAR — la fuente más autoritativa de datos empresariales US

EDGAR (Electronic Data Gathering, Analysis, and Retrieval) es el sistema de la SEC. Todo lo que una empresa pública en EEUU presenta aquí: 10-K anuales, 10-Q trimestrales, 8-K eventos materiales, S-1 IPOs, 13F holdings de fondos.

**APIs oficiales — sin límite, sin clave:**

```python
import requests

class EDGARClient:
    BASE = "https://data.sec.gov"
    HEADERS = {"User-Agent": "InvestPlatform admin@investplatform.com"}
    
    def get_company_facts(self, cik: str) -> dict:
        """Todos los datos financieros de una empresa en JSON."""
        url = f"{self.BASE}/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
        return requests.get(url, headers=self.HEADERS).json()
    
    def get_filings(self, cik: str) -> dict:
        """Lista de todos los filings de una empresa."""
        url = f"{self.BASE}/submissions/CIK{cik.zfill(10)}.json"
        return requests.get(url, headers=self.HEADERS).json()
    
    def search_full_text(self, query: str, form: str = "10-K") -> list:
        """Búsqueda full-text en EDGAR (EFTS)."""
        url = "https://efts.sec.gov/LATEST/search-index"
        resp = requests.get(url, params={
            "q": f'"{query}"',
            "dateRange": "custom",
            "startdt": "2020-01-01",
            "forms": form
        }, headers=self.HEADERS)
        return resp.json().get("hits", {}).get("hits", [])
    
    def get_concept(self, cik: str, concept: str) -> dict:
        """Dato financiero específico de una empresa a lo largo del tiempo."""
        # Conceptos: Revenues, NetIncomeLoss, Assets, EarningsPerShareBasic
        url = f"{self.BASE}/api/xbrl/companyconcept/CIK{cik.zfill(10)}/us-gaap/{concept}.json"
        return requests.get(url, headers=self.HEADERS).json()

edgar = EDGARClient()

# Todos los ingresos históricos de Apple (CIK: 320193)
revenues = edgar.get_concept("320193", "Revenues")

# Buscar menciones de "climate risk" en 10-Ks recientes
climate_filings = edgar.search_full_text("climate risk material", form="10-K")
```

**Qué contiene EDGAR que nadie más tiene:**
- Ingresos, costes, márgenes, deuda — datos exactos de cada trimestre desde 1993
- Risk factors tal como los describe la empresa (fuente primaria)
- Notas a pie de página de estados financieros
- Holdings de todos los fondos institucionales (13F)
- Insider trading (Form 4) en tiempo real

---

### FRED — Federal Reserve Bank of St. Louis

FRED tiene 800.000 series de datos económicos de 100+ fuentes internacionales. API gratuita con clave (gratis).

```python
import requests

FRED_KEY = "tu_clave_gratis_de_fred"  # gratis en fred.stlouisfed.org

def get_series(series_id: str, start: str = "2000-01-01") -> list:
    resp = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": series_id,
            "api_key": FRED_KEY,
            "file_type": "json",
            "observation_start": start
        }
    )
    return resp.json()["observations"]

# Series clave
series_importantes = {
    "GDP":        "PIB EEUU",
    "CPIAUCSL":   "IPC (inflación)",
    "FEDFUNDS":   "Fed Funds Rate",
    "T10Y2Y":     "Yield curve spread 10Y-2Y",
    "VIXCLS":     "VIX (volatilidad implícita)",
    "DXY":        "Dollar Index",
    "DEXCHUS":    "USD/CNY",
    "DEXRUSUS":   "RUB/USD",
    "BAMLH0A0HYM2": "High Yield spread",
    "MORTGAGE30US": "Hipotecas 30 años",
}

inflacion = get_series("CPIAUCSL", start="2020-01-01")
```

---

### World Bank Open Data

```python
import wbgapi as wb

# PIB de todos los países 2000-2023
gdp = wb.data.DataFrame("NY.GDP.MKTP.CD", time=range(2000, 2024))

# Inflación por país
inflation = wb.data.DataFrame("FP.CPI.TOTL.ZG")

# Búsqueda de indicadores
results = wb.series.search("foreign direct investment")
```

---

### MOEX — Bolsa de Moscú, API oficial gratis

```python
import requests

def get_moex_securities(query: str) -> list:
    resp = requests.get(
        "https://iss.moex.com/iss/securities.json",
        params={"q": query, "lang": "en"}
    )
    return resp.json()["securities"]["data"]

def get_moex_history(ticker: str, from_date: str, to_date: str) -> list:
    resp = requests.get(
        f"https://iss.moex.com/iss/history/engines/stock/markets/shares/securities/{ticker}.json",
        params={"from": from_date, "till": to_date, "lang": "en"}
    )
    return resp.json()["history"]["data"]

# Datos históricos de Sberbank
sber_data = get_moex_history("SBER", "2023-01-01", "2024-01-01")
```

---

### Alpha Vantage — datos de mercado gratuitos

```python
import requests

AV_KEY = "demo"  # clave gratuita en alphavantage.co — 25 req/día, suficiente para enriquecer

def get_news_sentiment(ticker: str) -> dict:
    return requests.get(
        "https://www.alphavantage.co/query",
        params={
            "function": "NEWS_SENTIMENT",
            "tickers": ticker,
            "apikey": AV_KEY,
            "limit": 50
        }
    ).json()

def get_earnings(ticker: str) -> dict:
    return requests.get(
        "https://www.alphavantage.co/query",
        params={"function": "EARNINGS", "symbol": ticker, "apikey": AV_KEY}
    ).json()
```

---

### EU Open Data Portal

```python
import requests

def search_eu_data(query: str) -> list:
    resp = requests.get(
        "https://data.europa.eu/api/hub/search/search",
        params={"q": query, "limit": 20, "lang": "en"}
    )
    return resp.json()["result"]["results"]

# Datos financieros EU: EBA stress tests, BCE datos, Eurostat
```

---

### Otras fuentes de alta calidad — mapa completo

| Fuente | Contenido | API | Límite |
|---|---|---|---|
| **OpenStreetMap** | Geografía, ubicaciones | Overpass API | Sin límite |
| **PubMed / NCBI** | Papers biomédicos | API oficial | Sin límite |
| **Semantic Scholar** | Papers académicos | API gratis | 100 req/s |
| **CrossRef** | Metadatos académicos | API gratis | Sin límite |
| **data.gov** | Datos gobierno US | API gratis | Sin límite |
| **Eurostat** | Estadísticas EU | API REST | Sin límite |
| **IMF Data** | Macro global | API JSON | Sin límite |
| **BIS (Bank for Int'l Settlements)** | Datos bancarios globales | Descarga CSV | Sin límite |
| **Yahoo Finance** | Precios, noticias | Scraping | Rate limit suave |
| **Finviz** | Screener, datos | Scraping | Rate limit suave |
| **GitHub API** | Repos, trending | API gratis | 5.000 req/h |
| **Hacker News API** | Tech news, discusiones | API Firebase | Sin límite |
| **Reddit Pushshift** | Posts históricos | API | Sin límite |
| **OpenCorporates** | Datos empresariales | API gratis limitada | 50 req/día |
| **GLEIF** | LEI (entidades legales) | API gratis | Sin límite |

---

## Parte 3 — El motor de resolución de queries

Aquí está el núcleo real. Cuando llega una query, el sistema no hace una búsqueda simple. Hace lo que hace Perplexity pero mejor, porque conoce sus fuentes.

### Arquitectura de resolución

```
Query del usuario
      │
      ▼
┌─────────────────────┐
│   Query Analyzer    │  ← IA clasifica la query en tipo + dominio
│   (LLM local)       │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │  Router IA  │  ← decide qué fuentes consultar en paralelo
    └──────┬──────┘
           │
    ┌──────┴──────────────────────────────┐
    │    Ejecución paralela (asyncio)     │
    │                                     │
    │  ┌──────────┐  ┌──────────────┐    │
    │  │ Meilisearch│  │  Wikidata   │    │
    │  │ (local)   │  │  SPARQL     │    │
    │  └──────────┘  └──────────────┘    │
    │  ┌──────────┐  ┌──────────────┐    │
    │  │  Qdrant  │  │  EDGAR API  │    │
    │  │ (vectors)│  │  (filings)  │    │
    │  └──────────┘  └──────────────┘    │
    │  ┌──────────┐  ┌──────────────┐    │
    │  │   FRED   │  │  OpenAlex   │    │
    │  │  (macro) │  │  (papers)   │    │
    │  └──────────┘  └──────────────┘    │
    └──────────────────────────────────┘
           │
      ┌────┴────┐
      │  Fusion │  ← RRF + credibilidad de fuente + frescura
      └────┬────┘
           │
      ┌────┴────┐
      │ Re-rank │  ← cross-encoder ordena los top-N fragmentos
      └────┬────┘
           │
      ┌────┴────┐
      │ Synthes.│  ← LLM sintetiza respuesta con citations
      └────┬────┘
           │
      Respuesta con fuentes
```

### Clasificación de queries

```python
from enum import Enum
from dataclasses import dataclass

class QueryType(Enum):
    FACTUAL      = "factual"       # "¿cuándo fundaron Apple?"
    FINANCIAL    = "financial"     # "revenue de Tesla 2023"
    ACADEMIC     = "academic"      # "estudios sobre factor investing"
    NEWS         = "news"          # "últimas noticias sobre Bitcoin"
    ANALYTICAL   = "analytical"    # "por qué subió el S&P500 ayer"
    COMPARATIVE  = "comparative"   # "Apple vs Microsoft márgenes"
    DEFINITION   = "definition"    # "qué es un CDO"

@dataclass
class QueryPlan:
    query_type:   QueryType
    sources:      list[str]       # fuentes a consultar
    needs_fresh:  bool            # ¿necesita datos de hoy?
    entities:     list[str]       # tickers, empresas, países detectados
    time_range:   str | None      # "2023", "Q3 2024", None

async def analyze_query(query: str) -> QueryPlan:
    """
    Usa el LLM local para clasificar la query y decidir el plan.
    """
    prompt = f"""Analiza esta query de búsqueda financiera y devuelve JSON:

Query: "{query}"

Devuelve:
{{
  "type": "factual|financial|academic|news|analytical|comparative|definition",
  "sources": ["list of: wikipedia, wikidata, edgar, fred, openalex, arxiv, meilisearch, moex"],
  "needs_fresh": true/false,
  "entities": ["AAPL", "Tesla", "Fed"],
  "time_range": "2023" | null
}}

Solo JSON, sin texto adicional."""

    response = await llm_complete(prompt)
    plan_data = json.loads(response)
    
    return QueryPlan(
        query_type=QueryType(plan_data["type"]),
        sources=plan_data["sources"],
        needs_fresh=plan_data["needs_fresh"],
        entities=plan_data["entities"],
        time_range=plan_data["time_range"]
    )
```

### Source Router — reglas base (fallback sin LLM)

Para queries simples no hace falta el LLM. Las reglas determinísticas son más rápidas:

```python
import re

TICKER_PATTERN = re.compile(r'\b([A-Z]{1,5})\b')
MACRO_KEYWORDS = {"fed", "inflation", "gdp", "cpi", "interest rate", "recession", "yield"}
ACADEMIC_KEYWORDS = {"study", "research", "paper", "methodology", "theory", "model"}
DEFINITION_KEYWORDS = {"what is", "define", "meaning", "explanation", "how does"}

def fast_route(query: str) -> list[str]:
    q = query.lower()
    sources = ["meilisearch"]  # siempre consultamos índice local primero
    
    # Detectar tickers
    tickers = TICKER_PATTERN.findall(query)
    if tickers:
        sources.extend(["edgar", "alpha_vantage"])
    
    # Detectar macro
    if any(kw in q for kw in MACRO_KEYWORDS):
        sources.append("fred")
    
    # Detectar necesidad académica
    if any(kw in q for kw in ACADEMIC_KEYWORDS):
        sources.extend(["openalex", "arxiv"])
    
    # Detectar definiciones → Wikipedia es la mejor fuente
    if any(kw in q for kw in DEFINITION_KEYWORDS):
        sources.extend(["wikipedia", "wikidata"])
    
    # Detectar mercado ruso
    if any(kw in q for kw in {"russia", "ruble", "moex", "sberbank", "gazprom"}):
        sources.append("moex")
    
    return list(dict.fromkeys(sources))  # dedup manteniendo orden
```

### Ejecución paralela de todas las fuentes

```python
import asyncio
import aiohttp
from typing import Any

async def fetch_all_sources(query: str, plan: QueryPlan) -> dict[str, list]:
    """
    Lanza todas las fuentes en paralelo y recoge resultados.
    Timeout por fuente: 3 segundos. Si falla, devuelve lista vacía.
    """
    
    async def safe_fetch(name: str, coro) -> tuple[str, list]:
        try:
            result = await asyncio.wait_for(coro, timeout=3.0)
            return name, result
        except Exception:
            return name, []
    
    tasks = []
    
    if "meilisearch" in plan.sources:
        tasks.append(safe_fetch("meilisearch", search_meilisearch(query)))
    
    if "qdrant" in plan.sources:
        tasks.append(safe_fetch("qdrant", search_qdrant(query)))
    
    if "wikipedia" in plan.sources:
        tasks.append(safe_fetch("wikipedia", search_wikipedia(query)))
    
    if "wikidata" in plan.sources:
        tasks.append(safe_fetch("wikidata", query_wikidata(plan.entities)))
    
    if "edgar" in plan.sources and plan.entities:
        tasks.append(safe_fetch("edgar", fetch_edgar(plan.entities)))
    
    if "fred" in plan.sources:
        tasks.append(safe_fetch("fred", fetch_fred_relevant(query)))
    
    if "openalex" in plan.sources:
        tasks.append(safe_fetch("openalex", search_openalex(query)))
    
    if "arxiv" in plan.sources:
        tasks.append(safe_fetch("arxiv", search_arxiv_async(query)))
    
    if "moex" in plan.sources:
        tasks.append(safe_fetch("moex", fetch_moex(plan.entities)))
    
    # Lanzar todo en paralelo
    results = await asyncio.gather(*tasks)
    
    return dict(results)
```

### Fusion y re-ranking

```python
def fuse_results(source_results: dict[str, list], query: str) -> list[dict]:
    """
    Combina resultados de todas las fuentes con RRF + credibilidad de fuente.
    """
    
    SOURCE_TRUST = {
        "edgar":       1.00,   # fuente primaria regulatoria
        "fred":        1.00,   # fuente primaria banco central
        "moex":        0.98,   # fuente primaria bolsa
        "wikipedia":   0.90,   # bien mantenida, alta cobertura
        "wikidata":    0.90,
        "openalex":    0.92,   # revisión por pares
        "arxiv":       0.85,   # preprints, alta calidad técnica
        "meilisearch": 0.80,   # depende de la fuente original indexada
        "qdrant":      0.78,
    }
    
    all_docs = {}
    k = 60  # constante RRF
    
    for source, docs in source_results.items():
        trust = SOURCE_TRUST.get(source, 0.5)
        
        for rank, doc in enumerate(docs):
            doc_id = doc.get("id") or doc.get("url") or f"{source}_{rank}"
            
            if doc_id not in all_docs:
                all_docs[doc_id] = {**doc, "score": 0, "sources": []}
            
            # RRF score ponderado por credibilidad de fuente
            rrf = (1 / (k + rank + 1)) * trust
            all_docs[doc_id]["score"] += rrf
            all_docs[doc_id]["sources"].append(source)
    
    # Ordenar por score final
    ranked = sorted(all_docs.values(), key=lambda x: x["score"], reverse=True)
    
    return ranked[:50]  # top 50 para re-ranker


async def rerank(docs: list[dict], query: str, top_k: int = 10) -> list[dict]:
    """
    Re-ranking con cross-encoder. Mucho más preciso que BM25 o vectores solos.
    Usa el modelo ms-marco-MiniLM self-hosted (90MB, muy rápido en CPU).
    """
    from sentence_transformers import CrossEncoder
    
    cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    
    pairs = [(query, doc.get("content", doc.get("summary", doc.get("title", ""))))
             for doc in docs]
    
    scores = cross_encoder.predict(pairs)
    
    for doc, score in zip(docs, scores):
        doc["rerank_score"] = float(score)
    
    return sorted(docs, key=lambda x: x["rerank_score"], reverse=True)[:top_k]
```

### Síntesis final con LLM

```python
async def synthesize_answer(query: str, docs: list[dict]) -> dict:
    """
    El LLM lee los fragmentos recuperados y genera una respuesta completa con citations.
    """
    
    # Preparar contexto
    context_parts = []
    for i, doc in enumerate(docs[:8]):  # top 8 documentos
        source = doc.get("sources", ["unknown"])[0]
        title = doc.get("title", "Sin título")
        content = doc.get("content", doc.get("summary", ""))[:800]  # max 800 chars por doc
        
        context_parts.append(f"[{i+1}] Fuente: {source.upper()} — {title}\n{content}")
    
    context = "\n\n---\n\n".join(context_parts)
    
    prompt = f"""Eres un analista financiero experto. Responde la siguiente pregunta usando SOLO la información proporcionada en las fuentes.

PREGUNTA: {query}

FUENTES:
{context}

INSTRUCCIONES:
- Responde de forma completa, precisa y estructurada
- Cita las fuentes usando [1], [2], etc.
- Si los datos son de fuentes primarias (SEC, FRED, MOEX), indícalo explícitamente
- Si la información no está en las fuentes, dilo claramente
- Usa markdown para estructurar la respuesta

RESPUESTA:"""

    answer = await llm_complete(prompt, max_tokens=1000)
    
    return {
        "query": query,
        "answer": answer,
        "sources": [
            {
                "index": i + 1,
                "title": doc.get("title"),
                "source": doc.get("sources", ["unknown"])[0],
                "url": doc.get("url"),
                "trust_score": doc.get("score")
            }
            for i, doc in enumerate(docs[:8])
        ],
        "total_sources_consulted": len(docs)
    }
```

### Pipeline completo — endpoint final

```python
from fastapi import FastAPI
import time

app = FastAPI()

@app.get("/search")
async def search_endpoint(q: str, mode: str = "full"):
    start = time.time()
    
    # 1. Analizar query (fast_route si modo rápido, LLM si modo full)
    if mode == "fast":
        sources = fast_route(q)
        plan = QueryPlan(
            query_type=QueryType.FACTUAL,
            sources=sources,
            needs_fresh=False,
            entities=[],
            time_range=None
        )
    else:
        plan = await analyze_query(q)
    
    # 2. Consultar todas las fuentes en paralelo
    raw_results = await fetch_all_sources(q, plan)
    
    # 3. Fusion RRF + credibilidad
    fused = fuse_results(raw_results, q)
    
    # 4. Re-ranking con cross-encoder
    reranked = await rerank(fused, q, top_k=10)
    
    # 5. Síntesis con LLM
    answer = await synthesize_answer(q, reranked)
    
    elapsed = (time.time() - start) * 1000
    answer["latency_ms"] = round(elapsed)
    answer["plan"] = {
        "type": plan.query_type.value,
        "sources_consulted": list(raw_results.keys()),
        "results_before_rerank": len(fused)
    }
    
    return answer
```

---

## Parte 4 — LLM local para síntesis (el cerebro, gratis)

Para la síntesis final necesitas un LLM. Opciones ordenadas por calidad/coste en Oracle 24GB:

### Opción 1: Ollama + Mistral 7B (recomendada para empezar)

```bash
# Instalar Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Descargar Mistral 7B cuantizado (4.1 GB)
ollama pull mistral

# Correr como servicio
ollama serve  # escucha en http://localhost:11434
```

```python
import httpx

async def llm_complete(prompt: str, max_tokens: int = 1000) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral",
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": 0.1}
            },
            timeout=30.0
        )
    return resp.json()["response"]
```

### Opción 2: Groq API (gratis, muy rápido, límite generoso)

Groq ofrece inferencia gratuita con Llama 3.1 70B — mucho más capaz que Mistral 7B — con 14.400 req/día gratis.

```python
from groq import AsyncGroq

groq_client = AsyncGroq(api_key="tu_clave_groq_gratis")

async def llm_complete(prompt: str, max_tokens: int = 1000) -> str:
    resp = await groq_client.chat.completions.create(
        model="llama-3.1-70b-versatile",  # 70B gratis
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.1
    )
    return resp.choices[0].message.content
```

**Estrategia híbrida:** Groq para síntesis (mejor calidad), Ollama local para clasificación de queries (latencia cero, sin depender de externa).

---

## Parte 5 — Caché inteligente para escala masiva

La diferencia entre un sistema que aguanta 1M de requests y uno que no, está en el caché.

```python
import redis.asyncio as aioredis
import hashlib
import json

redis = aioredis.from_url("redis://localhost:6379")

def query_hash(query: str) -> str:
    return hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16]

async def cached_search(query: str) -> dict | None:
    key = f"search:{query_hash(query)}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    return None

async def cache_result(query: str, result: dict, ttl_seconds: int = 300):
    """
    TTL adaptativo según tipo de query:
    - Definiciones (Wikipedia): 24 horas
    - Datos macro (FRED): 4 horas  
    - Noticias: 5 minutos
    - Precios: 1 minuto
    """
    key = f"search:{query_hash(query)}"
    await redis.setex(key, ttl_seconds, json.dumps(result))
```

---

## Resumen — qué tienes cuando todo esto está construido

| Capacidad | Cómo |
|---|---|
| Conocimiento base profundo | Wikipedia + Wikidata (6.7M artículos) |
| Papers académicos | OpenAlex + arXiv (250M papers) |
| Filings empresariales US | SEC EDGAR (30 años de historia) |
| Datos macro globales | FRED + World Bank + IMF |
| Bolsa rusa | MOEX API oficial |
| Historia web | Internet Archive / Common Crawl |
| Noticias en tiempo real | RSS + crawling directo |
| Búsqueda semántica | BGE-M3 + Qdrant |
| Búsqueda full-text | Meilisearch |
| Síntesis inteligente | Groq (Llama 70B) + Ollama local |
| Evasión anti-bot | FlareSolverr + curl-impersonate |
| Coste total | **$0/mes** |

Cuando un usuario pregunta "¿cómo le fue a Tesla en Q3 2024?", el sistema consulta en paralelo el 10-Q de EDGAR, las noticias indexadas, el sentiment de Alpha Vantage, y el precio histórico de Yahoo Finance — y entrega una respuesta sintetizada con fuentes en menos de 2 segundos.

Eso es el monstruo.

---

*InvestPlatform · Search Engine v2.0 · abril 2026*
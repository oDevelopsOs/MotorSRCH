# Guía 2026: Scraper masivo anti-Cloudflare + backend para IA (100 % headless, sin frontend)

**Plataforma:** Go (backend principal) + Python (processor / scraping) | Podman (dev) | Docker (prod)

**Fecha:** 19 de abril de 2026

Investigación orientada solo a **backend / API / librerías**: sin productos tipo UI (Vane, Scraperr, dashboards Next.js, etc.). Todo **self-hosted**, Docker/Podman, pensado para competir con Perplexity por **inteligencia** (extracción con LLM, no brute-force de HTML basura).

**Por qué encajan mejor que stacks genéricos:**

- Buena evasión nativa (Cloudflare, Akamai, etc., según herramienta).
- Salidas **LLM-ready** (Markdown limpio, JSON estructurado, acciones cuando aplica).
- Diseño **microservicio**: los invocas desde Go por **HTTP** o SDK.
- Escalado horizontal sin capa de presentación.

---

## 1. Resumen de proyectos (solo backend 2026)

| Proyecto | Stars (aprox.) | Lenguaje | Anti-Cloudflare | LLM-ready + inteligencia | Integración con tu stack | Notas |
|----------|------------------|----------|-----------------|----------------------------|---------------------------|-------|
| **Firecrawl** | ~111k | Python (API) | ★★★★☆ (proxies + JS) | ★★★★★ (markdown, JSON, acciones) | SDK Go oficial + Python SDK; HTTP `/v1/scrape` | Muy encajado si quieres **Go SDK** contra tu API self-hosted |
| **Crawl4AI** | ~64k | Python (FastAPI) | ★★★★★ (stealth, undetected, proxies) | ★★★★★ (Markdown, `LLMExtractionStrategy`, chunking) | Librería Python o **HTTP** `POST /crawl` (fácil desde Go) | **Máxima evasión**; en este repo el **crawler ya llama por HTTP** |
| **Crawlee** | ~23k | Python + JS | ★★★★★ (fingerprints, proxies) | ★★★★☆ (pipeline hacia RAG/LLM) | Librería → tu microservicio FastAPI | Máxima flexibilidad; tú envuelves la librería |
| **FlareSolverr** | ~13.5k | Python | ★★★★★ (bypass dedicado) | No (HTML crudo) | HTTP `POST /v1` → cualquier flujo | **Fallback** para casos duros |

**Fuentes oficiales:**

- Firecrawl → <https://github.com/firecrawl/firecrawl>
- Crawl4AI → <https://github.com/unclecode/crawl4ai>
- Crawlee → <https://github.com/apify/crawlee> (ecosistema; hay bindings Python)
- FlareSolverr → <https://github.com/FlareSolverr/FlareSolverr>

### Stack recomendado (0 €, “pequeño pero listo”)

```
Go (crawler + API de búsqueda) → HTTP → Firecrawl y/o Crawl4AI (microservicios)
        → FlareSolverr si hace falta
        → Ollama (extracción / prompts)
        → PostgreSQL + vector store (Qdrant en este monorepo) + Meilisearch
```

Prioridad práctica en **MotorDeBusqueda**: Firecrawl opcional vía **SDK Go** (`FIRECRAWL_*`) + Crawl4AI vía HTTP (`CRAWL4AI_*`) + FlareSolverr; ver [`crawler/main.go`](crawler/main.go) y [`integrations/anti-cloudflare-acquisition.md`](integrations/anti-cloudflare-acquisition.md).

---

## 2. Instalación Podman (dev) / Docker (prod)

Todo como contenedor **headless** (sin interfaz de producto). En este repo, **Crawl4AI** y **FlareSolverr** van **sin publicar puerto al host** en [`docker-compose.yml`](docker-compose.yml): solo red Docker (`http://crawl4ai:11235`, `http://flaresolverr:8191`).

### 2.1 Firecrawl (API)

El self-hosting oficial suele ser **`docker compose` en el repo** (varios servicios: API, Redis, Playwright, etc.). No dependas de una sola línea genérica sin revisar [SELF_HOST.md](https://github.com/mendableai/firecrawl/blob/main/SELF_HOST.md) y etiquetas GHCR actuales. Resumen en este repo: [`integrations/firecrawl.md`](integrations/firecrawl.md).

Ejemplo ilustrativo (ajusta imagen / build según la doc oficial del momento):

```yaml
# docker-compose.firecrawl.yml (referencia; validar contra el repo firecrawl)
services:
  firecrawl-api:
    # Suele ser build: apps/api o imagen publicada; ver documentación vigente
    ports:
      - "3002:3002"
    environment:
      # Variables mínimas según SELF_HOST.md
      PORT: "3002"
    shm_size: 1g
```

`podman compose -f docker-compose.firecrawl.yml up -d`

### 2.2 Crawl4AI (FastAPI embebida en la imagen)

En **MotorDeBusqueda** el servicio `crawl4ai` ya está definido; la imagen ejecuta el servidor de API **sin UI en tu producto** (navegación headless dentro del contenedor). No hace falta exponer `11235` al host salvo depuración.

Ejemplo mínimo standalone (si quisieras otro archivo):

```yaml
services:
  crawl4ai:
    image: unclecode/crawl4ai:latest
    ports:
      - "11235:11235"   # opcional: solo en dev; en este monorepo se omite a propósito
    shm_size: 1g
```

API: `POST http://crawl4ai:11235/crawl` (desde otros contenedores).

### 2.3 Crawlee (como microservicio tuyo)

Crawlee es **librería**: típicamente un **FastAPI** pequeño que importa Crawlee/Crawlee Python y expone `POST /crawl`. No viene como imagen única “oficial” del mismo modo que Crawl4AI; lo integras tú en `./processor` o un servicio nuevo.

### 2.4 FlareSolverr (bypass)

Mismo patrón: en este monorepo **sin publicar 8191** al host; el crawler usa `http://flaresolverr:8191/v1`.

---

## 3. Integración Go + Python

### Opción A — Firecrawl (limpia para Go): SDK o HTTP

El SDK de referencia histórico es `github.com/mendableai/firecrawl-go/v2` (`NewFirecrawlApp(apiKey, apiBaseURL)`). Comprueba en el repo de Firecrawl si han movido el paquete a `apps/go-sdk` y usa la ruta que indique el README actual.

Ejemplo conceptual (self-hosted, clave vacía o dummy si tu instancia no exige auth):

```go
package scraper

import (
    "context"
    "github.com/mendableai/firecrawl-go/v2"
)

func ScrapeWithFirecrawl(baseURL, apiKey, target string) (string, error) {
    app, err := firecrawl.NewFirecrawlApp(apiKey, baseURL)
    if err != nil {
        return "", err
    }
    out, err := app.ScrapeURL(target, nil)
    if err != nil {
        return "", err
    }
    if out == nil {
        return "", nil
    }
    return out.Markdown, nil
}
```

En **este repo** el crawler usa **solo el SDK Go** `github.com/mendableai/firecrawl-go/v2` (dependencia directa) cuando `FIRECRAWL_URL` está definido; si la clave va vacía se usa `dummy` (típico en self-host sin auth). Si `FIRECRAWL_URL` está vacío, no se carga el cliente Firecrawl.

Ver `fetchFirecrawl` / `fetchFirecrawlSDK` en [`crawler/main.go`](crawler/main.go).

### Opción B — Crawl4AI (máxima evasión)

- **Microservicio** ya levantado → desde Go `http.Post` a `/crawl` (implementado en el crawler).
- **In-process Python** (processor u otro worker):

```python
from crawl4ai import AsyncWebCrawler

async def scrape(url: str):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, bypass_cloudflare=True)
        return result.markdown
```

### Opción C — Crawlee (personalización)

```python
from fastapi import FastAPI
# from crawlee.playwright import ...  # según paquete Python que uses

app = FastAPI()

@app.post("/crawl")
async def crawl(url: str):
    # lógica masiva + rate limit + reintentos + opcional paso LLM (Ollama)
    ...
```

---

## 4. Instrucciones exactas para tu IA (copiar y pegar)

> Eres mi asistente para integrar scrapers masivos en un backend **Go + Python**. El usuario **no quiere frontend**: todo headless, microservicios Docker/Podman.
>
> Stack: **Go** como proceso principal (crawler + API de búsqueda), **Python** para processor y scraping pesado.
>
> Usa siempre:
>
> - **Firecrawl** (SDK Go o HTTP) o **Crawl4AI** (HTTP o FastAPI) como scraper principal.
> - **FlareSolverr** como fallback (`http://flaresolverr:8191`).
> - **Ollama** para extracción inteligente (prompts RAG / JSON).
> - Podman en dev, Docker en prod.
>
> Genera: `docker-compose` coherente, código Go cliente (HTTP o SDK), microservicio Python mínimo si hace falta (Crawlee), prompts LLM para extracción fina, y patrón de **rate limit + reintentos** en crawling masivo.
>
> Prioridad: **inteligencia > escala**; extraer solo datos relevantes con LLM.

---

## 5. Motores de búsqueda IA headless (top 2026, solo backend)

Comparativa de proyectos pensados como **API** (sin depender de una SPA como producto propio). En **MotorDeBusqueda** tu “cerebro” sigue siendo **FastAPI + crawler + Ollama + vector DB**; estas piezas pueden **sustituir o enriquecer** partes del pipeline.

| Motor | Tipo | Potencia vs Perplexity (orientativo) | Integración Go/Python | Docker/Podman |
|-------|------|--------------------------------------|------------------------|---------------|
| **Firecrawl Agent** | API de agente (investigación autónoma) | Muy alta (multi-paso, navegación) | API HTTP / SDK cloud; **no** el mismo paquete que `ScrapeURL` en self-host | Depende del modo |
| **OpenPerplex Backend** | API Python de búsqueda + LLM + citas | Alta (respuestas con fuentes) | Python nativo + **HTTP desde Go** | Según repo |
| **Vane API** | App con API expuesta (ex-Perplexica) | Media–alta (SearxNG + Ollama) | HTTP desde Go | Sí (p. ej. imagen slim) |

**Por qué compiten en “inteligencia” siendo ligeros:** combinan scraping/recuperación en tiempo razonable con **LLM** para filtrar y estructurar (no volcados masivos de basura), y con **Ollama** local mantienes coste cero y control de prompts.

### 5.1 Firecrawl Agent (recomendación típica #1 en cloud)

En la **API cloud** de Firecrawl, el endpoint de **Agent** permite flujos tipo “investiga esto en la web” con pasos autónomos. Documentación: [Firecrawl docs](https://docs.firecrawl.dev) (sección Agent / autonomous research).

**Limitación importante (self-host):** según la [documentación de self-hosting](https://docs.firecrawl.dev/contributing/self-host), **`/agent` y `/browser` no están soportados** en instancias self-hosted al mismo nivel que en cloud. Tu despliegue local con `docker compose` en el repo de Firecrawl suele cubrir **scrape / crawl**; para Agent en práctica suele usarse **API key + URL cloud** o esperar evolución del proyecto self-hosted.

El SDK Go **`github.com/mendableai/firecrawl-go/v2`** (el que usa este repo para scrape) expone **`ScrapeURL` / `CrawlURL`**, no un método `Agent` en la versión empaquetada en el crawler. Para Agent, la **API FastAPI** de este monorepo expone ya **`POST /brain/firecrawl/agent`**, **`GET /brain/firecrawl/agent/{id}`** y **`POST /brain/firecrawl/agent/sync`** (cliente HTTP en [`api/app/brain.py`](api/app/brain.py)), usando `FIRECRAWL_AGENT_API_KEY` y `FIRECRAWL_AGENT_BASE_URL`.

**Combinación con este monorepo:** usa Agent (si tu cuenta/API lo permite) para **preguntas abiertas multi-sitio**, y mantén **Crawl4AI + FlareSolverr** en el crawler para **ingesta masiva** y dominios difíciles. Además puedes combinarlo con la búsqueda local en un solo request: `GET /resolve?q=...&brain_boost=firecrawl_agent` (también `openperplex` o `vane`); la respuesta incluye `results` locales y la clave `brain_boost`.

### 5.2 OpenPerplex Backend (motor Python “puro backend”)

- Repositorio: <https://github.com/YassKhazzan/openperplex_backend_os>
- Enfoque: API de búsqueda tipo Perplexity (web + LLM + citas), sin frontend obligatorio en tu arquitectura.
- **Integración en MotorDeBusqueda:** proxy SSE `GET /brain/openperplex/search` → `OPENPERPLEX_URL/search`. Detalle: [`integrations/openperplex.md`](integrations/openperplex.md).

### 5.3 Vane API (opcional, “todo en uno” con API usable)

- Repositorio: <https://github.com/ItzCrazyKns/Vane>
- Incluye UI en el producto upstream; puedes desplegar solo lo necesario y consumir la **API documentada** (p. ej. búsqueda) desde Go **sin usar su interfaz**. Ver rutas en la documentación del repo (`/docs/...`).
- **Integración en MotorDeBusqueda:** `GET /brain/vane/search?q=...` con `VANE_API_URL` y `VANE_SEARCH_PATH` (por defecto `api/search`; ajusta según tu despliegue).
- Úsalo solo si aceptas operar ese servicio adicional; **no es requisito** para MotorDeBusqueda.

---

## 6. Instrucciones para tu IA — motor tipo Perplexity (copiar y pegar)

> Estás construyendo un motor de búsqueda IA tipo Perplexity, **100 % backend / headless**.
>
> El usuario usa **Go** (API principal) + **Python** (scraping pesado). Podman en dev, Docker en prod. Prioridad: **inteligencia** (agente autónomo donde exista API, extracción LLM, citas).
>
> Ten en cuenta:
>
> - **Firecrawl Agent** (puerto/API según doc) como motor principal **solo si la API lo permite** (cloud vs self-host); en self-host revisar limitaciones de `/agent`.
> - **OpenPerplex Backend** o **Vane API** como alternativas HTTP.
> - **Ollama** para razonamiento final o síntesis.
> - **Crawl4AI / FlareSolverr** como fallback de scraping masivo (como en este repo).
>
> Genera: `docker-compose` del servicio elegido, cliente Go (structs + funciones), wrapper Python si aplica, prompts para deep research con citas, y cómo combinarlo con un crawler NSQ + processor ya existente.

---

## 7. Próximos pasos

1. Levantar el stack del monorepo: `podman compose up --build -d` (Crawl4AI + FlareSolverr ya integrados en red interna).
2. Opcional: desplegar Firecrawl según [`integrations/firecrawl.md`](integrations/firecrawl.md) y rellenar `FIRECRAWL_URL` / `FIRECRAWL_DOMAINS`.
3. Configurar **Ollama** (`--profile ollama`) y `OLLAMA_URL` en la API para síntesis / planificación.
4. Afinar **CRAWL4AI_DOMAINS** / **FLARE_DOMAINS** por sitio (evasión vs coste).
5. Si quieres **Agent** de Firecrawl: confirmar en la doc si usas **cloud API** o qué soporta tu build self-hosted; integrar con HTTP desde la API de este repo, no asumir métodos inexistentes en el SDK de scrape.

---

## Referencia: FlareSolverr, ACLED y capa de adquisición

Estrategia anti-Cloudflare alineada con el crawler (`FLARE_DOMAINS`, orden de fallbacks, notas legales/API) y extensiones opcionales (Camoufox, etc.): [**`integrations/anti-cloudflare-acquisition.md`**](integrations/anti-cloudflare-acquisition.md).

---

*Documento alineado con MotorDeBusqueda: backend único, scrapers como dependencias de red, sin capa de UI de producto (abril 2026).*

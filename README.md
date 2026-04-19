# Motor de búsqueda F1

Monorepo según `PLAN_DE_TRABAJO.md`: crawler (Go), processor (Python), API (FastAPI), Meilisearch, Qdrant, Redis, **NSQ** (topic `raw_pages` entre crawler y processor), FlareSolverr, **Crawl4AI** (HTTP interno), PostgreSQL, NGINX. Opcional: **Ollama** (`--profile ollama`), **SearXNG** (`--profile searxng`, capa web principal en `/resolve` con `SEARXNG_AS_PRIMARY=1` por defecto: índice local + meta-motores, sin APIs wiki/OpenAlex directas), **Camoufox bridge** (`--profile camoufox`, Firefox anti-fingerprint para el crawler vía `CAMOUFOX_URL`), **nsqadmin** (`--profile nsqadmin`, UI en puerto 4171) y **Firecrawl** auto-alojado con **SDK Go obligatorio** si configuras `FIRECRAWL_URL` (véase [`integrations/firecrawl.md`](integrations/firecrawl.md)). **Scrappey** y proxies HTTP (`COLLY_HTTP_PROXY` / `CURL_HTTP_PROXY`) se configuran por variables, sin servicio extra en el compose. Orden de capas: [`integrations/acquisition-stack.md`](integrations/acquisition-stack.md).

## Docker (recomendado: VPS, CI y desarrollo)

El mismo [`docker-compose.yml`](docker-compose.yml) es el formato estándar de **Docker Compose** (`docker compose`). En un **VPS Linux** instala [Docker Engine](https://docs.docker.com/engine/install/) y usa:

```bash
cp .env.example .env   # edita secretos
docker compose --profile searxng up -d --build
```

Producción (puertos internos cerrados, etc.): ver [`state.md` §9](state.md) y fusiona [`docker-compose.prod.yml`](docker-compose.prod.yml):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile searxng up -d --build
```

En **Windows** con Docker Desktop, el arranque rápido es [`scripts/start-all.ps1`](scripts/start-all.ps1) (usa **Docker** si el demonio responde).

### Podman (opcional, sobre todo dev local sin Docker)

Si no usas Docker Desktop y trabajas con Podman en Windows: `podman machine start`, luego `podman compose up --build -d`, o [`scripts/dev-podman.ps1`](scripts/dev-podman.ps1), o `.\scripts\start-all.ps1 -UsePodman`. En algunos entornos `podman compose` delega en el binario `docker-compose.exe` como proveedor de Compose.

**Nota:** en servidor/producción el flujo previsto es **Docker Engine**, no Podman.

### Render.com (Blueprint)

En la raíz hay un [`render.yaml`](render.yaml) (Postgres, Redis, Meilisearch y Qdrant como *private services*, API como *Web Service*, processor como *Worker*). **No** replica todo el `docker-compose` (sin NSQ/crawler/SearXNG/nginx). Detalle y limitaciones: comentarios al inicio del YAML y [`state.md` §9–10](state.md).

## Superficie HTTP (producto)

Lo que debe consumir un cliente externo es solo la **API** (y NGINX delante). Crawl4AI y FlareSolverr **no publican puertos al host** en este compose: el crawler los llama por nombre de servicio dentro de la red Docker (`http://crawl4ai:11235`, `http://flaresolverr:8191`).

| URL | Descripción |
|-----|-------------|
| `http://localhost:8000/health` | API de búsqueda |
| `http://localhost:8000/search?q=markets&limit=10` | Búsqueda híbrida |
| `http://localhost:8888/search?q=markets` | Misma API vía NGINX (caché + rate limit) |
| `http://localhost:8081/health` | Processor (ingesta vía `nsq_to_http` → `POST /internal/ingest`) |
| `POST /brain/firecrawl/agent` | Inicia tarea **Firecrawl Agent** (cloud API v2); requiere `FIRECRAWL_AGENT_API_KEY` |
| `POST /brain/firecrawl/agent/sync` | Igual que arriba + polling hasta resultado (investigación autónoma) |
| `GET /brain/openperplex/search` | Proxy SSE → OpenPerplex (`OPENPERPLEX_URL`) |
| `GET /brain/vane/search` | Proxy → API de búsqueda Vane (`VANE_API_URL` + `VANE_SEARCH_PATH`) |
| `GET /brain/searxng/search?q=...` | JSON crudo de **SearXNG** (`ENABLE_SEARXNG=1`, `SEARXNG_URL`) |
| `GET /resolve?...&brain_boost=firecrawl_agent` | Igual que `/resolve` local + resultado de **Firecrawl Agent** en `brain_boost` |
| `GET /resolve?...&brain_boost=openperplex` | Local + texto SSE de OpenPerplex (hasta ~80k chars) |
| `GET /resolve?...&brain_boost=vane` | Local + JSON de la API Vane |

Parámetros opcionales: `brain_max_wait_sec`, `openperplex_date_context`, `openperplex_stored_location`, `openperplex_pro_mode`.

El servicio `nsq_to_http` reenvía el topic NSQ `raw_pages` al processor.

## Variables útiles

| Variable | Descripción |
|----------|-------------|
| `ENABLE_EMBEDDINGS` / `ENABLE_FINBERT` / `ENABLE_TRANSLATION` | Modelos pesados en el processor (por defecto FinBERT y traducción desactivados) |
| `CRAWL_INTERVAL_MINUTES` | Si es `>0`, el crawler repite el lote de seeds cada N minutos (por defecto una sola pasada) |
| `FLARE_DOMAINS` | Hostnames que deben obtenerse vía FlareSolverr (separados por comas) |
| `CAMOUFOX_URL` / `CAMOUFOX_DOMAINS` / `CAMOUFOX_BRIDGE_TOKEN` | Puente Camoufox (perfil `camoufox`); ver [`integrations/camoufox-bridge.md`](integrations/camoufox-bridge.md). |
| `SCRAPPEY_API_KEY` / `SCRAPPEY_DOMAINS` / `SCRAPPEY_URL` | API gestionada Scrappey; ver [`integrations/scrappey.md`](integrations/scrappey.md). |
| `COLLY_HTTP_PROXY` / `CURL_HTTP_PROXY` | Proxy HTTP(S) opcional para Colly y curl-impersonate (rotación / datacenter). |
| `CRAWL4AI_URL` / `CRAWL4AI_DOMAINS` | URL interna del servicio (por defecto `http://crawl4ai:11235`) y dominios a enrutar ahí (`*` = todos). Vacío = el crawler no usa Crawl4AI. |
| `FIRECRAWL_URL` / `FIRECRAWL_API_KEY` / `FIRECRAWL_DOMAINS` | Firecrawl self-host (opcional): el crawler usa **solo** el SDK `github.com/mendableai/firecrawl-go/v2` si `FIRECRAWL_URL` no está vacío; ver [`integrations/firecrawl.md`](integrations/firecrawl.md). |
| `FIRECRAWL_AGENT_API_KEY` | Clave para **Agent** (API cloud v2); usada por rutas `/brain/firecrawl/*` en la API FastAPI. |
| `OPENPERPLEX_URL` | Base URL del backend OpenPerplex si usas el proxy [`integrations/openperplex.md`](integrations/openperplex.md). |
| `VANE_API_URL` | Base URL del servicio Vane (solo llamadas HTTP a su API). |
| `ENABLE_SEARXNG` / `SEARXNG_URL` / `SEARXNG_MAX_RESULTS` | Activa la fuente **searxng** en `/resolve` (fusión RRF) y el proxy `/brain/searxng/search`. Con compose: `SEARXNG_URL=http://searxng:8080`. |
| `ENABLE_SEARXNG_DECOMPOSITION` / `SEARXNG_SUBQUERY_TIMEOUT` | Por defecto **1**: varias sub-búsquedas SearXNG (general/news/science/it) en paralelo vía `api/app/query_decomposer.py`. Motores: `searxng/settings.yml`. |
| `SEARXNG_AS_PRIMARY` | Por defecto **1**: `/resolve` no usa APIs directas Wikipedia/OpenAlex/Wikidata; descubrimiento web vía SearXNG + índice local (crawler). `0` = modo híbrido con esas APIs. |

Perfil **searxng** (SearXNG en `http://localhost:8088` en el host; la API en Docker usa `http://searxng:8080`):

```bash
docker compose --profile searxng up -d
```

Perfil **camoufox** (construcción pesada la primera vez: descarga del binario Camoufox):

```bash
docker compose --profile camoufox up -d --build
```

Perfil **ollama** (LLM local para la API o para prompts avanzados en Crawl4AI con `.llm.env` propio del contenedor):

```bash
docker compose --profile ollama up -d
```

Perfil **nsqadmin** (interfaz web para inspeccionar topics/canales NSQ en `http://localhost:4171`):

```bash
docker compose --profile nsqadmin up -d
```

Las imágenes instalan **PyTorch CPU** para contenedores más ligeros en desarrollo. La primera ejecución puede tardar (descarga de modelos Hugging Face); el volumen `hf_cache` cachea modelos entre reinicios.

## Verificación antes de servidor o VPN

1. Copia y edita [`.env.example`](.env.example): cambia **`POSTGRES_PASSWORD`** y **`MEILI_MASTER_KEY`** en producción; si quieres `/resolve` con meta-búsqueda web, **levanta el perfil `searxng`** y descomenta en `.env` al menos `ENABLE_SEARXNG=1` y `SEARXNG_URL=http://searxng:8080` (la API tiene `ENABLE_SEARXNG` en `0` por defecto en compose).
2. Arranque con SearXNG: `.\scripts\start-all.ps1 -ComposeProfile searxng` o `docker compose --profile searxng up -d --build` (en Linux/VPS; con Podman sustituye por `podman compose`).
3. Pruebas automáticas: [`scripts/smoke-stack.ps1`](scripts/smoke-stack.ps1) en Windows, o [`scripts/smoke-stack.sh`](scripts/smoke-stack.sh) en Linux/VPS (`API_BASE`, `NGINX_BASE`, etc. sobreescribibles por variables de entorno en bash).
4. **Puertos** que suelen exponerse al host: `8000` (API), `8888` (NGINX), `8081` (processor health), `8088` (SearXNG con perfil), `7700` (Meilisearch), `6333` (Qdrant), `5432` (Postgres). No expongas Postgres ni servicios internos a Internet sin firewall/VPN; delante de producción usa TLS y restricción por red.

## Integraciones (docs)

| Tema | Archivo |
|------|---------|
| Firecrawl self-host | [`integrations/firecrawl.md`](integrations/firecrawl.md) |
| OpenPerplex | [`integrations/openperplex.md`](integrations/openperplex.md) |
| FlareSolverr, anti-Cloudflare, ACLED (contexto) | [`integrations/anti-cloudflare-acquisition.md`](integrations/anti-cloudflare-acquisition.md) |
| Pila de adquisición (diagrama) | [`integrations/acquisition-stack.md`](integrations/acquisition-stack.md) |
| Camoufox bridge | [`integrations/camoufox-bridge.md`](integrations/camoufox-bridge.md) |
| Scrappey | [`integrations/scrappey.md`](integrations/scrappey.md) |

## CI

GitHub Actions valida `go build` del crawler, `compileall` de Python y `docker compose config` (véase [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

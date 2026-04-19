# Anti-Cloudflare y capa de adquisición (2026)

Referencia para **MotorDeBusqueda**: cómo encaja **FlareSolverr** y herramientas relacionadas con el crawler y fuentes difíciles (p. ej. sitios con JS challenge, Turnstile, IUAM). No sustituye a términos de servicio ni a licencias de datos (ACLED, etc.).

## FlareSolverr (pieza central en este repo)

- **Qué es:** servicio que expone una **API HTTP** (`POST /v1`) y usa un navegador real para resolver muchos desafíos de Cloudflare; devuelve HTML/cookies útiles para el resto del pipeline.
- **En el monorepo:** imagen `ghcr.io/flaresolverr/flaresolverr:latest`, red interna `http://flaresolverr:8191`. El **crawler Go** enruta dominios listados en `FLARE_DOMAINS` a FlareSolverr (ver [`crawler/main.go`](../crawler/main.go)).
- **Imagen:** mantén la etiqueta que elijas (`latest` o fija según tu política); revisa releases en el [repositorio oficial](https://github.com/FlareSolverr/FlareSolverr).
- **Limitación:** ningún bypass es infalible; sitios con Turnstile + fingerprinting agresivo pueden fallar a menudo. Por eso el diseño recomienda **varias capas** (Crawl4AI, Firecrawl SDK, FlareSolverr, curl-impersonate, Colly).

**Exponer 8191 al host (solo desarrollo):** en un `docker-compose.override.yml` local añade bajo `flaresolverr`:

```yaml
ports:
  - "8191:8191"
```

Así puedes llamar a FlareSolverr desde tu máquina sin tocar el compose principal (sigue siendo headless respecto a “producto”, es API).

## Orden de prioridad (referencia para fuentes duras)

Diagrama actualizado: [`acquisition-stack.md`](acquisition-stack.md).

| Prioridad (crawler) | Tecnología | Rol típico |
|---------------------|------------|------------|
| — | **Crawl4AI** / **Firecrawl** | Primera línea si el dominio está en `CRAWL4AI_DOMAINS` / `FIRECRAWL_DOMAINS` |
| — | **Camoufox bridge** | Firefox con huella realista; servicio `camoufox-bridge` (perfil `camoufox`), `CAMOUFOX_DOMAINS` |
| 1 (switch final) | **FlareSolverr** | Dominios en `FLARE_DOMAINS`; API `POST /v1` |
| 2 | **Scrappey** | API gestionada; `SCRAPPEY_API_KEY` + `SCRAPPEY_DOMAINS` |
| 3 | **curl-impersonate** | TLS-JA3; `CURL_HTTP_PROXY` opcional |
| 4 | **Colly** | Último recurso; `COLLY_HTTP_PROXY` o `TOR_PROXY` |

## Cómo se mapea a este repositorio (no son 7 microservicios nuevos)

1. **Planificación de consulta** → `api/app/query_plan.py`, `/resolve`, opcional Ollama.
2. **Adquisición masiva de páginas** → **crawler** (orden: Crawl4AI → Firecrawl SDK → Camoufox bridge → FlareSolverr → Scrappey → curl → Colly; ver `acquisition-stack.md`).
3. **Cola** → **NSQ** `raw_pages`.
4. **Normalización / embeddings** → **processor**.
5. **Índice + búsqueda** → Meilisearch + Qdrant + **API** FastAPI.

Metadatos tipo `bypass_method` o `source_type` pueden añadirse en el **processor** al ingerir (campo en JSON / PG); hoy el crawler envía `via` (`flare`, `crawl4ai`, etc.) en `raw_pages`.

## Fuentes tipo ACLED (legal y técnico)

- Priorizar **API oficial** y **términos de uso** cuando existan credenciales OAuth o API key.
- El **Data Export Tool** y páginas web suelen estar detrás de Cloudflare: ahí encajan Crawl4AI, Firecrawl y **FlareSolverr** como capas técnicas, no como sustituto de permisos legales.
- Guardar secretos solo en **variables de entorno** o un gestor de secretos; no en el repositorio.

## Instrucciones para tu IA (copiar y pegar)

> En la capa de adquisición del monorepo MotorDeBusqueda, respeta el orden del crawler: Crawl4AI → Firecrawl (si configurado) → Camoufox bridge (si `CAMOUFOX_URL` + dominios) → en el bloque final FlareSolverr (`FLARE_DOMAINS`) o Scrappey (clave + dominios) o curl-impersonate → Colly; véase `acquisition-stack.md`.  
> Si se detecta bloqueo tipo Cloudflare, documenta `via` y el método de bypass en metadatos.  
> Para datos con API oficial (p. ej. ACLED), prioriza API con credenciales antes que scraping público.  
> No inventes versiones concretas de imágenes sin comprobar el registry; usa el compose del repo y overrides documentados.

## Próximos pasos opcionales

- Campos explícitos `cloudflare_challenge_solved` / `bypass_method` en el esquema de ingesta del processor.
- Perfiles de navegador persistentes o rotación de instancias Camoufox a escala.

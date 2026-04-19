# Firecrawl (opcional, stack aparte)

Firecrawl no está en el `docker-compose.yml` principal porque su stack oficial compila varias imágenes (API, Playwright, RabbitMQ, Postgres NUQ). El crawler de este repo puede consumirlo solo por HTTP.

1. Clona el repo oficial y sigue [SELF_HOST.md](https://github.com/mendableai/firecrawl/blob/main/SELF_HOST.md):

   ```bash
   git clone https://github.com/mendableai/firecrawl.git
   cd firecrawl
   # .env mínimo: PORT, USE_DB_AUTHENTICATION, BULL_AUTH_KEY, etc.
   docker compose up -d
   ```

2. En el `.env` de **MotorDeBusqueda** (o variables del servicio `crawler`):

   - `FIRECRAWL_URL=http://host.docker.internal:3002` (Windows/macOS; ajusta el puerto si cambiaste `PORT`)
   - `FIRECRAWL_API_KEY=` si tu instancia exige Bearer
   - `FIRECRAWL_DOMAINS=ejemplo.com` o `FIRECRAWL_DOMAINS=*`

3. El crawler de MotorDeBusqueda usa el **SDK Go** `github.com/mendableai/firecrawl-go/v2` contra tu `FIRECRAWL_URL` (no cliente HTTP manual). Si la URL está definida, el SDK debe inicializarse al arrancar el crawler.

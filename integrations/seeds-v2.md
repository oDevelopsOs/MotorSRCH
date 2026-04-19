# Seeds v2 (`crawler/seeds.json`)

## Formato

- **`version`**, **`updated`**, **`description`**: metadatos opcionales.
- **`feeds`**: lista de objetos con al menos **`url`** (RSS/Atom). Campos opcionales: `name`, `category`, `region`, `lang`, `priority`. También se acepta el formato antiguo: solo strings URL.
- **`urls`**: URLs a rastrear directamente (sin feed). Opcional: `crawl_strategy` (`api` | `scrape`) — se envía en el mensaje NSQ (`crawl_strategy` en el payload) para el processor.
- **`meta`**: JSON libre (p. ej. totales, notas).

El crawler **acepta comentarios `//` en línea** si guardas una copia como `seeds.jsonc` y generas JSON válido:

```bash
python scripts/jsonc_to_json.py crawler/seeds.jsonc crawler/seeds.json
```

## Lista global (finanzas / macro / regiones)

El repositorio incluye la **lista global v2** materializada en `crawler/seeds.json` (generada desde `scripts/materialize_global_seeds.py`; más de un centenar de feeds con cobertura regional y por tema ampliable). Para regenerarla tras editar la fuente canónica:

```bash
python scripts/materialize_global_seeds.py
```

Para listas personalizadas:

1. Pega tu lista completa (JSON o JSONC) en `crawler/seeds.jsonc`.
2. Ejecuta `python scripts/jsonc_to_json.py crawler/seeds.jsonc crawler/seeds.json`.
3. O divide feeds extra en `crawler/extra_feeds.json` (array de objetos) y:  
   `python scripts/merge_seed_feeds.py crawler/extra_feeds.json`

**Nota:** corrige el dominio **AllAfrica** (`allafrica.com`, no `alllafrica.com`). El BoJ en inglés usa el RSS general `…/en/rss/whatsnew.xml` (las rutas antiguas `release_YYYY/rss.xml` suelen quedar obsoletas al cambiar de año).

## Verificación de URLs (`scripts/verify_seeds_urls.py`)

- Carga opcionalmente **`FRED_API_KEY`** desde la raíz del proyecto (`.env`) sin pisar variables ya definidas en el proceso, igual que el crawler al resolver `api_key=&` en URLs de `api.stlouisfed.org`.
- Usa **User-Agent identificable** para dominios que lo exigen (p. ej. **SEC**, **BLS**, **IMF**); un UA genérico tipo navegador puede recibir **403** aunque la URL sea correcta.

## Límites (anti-bot, DNS, premium)

- Algunos agregadores (**Reuters** vía `feeds.reuters.com`, etc.) pueden fallar por **DNS** en ciertas redes o exigir políticas de cliente distintas; en esos casos la lista usa **equivalentes verificados** (p. ej. **Associated Press** en `apnews.com`, **BBC** / **FT** ya presentes) en lugar de URLs rotas.
- Fuentes **premium**, **con sesión** o **anti-bot estricto** (p. ej. ciertos medios, SSRN como RSS) no se incluyen como RSS estándar si no devuelven **200** de forma estable con el stack de verificación.
- El **crawler** configura `gofeed` con un User-Agent descriptivo; el valor por defecto `Gofeed/1.0` puede ser rechazado por sitios como el IMF.

## Variable

`SEEDS_PATH` (por defecto `seeds.json` relativo al directorio de trabajo del binario del crawler).

# Scrappey (API gestionada)

[Scrappey](https://docs.scrappey.com/) ofrece sesiones de navegador remotas. El crawler usa el mismo patrón que FlareSolverr: **POST** a `{SCRAPPEY_URL}/api/v1?key=...` con cuerpo:

```json
{ "cmd": "request.get", "url": "https://...", "maxTimeout": 60000 }
```

La respuesta JSON expone `solution.verified` y `solution.response` (HTML). Si `verified` es `false`, se registra el error y no se cobra según su documentación.

Variables:

| Variable | Descripción |
|----------|-------------|
| `SCRAPPEY_API_KEY` | Obligatoria para activar la rama Scrappey. |
| `SCRAPPEY_URL` | Por defecto `https://publisher.scrappey.com` si no se define. |
| `SCRAPPEY_DOMAINS` | Lista de hosts o `*` (misma semántica que `FLARE_DOMAINS`). |

**Prioridad:** en el `switch` final del crawler, `FLARE_DOMAINS` tiene prioridad sobre Scrappey si el host está en ambas listas.

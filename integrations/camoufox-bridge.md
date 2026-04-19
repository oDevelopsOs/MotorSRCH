# Camoufox bridge (self-hosted)

Servicio en `camoufox-bridge/`: **FastAPI** + **AsyncCamoufox** (Firefox con huella realista). Expone:

- `GET /health`
- `POST /v1/fetch` — cuerpo JSON `{"url":"https://...","timeout_ms":120000}` → `{"ok":true,"html":"...","title":"..."}`

Opcional: variable `CAMOUFOX_BRIDGE_TOKEN` en el contenedor; el crawler debe enviar `Authorization: Bearer <token>` (misma variable en el servicio `crawler`).

## Compose

```bash
podman compose --profile camoufox up -d --build
```

En el **crawler** (misma red Docker):

- `CAMOUFOX_URL=http://camoufox-bridge:8090`
- `CAMOUFOX_DOMAINS=ejemplo.com,otro.com` o `*` para todos los hosts (uso intensivo).

La primera construcción de la imagen ejecuta `python -m camoufox fetch` (descarga del binario Camoufox); puede tardar y ocupar varios GB en capas.

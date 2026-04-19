# OpenPerplex Backend (opcional)

Microservicio Python independiente: <https://github.com/YassKhazzan/openperplex_backend_os>

1. Clona y configura `.env` (Cohere, Jina, Serper, Groq según el repo).
2. Ejecuta `uvicorn main:app --host 0.0.0.0 --port 8000`.
3. En **MotorDeBusqueda**, en el servicio `api`, define `OPENPERPLEX_URL=http://openperplex:8000` (o `host.docker.internal` si corre en el host).
4. Usa el proxy SSE: `GET /brain/openperplex/search?query=...&date_context=...&stored_location=...`

La ruta original del backend es `GET /search` con respuesta **text/event-stream** (SSE).

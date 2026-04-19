# Gunicorn carga este archivo si está en el cwd (Render: raíz del repo).
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", os.environ.get("UVICORN_WORKERS", "2")))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))

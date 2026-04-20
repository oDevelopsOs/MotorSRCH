# Gunicorn carga este archivo si está en el cwd (Render: raíz del repo).
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.environ.get("WEB_CONCURRENCY", os.environ.get("UVICORN_WORKERS", "1")))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
accesslog = "-"
errorlog = "-"

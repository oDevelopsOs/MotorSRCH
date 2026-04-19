# Context: repository root (Render, etc.). Equivalent to api/Dockerfile with COPY api/…
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip install --no-cache-dir "torch>=2.2.0" --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt \
  && pip install --no-cache-dir "torch>=2.2.0" --index-url https://download.pytorch.org/whl/cpu --force-reinstall --no-deps

COPY api/app ./app
COPY api/main.py .
COPY api/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV UVICORN_WORKERS=2
EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# CPU-only PyTorch (evita metapaquetes NVIDIA en contenedor Linux dev/Podman)
RUN pip install --no-cache-dir "torch>=2.2.0" --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt \
  && pip install --no-cache-dir "torch>=2.2.0" --index-url https://download.pytorch.org/whl/cpu --force-reinstall --no-deps \
  && python -m spacy download en_core_web_sm

COPY app ./app
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV PROCESSOR_WORKERS=2
EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]

# Playwright base + Camoufox binary (python -m camoufox fetch).
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m camoufox fetch

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    CAMOUFOX_HEADLESS=1

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]

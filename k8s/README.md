# Kubernetes: escalado automático (referencia)

`docker compose` en un solo host **no** escala réplicas según CPU/cola. Para **subir y bajar pods automáticamente** hace falta un orquestador (p. ej. Kubernetes).

## HPA (Horizontal Pod Autoscaler)

El archivo [`example-api-hpa.yaml`](example-api-hpa.yaml) es un **ejemplo mínimo** (no completo para producción):

- `Deployment` + `Service` para la API (imagen y env deben adaptarse a tu registry y secretos).
- `HorizontalPodAutoscaler` con `minReplicas` / `maxReplicas` y objetivo de CPU.

Requisitos en el cluster:

- [Metrics Server](https://github.com/kubernetes-sigs/metrics-server) instalado para métricas de CPU/memoria.

Ajusta `averageUtilization` y recursos `requests`/`limits` según el modelo de embeddings (la API es **pesada en RAM** por réplica).

## KEDA (opcional)

Para escalar el **processor** por **profundidad de cola** NSQ o métricas Redis, [KEDA](https://keda.sh/) puede disparar réplicas desde ScaledObjects. No está versionado en este repo: depende de tu instalación de NSQ (dentro o fuera del cluster) y del formato de métricas expuesto.

## VPS sin Kubernetes

En una sola máquina, el escalado práctico es:

- **Más workers Gunicorn** (`UVICORN_WORKERS`, `PROCESSOR_WORKERS` en `.env`).
- Archivo opcional [`docker-compose.dual-api.yml`](../docker-compose.dual-api.yml) para **dos contenedores API** detrás de NGINX.
- Proveedor de nube con **auto scaling group** de VMs si pasas a varios nodos.

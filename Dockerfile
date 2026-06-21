FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY neuralrouter ./neuralrouter
COPY omni_training ./omni_training
COPY saas ./saas
COPY web ./web
COPY scripts ./scripts

RUN chmod +x /app/scripts/docker-entrypoint.sh \
    && mkdir -p /app/data/projects /app/omni_training/data/vault

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]

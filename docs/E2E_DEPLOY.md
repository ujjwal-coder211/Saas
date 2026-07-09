# Deploy Aksh on E2E Networks (India)

**Full step-by-step (inch by inch):** [E2E_DEPLOY_INCH_BY_INCH.md](./E2E_DEPLOY_INCH_BY_INCH.md)

Production target: **100% E2E Networks** — API, DB, storage, GPU.

## Quick Docker deploy (production)

```bash
cp .env.production.example .env
# edit .env — OPENROUTER_API_KEY, POSTGRES_PASSWORD, secrets
docker compose -f docker-compose.prod.yml up -d --build
curl http://127.0.0.1:8000/health
```

Files: `Dockerfile`, `docker-compose.prod.yml`, `scripts/docker-entrypoint.sh`

## Regions

| Workload | E2E region |
|----------|------------|
| API + Postgres + Redis | Delhi NCR |
| Object storage (projects, vault) | E2E Object Storage (S3-compatible) |
| Sarva train + infer | TIR GPU — Chennai |

Avoid Mumbai DC for new deploys (E2E migrating customers off Mumbai).

## Steps

1. **E2E account** — VPC + VM for FastAPI (Docker or uvicorn)
2. **Postgres** — managed DBaaS or VM; run `python scripts/init_db.py`
3. **Redis** — rate limits (`REDIS_URL`)
4. **Object Storage** — bucket; set env:
   - `E2E_OBJECT_STORAGE_ENDPOINT`
   - `E2E_OBJECT_STORAGE_BUCKET`
   - `E2E_OBJECT_STORAGE_ACCESS_KEY`
   - `E2E_OBJECT_STORAGE_SECRET_KEY`
   (Wire in `saas/storage/` when S3 adapter is added — local `data/projects/` works for MVP)
5. **TLS** — `api.aksh.aitotech.in` on load balancer
6. **Env secrets** — all keys from `.env.example`
7. **TIR GPU** — deploy Sarva inference; set `SARVA_INFERENCE_URL`
8. **IndiaAI credits** (optional) — [compute.indiaai.gov.in](https://compute.indiaai.gov.in) — jobs still on E2E

## Website

Point `aitotech.in/aksh` reverse proxy to this service `/web/index.html`.

## Verify

```bash
curl https://api.aksh.aitotech.in/health
curl https://api.aksh.aitotech.in/web/index.html
```

See also: `docs/DEPLOY.md`, `docs/USER_CHECKLIST.md`

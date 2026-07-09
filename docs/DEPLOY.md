# Deploying Aksh by Aitotech

Production scaffold for Railway, Render, or any Docker host. For India-focused SaaS, prefer **Mumbai (ap-south-1)** or nearest region for PostgreSQL/Redis latency.

## Prerequisites

1. Copy `.env.production.example` → platform secrets (never commit `.env`)
2. Provider keys: `OPENROUTER_API_KEY`, `MOONSHOT_API_KEY`, `DEEPINFRA_API_KEY` (at least one routing path)
3. PostgreSQL + Redis URLs
4. Vault keys: `SARVA_VAULT_HMAC_KEY`, `SARVA_VAULT_ENCRYPTION_KEY`, `SARVA_ADMIN_KEY`

## Related docs

- [ROUTELY_DEPLOY.md](./ROUTELY_DEPLOY.md) — Routely CI/CD (Railway + Vercel + domains)
- [ROUTELY.md](./ROUTELY.md) — product overview

## Railway

1. Connect GitHub repo `ujjwal-coder211/Saas`
2. **Settings → Deploy → Custom Start Command:** leave **empty** (uses `railway.toml` → `docker-entrypoint.sh`)
3. If you see `$PORT is not a valid integer`, delete the old start command and redeploy
4. Add PostgreSQL and Redis plugins; map `DATABASE_URL`, `REDIS_URL`
5. Set `PUBLIC_DEMO_ENABLED=true`, `OPENROUTER_API_KEY`, `DEEPINFRA_API_KEY`
6. Set `SAAS_PUBLIC_URL` to your Railway domain
7. Set `NEURALROUTER_CORS_ORIGINS` to your web origin

## Render

1. New Blueprint from `deploy/render.yaml`
2. Fill sync=false secrets in dashboard
3. Attach managed Postgres; paste connection string into `DATABASE_URL`

## Mumbai / India notes

- Choose **AWS ap-south-1 (Mumbai)** or **GCP asia-south1** for DB when available
- Keep inference provider keys global; latency is dominated by expert API round-trips
- Document data residency in customer agreements; vault encryption at rest via `SARVA_VAULT_ENCRYPTION_KEY`
- Stripe India: enable INR prices; set `STRIPE_PRICE_PRO` to India price ID

## Clerk (auth)

1. Create Clerk application → enable Email/OTP
2. Set `CLERK_SECRET_KEY` and `CLERK_PUBLISHABLE_KEY`
3. Wire Clerk JWT verification in `saas/auth/` when moving beyond API-key MVP (scaffold env vars ready)
4. Dashboard signup MVP uses `/saas/v1/signup` until Clerk is integrated

## Stripe (billing)

1. Create Product + Price (INR recommended)
2. Set `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO`
3. Webhook URL: `https://YOUR_DOMAIN/saas/v1/stripe/webhook`

## Health check

```bash
curl https://YOUR_DOMAIN/health
```

Extended response includes `version`, `brain`, and `search` status.

## Post-deploy verification

```powershell
python scripts/verify_setup.py
```

## Sarva brain promote (production)

```powershell
python sarva_training/brain_eval.py sarva-v2
python sarva_training/brain_promote.py sarva-v2 --approve
```

Or admin API with `X-Sarva-Admin-Key`.

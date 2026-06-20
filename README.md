# Aitotech NeuralRouter SaaS

**SarvAI / Aitotech** — Multi-tenant AI router + Omni training flywheel.

```
Saas/
├── neuralrouter/     SYSTEM 1 — 5-brain API (production)
├── omni_training/    SYSTEM 2 — model behavior research + datasets
├── saas/             Billing & control layer (NEW)
│   ├── db/           PostgreSQL schema
│   ├── auth/         Per-user API keys (hashed)
│   ├── billing/      Token usage + Stripe
│   └── api/          Dashboard REST routes
├── web/
│   ├── chat.html
│   └── dashboard/    Usage + signup UI
├── Dockerfile
└── docker-compose.yml
```

## Quick start — Docker (recommended)

```powershell
cd C:\Users\ujjwa\Saas
copy .env.example .env
# Add OPENROUTER_API_KEY etc. to .env

docker compose up --build
```

Open:
- **Dashboard:** http://localhost:8000/web/dashboard/
- **API docs:** http://localhost:8000/docs
- **Chat:** http://localhost:8000/web/chat.html

Signup on dashboard → copy `sk_live_...` API key → use in Cursor or chat.

## Quick start — local (without Docker)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env

# Start Postgres + Redis locally, then:
python scripts/init_db.py
python scripts/seed_tenant.py demo@your.com

.\scripts\run_dev.ps1
```

## Cursor / OpenAI-compatible

| Setting | Value |
|---------|--------|
| Base URL | `http://localhost:8000/v1` |
| API Key | Your `sk_live_...` from dashboard |
| Model | `auto` |

## SaaS API (`/saas/v1`)

| Endpoint | Purpose |
|----------|---------|
| `POST /saas/v1/signup` | Create user + API key (MVP) |
| `GET /saas/v1/me` | Profile + usage + keys |
| `GET /saas/v1/usage` | Token usage this month |
| `POST /saas/v1/api-keys` | Rotate / add key |
| `PATCH /saas/v1/training-opt-in` | Opt-in for Omni training |
| `POST /saas/v1/checkout-session` | Stripe Pro upgrade |

## Billing & plans

| Plan | Tokens/mo | Rate limit |
|------|-----------|------------|
| Free | 50,000 | 30/min |
| Pro | 2,000,000 | 120/min |
| PAYG | Unlimited | 60/min |

Every chat call records `usage_events` in PostgreSQL. Over limit → HTTP 402.

## Omni training pipeline

```powershell
cd omni_training
python curate.py
python build_dataset.py
python research_report.py
python scheduler.py
```

Customer data is **redacted by default** unless `training_opt_in=true`.

## Security

- API keys stored as SHA-256 hash only
- Training vault: HMAC + optional AES (`OMNI_VAULT_*`)
- Redis rate limits per tenant
- Stripe webhooks signature verified
- Admin routes need `X-Omni-Admin-Key`

## Deploy

Railway / Render / AWS ECS — use `Dockerfile`. Set all env vars from `.env.example`.

## Company structure

```
Aitotech (company)
  └── SarvAI NeuralRouter SaaS (this repo)
        └── Omni Training Program → proprietary model (Colab LoRA)
```

Existing Omni v1 LoRA: https://huggingface.co/Ujjwal211/aitotech-omni-v1

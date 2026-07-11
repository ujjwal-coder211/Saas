# Production Launch Checklist — Saira / Sarva

Work top to bottom. `[ ]` = you do it, `[x]` = already handled in the repo.
Nothing here charges money or exposes data until **you** flip the switches.

---

## 1. Secrets & keys (do first)

- [x] `.env` is git-ignored (secrets never committed)
- [x] `.env.production.example` provided
- [ ] **Rotate every key that has ever been pasted anywhere** (HF token, OpenRouter key)
- [ ] Generate strong values for: `JWT_SECRET`, `POSTGRES_PASSWORD`, `SARVA_ADMIN_KEY`
      (use `openssl rand -hex 32`)
- [ ] Store production secrets in your host's secret manager (Railway/Render vars,
      or a vault) — not in a file on disk
- [ ] `NEURALROUTER_API_KEYS` = the real client keys you issue to customers

## 2. Auth & access (must-do before any public URL)

- [ ] `NEURALROUTER_ALLOW_UNAUTH=false` (default; confirm it's not `true` in prod)
- [ ] `SAAS_ALLOW_PUBLIC_SIGNUP` — set deliberately (false until you're ready)
- [ ] `PUBLIC_DEMO_ENABLED=false` unless you want an open demo (it's rate-limited)
- [ ] Set `NEURALROUTER_CORS_ORIGINS` to your real front-end origin(s) only
- [ ] Rate limits sane: `NEURALROUTER_RATE_LIMIT`, `MAX_CONCURRENT_PER_CLIENT`,
      `MAX_GLOBAL_CONCURRENT`
- [ ] Per-team budget ceilings enabled (governance module) for any team plan

## 3. Data & database

- [ ] Provision Postgres; set `DATABASE_URL`
- [ ] Run/verify schema (`saas/db/schema.sql`)
- [ ] Backups enabled on the DB
- [ ] Redis (`REDIS_URL`) if you use it for rate-limit/session

## 4. Providers & cost model (decide before pricing)

- [ ] Confirm **OpenRouter commercial ToS** + rate limits for the `:free` models
      you route to — free models can be unreliable/deprecated (you already hit
      404'd `:free` strings once). Budget for **paid** models for paying users.
- [ ] Add a paid-model tier in `sarva_training/models_registry/` for pro users
- [ ] Compute margin: `price_charged − provider_cost` per request (see
      `saas/billing/plans.py` COST_PER_MILLION_TOKENS_USD / BILLING_MARKUP)
- [ ] Hard budget ceiling + kill switch on (loop/budget guards exist in
      `neuralrouter/security/limits.py`)

## 5. Billing (test end-to-end before charging anyone)

- [ ] Stripe account in **test mode** first
- [ ] Set `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO`
- [ ] Point a Stripe webhook at `POST /saas/v1/stripe/webhook`
- [ ] Run a full test purchase: checkout → webhook received → plan upgraded →
      quota enforced (`saas/billing/`)
- [ ] Refund policy decided and documented in ToS

## 6. Model / IP licensing (legal-adjacent — verify)

- [ ] Base model **Qwen2.5-14B** license — confirm commercial serving is allowed
- [ ] Training datasets (Magicoder-OSS-Instruct, SWE-bench, CodeFeedback) —
      confirm licenses permit commercial model training/serving
- [ ] `LICENSE` present (proprietary) — fill in your contact email
- [ ] Add a `NOTICE` file crediting open-weight models/datasets if required

## 7. Deploy & reliability

- [ ] Pick a host: Railway (`railway.toml`), Render (`render.yaml`), or a VPS +
      `docker-compose.prod.yml`
- [ ] HTTPS/TLS on your domain (host usually provides)
- [ ] Health check wired to `/health`
- [ ] Error monitoring (e.g. Sentry) + uptime monitor
- [ ] Log retention; audit trail (`neuralrouter/security/audit.py`) shipped to storage
- [ ] Trained Sarva (optional): serve `deploy/runpod/serve_sarva.py` on a GPU,
      set `SARVA_INFERENCE_URL` — otherwise the rules brain + OpenRouter is used

## 8. Security pre-flight

- [x] Permission gate, injection firewall, credential vault, red-team (12/12) in code
- [ ] Run `python -m neuralrouter.security.redteam` on the deployed build
- [ ] External security review before you hold real customer code/data (the
      internal red-team is a floor, not an external audit)
- [ ] Dependency scan (`pip-audit`) + keep deps patched

## 9. Legal pages (lawyer-reviewed) live on the site

- [ ] Terms of Service (draft: `docs/legal/TERMS_OF_SERVICE.md`)
- [ ] Privacy Policy (draft: `docs/legal/PRIVACY_POLICY.md`)
- [ ] Cookie/consent if you use analytics

## 10. Go-live smoke

- [ ] `python scripts/smoke_local.py` → READY
- [ ] `/health` shows `providers.openrouter=true`, correct active brain
- [ ] One real `POST /v1/chat` returns a good answer
- [ ] Billing test purchase works
- [ ] Rollback plan written (how to revert a bad deploy)

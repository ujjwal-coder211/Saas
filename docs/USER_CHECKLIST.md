# Aksh — Aapko kya karna hai (Complete checklist)

Ye checklist sab blocks ko **proper complete** karne ke liye hai — local dev se lekar E2E production tak.

---

## Block 1 — Local setup (aaj, laptop par)

- [ ] Repo clone: `git clone https://github.com/ujjwal-coder211/Saas.git`
- [ ] `copy .env.example .env` — keys bharo:
  - `OPENROUTER_API_KEY` (ya Moonshot / DeepInfra — kam se kam ek)
  - `NEURALROUTER_API_KEYS=dev-key-123` (local testing)
  - `DATABASE_URL=postgresql://...` (Docker Postgres)
  - `SAAS_ALLOW_PUBLIC_SIGNUP=true`
  - `OMNI_VAULT_HMAC_KEY`, `OMNI_VAULT_ENCRYPTION_KEY` (random strings)
- [ ] `docker compose up --build`
- [ ] `python scripts/init_db.py` — naye tables (threads, projects)
- [ ] Verify: `python scripts/verify_setup.py`
- [ ] Browser: http://localhost:8000/web/index.html
- [ ] Signup → Studio → chat test

---

## Block 2 — API keys (AI providers)

- [ ] [OpenRouter](https://openrouter.ai) — account + API key
- [ ] Optional: Moonshot, DeepInfra keys
- [ ] Optional search: `AKSH_SEARCH_API_KEY` (Tavily) + `AKSH_SEARCH_PROVIDER=tavily`

**Bina in keys ke Omni experts jawab nahi de payenge** (routing fail).

---

## Block 3 — Product test (user journey)

- [ ] Landing page: `/web/index.html`
- [ ] Docs: `/web/docs/`
- [ ] Dashboard signup → API key save
- [ ] Studio: cloud project create / zip upload
- [ ] Chat thread: naya thread → message → refresh → history wapas
- [ ] Omni label: response mein `brain_used: omni` (experts hidden)
- [ ] Cursor: model `omni`, base URL `/v1`

---

## Block 4 — E2E Networks (production India)

- [ ] Account: [myaccount.e2enetworks.com](https://myaccount.e2enetworks.com)
- [ ] **Delhi NCR** — API VM + Postgres + Redis
- [ ] **E2E Object Storage** — bucket for projects + vault backup
- [ ] **Chennai TIR GPU** — Omni train + `OMNI_INFERENCE_URL`
- [ ] Domain: `api.aksh.aitotech.in` → E2E load balancer
- [ ] Website: `aitotech.in/aksh` → reverse proxy to Aksh app
- [ ] See: `docs/E2E_DEPLOY.md`

---

## Block 5 — Aitotech website link

- [ ] Main company site (`aitotech.in`) par Aksh section:
  - Hero → link `/aksh` or full URL to deployed Aksh landing
  - Footer: Docs, Studio, Pricing
- [ ] Old `aitotech` NeuralRouter repo → README points to **Saas** repo (Aksh product)
- [ ] GitHub: `ujjwal-coder211/Saas` = canonical product repo

---

## Block 6 — Billing & auth (later)

- [ ] Stripe India INR price → `STRIPE_*` env
- [ ] Clerk auth → replace MVP signup
- [ ] Razorpay optional Phase 5

---

## Block 7 — Omni brain train (System 2)

- [ ] Usage + feedback → vault
- [ ] `scripts/run_pipeline.ps1`
- [ ] E2E TIR GPU train (Colab replacement)
- [ ] `brain_register` → `brain_eval` → `brain_promote`

---

## Quick URLs (local)

| What | URL |
|------|-----|
| Landing | http://localhost:8000/web/index.html |
| Studio | http://localhost:8000/web/studio/ |
| Dashboard | http://localhost:8000/web/dashboard/ |
| Docs | http://localhost:8000/web/docs/ |
| API Swagger | http://localhost:8000/docs |

---

## Agar kuch fail ho

| Problem | Fix |
|---------|-----|
| Signup 503 | `DATABASE_URL` + `init_db.py` |
| Threads 503 | Same — Postgres required |
| Chat error 401 | API key Dashboard se copy |
| Chat error 402 | Quota — upgrade or new month |
| Empty AI reply | Provider API keys in `.env` |
| Upload fail | `python-multipart` installed, SaaS key |

**Support docs:** `/web/docs/` · **Dev README:** `README.md`

# Founder Launch Guide — Aitotech / Saira

A step-by-step path from "code that runs" to "a company can charge for it."
**✅ = already done in the repo.  👤 = only YOU can do it (accounts, money, legal).**

> Reality check: the product runs and is documented, but it is pre-launch. No
> real users, no external security audit, live quality numbers not yet measured.
> This guide is ordered so you don't expose anything before it's ready.

---

## PHASE 0 — Protect what you have (TODAY, ~1 hour)

**0.1 👤 Make the GitHub repo private**
- GitHub → your repo → **Settings** → scroll to **Danger Zone** →
  **Change repository visibility** → **Private**.
- Why: right now your entire commercial product (routing, billing, training
  pipeline) is public — anyone can copy it.

**0.2 ✅ LICENSE added** (proprietary, `LICENSE`). 👤 Fill in your contact email in it.

**0.3 👤 Rotate every key that was ever pasted or shared**
- HuggingFace token → https://huggingface.co/settings/tokens (delete old, make new).
- OpenRouter key → https://openrouter.ai/keys.
- Never paste a real key into chat, commits, or screenshots again.

**0.4 ✅ `.env` is git-ignored** — confirm you never committed a real `.env`.
Run: `git log --all --oneline -- .env` (should be empty).

---

## PHASE 1 — Register the company (start now, runs in parallel; YOUR task)

> 👤 All of this needs a **CA (Chartered Accountant) / Company Secretary**. I am
> not a lawyer — these are pointers, not legal advice.

**1.1** Decide structure (India context): **Private Limited** (best for raising
funds / SaaS) vs **LLP** vs **sole proprietor** (simplest, weakest protection).
Ask a CA which fits your plan.

**1.2** Register **Aitotech** via a CA / MCA portal. You'll get: Certificate of
Incorporation, PAN, TAN.

**1.3** Open a **current (business) bank account** in the company's name.

**1.4** **GST registration** if/when required (turnover threshold or B2B invoicing).

**1.5** Trademark the name/logo "Aitotech" / your product name (optional but wise).

**1.6** Keep founder ↔ company IP clean: a simple assignment that the code/IP
belongs to the company.

---

## PHASE 2 — Make the product production-ready (mix of ✅ and 👤)

Follow **[docs/PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)** in full. The
essentials:

**2.1 👤 Buy a domain** (e.g. aitotech.in) and set up email.

**2.2 👤 Pick a host & deploy**
- Easiest: **Railway** (`railway.toml`) or **Render** (`render.yaml`).
- Copy `.env.production.example` → set real values in the host's secret manager:
  `OPENROUTER_API_KEY`, `DATABASE_URL`, `JWT_SECRET`, `SARVA_ADMIN_KEY`,
  `NEURALROUTER_API_KEYS`, and keep `NEURALROUTER_ALLOW_UNAUTH=false`.

**2.3 👤 Provision Postgres** (host add-on) → set `DATABASE_URL` → enable backups.

**2.4 👤 Decide the cost/pricing model** (I can help compute margins)
- Free `:free` OpenRouter models are unreliable for paying users — add a **paid**
  model tier and price above your provider cost. See `saas/billing/plans.py`.

**2.5 👤 Set up Stripe** (test mode first)
- Create products/prices → set `STRIPE_*` env → point a webhook at
  `POST /saas/v1/stripe/webhook` → run one full test purchase end-to-end.

**2.6 ✅ Verify:** `python scripts/smoke_local.py` → READY. Then hit `/health` on
the deployed URL and do one real `POST /v1/chat`.

**2.7 👤 (Optional) Serve the trained conductor**
- On a GPU (RunPod), run `deploy/runpod/serve_sarva.py` with the v4 adapter, set
  `SARVA_INFERENCE_URL`. Otherwise the rules brain + OpenRouter works fine.

---

## PHASE 3 — Legal & trust (before real users)

**3.1 ✅ Drafts written:** `docs/legal/TERMS_OF_SERVICE.md`,
`docs/legal/PRIVACY_POLICY.md`. 👤 **Get a lawyer to review/adapt them**, fill the
`[BRACKETS]`, and publish on your site.

**3.2 👤 Verify model & data licenses** for commercial use (Qwen2.5 base;
Magicoder / SWE-bench / CodeFeedback training data). Add a `NOTICE` file if needed.

**3.3 👤 Decide the data-training stance** and state it plainly (do you train on
customer code? The app has a `training_opt_in` flag). "We never train on your
code" is a strong trust line if you can commit to it.

---

## PHASE 4 — Beta (validate before scaling)

**4.1 👤 Get 5–10 real users** (friends, dev communities, Twitter/X, Discord).
Free/beta access.

**4.2 👤 Watch them use it.** Does routing feel good? Is it faster/cheaper than
the tool they use now? Collect the `/v1/feedback` signal.

**4.3 👤 Fix the top 3 friction points** before you charge anyone.

**4.4 👤 Measure real quality** — run the eval harness with live keys, and use the
RLEF loop; the numbers become "measured" (not simulated) once real usage flows.

---

## PHASE 5 — Launch

**5.1 👤** Public landing page with a crisp value line:
*"The best AI model for every coding task — and it gets cheaper as it learns."*

**5.2 👤** Turn on paid plans (Stripe live mode).

**5.3 👤** Launch post (Product Hunt / X / Reddit r/SideProject / dev communities).

**5.4 👤** Have an incident/rollback plan and someone watching monitoring on day 1.

---

## What I (Claude) can still do for you on request
- Compute the cost/margin model and a pricing table
- Write the landing-page copy / one-page pitch
- A Stripe billing test script + walkthrough
- A production `.env` filled skeleton (no secrets)
- A `NOTICE` file for third-party model/data credits
- Harden any specific endpoint or add missing prod config

## Your single next action
**Make the repo private, fill your email in `LICENSE`, rotate keys — then call a CA
to start Aitotech's registration.** Everything else can follow.

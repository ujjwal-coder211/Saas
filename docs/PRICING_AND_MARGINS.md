# Pricing & Margin Model — Saira / Sarva

> Illustrative business modeling, not a guarantee. **Plug in current OpenRouter
> prices** (they change) and your real infra costs before committing. Numbers use
> the repo's defaults in `saas/billing/plans.py`.

## The core insight
Your **cost lever is routing**: free `:free` OpenRouter models cost ~$0, and
Sarva self-executes easy tasks on a cheap model — so a task only costs real money
when it's delegated to a paid model. Margin = **how well the conductor keeps work
on cheap/free models** without hurting quality.

---

## 1. Provider cost per 1M tokens (fill with live OpenRouter prices)

| Model class | Example | ~Cost / 1M tok (in+out) | When Sarva uses it |
|---|---|---|---|
| Free | `*:free` (current default) | **$0** | default / self-execute |
| Small paid | Qwen2.5-Coder-7B etc. | ~$0.10–0.40 | routine delegation |
| Mid paid | DeepSeek-V3, GLM-4 | ~$0.50–1.50 | hard tasks |
| Premium | Claude/GPT-class arbiter | ~$3–15 | rare escalation only |

The repo assumes a **blended** `$2.50 / 1M tokens` with a **1.35× markup**
(`COST_PER_MILLION_TOKENS_USD`, `BILLING_MARKUP`). That blended figure is
conservative — if most traffic stays on free/small models your real cost is far
lower.

---

## 2. Plan economics (defaults in `plans.py`)

| Plan | Price/mo | Included tokens | Rate limit | Cost if 100% free models | Cost if blended $2.50/M | Margin (blended) |
|---|---|---|---|---|---|---|
| **Free** | $0 | 50K | 30 rpm | ~$0 | ~$0.13 | loss-leader (fine) |
| **Pro** | $29 | 2M | 120 rpm | ~$0 | ~$5.00 | **~$24 (83%)** |
| **PAYG** | usage | unlimited | 60 rpm | passthrough + markup | passthrough + markup | ~26% (1.35×) |

**Pro at full 2M usage:** worst case (all blended-paid) still ~83% gross margin.
Realistically most traffic is free/small → margin approaches 95%+. Infra
(hosting + Postgres) is a small fixed cost (~$20–50/mo on Railway/Render).

---

## 3. Break-even & guardrails

- **Free tier** is safe: 50K tokens × mostly-free models ≈ near-zero cost. Cap it
  hard so abuse can't run up paid-model spend.
- **Pro** breaks even vs infra after ~2–3 paying users.
- **Protect margin with the tools you already have:**
  - Per-team **budget ceilings** (`neuralrouter/security/limits.py`,
    `saas/governance/budget.py`) — cap paid-model spend per account.
  - Free-tier users get **weight 0 on premium models** (enforced by the routing
    policy, `user_tier` input) — monetization is in the router, not bypassable.
  - Loop/kill-switch guards stop runaway spend.

---

## 4. Suggested launch pricing (a starting point)

| Tier | Price | For | Notes |
|---|---|---|---|
| **Free** | $0 | trial / hobby | 50K tok/mo, free models only, 1 project |
| **Pro** | **$19–29/mo** | individual devs | 2M tok/mo, mixed models, memory, agent |
| **Team** | **$49–99/seat/mo** | small teams | governance, skill pooling, budgets, audit |
| **Enterprise** | custom | orgs | SSO, on-prem/air-gapped, SLA, dedicated tuning |

Start **lower** ($19 Pro) to get your first 20 users, then raise once you have
proof of value. Annual plans (2 months free) improve cash flow.

---

## 5. The moat is the cost curve
As Sarva learns (RLEF + Hermes skills), more tasks are handled on cheap/free
models → your **cost per task falls with usage** while a single-model competitor's
is fixed. That's the number to track: **average provider cost per successful task,
month over month.** If it trends down, the business thesis is working.

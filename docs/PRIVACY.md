# Aksh Privacy & Training Policy

**Product:** Aksh by Aitotech  
**Model:** Sarva (controller brain)

## Default: training opt-in OFF

- New accounts have **training_opt_in = false**
- Chat logs are stored for billing/ops; **only opt-in rows** enter the Sarva training vault
- Users enable opt-in explicitly in the dashboard (`PATCH /saas/v1/training-opt-in`)

## What we collect

| Data | Purpose | Training use |
|------|---------|--------------|
| Chat messages | Answer requests | Only if opt-in |
| Model routing metadata | Improve Sarva controller | Only if opt-in |
| Thumbs up/down | Quality signals | Only if opt-in |
| Skills/MCP repos user adds | Skill ingest pipeline | Tenant-scoped; opt-in for vault rows |
| API usage tokens | Billing | Never used for training |

## Vault security

- Training vault encrypted with `SARVA_VAULT_ENCRYPTION_KEY`
- Integrity via `SARVA_VAULT_HMAC_KEY`
- Admin promote/register requires `SARVA_ADMIN_KEY`

## Aksh Search

- Search queries may be sent to Tavily/Serper when enabled
- Without `AKSH_SEARCH_API_KEY`, search is skipped gracefully — no third-party call

## Data residency (India)

- Production deploy should use India-region PostgreSQL when available (see `docs/DEPLOY.md`)
- Expert model calls may route through global providers (OpenRouter, Moonshot, DeepInfra)

## User rights

- Disable training opt-in anytime in dashboard
- Request account deletion via support (SaaS MVP — implement deletion endpoint in Phase D)

## Contact

Aitotech — update with your legal contact before public launch.

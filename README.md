# Routely by Aitotech

**AI coding tool** — picks the best **free OpenRouter model** per task, understands your codebase, remembers chat history, runs agent workflows.

```
Aitotech (company)
  └── Routely (product)
        ├── Router — best :free model per coding task
        ├── Memory — persistent chat threads
        ├── Agent — multitask jobs, git, fix
        └── Clients — browser + desktop download
```

Deploy: [docs/DEPLOY.md](docs/DEPLOY.md) · E2E: [docs/E2E_DEPLOY_INCH_BY_INCH.md](docs/E2E_DEPLOY_INCH_BY_INCH.md)  
Product plan: [docs/ROUTELY.md](docs/ROUTELY.md)

## Stack

| Layer | Folder |
|-------|--------|
| Routely API + Router | `neuralrouter/` |
| Agent + git + terminal | `neuralrouter/agent/`, `neuralrouter/parity/` |
| SaaS auth + memory | `saas/` |
| Browser IDE (new) | `apps/browser/` |
| Legacy static studio | `web/studio/` |

## Quick start

**Full guide: [GETTING_STARTED.md](GETTING_STARTED.md)** — clone → configure → run → use, in ~5 min.

```bash
cp .env.example .env          # set OPENROUTER_API_KEY (free key at openrouter.ai/keys)

# Local:
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn neuralrouter.main:app --port 8000

# ...or Docker:
docker compose up --build
```

Verify in one command (no key needed):

```bash
python scripts/smoke_local.py     # -> RESULT: READY ✅
```

- API health: http://localhost:8000/health
- OpenAI-compatible endpoint: `POST /v1/chat/completions` (model `sarva`) — works with Cursor/Continue
- Legacy Studio: http://localhost:8000/web/studio/
- **Browser app (dev):** `cd apps/browser && npm install && npm run dev`

## Model routing (free tier)

Each user task is classified (code, debug, git, refactor, tests). Routely picks **one** best matching slot from `sarva_training/models_registry/` — all use OpenRouter `:free` models by default.

Set `NEURALROUTER_MAX_EXPERTS=1` (default) for single-model replies.

## Phase 1 scope

- Coding only (build, fix, refactor, git)
- Browser try-online + desktop download (month 5)
- Persistent memory via Postgres (`/saas/v1/threads`)

# Aksh by Aitotech

**India's AI coding platform** — Omni controller brain, 5 expert models, web search, skills → training.

```
Aitotech (company)
  └── Aksh (product)
        └── Omni (model + controller brain)
```

Full roadmap: [docs/AKSH_ROADMAP.md](docs/AKSH_ROADMAP.md)  
**Ship (idea → deploy):** [docs/AKSH_SHIP.md](docs/AKSH_SHIP.md)  
**Cursor parity:** [docs/CURSOR_PARITY.md](docs/CURSOR_PARITY.md)  
**User guide:** [README_USER.md](README_USER.md) · [docs/USER_CHECKLIST.md](docs/USER_CHECKLIST.md)  
**Web docs:** `/web/docs/` · **Landing:** `/web/index.html`  
Deploy: [docs/DEPLOY.md](docs/DEPLOY.md) · E2E: [docs/E2E_DEPLOY_INCH_BY_INCH.md](docs/E2E_DEPLOY_INCH_BY_INCH.md) · Privacy: [docs/PRIVACY.md](docs/PRIVACY.md)

## Stack

| Layer | Folder |
|-------|--------|
| Aksh API + Omni Controller | `neuralrouter/` |
| Web Search | `neuralrouter/search/` |
| Aksh Agent | `neuralrouter/agent/` |
| Codebase index (MVP) | `neuralrouter/index/` |
| SaaS billing | `saas/` |
| Omni training + skill ingest | `omni_training/` |
| Dashboard + chat + studio | `web/` |

## Quick start

```powershell
copy .env.example .env
docker compose up --build
```

- Dashboard: http://localhost:8000/web/dashboard/
- **Landing:** http://localhost:8000/web/index.html
- **Docs:** http://localhost:8000/web/docs/
- Chat: http://localhost:8000/web/chat.html
- Studio: http://localhost:8000/web/studio/

## M0 — Foundation verify

Run before any milestone work:

```powershell
.\scripts\verify_setup.ps1
# or
python scripts/verify_setup.py
```

Checks: Python imports, `brain_registry.json`, docker-compose syntax, `/health` smoke test (no live API keys required).

## M1 — Omni brain promote

**Read active brain (authenticated):** `GET /v1/omni/brain`

**Pre-promote checklist:**

```powershell
.\scripts\eval_omni_brain.ps1 omni-v1
python omni_training/brain_eval.py omni-v1
```

**Promote flow:**

```powershell
# After Colab training — register candidate
python omni_training/brain_register.py omni-v2 lora_hf --label "Omni v2" --adapter-repo YOU/repo --eval-score 0.85

# Checklist then hot-replace
python omni_training/brain_eval.py omni-v2
python omni_training/brain_promote.py omni-v2 --approve
```

Admin API: `GET /admin/omni/brain`, `POST /admin/omni/brain/promote` + header `X-Omni-Admin-Key`

Dashboard shows active brain version via `/v1/omni/brain`.

## M2 — Aksh Search

Chat UI search toggle: **Auto / On / Off** → `search` field on `POST /v1/chat`.

```json
POST /v1/chat
{ "message": "Aaj ka latest AI news?", "search": "auto" }
```

Set `AKSH_SEARCH_API_KEY` (Tavily/Serper) in `.env`. Without key, chat works — search skipped gracefully.

Dashboard **Aksh Search** card reads `/health` → `search.ready`.

## M3 — Training flywheel

```powershell
.\scripts\run_pipeline.ps1
```

Runs: `curate.py` → `build_dataset.py` → `research_report.py` → `scheduler.py`

**Skill ingest:** Dashboard → Add Skill → then run pipeline.

**Colab export:**

```powershell
python omni_training/colab_export.py
```

Upload `omni_training/data/colab_export.zip` to Colab. Scheduler suggests next `omni-vN` + `brain_register` command when thresholds met.

## M4 — Web Studio

`web/studio/index.html` — Monaco editor, localStorage projects, file tree, `.akshrules`, @file context on chat.

## M5 — Aksh Agent

- `POST /v1/agent/run` — plan → tools (read/write/grep) → synthesize (max 5 steps)
- Agent tab in Chat and Studio
- `neuralrouter/index/` — keyword index scaffold (Qdrant-ready)

## M6 — Production

- `deploy/railway.toml`, `deploy/render.yaml`
- `.env.production.example`
- Extended `GET /health` with version, brain, search

## Chat with search

Set `AKSH_SEARCH_API_KEY` (Tavily/Serper) in `.env`.

## Cursor

| Setting | Value |
|---------|--------|
| Base URL | `http://localhost:8000/v1` |
| Model | `auto` |

---

Omni v1 LoRA: https://huggingface.co/Ujjwal211/aitotech-omni-v1

# Aksh by Aitotech

**India's AI coding platform** — Omni controller brain, 5 expert models, web search, skills → training.

```
Aitotech (company)
  └── Aksh (product)
        └── Omni (model + controller brain)
```

Full roadmap: [docs/AKSH_ROADMAP.md](docs/AKSH_ROADMAP.md)

## Stack

| Layer | Folder |
|-------|--------|
| Aksh API + Omni Controller | `neuralrouter/` |
| Web Search | `neuralrouter/search/` |
| SaaS billing | `saas/` |
| Omni training + skill ingest | `omni_training/` |
| Dashboard + chat | `web/` |

## Quick start

```powershell
copy .env.example .env
docker compose up --build
```

- Dashboard: http://localhost:8000/web/dashboard/
- Chat: http://localhost:8000/web/chat.html

## New in Aksh v0.2

| Feature | Endpoint / module |
|---------|-------------------|
| **Omni Controller** | `neuralrouter/omni_controller.py` |
| **Aksh Search** | `search=auto\|on\|off` on `/v1/chat` |
| **Add Skill → train** | `POST /saas/v1/skills/register` |

## Chat with search

```json
POST /v1/chat
{ "message": "Aaj ka latest AI news?", "search": "auto" }
```

Set `AKSH_SEARCH_API_KEY` (Tavily/Serper) in `.env`.

## Cursor

| Setting | Value |
|---------|--------|
| Base URL | `http://localhost:8000/v1` |
| Model | `auto` |

---

Omni v1 LoRA: https://huggingface.co/Ujjwal211/aitotech-omni-v1

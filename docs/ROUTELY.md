# Routely — product overview

Routely is AitoTech's AI coding tool. Users describe what they want in plain English; Routely routes the task to the best **free OpenRouter model**, uses codebase context, and remembers chat history.

## Architecture (Phase 1)

| Module | Role |
|--------|------|
| **Router** | Classify task → pick one `:free` model from registry |
| **Memory** | Postgres threads — full chat history per project |
| **Workspace** | Files, editor, git, terminal |
| **Agent** | Multi-step jobs, multitasking (Redis queue) |

## Clients

1. **Browser** — `apps/browser/` — try online, no install
2. **Desktop** — Tauri (planned month 5) — local folder + real git

## Domains (planned)

| Service | URL |
|---------|-----|
| Marketing | `aitotech.in/routely` |
| Browser app | `app.routely.aitotech.in` |
| API | `api.routely.aitotech.in` |

## Cost

- User free tier: OpenRouter `:free` models only
- Infra: Railway Postgres + Redis (~$15–25/mo)

## Not in Phase 1

- General assistant (non-coding)
- Paid model tier
- Custom trained brain
- VS Code extensions

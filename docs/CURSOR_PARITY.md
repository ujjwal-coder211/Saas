# Cursor feature parity — Aksh vs what we built

Honest status after parity sprint. **100% identical to Cursor desktop is not possible in a browser** without forking VS Code (Electron). This doc says what works, what is partial, and **what you must do**.

---

## Feature matrix

| Cursor feature | Aksh status | How to use | You must do |
|----------------|-------------|------------|-------------|
| **Tab autocomplete** | ✅ Functional | Studio: Sarva suggests via `/v1/complete/tab` | Set `OPENROUTER_API_KEY` |
| **Inline edit (Cmd+K)** | ✅ Functional | Studio: select code → **Ctrl+K** → instruction | Same API key |
| **Composer (multi-file)** | ✅ Functional | Studio **Composer** tab → `/v1/composer/run` | Cloud project + API key |
| **Terminal agent** | ✅ Functional (sandbox) | Studio terminal drawer → `/v1/terminal/run` | Server needs `git`, `node`, `python` as needed |
| **Git UI** | ✅ Functional | Status / Diff / Commit buttons → `/v1/git/*` | **Install `git` on E2E server** (see Dockerfile) |
| **MCP runtime** | ⚠️ Partial | Add `.aksh/mcp.json` → `/v1/mcp/tools` lists servers | Full stdio MCP: set `AKSH_MCP_ENABLE=true` (future); use built-in tools today |
| **VS Code extensions** | ❌ Not in browser | Use **Cursor desktop** + Aksh API as Sarva backend | Or build **Aksh Desktop** (Electron) — separate project |
| **Debugger + LSP** | ⚠️ Partial | Monaco syntax only | Optional: add language-server containers (see below) |
| **Background agents** | ✅ Functional | `POST /v1/jobs/agent` → poll `GET /v1/jobs/{id}` | Production: enable Redis for multi-instance |
| **Bugbot (PR review)** | ✅ Functional | Studio **Bugbot review** → `/v1/review/code` | API key; GitHub PR bot = add `GITHUB_TOKEN` (you) |

---

## What we implemented (code)

| Module | Path |
|--------|------|
| Inline + Tab | `neuralrouter/parity/inline.py` |
| Composer | `neuralrouter/parity/composer.py` |
| Terminal sandbox | `neuralrouter/parity/terminal.py` |
| Git | `neuralrouter/parity/git.py` |
| MCP bridge | `neuralrouter/parity/mcp.py` |
| Background jobs | `neuralrouter/parity/jobs.py` |
| Bugbot review | `neuralrouter/parity/review.py` |
| API routes | `neuralrouter/parity/router.py` |
| Studio UI | `web/studio/index.html` |

---

## Your checklist for E2E deploy

### 1. Required env (`.env` on server)

```env
OPENROUTER_API_KEY=sk-or-v1-...
DATABASE_URL=postgresql://...
JWT_SECRET=long-random-string
SAAS_ALLOW_PUBLIC_SIGNUP=true
```

### 2. Server packages (Dockerfile / VM)

```dockerfile
RUN apt-get update && apt-get install -y git nodejs npm python3 python3-pip
```

Without **git**, Git UI buttons fail. Without **node/npm**, JS projects cannot run in terminal sandbox.

### 3. After deploy

1. Sign up → Dashboard → copy API key  
2. Studio → New cloud project  
3. Test: **Ctrl+K**, Tab completion, Composer, Terminal (`npm -v`), Git Status, Bugbot  

### 4. Optional — closer to Cursor desktop

| Goal | Your action |
|------|-------------|
| Cursor-like IDE + extensions | Install Cursor; point to `https://YOUR_API/v1`, model `sarva` |
| GitHub PR Bugbot | Add GitHub App + webhook (not shipped yet) |
| Full LSP | Run `pyright` / `typescript-language-server` sidecar; wire later |
| MCP tools live | Configure `.aksh/mcp.json`; enable stdio bridge when released |
| Persistent background jobs | Set `REDIS_URL` + we migrate jobs from memory |

---

## What Aksh still cannot match (truth)

1. **VS Code extension marketplace** — needs Electron/desktop fork  
2. **Native debugger (breakpoints)** — needs Debug Adapter Protocol integration  
3. **Cursor Tab speed** — Cursor uses custom small model; we use API round-trip  
4. **Unrestricted terminal** — Aksh sandbox blocks dangerous commands by design  

---

## API quick reference

```http
POST /v1/inline/edit
POST /v1/complete/tab
POST /v1/composer/run
POST /v1/terminal/run
GET  /v1/git/status?project_id=
GET  /v1/git/diff?project_id=
POST /v1/git/commit
GET  /v1/mcp/tools?project_id=
POST /v1/review/code
POST /v1/jobs/agent
GET  /v1/jobs/{job_id}
```

All require `Authorization: Bearer YOUR_SAAS_API_KEY`.

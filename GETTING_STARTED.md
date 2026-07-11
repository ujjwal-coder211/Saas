# Getting Started — Saira / Sarva

Saira is a confidence-gated routing agent. **Sarva**, its conductor, self-assesses
each task and either answers it with a cheap model or delegates to a stronger
open-weight teacher, refining the result before returning it. The app is an
**OpenAI-compatible AI gateway** — you can point Cursor, Continue, or any OpenAI
client at it.

This guide takes you from a fresh clone to a working, usable server in ~5 minutes.

---

## 1. Prerequisites

- **Python 3.11+** (3.12 recommended) — for local run
- **OR Docker + Docker Compose** — for the containerized path
- An **OpenRouter API key** (free): https://openrouter.ai/keys
  The default model registry uses free `:free` models, so this is the only key you need to start.

---

## 2. Install

### Option A — Local (venv)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### Option B — Docker

Nothing to install beyond Docker; see step 4.

---

## 3. Configure

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Edit `.env` and set the one required key:

```ini
OPENROUTER_API_KEY=sk-or-v1-...        # required — get one at openrouter.ai/keys

# For local dev without auth (do NOT use in production):
NEURALROUTER_ALLOW_UNAUTH=true

# For real API auth, instead set client keys (comma-separated):
# NEURALROUTER_API_KEYS=mykey1,mykey2
```

Everything else in `.env.example` is optional (Postgres, Stripe, NVIDIA NIM,
Moonshot, etc.). The app runs fine with just `OPENROUTER_API_KEY`.

---

## 4. Run

### Local

```bash
uvicorn neuralrouter.main:app --host 0.0.0.0 --port 8000
```

`.env` is loaded automatically on startup.

### Docker

```bash
docker compose up --build
```

Server is now at **http://localhost:8000**.

---

## 5. Verify it works

One command (no API key needed — checks the core endpoints in-process):

```bash
python scripts/smoke_local.py
```

Expected tail:

```
[/health]          200  brain=sarva-v2  models=6
[/v1/models      ] 200
[/v1/sarva/brain ] 200
[/api            ] 200
RESULT: READY ✅
```

Or hit the running server directly:

```bash
curl http://localhost:8000/health
```

---

## 6. Use it

### Native chat

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "write a Python function to reverse a linked list"}'
```

(With auth enabled, add `-H "Authorization: Bearer <your NEURALROUTER_API_KEYS value>"`.)

### OpenAI-compatible (Cursor / Continue / any OpenAI SDK)

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <your key>" \
  -H "Content-Type: application/json" \
  -d '{"model": "sarva", "messages": [{"role": "user", "content": "hello"}]}'
```

**Cursor / OpenAI client config:**
- Base URL: `http://localhost:8000/v1`
- Model: `sarva`
- API key: any value from `NEURALROUTER_API_KEYS`

### Agent (multi-step)

```bash
curl -X POST http://localhost:8000/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message": "add a health endpoint and a test for it", "project_id": "demo"}'
```

### Key endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | status, active brain, providers |
| `POST /v1/chat` | native Sarva chat |
| `POST /v1/chat/completions` | OpenAI-compatible |
| `GET /v1/models` · `GET /v1/router/models` | model list |
| `GET /v1/sarva/brain` | active conductor brain |
| `POST /v1/agent/run` | agent workflows |
| `POST /admin/sarva/brain/promote` | promote a brain (admin key) |

---

## 7. The trained Sarva conductor (optional)

By default the app uses the **rules brain** (`sarva-v2`) and routes to OpenRouter
models — no GPU needed. To use a **trained conductor**:

Brains live in `sarva_training/brain_registry.json`:
- `sarva-v2` — active (rules + reasoning)
- `sarva-v3` — trained on the §10 seed (template smoke-test), HF `Ujjwal211/aitotech-sarva-v3`
- `sarva-v4` — trained on **real corpora** (Magicoder + SWE-bench + CodeFeedback), HF `Ujjwal211/aitotech-sarva-v4`

**Serve a trained brain (needs a GPU, e.g. RunPod):**

```bash
# on a GPU pod:
bash deploy/runpod/setup.sh
HF_TOKEN=... ADAPTER_REPO=Ujjwal211/aitotech-sarva-v4 python deploy/runpod/serve_sarva.py
```

Then point the app at it and it will route self-execution to the trained Sarva:

```ini
SARVA_INFERENCE_URL=https://<your-pod-endpoint>
```

**Train your own** (see also `sarva_training/data/saira_conductor_seed/`):

```bash
# real-corpora dataset (on a GPU pod with `datasets` installed):
python sarva_training/data/saira_conductor_seed/build_real_dataset.py --limit 2000
# then QLoRA train + push:
HF_TOKEN=... DATA_PATH=sarva_training/data/export/saira_conductor_real_v1_train.jsonl \
  ADAPTER_REPO=Ujjwal211/aitotech-sarva-vN python deploy/runpod/train_sarva.py
```

---

## 8. Develop & evaluate

```bash
# full test suite (98 tests)
python -m pytest neuralrouter/tests -q

# §14 evaluation harness (RQ1–RQ6)
python -m neuralrouter.evaluation

# §6 security red-team (12 attacks, 6 threat categories)
python -m neuralrouter.security.redteam
```

---

## 9. Deploy to production

- **Docker (prod):** `docker compose -f docker-compose.prod.yml up -d`
- **Railway:** `railway.toml` · **Render:** `render.yaml`
- Full guide: [docs/DEPLOY.md](docs/DEPLOY.md)

For production, set: `NEURALROUTER_API_KEYS` (real auth), `DATABASE_URL`
(Postgres for memory/usage), and unset `NEURALROUTER_ALLOW_UNAUTH`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `providers: openrouter=false` in /health | set `OPENROUTER_API_KEY` in `.env` |
| 401 / auth errors | set `NEURALROUTER_API_KEYS`, or `NEURALROUTER_ALLOW_UNAUTH=true` for local dev |
| `ModuleNotFoundError` | run from the repo root; `pip install -r requirements.txt` |
| chat returns an error string | check the OpenRouter key is valid and the `:free` model strings in `/health` aren't 404 |

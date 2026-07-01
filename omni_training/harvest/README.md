# Saira Harvest Engine

Modular, production-oriented async client for batch-querying LLM APIs
(OpenRouter-compatible) across many queries and many models, with:

- **Producer/consumer worker pool** (`src/engine/crawler.py`) instead of an
  unbounded `asyncio.gather` flood.
- **Per-model 3-state circuit breaker** (`src/engine/circuit_breaker.py`):
  CLOSED → OPEN → HALF_OPEN, so one failing model doesn't burn retries
  forever or take down the whole run.
- **Adaptive concurrency** (`src/engine/scheduler.py`): worker capacity
  grows on sustained success and shrinks on sustained failure, bounded by
  `min_workers`/`max_workers` in config.
- **Atomic, batched JSONL writer with fsync** (`src/storage/writer.py`): a
  crash loses at most one buffered batch, not the whole output file.
- **SQLite dedupe ledger + usage table** (`src/storage/database.py`): safe
  re-runs (already-processed query/model pairs are skipped) and a durable
  record of token usage per call.
- **Token/cost tracking** (`src/utils/metrics.py`): usage extracted from
  each response and priced from `config/settings.yaml`.
- **Structured JSON logging** (`src/utils/logger.py`): ships straight into
  ELK/Datadog-style pipelines.
- **No secrets in code or CLI args**: the API key is read only from the
  `OPENROUTER_API_KEY` environment variable.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export OPENROUTER_API_KEY="sk-..."
```

## Run

```bash
python -m src.main --queries queries.txt --config config/settings.yaml
```

`queries.txt` is a newline-delimited list of prompts. Models come from
`config/settings.yaml` (`models:` list) unless overridden with
`--models model-a,model-b`.

Output:
- `reservoir.jsonl` — harvested results, one JSON object per line.
- `state.db` — SQLite dedupe ledger + per-call usage/cost table.
- `harvest.log` — structured JSON logs (also mirrored to stdout).

Stop any time with `Ctrl+C`: in-flight requests are allowed to finish, the
writer flushes its buffer, and a cost summary is logged before exit.

## Tests

```bash
pip install pytest pytest-asyncio
pytest tests/
```

## Config reference

See `config/settings.yaml` for all tunables: retry/backoff, circuit breaker
thresholds, concurrency bounds, batch/flush sizing, and per-model pricing
for cost estimation.

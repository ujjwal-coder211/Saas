# Dataset Card — Sarva Conductor Seed

- schema: `sarva-conductor-1.0`  | paper: Saira v5.0 / v6.1  | scale: 0.0016  | seed: 42
- total rows: **2,440**

## Composition vs §10 targets

| Stage | Category | Seed rows | §10 target (scale=1.0) |
|---|---|---:|---:|
| 1 | code_generation | 320 | 200,000 |
| 1 | debugging | 192 | 120,000 |
| 1 | code_review | 128 | 80,000 |
| 1 | refactoring | 96 | 60,000 |
| 1 | architecture | 64 | 40,000 |
| 2 | file_ops | 128 | 80,000 |
| 2 | browser_automation | 112 | 70,000 |
| 2 | shell_system | 96 | 60,000 |
| 2 | multi_tool | 128 | 80,000 |
| 2 | voice_to_action | 64 | 40,000 |
| 2 | error_recovery | 32 | 20,000 |
| 3 | routing | 80 | 50,000 |
| 4 | rlef | 1,000 | 1,000 |

## Provenance
- Seed payloads are template placeholders (§10 sources not bundled).
- Real data enters via `convert_public.py` (The Stack v2, SWE-bench, Mind2Web, WebArena, OSWorld, CodeReviewer).
- Distillation teachers are open-weight only (§4.4); the premium arbiter is escalation-only and never a source.

## Intended use
- Schema validation + QLoRA smoke-test of the conductor decision structure.
- Curriculum scaffold: assemble Stage 1→2→3→4 in dependency order (§10).

## Out-of-scope / cautions
- Not a benchmark; no held-out eval split included.
- Confidence + reward values are authored/sampled, not calibrated/measured.
- Do not train the full template scale as-is; wire real corpora first.

# Sarva Conductor Training Data (Saira §10)

JSONL training data for **Sarva**, the confidence-gated conductor of the Saira
architecture. This kit produces data in the exact shape the paper's 4-stage
pipeline (§10) and conductor heads (§4) require, and ships a **runnable seed** so
you can validate your fine-tuning pipeline before spending compute on the full
targets.

## What this is (and is not)

Your current `sarva_master_train` (~972 examples) is a proof-of-concept conductor
QLoRA. The paper commits to a ~900K, 4-stage curriculum. This kit gives you:

- ✅ the **correct conductor schema** for all four stages (§4.2 heads),
- ✅ a **generator** that reproduces §10's category proportions at any size,
- ✅ a **validated seed** (2,440 rows) you can train on today,
- ✅ a **converter** (`convert_public.py`) that folds the real corpora and
  teacher-distillation outputs the paper depends on into the *same* schema.

It is **not** a substitute for those real corpora. §10.1/§10.2 draw from The
Stack v2, SWE-bench, Mind2Web, WebArena, OSWorld, CodeReviewer, etc., plus
distillation from open-weight teachers (§4.4). A template generator can give you
correct *structure* and diversity of *control-flow decisions*, but the code/tool
*payloads* in the seed are placeholders labelled as such. Real quality comes from
`convert_public.py`. Treat the seed as a schema harness and a smoke-test corpus.

## The schema (one conductor turn)

Every row is a chat record: `system` (stable conductor prompt) → `user` (task +
context envelope) → `assistant` (the conductor's decision, as tagged sections):

```
<sarva:assess>    {confidence, threshold, gate, stage_persona, rationale}   # §4.3 self-assessment
<sarva:classify>  {task_type, distribution}                                 # §4.2 classification
<sarva:route>     {decision:"local"} | {decision:"delegate", models:[...]}  # §4.2 routing policy
<sarva:execute>   ...code / tool-plan...        # when gate = execute_local  # §4.3
<sarva:refine>    ...refined teacher draft...   # when gate = delegate       # §4.3
<sarva:synthesis> {scores, strategy}            # multi-model only           # §7.2
<sarva:reward>    {components, weights, R, kept_for_ppo}  # Stage 4 only      # §8.1
```

Ordering invariant (checked by `validate.py`): **assess → classify → route**,
then execute/refine. Swap `serialize_turn()` in `sarva_schema.py` if you prefer
pure JSON or ChatML tool-calls; nothing else depends on the serialization.

Key behaviours baked into the data, each traceable to the paper:

| Behaviour | Section | How it shows up |
|---|---|---|
| Per-class confidence gate | §4.3 | `threshold` is elevated (0.88) for high-stakes types; gate = execute_local vs delegate |
| Conservative persona curriculum | §4.3 | `stage_persona` early→mid→mature; early rows delegate almost everything |
| Open-weight teachers only | §4.4 | `route.models` never distills from the premium arbiter |
| Tier-gated monetization | §4.2 | free tier → premium weight 0, capped at mid pool |
| Permission tiers + injection escalation | §6.2/§6.3 | tool plans carry `risk`/`approval`; untrusted content escalates one tier and is treated as inert |
| DAG decomposition | §7.1 | compound requests emit a vertex graph with parallelism |
| Synthesis strategies | §7.2 | multi-model routes attach defer/vote/merge by Q-spread |
| Execution-feedback reward | §8.1/§8.2 | Stage-4 rows carry composite `R` and the `|R|>0.3` PPO filter |

## Usage

```bash
# runnable seed for all four stages (default scale, ~2.4K rows, ~4.7 MB)
python sarva_datagen.py --stage all --scale 0.0016 --out ./out

# one stage, custom size
python sarva_datagen.py --stage 1 --scale 0.01 --out ./out

# full §10 targets — WARNING: ~901K rows, ~1.8 GB of PLACEHOLDER payloads.
# Only meaningful once you've routed real corpora through convert_public.py.
python sarva_datagen.py --stage all --scale 1.0 --out ./full

# validate any output
python validate.py "out/*.jsonl"
```

`--scale` multiplies every §10 target. `scale=1.0` reproduces the paper's tables
exactly (Stage 1 = 500K, Stage 2 = 350K, Stage 3 = 50K); Stage 4 emits one full
~1K RLEF cycle (§8.2) regardless of scale ≤ 1.

## Building the real thing (recommended order)

1. **Schema smoke-test.** Train a QLoRA on the seed. Confirm the model emits
   well-formed `<sarva:*>` sections and respects the gate. This replaces your
   972-example run as a structural baseline.
2. **Stage 1/2 from real corpora.** Wire the loaders in `convert_public.py`
   (`load_the_stack_v2`, `load_swebench`, `load_mind2web`, `load_osworld`, …).
   The mapping logic is complete; only the `datasets.load_dataset(...)` I/O is
   left to your environment. Merge with a small fraction of seed rows to keep the
   conductor-decision distribution intact.
3. **Distillation.** Run tasks through open-weight teachers (§4.4), capture
   outputs, feed to `code_task_to_record(..., gate="delegate", teacher=...)`.
   The converter refuses closed-API teachers by assertion.
4. **Stage 3.** Routing decisions can stay largely synthetic (they teach policy,
   not code), but replace `pool_state`/budgets with logged production values as
   you accumulate them.
5. **Stage 4 (RLEF).** Replace sampled outcomes with **real** execution results
   via `execution_to_reward_record(...)`: run SWE-bench FAIL_TO_PASS tests, read
   the linter, measure cost/latency. `R_exec` maps exactly as §8.1.

## The 30B / Nemotron note

The paper commits to a ~30B Nemotron-class base (§4.1); your Unsloth run fell back
to 14B Qwen because `nemotron_h` isn't Unsloth-trainable. This data is
**base-agnostic** — it's plain chat JSONL. For the 30B non-Unsloth path, the same
files feed a standard HF `SFTTrainer` / TRL `PPOTrainer` pipeline; only the
Stage-4 `chosen_route`/`rejected_route` fields in `meta` are there to support an
optional DPO-style pairing if you don't want full PPO.

## Files

| File | Purpose |
|---|---|
| `sarva_schema.py` | Constants, teacher pool, tiers, reward/synthesis math, system prompt — all §-cited |
| `sarva_datagen.py` | Stage builders + CLI |
| `convert_public.py` | Map real corpora + distillation into the schema |
| `validate.py` | JSONL + tagged-block + ordering validator |
| `out/*.seed.jsonl` | The generated seed (Stage 1–4) |
| `out/manifest.json` | Row counts + composition per stage |
| `dataset_card.md` | Composition vs §10 targets, provenance, limitations |

## Honest limitations

- Seed code/tool payloads are **placeholders**; only the conductor-decision
  structure around them is trainable signal until you run step 2–3 above.
- Full-scale template output is ~1.8 GB of low-diversity payloads — not worth
  training on as-is. Scale up **after** wiring real corpora.
- Stage-4 rewards in the seed are **sampled**, not measured. Real RLEF needs real
  execution (`execution_to_reward_record`).
- Confidence values are authored around thresholds, not calibrated. A trained
  self-assessment head (the paper's first item of future work, §4.3) replaces
  them; this data only teaches the *shape* of the decision.

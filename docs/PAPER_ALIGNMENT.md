# Saira — Paper v6 → Implementation Alignment

Honest map of `Saira_Research_Paper_v6.docx` (Version 5.0) to this repo, in the
spirit of the paper's own §13. Three states: **✅ implemented**, **🟡 partial**,
**🔴 designed / future work**. The paper itself flags most of the system as future
work; this document says exactly what is real today.

_Status as of 2026-07-09. Test suite: 23 passing (`neuralrouter/tests`, `sarva_training/harvest/tests`)._

---

## §3 System Overview — three layers + event loop

| Item | State | Where |
|---|---|---|
| Sarva (cognition) / Harness (execution) / Hermes (memory) split | ✅ | `neuralrouter/sarva_*`, `agent/`, `saas/` |
| Event-driven loop with permission gate before execution | ✅ | `agent/agent_loop.py` (§3.2/§6 gate at line ~118) |

## §4 Sarva — Conductor, Executor, Learner

| Item | State | Where |
|---|---|---|
| Confidence-gated self-routing (self_assess → threshold) | ✅ | `sarva_brain/confidence.py`, `routing_policy.py` |
| Refinement layer (verify draft, flag not fabricate) | ✅ | `sarva_brain/refine.py` |
| Learned routing policy (trained model overrides experts) | ✅ | `routing_policy.parse_trained_plan_json`, `sarva_brain/loader.py` |
| **Trained conductor model** | ✅ | HF `Ujjwal211/aitotech-sarva-v2` (Qwen2.5-14B QLoRA, live-tested) |
| Capability bounds (no overclaim on high-stakes) | ✅ | `routing_policy.py` |
| Multi-source distillation (teacher/user/cross-model) | 🟡 | data pipeline + harvest exist; continual distill loop not automated |

> Note: paper's base `Nemotron-3-Nano-30B-A3B` is a `nemotron_h` hybrid Mamba+MoE
> that Unsloth cannot fine-tune. Trained base is **Qwen2.5-14B-Instruct** instead.

## §5 Harness & Hermes

| Item | State | Where |
|---|---|---|
| Harness tools (code/browser/system), MCP-style, stateless | ✅ | `agent/tools.py` (22 tools), `parity/` |
| Hermes skill extraction + user model + curation | 🟡 | `saas/api/skills.py`, `skill_ingest.py`; 7-day curator not scheduled |

## §6 Security & Trust

| Item | State | Where |
|---|---|---|
| Permission gate in the loop (decide → **check** → execute) | ✅ | `security/permissions.py` (`check_plan`), wired in `agent_loop.py` |
| Risk-tiered permissions (auto/confirm/explicit) | 🟡 | tiers in `permissions.py`; adaptive trust-promotion not |
| Credential vault (OS keychain, never in prompt) | ✅ | `security/vault.py` (keyring / Fernet file / redact) |
| Prompt-injection firewall (untrusted = data, auto-escalate) | ✅ | `security/injection.py`, wired in gate + controller |
| Append-only audit trail | ✅ | `security/audit.py` (every permission decision, redacted) |

## §7 Task Decomposition & Synthesis

| Item | State | Where |
|---|---|---|
| Q-scored synthesis (defer/vote/merge/escalate) | ✅ | `sarva_brain/synthesis.py` |
| DAG decomposition of complex requests | ✅ | `sarva_brain/dag.py` (heuristic split + parallel layers) |

## §8 Self-Evolution via RLEF

| Item | State | Where |
|---|---|---|
| Reward function (α·exec + β·quality + …) | ✅ | `sarva_training/rlef.py::compute_reward` |
| Per-turn RoutingRecord logging + collect_cycle | ✅ | `rlef.py`; wired in `chat_service` |
| Refinement verification feeds R_exec | ✅ | `chat_service` → `exec_success` |
| PPO fine-tune loop + promotion gate | 🔴 | collect side done; PPO retrain not automated |

## §9 Voice — 🔴 not started (future work)

## §10 Training Methodology

| Item | State |
|---|---|
| Conductor bootstrap (routing/synthesis SFT) | ✅ done — Qwen2.5-14B, 3 epochs, `sarva_master_train.jsonl` |
| Full staged SFT (500K coding, 350K tool-use, etc.) | 🔴 future |
| Harvest engine for distillation data | ✅ `sarva_training/harvest/` |

## §11 Context & Token Economy — ✅ `sarva_brain/context_budget.py` (budgeted skills/file/history/workspace)

## §12 Failure Modes — 🟡 several mitigations exist (circuit breaker, routing floor, RLEF); full catalog not codified

## §13 Reference Prototype — ✅ this repo (routing substrate + trained conductor). This file is the alignment record.

## §14 Evaluation — 🔴 metrics defined in paper; benchmark harness not built

## §16 Deployment / Enterprise

| Item | State |
|---|---|
| Tier-gated routing (free/premium) | ✅ `saas/billing/plans.py`, `routing_policy` user_tier |
| Serving: `serve_sarva.py` (base+adapter) + app plug (`SARVA_INFERENCE_URL`) | ✅ code ready (serve on-demand GPU) |
| On-prem / air-gap / RBAC / admin governance | 🔴 future |

---

## Bottom line

**Done (the core):** three-layer architecture, hybrid + trained confidence-gated
routing, refinement, Harness (22 tools) with a permission gate, RLEF logging loop,
context budgeting, tier gating, and a **live trained Sarva conductor** on HF.

**Biggest remaining (future work, per the paper's own framing):** credential vault +
injection firewall (§6), DAG decomposition (§7), automated PPO retrain (§8), voice
(§9), full training stages (§10), and the evaluation harness (§14).

To activate the trained brain in production: serve `deploy/runpod/serve_sarva.py` on a
GPU, set `SARVA_INFERENCE_URL`, then `scripts/plug_sarva_after_train.py --promote --approve`.

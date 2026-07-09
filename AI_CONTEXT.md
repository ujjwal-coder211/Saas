# AI_CONTEXT.md — Saira / Routely Build Context

> Yeh file AI (Claude Code) ke saath hui kaam ki **poori context** rakhti hai — kya banaya,
> kya badla, aur kya important hai. Agle session mein AI ya koi bhi developer isse padhke
> turant samajh jaaye ki project kahaan khada hai. Naya kaam hone par isi file ko update karte rehna.

---

## 1. Project ek line mein

**Saira** (research paper ka naam) = **Routely** (product, by Aitotech) — ek universal AI agent
jiska dimaag **Sarva** conductor model hai. Sarva har task ke liye best free LLM choose karta hai
(learned routing), aur system teen layers par bana hai: **Sarva** (cognition), **Harness** (execution),
**Hermes** (memory/learning).

- GitHub: https://github.com/ujjwal-coder211/Saas
- Local repo: `C:\Users\ujjwa\Saas`
- Research paper: **`Saira_Research_Paper_v6.docx`** (andar "Version 5.0", Jul 2026) — latest spec. (v2/v4 purane.)
  - **Conductor ab "Sarva" naam se hai** (= code ka "Sarva"). Sarva = Conductor + Executor + Learner:
    confidence-gated self-routing + refinement + multi-source distillation.
  - v6 poora **honest academic report** ban gaya — "designed vs implemented vs validated" clearly alag.
    Saaf likha: **abhi koi trained model nahi**, saare targets sirf hypotheses.
  - Naye sections: **§2 Related Work, §8.3 Objective Stability, §13 Implementation Status
    (= harvest prototype).** Security (§6) MVP gate ab `permissions.py` mein hai; full vault later.
  - **GLM base model NAHI** — open-weight *delegate teacher* (GLM/DeepSeek/Kimi/Qwen). Base = Nemotron-Nano-30B.

---

## 2. Paper vs Repo — abhi kahaan khade hain (gap analysis)

| Paper layer (v6) | Status | Kahaan hai code |
|---|---|---|
| **Sarva — Cognition (Conductor+Executor+Learner)** | 🟢 Hybrid **rules + reasoning** routing policy; confidence self-assess; capability bound (no overclaim); refine. Trained 30B still not promoted. | `sarva_controller.py`, `sarva_brain/routing_policy.py`, `confidence.py`, `refine.py`, `loader.py` |
| **Harness — Execution** | 🟢 File/shell/git + browser + system tools (**22**). | `agent/tools.py`, `parity/` |
| **Hermes — Memory** | 🟡 Threads + skills; RLEF logging; context budget (§11). | `saas/api/threads.py`, `rlef.py`, `sarva_brain/context_budget.py` |
| **RLEF self-evolution (§8)** | 🟢 Loop close (logging + collect_cycle). | `sarva_training/rlef.py` |
| **Security & Trust (§6)** | 🟢 MVP permission gate in agent loop (`check_plan`). Vault / injection firewall later. | `security/permissions.py` |
| **Context budgeting (§11)** | 🟢 Skills/code/history/workspace soft caps. | `sarva_brain/context_budget.py` |
| **Failure Modes (§12)** | 🔴 Catalog + mitigations abhi nahi. | — |
| **Enterprise/B2B (§16)** | 🟡 Tier-gated routing; on-prem/RBAC later. | `saas/billing/plans.py` |
| **Voice (§9)** | 🔴 Abhi tak nahi. | — |
| **Trained Sarva 30B** | 🔴 Train + promote pending (out of this pass). | RunPod kit ready |

**Honest verdict (2026-07-09):** Paper loop minus **GPU train** is end-to-end ready:
hybrid routing, security gate, context budget, refine, RLEF (+ historical prior),
22 tools, harvest, **inference serve** (`deploy/runpod/serve_sarva.py`),
**plug script** (`scripts/plug_sarva_after_train.py`). After RunPod push HF adapter:
serve `/plan` → set `SARVA_INFERENCE_URL` → `--promote --approve`. Active brain still
`sarva-rules-v0` until you promote. Dataset: `sarva_master_train.jsonl` (972) + v1 (2154).
`sarva-v2` candidate slot pre-registered for `Ujjwal211/aitotech-sarva-v2`.

---

## 3. Is session mein kya naya bana / kya change hua

### 🆕 Naye files

1. **`neuralrouter/parity/browser.py`** — Harness browser tools (paper §4.2.2), Chrome DevTools Protocol
   via Playwright. 8 tools: `browser_open / navigate / click / type / extract / screenshot / wait / execute`.
   - Ek **persistent worker thread** mein Chromium chalta hai → cookies/auth calls ke beech survive karte
     hain, aur Playwright sync API server ke asyncio loop se collide nahi karti.
   - Playwright **optional** hai — na ho to clean `{ok: false, error: "...install hint"}` return hota hai
     (crash nahi). Local browser ke liye: `pip install playwright && playwright install chromium`.

2. **`neuralrouter/parity/system_tools.py`** — Harness system tools (paper §4.2.3). 4 tools:
   `open_app / manage_clipboard / notify / screenshot_region`.
   - Native OS, koi hard dependency nahi (`clip`/`pbcopy`/`xclip`, `osascript`/`notify-send`/PowerShell toast).
   - Headless server par graceful degrade.

3. **`sarva_training/rlef.py`** — RLEF reward logging (paper §5.2.3 / §7.5.1 / §8.2).
   - `compute_reward(...)` = `0.45·R_exec + 0.25·R_quality + 0.15·R_cost + 0.10·R_latency + 0.05·R_user`
     (paper ka exact formula).
   - `RoutingRecord` dataclass = paper §5.2.3 record.
   - `build_and_log(...)` = reward compute + record banake JSONL ledger mein append (best-effort, kabhi raise nahi karta).
   - `collect_cycle(...)` = paper §8.2 — baseline `V = mean(reward)`, advantage `A = R − V`, `|A| > threshold`
     wale high-signal records rakhke retrain-ready batch + manifest likhta hai. 1,000 records par `ready_for_retrain` flag.

### ✏️ Changed files

4. **`neuralrouter/agent/tools.py`** — naye browser + system tools register hue.
   - `ALLOWED_TOOLS` 10 → **22 tools**.
   - Naya `_WRITE_TOOLS` set — write-class tools (browser_click/type/execute, open_app, clipboard, notify, etc.)
     work-mode read-only scope respect karte hain.
   - `run_tool(...)` mein 12 naye dispatch branches.

5. **`neuralrouter/chat_service.py`** — har turn par RLEF `RoutingRecord` log hota hai.
   - `run_chat(...)` mein `build_and_log(...)` call (best-effort, try/except wrapped — user response kabhi break nahi hota).
   - Import: `from sarva_training.rlef import build_and_log`.

6. **`.gitignore`** — `sarva_training/data/rlef/` add hua (runtime-generated records commit na ho).

### ✅ Verify / test

- Smoke test pass hua: 22 tools registered, browser bina Playwright graceful degrade, clipboard write OK,
  reward math `0.906` sahi component breakdown ke saath, `build_and_log` + `collect_cycle` round-trip OK.
- Test ledger (`sarva_training/data/rlef/`) cleanup kar diya gaya.
- **Kuch commit nahi hua** — user ne abhi commit nahi bola.

---

## 4. Sabse important baat (ⓘ padho — yeh #1 pending gap hai)

**Trained brain abhi bhi routing change nahi karta.** `sarva_native_plan_hint` (`neuralrouter/chat_service.py:181`)
sirf system *directives* inject karta hai — woh kabhi `activate_experts` ke model choice ko **override nahi karta**.
Matlab trained Sarva v2 aane ke baad bhi, jab tak yeh wire nahi hota, woh actually kaunsa model chalega yeh decide
nahi kar paata.

➡️ **Next code step (Step 2):** `plan_turn` / `run_chat` ko aise banana ki native hint experts ko override kare.
Tab tak routing rules-based hi rahega.

### 4.1 Sarva Phase-1 port (2026-07-05) — confidence + refine

`saira_harvest_1.zip` ke `src/sarva/` (v4 §3.3/§3.4) ko `neuralrouter/sarva_brain/` mein port kiya:
- **`confidence.py`** — `self_assess(query, task_type)` (lexical + optional historical blend) + `threshold_for()`.
  `sarva_controller.plan_turn` ab har turn ke liye confidence + `self_handled` decide karke `SarvaPlan` par set karta hai.
- **`refine.py`** — `refine(draft)` deterministic verification (Python syntax check, TODO/placeholder detection).
  `chat_service._run_with_plan` ab answer ko refine karke `ChatResult.verified` + `verification_issues` set karta hai,
  aur ye verification **RLEF ke R_exec signal** mein feed hota hai (pehle sirf proxy tha — ab real).
- **Note:** `saira_harvest_1.zip` `sarva_training/harvest/` (jo committed hai) ka bada superset hai. Humne
  Sarva *logic* port kiya (do parallel Sarva maintain nahi karna); `sarva_training/harvest/` abhi Phase-0-only stale copy hai.

⚠️ **Regression recovery (2026-07-05):** ek external tool (shayad Cursor) ne working-tree ke `tools.py` +
`chat_service.py` ko purane version par revert kar diya tha (browser tools + RLEF gayab). Committed HEAD safe tha —
dono HEAD se restore karke port dubara clean apply kiya. **Sabak: kaam ke beech Cursor/dusre editor repo par
git ops mat chalao, warna working tree revert ho sakta hai.**

---

## 4.5 Saira Harvest — training-data harvesting engine (NEW component, 2026-06-30)

Ek production-grade **async batch LLM harvesting engine** — ab repo mein `sarva_training/harvest/` ke andar
integrate ho chuka (2026-06-30). Yeh Sarva ke **training data pipeline** ka scale engine hai — model pool ko
bade paimane par query karke SFT / synthesis datasets aur routing labels banata hai
(paper §7.4: "run each task through all models in pool, measure R scores" ka exact tool).

**Features:**
- Producer/consumer worker pool crawler (`src/engine/crawler.py`) — unbounded `asyncio.gather` flood nahi.
- Per-model 3-state **circuit breaker** (CLOSED→OPEN→HALF_OPEN) — ek failing model poora run down na kare.
- **Adaptive concurrency** scheduler — success par workers badhte, failure par ghatte (`min/max_workers`).
- **Atomic batched JSONL writer** + fsync — crash mein max ek batch loss.
- **SQLite dedupe ledger** + usage/cost table — safe re-runs, per-call token cost record.
- Token/cost tracking + structured JSON logging. Secrets sirf `OPENROUTER_API_KEY` env se.

**Stack:** `aiosqlite`, `httpx`, `PyYAML`. OpenRouter-compatible endpoint.
**Run (harvest folder se):** `cd sarva_training/harvest && python -m src.main --queries queries.txt --config config/settings.yaml`
→ output `reservoir.jsonl` + `state.db`. Deps: `pip install -r sarva_training/harvest/requirements.txt`
(aiosqlite + PyYAML main `requirements.txt` mein bhi merge kiye).

**Saira mein role:** yeh harvest ka `reservoir.jsonl` → `sarva_training/` ke dataset builders
(`build_conductor_dataset.py` / `build_dataset.py` / `ingest_post_train.py`) mein feed hoga → RunPod par Sarva training.

**TODO (next):** `reservoir.jsonl` → dataset-builder format ka adapter likhna (harvest output ko conductor/routing/synthesis JSONL mein convert).

---

## 5. Roadmap — bache hue steps (order mein)

- **Step 0 ✅** — current data export commit karna (cot/routing/synthesis `.jsonl`; bade `.zip` ignore).
- **Step 0.5 ✅ (integrate done)** — **Saira Harvest** engine `sarva_training/harvest/` mein aa gaya.
  Baaki: `reservoir.jsonl` → dataset-builder format adapter, phir model pool query → RunPod training.
- **Step 1 (USER ka kaam) — PLATFORM CHANGED (2026-06-30):** base model wahi **Nemotron-Nano-30B**
  (no change), bas training ab **RunPod** par hogi (pehle Google Colab thi).
  Flow: Nemotron-Nano-30B → RunPod GPU pod par LoRA/QLoRA fine-tune → adapter HF par push
  (`Ujjwal211/aitotech-sarva-v2`) → `brain_registry.json` mein candidate register.
  - **RunPod kit ready:** `deploy/runpod/` — `train_sarva.py` (standalone QLoRA script, env-driven),
    `setup.sh` (deps), `README_RUNPOD.md` (exact step-by-step). Data repo mein committed
    (`conductor_v1_train.jsonl`, 2154 rows), to pod par sirf `git clone` + 4 commands.
  - Pod par: `bash deploy/runpod/setup.sh` → `export HF_TOKEN=...` → `python deploy/runpod/train_sarva.py`.
  - Colab notebook (`deploy/colab/`) ab secondary/fallback path hai.
- **Step 2 (NEXT CODE — #1 gap)** — trained brain ko routing mein wire karna (upar section 4 dekho).
- **Step 3** — `brain_eval.py` se eval, threshold (>2% RA) pass hone par `brain_promote.py` se `active_version_id` flip.
- **Step 4 ✅** — RLEF reward logging (is session mein ho gaya).
- **Step 5 ✅** — browser + system tools (is session mein ho gaya).
- **Step 6** — Voice pipeline (Whisper STT + TTS, paper §6). Abhi greenfield, kuch nahi bana.

---

## 6. RLEF loop kaise chalana hai (end-to-end)

1. Chat chalti rahe → har turn auto-log hota hai `sarva_training/data/rlef/routing_records.jsonl` mein.
   (Override: env `RLEF_RECORDS_PATH`.)
2. ~1,000 records jama hone par: `python -m sarva_training.rlef` → cycle batch + manifest banta hai
   `sarva_training/data/rlef/cycles/` mein.
3. Us batch ko Colab/training mein feed karo (routing-head LoRA).
4. `brain_eval.py` → pass ho to `brain_promote.py` → `active_version_id` flip.

---

## 7. Useful paths / commands

- Health: `http://localhost:8000/health`
- Dev run: `docker compose up --build` (ya `apps/browser` ke liye `npm install && npm run dev`)
- Reward weights / ceilings env se tunable: `RLEF_LATENCY_CEILING_S`, `RLEF_COST_CEILING`, `RLEF_CYCLE_SIZE`.
- Browser headed debug: env `BROWSER_HEADED=1`.

---

## 8. Plan change log

- **2026-06-30** — Training platform **Google Colab → RunPod**. Base model **Nemotron-Nano-30B (unchanged)**.
  (GLM 5.2 wala plan socha tha, phir cancel — base model same rakha, sirf platform RunPod kiya.)
- **2026-06-30** — **Saira Harvest** engine repo mein integrate kiya (`sarva_training/harvest/`, 18 files,
  `.pytest_cache` chhod ke) — Sarva ke liye scale par training-data harvesting tool (section 4.5 + Step 0.5).
  `aiosqlite` + `PyYAML` main requirements mein merge.
- **2026-06-30** — **RunPod training kit** banaya (`deploy/runpod/`): `train_sarva.py` + `setup.sh` +
  `README_RUNPOD.md`. Ab Sarva training pod par `git clone` + 4 commands se chalti hai (Colab ke bajaye).
- **2026-07-05** — Paper **v2 → v4** re-sync. Sarva ab Conductor+Executor+Learner. `saira_harvest_1` ka
  Phase-1 Sarva logic (confidence + refine) `neuralrouter/sarva_brain/` mein port; refine ab RLEF R_exec feed karta hai.
  v4 ke naye sections (Security §5, Failure Modes §12, Enterprise §13, Future of Work §14, Moat §15) abhi 🔴 pending.
- **2026-07-05** — External-tool regression se `tools.py`+`chat_service.py` recover kiye (HEAD se restore).
- **2026-07-09** — LIVE RunPod training (A40, SSH-driven). Findings: (1) RunPod Python PEP 668 —
  setup.sh ko `--break-system-packages` chahiye (fixed). (2) Paper ka `nvidia/Nemotron-3-Nano-30B-A3B`
  ek `nemotron_h` hybrid Mamba+MoE hai jise **Unsloth support nahi karta** — QLoRA ke liye default base
  ab `unsloth/Qwen2.5-14B-Instruct-bnb-4bit` (train_sarva.py). Nemotron-30B baad mein non-Unsloth pipeline se.
- **2026-07-05** — Paper **v4 → v6** ("v5.0"). Conductor ka naam **Sarva → Sarva** (paper mein; code abhi "Sarva").
  Naye: §2 Related Work, §8.3 Objective Stability, §13 Implementation Status (prototype + harvest, 29 tests).
  Honest reframe: koi trained model nahi, sab hypotheses. **Pending decision:** code mein Sarva→Sarva rename karna ya nahi.

---

_Last updated: 2026-06-30 — session: Harness browser/system tools + RLEF reward logging; plan change → GLM 5.2 open weights on RunPod._

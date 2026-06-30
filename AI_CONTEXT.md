# AI_CONTEXT.md — Saira / Routely Build Context

> Yeh file AI (Claude Code) ke saath hui kaam ki **poori context** rakhti hai — kya banaya,
> kya badla, aur kya important hai. Agle session mein AI ya koi bhi developer isse padhke
> turant samajh jaaye ki project kahaan khada hai. Naya kaam hone par isi file ko update karte rehna.

---

## 1. Project ek line mein

**Saira** (research paper ka naam) = **Routely** (product, by Aitotech) — ek universal AI agent
jiska dimaag **Omni** conductor model hai. Omni har task ke liye best free LLM choose karta hai
(learned routing), aur system teen layers par bana hai: **Omni** (cognition), **Harness** (execution),
**Hermes** (memory/learning).

- GitHub: https://github.com/ujjwal-coder211/Saas
- Local repo: `C:\Users\ujjwa\Saas`
- Research paper: `Saira_Research_Paper_v2.docx` (Downloads mein) — yeh full architecture spec hai.

---

## 2. Paper vs Repo — abhi kahaan khade hain (gap analysis)

| Paper layer | Status | Kahaan hai code |
|---|---|---|
| **Omni — Cognition** | 🟡 Sirf rules-based (paper §8.1 cold-start heuristic). Trained 30B model abhi wire nahi hua. | `neuralrouter/omni_controller.py`, `neuralrouter/omni_brain/loader.py`, `omni_training/` |
| **Harness — Execution** | 🟢 File/shell/git + **ab browser + system tools bhi** (is session mein add hue). | `neuralrouter/agent/tools.py`, `neuralrouter/parity/` |
| **Hermes — Memory** | 🟡 Threads + skills storage hai; RLEF reward logging **ab add ho gaya**. | `saas/api/threads.py`, `saas/api/skills.py`, `omni_training/skill_ingest.py` |
| **RLEF self-evolution** | 🟢 Pehle sirf scaffold tha, **ab loop close ho gaya** (logging + collect_cycle). | `omni_training/rlef.py` (NEW) |
| **Voice (STT/TTS)** | 🔴 Abhi tak nahi bana. | — |
| **Monetization (tier-gated routing)** | 🟢 Ban chuka. | `saas/billing/plans.py` |

**Honest verdict:** Body (Harness + SaaS + tier gating) aur training rig (dataset pipeline + Colab notebook +
brain hot-swap registry) ban chuke hain. Asli missing cheez = **trained brain khud** + voice + (ab tak)
browser/RLEF — jinme se browser aur RLEF is session mein ban gaye.

`omni_training/brain_registry.json` confirm karta hai: `active_version_id` abhi bhi `omni-rules-v0` hai;
`omni-v1` ek `candidate` hai jiska `eval_score: null`.

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

3. **`omni_training/rlef.py`** — RLEF reward logging (paper §5.2.3 / §7.5.1 / §8.2).
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
   - Import: `from omni_training.rlef import build_and_log`.

6. **`.gitignore`** — `omni_training/data/rlef/` add hua (runtime-generated records commit na ho).

### ✅ Verify / test

- Smoke test pass hua: 22 tools registered, browser bina Playwright graceful degrade, clipboard write OK,
  reward math `0.906` sahi component breakdown ke saath, `build_and_log` + `collect_cycle` round-trip OK.
- Test ledger (`omni_training/data/rlef/`) cleanup kar diya gaya.
- **Kuch commit nahi hua** — user ne abhi commit nahi bola.

---

## 4. Sabse important baat (ⓘ padho — yeh #1 pending gap hai)

**Trained brain abhi bhi routing change nahi karta.** `omni_native_plan_hint` (`neuralrouter/chat_service.py:181`)
sirf system *directives* inject karta hai — woh kabhi `activate_experts` ke model choice ko **override nahi karta**.
Matlab trained Omni v2 aane ke baad bhi, jab tak yeh wire nahi hota, woh actually kaunsa model chalega yeh decide
nahi kar paata.

➡️ **Next code step (Step 2):** `plan_turn` / `run_chat` ko aise banana ki native hint experts ko override kare.
Tab tak routing rules-based hi rahega.

---

## 5. Roadmap — bache hue steps (order mein)

- **Step 0 ✅** — current data export commit karna (cot/routing/synthesis `.jsonl`; bade `.zip` ignore).
- **Step 1 (USER ka kaam)** — Omni v2 ko Colab par train karna. Sirf user kar sakta hai (Google login chahiye).
  Notebook ready: `deploy/colab/README_COLAB_ONE_CLICK.md` → A100 → `HF_TOKEN` secret → Run all → push `Ujjwal211/aitotech-omni-v2`.
- **Step 2 (NEXT CODE — #1 gap)** — trained brain ko routing mein wire karna (upar section 4 dekho).
- **Step 3** — `brain_eval.py` se eval, threshold (>2% RA) pass hone par `brain_promote.py` se `active_version_id` flip.
- **Step 4 ✅** — RLEF reward logging (is session mein ho gaya).
- **Step 5 ✅** — browser + system tools (is session mein ho gaya).
- **Step 6** — Voice pipeline (Whisper STT + TTS, paper §6). Abhi greenfield, kuch nahi bana.

---

## 6. RLEF loop kaise chalana hai (end-to-end)

1. Chat chalti rahe → har turn auto-log hota hai `omni_training/data/rlef/routing_records.jsonl` mein.
   (Override: env `RLEF_RECORDS_PATH`.)
2. ~1,000 records jama hone par: `python -m omni_training.rlef` → cycle batch + manifest banta hai
   `omni_training/data/rlef/cycles/` mein.
3. Us batch ko Colab/training mein feed karo (routing-head LoRA).
4. `brain_eval.py` → pass ho to `brain_promote.py` → `active_version_id` flip.

---

## 7. Useful paths / commands

- Health: `http://localhost:8000/health`
- Dev run: `docker compose up --build` (ya `apps/browser` ke liye `npm install && npm run dev`)
- Reward weights / ceilings env se tunable: `RLEF_LATENCY_CEILING_S`, `RLEF_COST_CEILING`, `RLEF_CYCLE_SIZE`.
- Browser headed debug: env `BROWSER_HEADED=1`.

---

_Last updated: 2026-06-30 — session: Harness browser/system tools + RLEF reward logging add kiye._

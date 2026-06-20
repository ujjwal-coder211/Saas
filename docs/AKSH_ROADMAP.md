# Aksh by Aitotech — Product Roadmap

**Company:** Aitotech  
**Product:** Aksh (AI coding platform)  
**Model:** Omni (controller + proprietary brain)  
**Engine:** NeuralRouter (5 expert APIs)

---

## Feature checklist — Cursor vs Aksh (TARGET)

Legend:
- **Now** = shipped today in repo
- **Target** = must build (✅ = planned / required for Aksh v1)

| Feature | Cursor | Aksh Target | Now | Phase |
|---------|--------|-------------|-----|-------|
| Multi-model | ✅ | ✅ | ✅ API | A |
| Auto router | ✅ | ✅ | ✅ | A |
| **Omni controller brain** | — | ✅ | 🔨 scaffold | A→C |
| **Web search (latest info)** | ✅ | ✅ | 🔨 scaffold | B |
| Chat | ✅ | ✅ | ✅ web | A |
| Inline edit | ✅ | ✅ | ⬜ | C |
| Composer multi-file | ✅ | ✅ | ⬜ | C |
| Agent autonomous | ✅ | ✅ | ⬜ | C |
| Codebase @context | ✅ | ✅ | ⬜ | B→C |
| Projects | ✅ | ✅ | ⬜ | B |
| Rules / customization | ✅ | ✅ | ⚠️ env | B→C |
| **MCP / Skills + Add button** | ✅ | ✅ | 🔨 scaffold | B |
| **Skill codebase → Omni train** | — | ✅ | 🔨 scaffold | B→C |
| Automation / background | ✅ | ✅ | ⬜ | D |
| INR billing | ❌ | ✅ | ✅ SaaS | A |
| India data residency | ❌ | ✅ | ⚠️ | B→D |
| Own model (Omni) | ❌ | ✅ | ✅ v1 LoRA HF | C→D |

**All rows in “Aksh Target” = ✅** — yeh poora product vision hai; abhi kuch scaffold + Phase A live hai.

---

## 3 new pillars (aapki requirement)

### 1. Aksh Search — internet se latest jawab

User jab kuch puche jisme **fresh / live data** chahiye:

```
User query → Omni Controller decides: needs_search?
  → YES: Web Search (Tavily/Serper/Brave) → snippets
  → Expert model + search context → final answer
  → Log to vault (training opt-in only)
```

**UI:** Chat/Agent mein **Search toggle** (Auto / On / Off). Default **Auto** — Omni decide kare.

**Files:** `neuralrouter/search/web_search.py`, wired from `neuralrouter/omni_controller.py`

---

### 2. Omni — main controller brain (sab experts ko control)

Omni sirf “trained model file” nahi — **runtime orchestrator**:

| Decision | Omni controller kya kare |
|----------|---------------------------|
| Kaun sa expert? | nemotron / kimi / qwen / … |
| Collaborative? | 1 vs 3 experts |
| Web search? | On/off + query rewrite |
| Output format | code / prose / Hinglish / steps |
| MCP/Skill? | Kaun sa tool call |
| User satisfaction signal | Retry/thumbs → next routing |

**Evolution:**
- **Phase A:** Rule + LLM hybrid (`omni_controller.py`) — keyword + optional small model
- **Phase C:** Fine-tuned Omni LoRA as controller (HF adapter)
- **Phase D:** Omni native — experts fallback only

**Files:** `neuralrouter/omni_controller.py`

---

### 3. Add Skill / MCP → direct training ingest

User dashboard: **Add → MCP or Skill** (path / Git URL / upload)

```
User adds skill/MCP
  → skill_ingest scans codebase (SKILL.md, tools, examples)
  → Generates training rows (tool usage patterns, API shapes)
  → Vault → curate → omni_v1_train.jsonl
  → Next Colab round: Omni learns that skill
```

**Trust:** Only tenant’s opt-in + their added skills; vault encrypted.

**Files:** `omni_training/skill_ingest.py`, API `POST /saas/v1/skills/register`

---

## Phase map (all features → ✅)

| Phase | Deliverable | Features unlocked |
|-------|-------------|-------------------|
| **A** (now) | NeuralRouter SaaS live | Multi-model, auto, chat, billing, Omni controller v0 |
| **B** | Aksh Web Studio | Projects, @context v1, Search, Skills Add UI, rules file |
| **C** | Aksh Agent | Inline, Composer, agent loop, MCP runtime, skill→train auto |
| **D** | Aksh Desktop + Omni native | Background jobs, full IDE, Omni controller model |

---

## Architecture

```
                    ┌─────────────────┐
                    │  Aksh Client    │
                    │  IDE / Web / Agent│
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Omni Controller │  ← main brain (smart routing)
                    │  search? tools? │
                    └────────┬────────┘
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        Web Search    Expert Models    MCP / Skills
        (internet)    (5 brains)       (user added)
              │              │              │
              └──────────────┼──────────────┘
                             ▼
                    ┌─────────────────┐
                    │ Omni Training   │  ← skill codebase auto-ingest
                    │ Vault → Colab   │
                    └─────────────────┘
```

---

## Implementation status (repo)

| Module | Path | Status |
|--------|------|--------|
| Omni controller | `neuralrouter/omni_controller.py` | Scaffold |
| Web search | `neuralrouter/search/web_search.py` | Scaffold |
| Skill ingest | `omni_training/skill_ingest.py` | Scaffold |
| Skills API | `saas/api/skills.py` | Scaffold |
| **Brain registry** | `omni_training/brain_registry.json` | Live |
| **Brain promote** | `omni_training/brain_promote.py` | Live |
| Roadmap | `docs/AKSH_ROADMAP.md` | This file |

Execute order: wire controller into `chat_service.py` → enable search env → skills register endpoint → Web Studio UI.

---

## Omni brain versioning — train chalta rahe, brain replace jab ready

Training **code/files se continuous** chalegi. Jab naya version train ho aur **aap approve** karo → **main brain hot-replace**.

```
Aksh logs + skills
    → curate.py → build_dataset.py
    → Colab SFT (omni-v2, omni-v3, …)
    → brain_register.py   # status = candidate
    → aap check (eval_score / manual)
    → brain_promote.py    # candidate → active, purana → archived
```

| Status | Matlab |
|--------|--------|
| `active` | Abhi live main brain — har request |
| `candidate` | Train ho gaya, approve pending |
| `training` | Colab chal raha |
| `archived` | Purana brain (rollback possible) |

**Registry:** `omni_training/brain_registry.json`  
**Abhi active:** `omni-rules-v0` (rules)  
**Ready candidate:** `omni-v1` (HF LoRA — promote jab tum bolo)

**CLI:**
```powershell
python omni_training/brain_register.py omni-v2 lora_hf --label "Omni v2" --adapter-repo YOU/repo --eval-score 0.85
python omni_training/brain_promote.py omni-v2 --approve
```

**Admin API:** `GET /admin/omni/brain`, `POST /admin/omni/brain/promote` + `X-Omni-Admin-Key`

Optional: `OMNI_INFERENCE_URL` — GPU par native Omni inference jab deploy ho.

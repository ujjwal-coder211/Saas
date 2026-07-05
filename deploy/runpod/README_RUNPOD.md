# Omni Conductor — RunPod Training (step by step)

Ye guide tumhare RunPod account (already logged in, ~$148 credit) par Omni ka
conductor brain train karne ke liye hai. **Base model:** `nvidia/Nemotron-3-Nano-30B-A3B`.
**Data:** repo mein already committed (`omni_training/data/export/conductor_v1_train.jsonl`, 2154 rows).

Jo main (AI) bana chuka hoon: training script + setup + ye guide + dataset — sab repo mein.
Jo tumhe karna hai: RunPod console par pod deploy + 4 commands. Neeche exactly wahi hai.

---

## Step 0 — HuggingFace write token (ek baar)

1. https://huggingface.co/settings/tokens → **New token** → type **Write** → copy.
2. Ye token training ke waqt `HF_TOKEN` env mein chahiye (base model pull + adapter push ke liye).

---

## Step 1 — RunPod pod deploy karo

1. RunPod console → left sidebar **Pods** → **Deploy** (ya home par "Deploy a Pod").
2. **GPU choose karo:**
   - Sasta + kaafi: **1× A40 (48 GB)** — ~$0.40–0.79/hr. 30B QLoRA 4-bit isme fit ho jaata hai.
   - Fast (optional): **1× A100 80GB** — mehenga par jaldi.
   - ⚠️ Tumhare screenshot wala `extensive_orange_worm` ($0.01/hr A40) shayad **stopped/spot** hai — training ke liye ek chalu (running) A40/A100 pod chahiye.
3. **Template:** "RunPod PyTorch 2.x" (CUDA 12.x) — koi bhi recent PyTorch template.
4. **Disk:** Container disk **60 GB+** (30B model weights ~18–20 GB download honge).
5. **Deploy** dabao. Pod "Running" hone ka wait karo.

---

## Step 2 — Pod se connect karo

Pod card par **Connect** → in mein se koi ek:
- **Web Terminal** (sabse simple), ya
- **Jupyter Lab** → new Terminal.

Ab pod ke andar terminal mein ho.

---

## Step 3 — Repo clone + setup (pod terminal mein)

```bash
cd /workspace
git clone https://github.com/ujjwal-coder211/Saas.git
cd Saas
bash deploy/runpod/setup.sh
```

`setup.sh` deps install karega aur GPU/VRAM print karega (CUDA available: True dikhna chahiye).

---

## Step 4 — Train (pod terminal mein)

```bash
export HF_TOKEN="hf_xxxxxxxxxxxxxxxxx"      # Step 0 wala write token
python deploy/runpod/train_omni.py
```

Bas. Script khud sab karega:
- Nemotron-30B 4-bit load
- 2154 rows par QLoRA train (3 epochs)
- adapter save + HuggingFace par push → **`Ujjwal211/aitotech-omni-v2`**

**Time:** A40 par roughly 2–4 ghante. Terminal band mat karo (ya `nohup ... &` / `tmux` use karo taaki
disconnect hone par bhi chale — optional).

### Tuning (optional env, run se pehle export karo)
```bash
export EPOCHS=3            # aur data hua to 2 kar sakte ho
export ADAPTER_REPO="Ujjwal211/aitotech-omni-v2"
export DATA_PATH="omni_training/data/export/conductor_bootstrap_train.jsonl"   # tez test (500 rows)
export RESUME_ADAPTER="Ujjwal211/aitotech-omni-v1"   # purane adapter se continue karna ho to
```

**Pehli baar test karna ho** to `conductor_bootstrap_train.jsonl` (500 rows) se chalao — ~30–45 min mein
pura pipeline verify ho jaata hai, phir full 2154 rows par chalao.

---

## Step 5 — Pod BAND karo (paisa bachao)

Push complete hone ke baad ("DONE. Pushed to ..."): RunPod console → pod → **Stop** ya **Terminate**.
Running pod paisa khaata hai — kaam ke baad turant band karo.

---

## Step 6 — Apne PC par: register + eval + promote

Training ho gaya to adapter HuggingFace par hai. Ab local repo mein register karo:

```powershell
cd C:\Users\ujjwa\Saas
python omni_training/brain_register.py omni-v2 lora_hf `
  --label "Omni Conductor v2" `
  --adapter-repo Ujjwal211/aitotech-omni-v2 `
  --base-model nvidia/Nemotron-3-Nano-30B-A3B
python omni_training/brain_eval.py omni-v2
```

Eval theek lage tabhi promote karo (`active_version_id` flip):
```powershell
python omni_training/brain_promote.py omni-v2 --approve
```

---

## Step 7 — (Baad mein) Inference serve karke routing mein wire karna

Trained brain ko *actually* routing badalne ke liye ek inference endpoint chahiye:
1. RunPod par ek serving pod (vLLM/TGI) chalao jo base + adapter serve kare, ek `/plan` endpoint de.
2. Apne app mein env set karo: `OMNI_INFERENCE_URL=https://<runpod-endpoint>`.
3. Code side ka **Step 2 gap** (loader ka `omni_native_plan_hint` ko routing override banana) —
   ye abhi bhi pending hai (dekho `AI_CONTEXT.md` section 4). Bolo to main wo code likh dun.

---

## Quick reference — sab commands ek jagah

```bash
# Pod par:
cd /workspace && git clone https://github.com/ujjwal-coder211/Saas.git && cd Saas
bash deploy/runpod/setup.sh
export HF_TOKEN="hf_xxx"
python deploy/runpod/train_omni.py
# -> phir pod STOP/TERMINATE
```

---

## Kya-kaun kar raha hai (summary)

| Kaam | Kaun |
|---|---|
| Training script, setup, dataset, ye guide | ✅ AI (ho gaya, repo mein) |
| HF write token banana | 👤 Tum (Step 0) |
| RunPod pod deploy + connect | 👤 Tum (Step 1–2) |
| 4 commands chalana | 👤 Tum (Step 3–4) |
| Pod band karna | 👤 Tum (Step 5) |
| register/eval/promote | 👤 Tum (Step 6) — ya bolo main karadun jab adapter ready ho |
| routing wire (Step 2 gap) + inference serve | ⏳ AI code likh dega jab bolo (Step 7) |

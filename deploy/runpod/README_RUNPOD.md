# Sarva Conductor — RunPod Training + Plug-in (end-to-end)

Train on RunPod → push HF → serve `/plan` → set URL → promote. App already wired.

**Base:** `nvidia/Nemotron-3-Nano-30B-A3B`  
**Default data:** `sarva_master_train.jsonl` (972) if present, else `conductor_v1_train.jsonl` (2154)  
**HF target:** `Ujjwal211/aitotech-sarva-v2`

---

## Step 0 — HuggingFace write token

1. https://huggingface.co/settings/tokens → **Write** token  
2. Training + push need `HF_TOKEN`

---

## Step 1–2 — Deploy + connect RunPod GPU pod

- GPU: **1× A40 48GB** (or A100)  
- Template: PyTorch 2.x / CUDA 12  
- Disk: **60GB+**  
- Connect via Web Terminal

---

## Step 3 — Clone + setup (on pod)

```bash
cd /workspace
git clone https://github.com/ujjwal-coder211/Saas.git
cd Saas
bash deploy/runpod/setup.sh
```

---

## Step 4 — Train (on pod)

```bash
export HF_TOKEN="hf_xxxxxxxx"
python deploy/runpod/train_sarva.py
```

Pushes adapter → **`Ujjwal211/aitotech-sarva-v2`**.

Optional:
```bash
export DATA_PATH="sarva_training/data/export/conductor_v1_train.jsonl"  # larger set
export EPOCHS=3
export ADAPTER_REPO="Ujjwal211/aitotech-sarva-v2"
```

---

## Step 5 — Stop training pod (save money)

Stop/Terminate the training pod after "DONE. Pushed to ...".

---

## Step 6 — Serve inference (new GPU pod OR same machine)

```bash
cd /workspace/Saas   # or re-clone
export HF_TOKEN="hf_xxxxxxxx"
export ADAPTER_REPO="Ujjwal211/aitotech-sarva-v2"
python deploy/runpod/serve_sarva.py
# listens on 0.0.0.0:8001  →  POST /plan  POST /synthesize  GET /health
```

Expose port **8001** (RunPod TCP / proxy). Copy public URL, e.g. `https://xxxx-8001.proxy.runpod.net`.

**Wiring test without GPU (local PC):**
```powershell
$env:SARVA_INFERENCE_MOCK="1"
python deploy/runpod/serve_sarva.py
```

---

## Step 7 — Plug into app (your PC)

```powershell
cd C:\Users\ujjwa\Saas

# Register/update candidate + promote
python scripts/plug_sarva_after_train.py --promote --approve `
  --inference-url "https://xxxx-8001.proxy.runpod.net"

# Or set env on Railway / .env (wins over registry artifact):
# SARVA_INFERENCE_URL=https://xxxx-8001.proxy.runpod.net
```

Restart API. Chat path already:
1. Calls `{SARVA_INFERENCE_URL}/plan`
2. Parses JSON → **overrides experts** (capability bounds still apply)
3. Falls back to hybrid rules+reasoning if URL down

Smoke:
```powershell
python scripts/smoke_sarva_stack.py
```

---

## Step 8 — Browser IDE (optional)

```powershell
cd apps/browser
# .env: VITE_ROUTELY_API_URL=https://your-api
npm run dev
```

Already posts to `/v1/chat` with Bearer API key.

---

## Quick command sheet

```bash
# TRAIN (pod)
bash deploy/runpod/setup.sh && export HF_TOKEN=hf_xxx && python deploy/runpod/train_sarva.py

# SERVE (pod)
export HF_TOKEN=hf_xxx ADAPTER_REPO=Ujjwal211/aitotech-sarva-v2
python deploy/runpod/serve_sarva.py

# PLUG (PC)
python scripts/plug_sarva_after_train.py --promote --approve --inference-url https://...
```

---

## Who does what

| Step | Who |
|------|-----|
| Scripts, serve, plug, hybrid routing, security, context | ✅ Done in repo |
| HF token + RunPod deploy + train + serve URL | 👤 You |
| `--promote --approve` after train | 👤 You (one command) |

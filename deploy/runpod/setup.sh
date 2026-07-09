#!/usr/bin/env bash
# Sarva Conductor — RunPod pod setup. Run once after the pod boots.
# Usage:  bash deploy/runpod/setup.sh
set -e

echo "==> Python / pip versions"
python --version
pip --version

echo "==> Installing training deps (Unsloth + TRL + PEFT stack)"
# RunPod base images use an externally-managed Python (PEP 668); allow system installs.
export PIP_BREAK_SYSTEM_PACKAGES=1
PIP="pip install --break-system-packages -q"
$PIP "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
$PIP --no-deps trl peft accelerate bitsandbytes datasets
$PIP huggingface_hub

echo "==> GPU check"
python - <<'PY'
import torch
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
    print("VRAM GB:", round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1))
PY

echo "==> Setup done. Now: export HF_TOKEN=...  then  python deploy/runpod/train_sarva.py"

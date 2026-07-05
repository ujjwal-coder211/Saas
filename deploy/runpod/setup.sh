#!/usr/bin/env bash
# Omni Conductor — RunPod pod setup. Run once after the pod boots.
# Usage:  bash deploy/runpod/setup.sh
set -e

echo "==> Python / pip versions"
python --version
pip --version

echo "==> Installing training deps (Unsloth + TRL + PEFT stack)"
pip install -q "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
pip install -q --no-deps trl peft accelerate bitsandbytes datasets
pip install -q huggingface_hub

echo "==> GPU check"
python - <<'PY'
import torch
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
    print("VRAM GB:", round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1))
PY

echo "==> Setup done. Now: export HF_TOKEN=...  then  python deploy/runpod/train_omni.py"

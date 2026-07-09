#!/usr/bin/env python3
"""Sarva Conductor — RunPod training script (QLoRA on Nemotron-Nano-30B).

Standalone version of deploy/colab/SARVA_CONDUCTOR_TRAIN.md, driven entirely by
environment variables so it runs unattended on a RunPod GPU pod.

Required env:
  HF_TOKEN         HuggingFace WRITE token (to pull base model + push adapter)

Optional env (sensible defaults):
  BASE_MODEL       default: nvidia/Nemotron-3-Nano-30B-A3B
  DATA_PATH        default: sarva_training/data/export/conductor_v1_train.jsonl
  ADAPTER_REPO     default: Ujjwal211/aitotech-sarva-v2
  RESUME_ADAPTER   default: (none) — set to continue from an existing adapter repo
  EPOCHS           default: 3
  LEARNING_RATE    default: 2e-4
  BATCH_SIZE       default: 2
  GRAD_ACCUM       default: 8
  MAX_SEQ_LEN      default: 4096
  LORA_RANK        default: 32
  OUTPUT_DIR       default: sarva_conductor_lora

Run:  python deploy/runpod/train_sarva.py
"""

from __future__ import annotations

import json
import os
import sys


def _env(name: str, default: str) -> str:
    v = os.environ.get(name, "").strip()
    return v if v else default


def main() -> int:
    hf_token = os.environ.get("HF_TOKEN", "").strip()
    if not hf_token:
        print("ERROR: HF_TOKEN env var is required (HuggingFace write token).", file=sys.stderr)
        return 2

    base_model = _env("BASE_MODEL", "nvidia/Nemotron-3-Nano-30B-A3B")
    data_path = _env("DATA_PATH", "sarva_training/data/export/conductor_v1_train.jsonl")
    adapter_repo = _env("ADAPTER_REPO", "Ujjwal211/aitotech-sarva-v2")
    resume_adapter = os.environ.get("RESUME_ADAPTER", "").strip()
    epochs = float(_env("EPOCHS", "3"))
    lr = float(_env("LEARNING_RATE", "2e-4"))
    batch_size = int(_env("BATCH_SIZE", "2"))
    grad_accum = int(_env("GRAD_ACCUM", "8"))
    max_seq_len = int(_env("MAX_SEQ_LEN", "4096"))
    lora_rank = int(_env("LORA_RANK", "32"))
    output_dir = _env("OUTPUT_DIR", "sarva_conductor_lora")

    if not os.path.exists(data_path):
        print(f"ERROR: DATA_PATH not found: {data_path}", file=sys.stderr)
        print("Run this from the repo root, or set DATA_PATH.", file=sys.stderr)
        return 2

    print("=" * 60)
    print("Sarva Conductor — RunPod training")
    print(f"  base_model   : {base_model}")
    print(f"  data_path    : {data_path}")
    print(f"  adapter_repo : {adapter_repo}")
    print(f"  resume       : {resume_adapter or '(fresh)'}")
    print(f"  epochs={epochs} lr={lr} batch={batch_size} grad_accum={grad_accum}")
    print(f"  max_seq_len={max_seq_len} lora_rank={lora_rank}")
    print("=" * 60)

    from huggingface_hub import login

    login(token=hf_token)

    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_len,
        load_in_4bit=True,
        dtype=None,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_rank,
        lora_alpha=lora_rank * 2,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing=True,
    )

    if resume_adapter:
        print(f"Continuing from adapter: {resume_adapter}")
        model.load_adapter(resume_adapter)

    from datasets import Dataset

    rows = []
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    def format_example(ex: dict) -> str:
        return tokenizer.apply_chat_template(
            ex["messages"], tokenize=False, add_generation_prompt=False
        )

    dataset = Dataset.from_list([{"text": format_example(r)} for r in rows])
    print("Training rows:", len(dataset))

    from trl import SFTTrainer, SFTConfig

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            output_dir=output_dir,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            num_train_epochs=epochs,
            learning_rate=lr,
            lr_scheduler_type="cosine",
            warmup_ratio=0.1,
            logging_steps=10,
            save_steps=100,
            fp16=True,
            dataset_text_field="text",
        ),
    )
    trainer.train()

    print(f"Saving adapter to {output_dir} and pushing to {adapter_repo} ...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    model.push_to_hub(adapter_repo)
    tokenizer.push_to_hub(adapter_repo)
    print("DONE. Pushed to", adapter_repo)
    print("Next (on your PC): register + eval + promote — see deploy/runpod/README_RUNPOD.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Omni Conductor — Colab Training (Option A bootstrap + Option B full)

Upload `colab_export.zip` from `Saas/omni_training/data/export/` to Colab.

## Round 1A — Bootstrap (500 rows)

Use `conductor_bootstrap_train.jsonl` — fast first train from your `files.zip`.

## Round 1B — Full (3000+ rows)

Use `conductor_v1_train.jsonl` after `build_best_dataset.py`.

---

## Cell 1 — Install

```python
!pip install -q "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
!pip install -q --no-deps trl peft accelerate bitsandbytes datasets
```

## Cell 2 — HuggingFace login

```python
from huggingface_hub import login
import os
login(token=os.environ["HF_TOKEN"])  # Colab secrets
```

## Cell 3 — Load model (YOUR base — 30B-A3B, NOT 4B)

```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="nvidia/Nemotron-3-Nano-30B-A3B",
    max_seq_length=4096,
    load_in_4bit=True,
    dtype=None,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=32,
    lora_alpha=64,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05,
    bias="none",
    use_gradient_checkpointing=True,
)

# Optional: continue from existing adapter
# model.load_adapter("Ujjwal211/aitotech-omni-v1")
```

## Cell 4 — Load dataset

```python
import json
from datasets import Dataset

DATA_PATH = "/content/colab_export/conductor_v1_train.jsonl"  # or conductor_bootstrap_train.jsonl

rows = []
with open(DATA_PATH) as f:
    for line in f:
        if line.strip():
            rows.append(json.loads(line))

def format_example(ex):
    return tokenizer.apply_chat_template(ex["messages"], tokenize=False, add_generation_prompt=False)

dataset = Dataset.from_list([{"text": format_example(r)} for r in rows])
print("Training rows:", len(dataset))
```

## Cell 5 — Train

```python
from trl import SFTTrainer, SFTConfig

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    args=SFTConfig(
        output_dir="omni_conductor_lora",
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        num_train_epochs=3,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        logging_steps=10,
        save_steps=100,
        fp16=True,
        dataset_text_field="text",
    ),
)
trainer.train()
```

## Cell 6 — Save + push

```python
ADAPTER_REPO = "Ujjwal211/aitotech-omni-v2"  # bump to v3 for Round 1B

model.save_pretrained("omni_conductor_lora")
tokenizer.save_pretrained("omni_conductor_lora")
model.push_to_hub(ADAPTER_REPO)
tokenizer.push_to_hub(ADAPTER_REPO)
print("Pushed to", ADAPTER_REPO)
```

## After Colab

```powershell
cd C:\Users\ujjwa\Saas
python omni_training/brain_register.py omni-v2 lora_hf ^
  --label "Omni Conductor v2" ^
  --adapter-repo Ujjwal211/aitotech-omni-v2 ^
  --base-model nvidia/Nemotron-3-Nano-30B-A3B
python omni_training/brain_eval.py omni-v2
# Deploy on RunPod, set OMNI_INFERENCE_URL, then:
python omni_training/brain_promote.py omni-v2 --approve
```

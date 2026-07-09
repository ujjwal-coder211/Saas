#!/usr/bin/env python3
"""Sarva inference server — /plan + /synthesize for trained conductor.

After RunPod QLoRA training, run this on a GPU pod (or CPU mock for wiring tests).
Railway / local app sets SARVA_INFERENCE_URL to this service; chat then overrides
experts with the returned JSON (capability bounds still apply).

Env:
  HF_TOKEN           pull private adapters
  BASE_MODEL         default nvidia/Nemotron-3-Nano-30B-A3B
  ADAPTER_REPO       default Ujjwal211/aitotech-sarva-v2
  ADAPTER_PATH       local adapter dir (wins over ADAPTER_REPO if set)
  SARVA_INFERENCE_MOCK=1   no GPU — hybrid rules+reasoning JSON (wiring smoke)
  PORT               default 8001
  HOST               default 0.0.0.0

Run:
  python deploy/runpod/serve_sarva.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MOCK = os.environ.get("SARVA_INFERENCE_MOCK", "").strip() in ("1", "true", "yes")
BASE_MODEL = os.environ.get("BASE_MODEL", "nvidia/Nemotron-3-Nano-30B-A3B").strip()
ADAPTER_REPO = os.environ.get("ADAPTER_REPO", "Ujjwal211/aitotech-sarva-v2").strip()
ADAPTER_PATH = os.environ.get("ADAPTER_PATH", "").strip()
HOST = os.environ.get("HOST", "0.0.0.0").strip()
PORT = int(os.environ.get("PORT", "8001"))

_model = None
_tokenizer = None

PLAN_SYSTEM = (
    "You are Sarva, an intelligent conductor AI. Analyze the user query and decide "
    "the best routing plan using BOTH rules and reasoning. Respond with valid JSON only. "
    "Fields: primary_model, secondary_models (list), parallel (bool), "
    "complexity (low/medium/high), reasoning_mode (on/off), "
    "confidence (0.0-1.0), self_executable (bool), task_type (string), "
    "reason (one line). Never claim you can answer everything — if unsure, "
    "self_executable=false and pick a strong teacher."
)

SYNTH_SYSTEM = (
    "You are Sarva. Synthesize the expert drafts into one clear answer. "
    "Do not invent facts that no draft stated."
)


def _load_gpu() -> None:
    global _model, _tokenizer
    if _model is not None:
        return
    hf_token = os.environ.get("HF_TOKEN", "").strip()
    if hf_token:
        from huggingface_hub import login

        login(token=hf_token)

    from unsloth import FastLanguageModel

    adapter = ADAPTER_PATH or ADAPTER_REPO
    print(f"Loading base={BASE_MODEL} adapter={adapter}")
    _model, _tokenizer = FastLanguageModel.from_pretrained(
        model_name=adapter if ADAPTER_PATH else BASE_MODEL,
        max_seq_length=4096,
        load_in_4bit=True,
        dtype=None,
    )
    if not ADAPTER_PATH and ADAPTER_REPO:
        # Base loaded — attach PEFT adapter from hub
        from peft import PeftModel

        _model = PeftModel.from_pretrained(_model, ADAPTER_REPO)
    FastLanguageModel.for_inference(_model)
    print("Model ready for inference")


def _generate(messages: list[dict[str, str]], *, max_new_tokens: int = 512) -> str:
    _load_gpu()
    assert _tokenizer is not None and _model is not None
    prompt = _tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = _tokenizer(prompt, return_tensors="pt").to(_model.device)
    out = _model.generate(**inputs, max_new_tokens=max_new_tokens, temperature=0.2, do_sample=True)
    text = _tokenizer.decode(out[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True)
    return text.strip()


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None


def _mock_plan(query: str) -> dict[str, Any]:
    from neuralrouter.sarva_brain.routing_policy import decide_routing

    trace = decide_routing(query)
    return {
        "primary_model": trace.primary_model,
        "secondary_models": trace.secondary_models,
        "parallel": trace.routing_mode == "multi_synthesize",
        "complexity": trace.complexity,
        "reasoning_mode": "on" if trace.task_type in ("reasoning", "security", "code") else "off",
        "confidence": trace.confidence,
        "self_executable": trace.self_executable,
        "task_type": trace.task_type,
        "reason": trace.reasoning_text()[:240],
        "mock": True,
    }


def plan_query(query: str) -> dict[str, Any]:
    if MOCK:
        return _mock_plan(query)
    raw = _generate(
        [
            {"role": "system", "content": PLAN_SYSTEM},
            {"role": "user", "content": query},
        ],
        max_new_tokens=400,
    )
    parsed = _extract_json(raw)
    if parsed:
        parsed.setdefault("reason", raw[:200])
        return parsed
    # Fallback: hybrid policy so the app never gets an empty plan
    fallback = _mock_plan(query)
    fallback["reason"] = f"parse_fallback: {raw[:120]}"
    fallback["mock"] = False
    fallback["parse_failed"] = True
    return fallback


def synthesize(query: str, drafts: list[str]) -> str:
    if MOCK:
        return "\n\n".join(d for d in drafts if d)[:8000] or "(no drafts)"
    body = (
        f"User query:\n{query}\n\nExpert drafts:\n"
        + "\n\n---\n\n".join(drafts[:5])
    )
    return _generate(
        [
            {"role": "system", "content": SYNTH_SYSTEM},
            {"role": "user", "content": body},
        ],
        max_new_tokens=1024,
    )


def create_app():
    from fastapi import FastAPI
    from pydantic import BaseModel, Field

    app = FastAPI(title="Sarva Conductor Inference", version="1.0.0")

    class PlanRequest(BaseModel):
        query: str
        brain_version: str | None = None
        artifact: dict | None = None
        mode: str | None = "controller_plan"

    class SynthRequest(BaseModel):
        query: str
        drafts: list[str] = Field(default_factory=list)

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "mock": MOCK,
            "base_model": BASE_MODEL,
            "adapter": ADAPTER_PATH or ADAPTER_REPO,
        }

    @app.post("/plan")
    def plan(req: PlanRequest):
        plan_obj = plan_query(req.query)
        return {
            "plan": plan_obj,
            "controller_context": plan_obj.get("reason"),
            "hint": plan_obj.get("reason"),
            "brain_version": req.brain_version,
        }

    @app.post("/synthesize")
    def synth(req: SynthRequest):
        text = synthesize(req.query, req.drafts)
        return {"content": text, "answer": text}

    return app


def main() -> int:
    import uvicorn

    print("=" * 60)
    print("Sarva inference server")
    print(f"  mock={MOCK} host={HOST} port={PORT}")
    print(f"  adapter={ADAPTER_PATH or ADAPTER_REPO}")
    print("=" * 60)
    if not MOCK:
        try:
            _load_gpu()
        except Exception as exc:
            print(f"GPU load failed: {exc}", file=sys.stderr)
            print("Hint: set SARVA_INFERENCE_MOCK=1 for wiring tests without GPU.", file=sys.stderr)
            return 2
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

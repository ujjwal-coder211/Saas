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
BASE_MODEL = os.environ.get("BASE_MODEL", "unsloth/Qwen2.5-14B-Instruct-bnb-4bit").strip()
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


# --- HTTP server: Python stdlib only (no fastapi/uvicorn/pydantic/starlette) ---
# RunPod base images ship an incompatible fastapi/starlette combo that 422s on
# every request. http.server has zero third-party deps and cannot version-skew.

def _handle(path: str, body: dict) -> tuple[int, dict]:
    if path == "/health":
        return 200, {"ok": True, "mock": MOCK, "base_model": BASE_MODEL,
                     "adapter": ADAPTER_PATH or ADAPTER_REPO}
    if path == "/plan":
        plan_obj = plan_query(str(body.get("query", "")))
        return 200, {"plan": plan_obj, "controller_context": plan_obj.get("reason"),
                     "hint": plan_obj.get("reason"), "brain_version": body.get("brain_version")}
    if path == "/synthesize":
        text = synthesize(str(body.get("query", "")), body.get("drafts") or [])
        return 200, {"content": text, "answer": text}
    return 404, {"error": "not found", "paths": ["/health", "/plan", "/synthesize"]}


def _make_handler():
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload: dict) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            code, payload = _handle(self.path.split("?")[0], {})
            self._send(code, payload)

        def do_POST(self):  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(body, dict):
                    body = {}
            except Exception:
                body = {}
            try:
                code, payload = _handle(self.path.split("?")[0], body)
            except Exception as exc:  # never 500 the caller into a bad state
                code, payload = 200, {"error": f"handler_error: {exc}", "plan": None}
            self._send(code, payload)

        def log_message(self, fmt, *args):  # quieter logs
            print("[serve]", self.address_string(), fmt % args)

    return Handler


def main() -> int:
    from http.server import ThreadingHTTPServer

    print("=" * 60)
    print("Sarva inference server (stdlib http.server)")
    print(f"  mock={MOCK} host={HOST} port={PORT}")
    print(f"  base={BASE_MODEL}  adapter={ADAPTER_PATH or ADAPTER_REPO}")
    print("=" * 60)
    if not MOCK:
        try:
            _load_gpu()
        except Exception as exc:
            print(f"GPU load failed: {exc}", file=sys.stderr)
            print("Hint: set SARVA_INFERENCE_MOCK=1 for wiring tests without GPU.", file=sys.stderr)
            return 2
    server = ThreadingHTTPServer((HOST, PORT), _make_handler())
    print(f"Listening on http://{HOST}:{PORT}  (POST /plan, /synthesize; GET /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

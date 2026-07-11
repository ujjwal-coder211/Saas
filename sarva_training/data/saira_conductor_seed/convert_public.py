#!/usr/bin/env python3
"""
convert_public.py  —  fold REAL corpora into the Sarva conductor schema
=======================================================================
The template generator gives you the correct schema and a runnable seed. It does
NOT give you the quality/diversity the paper's §10 targets assume — that comes
from real corpora + teacher distillation. This module is the bridge: each mapper
takes a record from a public dataset and emits it in the SAME schema the seed
uses, so Stage-1/2 can be assembled from real sources and merged with the seed.

Mapping (paper source -> Sarva stage/category):
    §10.1 Stage 1
      The Stack v2 / CodeFeedback / OSS-Instruct  -> code_generation
      SWE-bench / real GitHub issues              -> debugging
      CodeReviewer + human-feedback corpora       -> code_review
      OSS pull requests / synthetic transforms    -> refactoring
      Design docs / ADRs                          -> architecture
    §10.2 Stage 2
      programmatic task-action pairs              -> file_ops
      Mind2Web / WebArena / CDP sequences         -> browser_automation
      OSWorld / TerminalBench                     -> shell_system
      synthetic 3-7 step workflows                -> multi_tool
      transcription->tool mappings                -> voice_to_action
      fail->retry->success trajectories           -> error_recovery

Each loader is a STUB: wire it to `datasets.load_dataset(...)` or your local
dumps. The mapping logic (how a raw record becomes a conductor turn) is real and
complete; only the I/O is left to your environment, because these corpora are
large downloads / license-gated and are not bundled here.

The distillation path (teacher outputs) is intentionally the same shape: run a
task through an OPEN-WEIGHT teacher (§4.4), capture its output, and pass it to
`distilled_to_record(...)`. Closed APIs are never distillation sources (§4.4).
"""
from __future__ import annotations
import json, hashlib
import sarva_schema as S


def _id(prefix, *parts):
    h = hashlib.sha1("::".join(map(str, parts)).encode()).hexdigest()[:10]
    return f"{prefix}-{h}"

def _record(user, sections, stage, category, rid, extra=None):
    messages = [
        {"role": "system", "content": S.SYSTEM_PROMPT},
        {"role": "user", "content": user},
        {"role": "assistant", "content": S.serialize_turn(sections)},
    ]
    return S.make_record(messages, stage, category, rid, extra=extra)


# ---------------------------------------------------------------------------
# STAGE 1 mappers
# ---------------------------------------------------------------------------
def code_task_to_record(prompt: str, solution: str, category: str,
                        gate: str = "execute_local", teacher: str | None = None) -> dict:
    """Map a (prompt, solution) pair from any Stage-1 source into the schema.

    gate='execute_local' -> the solution is presented as local execution.
    gate='delegate'      -> the solution is presented as a refined teacher draft
                            (pass `teacher` = the open-weight model name).
    """
    assert category in S.CODING_TASK_TYPES, category
    thr = S.threshold_for(category)
    conf = round(thr + (0.08 if gate == "execute_local" else -0.08), 3)
    assess = {"confidence": conf, "threshold": thr, "gate": gate,
              "stage_persona": "mature" if gate == "execute_local" else "mid",
              "rationale": "clears threshold" if gate == "execute_local" else "delegated then refined"}
    classify = {"task_type": category, "distribution": {category: 0.9}}
    sections = [("assess", assess), ("classify", classify)]
    if gate == "execute_local":
        sections += [("route", {"decision": "local", "models": []}),
                     ("execute", solution)]
    else:
        assert teacher in S.DISTILLATION_TEACHERS, "distillation teacher must be open-weight (§4.4)"
        sections += [("route", {"decision": "delegate", "models": [{"model": teacher, "weight": 1.0}]}),
                     ("refine", f"[verified + refined from {teacher} draft]\n{solution}")]
    return _record(prompt, sections, 1, category, _id("s1", category, prompt[:64]))


def load_the_stack_v2(limit=None):
    """STUB: yield (prompt, solution) from The Stack v2 / CodeFeedback / OSS-Instruct.
        from datasets import load_dataset
        ds = load_dataset("bigcode/the-stack-v2", split="train", streaming=True)
        for i, ex in enumerate(ds):
            if limit and i >= limit: break
            yield build_instruction(ex), ex["content"]   # your instruction synthesis
    """
    raise NotImplementedError("wire to datasets.load_dataset; see docstring")

def load_swebench(limit=None):
    """STUB: SWE-bench (princeton-nlp/SWE-bench) -> debugging records.
    Map (problem_statement, patch, test_patch) -> (prompt, solution).
    R_exec for RLEF later comes from actually running FAIL_TO_PASS tests."""
    raise NotImplementedError("wire to SWE-bench; map issue+patch -> (prompt, solution)")


# ---------------------------------------------------------------------------
# STAGE 2 mappers  (tool trajectories -> permission-tiered plans, §6.2/6.3)
# ---------------------------------------------------------------------------
def trajectory_to_record(instruction: str, actions: list[str], category: str,
                        untrusted: bool = False) -> dict:
    """Map a tool trajectory (ordered action names) into a Stage-2 record.
    `actions` must use the vocabulary of S.RISK_OF_ACTION so risk tiers resolve.
    Set untrusted=True for records whose content came from the web/files (Mind2Web,
    WebArena) so the one-tier escalation of §6.3 is applied and learned."""
    assert category in S.TOOL_TASK_TYPES, category
    plan = []
    for a in actions:
        base = S.RISK_OF_ACTION.get(a, "mutation")
        tier = S.escalate_tier(base) if untrusted else base
        approval = {"read": "auto", "mutation": "one_click", "dangerous": "typed_confirm"}[tier]
        step = {"tool": a, "risk": tier, "approval": approval}
        if untrusted:
            step["reason"] = "proximate cause is untrusted content; escalated one tier (§6.3)"
        plan.append(step)
    assess = {"confidence": 0.9, "threshold": S.threshold_for(category),
              "gate": "execute_local", "stage_persona": "mature",
              "rationale": "tool execution is performed locally by the harness"}
    exec_payload = {"plan": plan}
    if untrusted:
        exec_payload["untrusted_content_detected"] = True
    sections = [("assess", assess),
                ("classify", {"task_type": category, "distribution": {category: 0.9}}),
                ("route", {"decision": "local", "models": []}),
                ("execute", exec_payload)]
    return _record(instruction, sections, 2, category, _id("s2", category, instruction[:64]))


def load_mind2web(limit=None):
    """STUB: Mind2Web / WebArena -> browser_automation trajectories.
    Convert each action (CLICK/TYPE/NAVIGATE) to browser_* tool names, mark
    web-sourced content untrusted=True."""
    raise NotImplementedError("wire to Mind2Web/WebArena; map actions -> browser_* tools")

def load_osworld(limit=None):
    """STUB: OSWorld / TerminalBench -> shell_system trajectories (untrusted=False
    unless the step consumes fetched content)."""
    raise NotImplementedError("wire to OSWorld/TerminalBench")


# ---------------------------------------------------------------------------
# STAGE 4  (real RLEF rewards from actually running code)
# ---------------------------------------------------------------------------
def execution_to_reward_record(task_type: str, route: dict,
                               tests_result: str, quality: float,
                               cost: float, latency: float, user_fb: float = 0.0) -> dict:
    """Build a Stage-4 record from a REAL execution outcome (§8.1). `tests_result`
    in {'pass','runtime_error','parsed_untested'} maps to R_exec exactly as §8.1."""
    r_exec = {"pass": 1.0, "runtime_error": 0.0, "parsed_untested": 0.3}[tests_result]
    R = S.composite_reward(r_exec, quality, 1 - cost, 1 - latency, user_fb)
    reward = {"components": {"R_exec": r_exec, "R_quality": quality,
                             "R_cost": round(1 - cost, 3), "R_latency": round(1 - latency, 3),
                             "R_user": user_fb},
              "weights": S.REWARD_WEIGHTS, "R": R,
              "kept_for_ppo": abs(R) > S.RLEF_REWARD_ABS_FLOOR}
    sections = [("assess", {"confidence": 0.8, "threshold": S.threshold_for(task_type),
                            "gate": "delegate", "stage_persona": "mature", "rationale": "logged interaction"}),
                ("classify", {"task_type": task_type, "distribution": {task_type: 0.9}}),
                ("route", route), ("reward", reward)]
    return _record(f"[RLEF] {task_type}, tests={tests_result}", sections, 4, "rlef",
                   _id("s4", task_type, tests_result, R),
                   extra={"reward": R, "kept_for_ppo": reward["kept_for_ppo"], "chosen_route": route})


if __name__ == "__main__":
    # Demonstrate the mappers on tiny inline examples (no downloads needed).
    demos = [
        code_task_to_record(
            "In Python, write a token-bucket rate limiter.",
            "```python\nclass TokenBucket: ...\n```",
            category="code_generation", gate="execute_local"),
        code_task_to_record(
            "Fix the off-by-one in this pagination code.",
            "```python\n# corrected offset\n```",
            category="debugging", gate="delegate", teacher="deepseek-v3"),
        trajectory_to_record(
            "Read the staging changelog page and summarize it.",
            ["browser_navigate", "browser_read"],
            category="browser_automation", untrusted=True),
        execution_to_reward_record(
            "code_generation",
            {"decision": "delegate", "models": [{"model": "qwen2.5-coder-32b", "weight": 1.0}]},
            tests_result="pass", quality=0.82, cost=0.3, latency=0.4, user_fb=1.0),
    ]
    for d in demos:
        print(json.dumps(d, ensure_ascii=False)[:240], "...")
    print(f"\n{len(demos)} demo records built from the mappers.")

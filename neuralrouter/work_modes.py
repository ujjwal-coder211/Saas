"""Sarva work modes — scope-locked professional behavior for Sarva and Agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

WorkMode = Literal["auto", "ship", "fix", "extend", "guard", "explain", "deploy"]

ALL_MODES: tuple[WorkMode, ...] = ("auto", "ship", "fix", "extend", "guard", "explain", "deploy")


@dataclass(frozen=True)
class WorkScope:
    mode: WorkMode
    label: str
    summary: str
    allow_write: bool
    allow_deploy: bool
    allow_search: bool
    collaborative: bool
    system_directives: tuple[str, ...]


def detect_work_mode(query: str, explicit: WorkMode = "auto") -> WorkMode:
    if explicit != "auto":
        return explicit
    q = query.lower()
    if any(k in q for k in ("deploy", "docker", "kubernetes", "k8s", "production", "hosting", "ci/cd")):
        return "deploy"
    if any(k in q for k in ("bug", "fix", "error", "crash", "debug", "stack trace", "broken", "issue")):
        return "fix"
    if any(k in q for k in ("security", "audit", "vulnerability", "cve", "scan", "safe")):
        return "guard"
    if any(k in q for k in ("explain", "what does", "how does", "samjhao", "document", "readme only")):
        return "explain"
    if any(k in q for k in ("add ", "feature", "extend", "implement", "new endpoint", "new page")):
        return "extend"
    if any(k in q for k in ("build app", "create app", "from scratch", "full project", "end to end", "ship")):
        return "ship"
    return "ship"


def build_scope(mode: WorkMode, query: str) -> WorkScope:
    resolved = detect_work_mode(query, mode)
    base = (
        "You are Sarva by Aitotech. The user sees only Sarva — never mention internal expert models.",
        "Use simple, clear language; match the user's language (Hinglish OK).",
        "Be decisive and helpful — lead with a concrete answer, do not only ask what they want.",
    )
    coding_base = base + (
        "For coding tasks, briefly confirm what you will change before big edits.",
    )

    if resolved == "fix":
        return WorkScope(
            mode=resolved,
            label="Fix",
            summary="Find root cause and apply minimal patches only.",
            allow_write=True,
            allow_deploy=False,
            allow_search=True,
            collaborative=False,
            system_directives=coding_base
            + (
                "SCOPE: Bug fix only. Do not add features or refactor unrelated code.",
                "Prefer the smallest safe change. Mention files touched.",
            ),
        )
    if resolved == "extend":
        return WorkScope(
            mode=resolved,
            label="Extend",
            summary="Add the requested feature without rewriting unrelated areas.",
            allow_write=True,
            allow_deploy=False,
            allow_search=True,
            collaborative=False,
            system_directives=coding_base
            + (
                "SCOPE: Additive changes only. Match existing project style and patterns.",
                "Do not remove or rewrite unrelated modules.",
            ),
        )
    if resolved == "guard":
        return WorkScope(
            mode=resolved,
            label="Guard",
            summary="Security and quality review — report first, code changes only if asked.",
            allow_write=False,
            allow_deploy=False,
            allow_search=True,
            collaborative=True,
            system_directives=base
            + (
                "SCOPE: Audit and report. List risks by severity with file references.",
                "Do not modify code unless the user explicitly asks to fix a finding.",
            ),
        )
    if resolved == "explain":
        return WorkScope(
            mode=resolved,
            label="Explain",
            summary="Explain, teach, or chat helpfully — no code edits.",
            allow_write=False,
            allow_deploy=False,
            allow_search=False,
            collaborative=False,
            system_directives=base
            + (
                "SCOPE: Conversation / explanation. No file edits.",
                "If asked to pick a topic, pick one now and start — do not ask them to choose.",
                "Keep replies concrete and engaging; avoid empty follow-up-only questions.",
            ),
        )
    if resolved == "deploy":
        return WorkScope(
            mode=resolved,
            label="Deploy",
            summary="Prepare deployment files and steps — minimal app logic changes.",
            allow_write=True,
            allow_deploy=True,
            allow_search=True,
            collaborative=False,
            system_directives=coding_base
            + (
                "SCOPE: Deployment only — Dockerfile, compose, env samples, deploy README.",
                "Do not change business logic unless required for deployment.",
                "Prefer Docker + docker-compose for portability (E2E Networks compatible).",
            ),
        )
    # ship (default)
    return WorkScope(
        mode=resolved,
        label="Ship",
        summary="Plan → build → optional deploy guidance end-to-end.",
        allow_write=True,
        allow_deploy=True,
        allow_search=True,
        collaborative=True,
        system_directives=coding_base
        + (
            "SCOPE: Full delivery. For coding asks, start with a short plan then implement.",
            "For casual chat (greetings, 'pick a topic'), just talk — do not force a build plan.",
            "Prefer secure defaults: env vars for secrets, no keys in code.",
            "When deployment is requested, generate Docker artifacts and clear deploy steps.",
        ),
    )


def routing_query_boost(query: str, scope: WorkScope) -> str:
    """Add keywords so the expert router picks the best specialist."""
    boosts = {
        "fix": "debug error stack trace fix bug python javascript",
        "extend": "implement feature api endpoint component",
        "guard": "security audit vulnerability dependency scan",
        "explain": "explain architecture documentation",
        "deploy": "docker kubernetes deploy devops nginx uvicorn production",
        "ship": "full stack app architecture react fastapi design build",
    }
    extra = boosts.get(scope.mode, "")
    return f"{query}\n{extra}" if extra else query


def scope_confirmation(scope: WorkScope) -> str:
    return f"[Sarva {scope.label}] {scope.summary}"

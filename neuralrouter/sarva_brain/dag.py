"""Task decomposition into a subtask DAG — paper §7.1.

A complex request rarely maps to one task type. We decompose it into a directed
acyclic graph G = (V, E): vertices are subtasks, edges are dependencies. Each
vertex is routed independently (via `routing_policy.decide_routing`), and
vertices without mutual dependencies execute concurrently.

Honesty note: the decomposition is HEURISTIC (conjunction / step-marker splitting
plus a small dependency heuristic), not an LLM planner. It matches the paper's
worked example — "refactor auth to JWT, add tests, update the README" → a refactor
node with test + doc nodes depending on it — without claiming learned planning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from neuralrouter.sarva_brain.routing_policy import RoutingDecisionTrace, decide_routing

# Where a compound request tends to break into subtasks.
_SPLIT = re.compile(
    r"\s*(?:,\s*(?:and|then|after that)\s+|\band then\b|\bafter that\b|\balso\b|;\s*|\n+|\d+[\).]\s+)\s*",
    re.IGNORECASE,
)

# A subtask that consumes the product of an earlier code/build subtask.
_DEPENDENT = ("test", "tests", "readme", "doc", "document", "lint", "review", "deploy", "benchmark")
_PRODUCER = ("refactor", "implement", "build", "create", "add", "write", "fix", "migrate")


@dataclass
class DagNode:
    id: str
    text: str
    task_type: str = "general"
    deps: list[str] = field(default_factory=list)
    route: RoutingDecisionTrace | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "task_type": self.task_type,
            "deps": self.deps,
            "primary_model": self.route.primary_model if self.route else None,
            "routing_mode": self.route.routing_mode if self.route else None,
        }


def _clean(part: str) -> str:
    return part.strip(" .\t").strip()


def decompose(query: str) -> list[DagNode]:
    """Split a compound request into routed DAG nodes with inferred dependencies."""
    raw = [_clean(p) for p in _SPLIT.split(query or "") if _clean(p)]
    # Not actually compound — single node.
    if len(raw) <= 1:
        node = DagNode(id="v1", text=query.strip())
        node.route = decide_routing(node.text)
        node.task_type = node.route.task_type
        return [node]

    nodes: list[DagNode] = []
    producer_id: str | None = None
    for i, part in enumerate(raw, 1):
        nid = f"v{i}"
        node = DagNode(id=nid, text=part)
        node.route = decide_routing(part)
        node.task_type = node.route.task_type
        low = part.lower()
        # Dependent subtasks depend on the first producer subtask, if any.
        if producer_id and any(k in low for k in _DEPENDENT):
            node.deps = [producer_id]
        nodes.append(node)
        if producer_id is None and any(k in low for k in _PRODUCER):
            producer_id = nid
    return nodes


def execution_layers(nodes: list[DagNode]) -> list[list[str]]:
    """Topological layers: each inner list is a set of node ids that run in parallel."""
    remaining = {n.id: set(n.deps) for n in nodes}
    layers: list[list[str]] = []
    done: set[str] = set()
    while remaining:
        ready = sorted([nid for nid, deps in remaining.items() if deps <= done])
        if not ready:  # cycle guard — should not happen for a DAG
            ready = sorted(remaining)
        layers.append(ready)
        done |= set(ready)
        for nid in ready:
            remaining.pop(nid, None)
    return layers


def plan_dag(query: str) -> dict:
    """Full decomposition result: nodes + parallel execution layers + a summary."""
    nodes = decompose(query)
    layers = execution_layers(nodes)
    parallel = any(len(l) > 1 for l in layers)
    return {
        "nodes": [n.to_dict() for n in nodes],
        "layers": layers,
        "parallelizable": parallel,
        "node_count": len(nodes),
        "summary": " -> ".join("{" + ",".join(l) + "}" for l in layers),
    }

"""§7 tests — DAG decomposition + Q-scored synthesis."""

from __future__ import annotations

import pytest


def test_dag_single_node():
    from neuralrouter.sarva_brain.dag import decompose

    nodes = decompose("what is a python list")
    assert len(nodes) == 1
    assert nodes[0].id == "v1" and nodes[0].route is not None


def test_dag_compound_with_deps():
    from neuralrouter.sarva_brain.dag import plan_dag

    r = plan_dag("refactor auth to JWT, and add tests, then update the README")
    assert r["node_count"] == 3
    ids = [n["id"] for n in r["nodes"]]
    assert ids == ["v1", "v2", "v3"]
    # test + readme nodes depend on the producer (v1 refactor)
    deps = {n["id"]: n["deps"] for n in r["nodes"]}
    assert deps["v2"] == ["v1"] and deps["v3"] == ["v1"]
    # v1 runs first, then v2+v3 in parallel
    assert r["layers"][0] == ["v1"]
    assert set(r["layers"][1]) == {"v2", "v3"}
    assert r["parallelizable"] is True


def test_synthesis_defer_to_best():
    from neuralrouter.sarva_brain.synthesis import choose_strategy

    good = "def add(a, b):\n    return a + b\n"  # valid code, high syntax
    bad = "uh i think maybe todo"                # weak
    d = choose_strategy([("qwen", good, 0.9), ("mistral", bad, 0.3)])
    assert d.strategy in ("DEFER_TO_BEST", "ESCALATE")
    assert d.winner == "qwen"


def test_synthesis_vote_when_close():
    from neuralrouter.sarva_brain.synthesis import choose_strategy

    a = "The capital of France is Paris, a well-known fact."
    b = "France's capital is Paris; it is widely known."
    d = choose_strategy([("qwen", a, 0.6), ("kimi", b, 0.6)])
    assert d.strategy == "VOTE"


def test_synthesis_escalate_on_contradiction():
    from neuralrouter.sarva_brain.synthesis import choose_strategy

    valid = "def f(x):\n    return x * 2\n"
    broken = "def f(x)\n    return x *"  # syntax error
    d = choose_strategy([("qwen", valid, 0.7), ("mistral", broken, 0.7)])
    assert d.strategy == "ESCALATE"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

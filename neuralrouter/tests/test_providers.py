"""Multi-provider execution tests (paper §13): OpenRouter aggregator +
NVIDIA NIM first-party host, OpenAI-compatible, keys from env only."""

from __future__ import annotations

import importlib

import pytest


def _reload_clients(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import neuralrouter.config as cfg
    import neuralrouter.model_clients as mc

    importlib.reload(cfg)
    importlib.reload(mc)
    return mc


def test_nim_registered_as_provider(monkeypatch):
    mc = _reload_clients(monkeypatch, NVIDIA_NIM_API_KEY="nim-key")
    assert "NVIDIA NIM" in mc.PROVIDER_CLIENTS
    assert mc.PROVIDER_CLIENTS["NVIDIA NIM"] is mc._nim


def test_nim_client_uses_env_key_and_base_url(monkeypatch):
    mc = _reload_clients(
        monkeypatch,
        NVIDIA_NIM_API_KEY="nim-secret",
        NVIDIA_NIM_BASE_URL="https://integrate.api.nvidia.com/v1",
    )
    client = mc._nim()
    assert str(client.base_url).rstrip("/").endswith("integrate.api.nvidia.com/v1")
    assert client.api_key == "nim-secret"


def test_per_provider_key_validation_nim_model(monkeypatch):
    # NIM-served model must validate the NIM key, NOT OpenRouter's.
    mc = _reload_clients(
        monkeypatch, NVIDIA_NIM_API_KEY=None, OPENROUTER_API_KEY="or-key"
    )
    if "nemotron-nim" not in mc.REGISTRY:
        pytest.skip("nemotron-nim registry model not present")
    with pytest.raises(RuntimeError, match="NVIDIA_NIM_API_KEY"):
        mc._ensure_provider_key("nemotron-nim")


def test_openrouter_model_unaffected_by_missing_nim(monkeypatch):
    mc = _reload_clients(
        monkeypatch, NVIDIA_NIM_API_KEY=None, OPENROUTER_API_KEY="or-key"
    )
    # An OpenRouter-served model resolves fine without a NIM key.
    mc._ensure_provider_key("qwen")


def test_providers_status_reports_configured(monkeypatch):
    mc = _reload_clients(
        monkeypatch, NVIDIA_NIM_API_KEY="x", OPENROUTER_API_KEY="y"
    )
    st = mc.providers_status()
    assert st["nvidia_nim"] is True
    assert st["openrouter"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

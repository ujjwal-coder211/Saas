"""Wraps API calls to the 5 providers (OpenAI-compatible chat completions)."""

from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI

from neuralrouter.config import (
    DEEPINFRA_API_KEY,
    MAX_RETRIES,
    MOONSHOT_API_KEY,
    OPENROUTER_API_KEY,
    REQUEST_TIMEOUT_SECONDS,
)
from neuralrouter.router import REGISTRY

from neuralrouter.load_balancer import balancer

logger = logging.getLogger(__name__)

_clients: dict[str, AsyncOpenAI] = {}


def _get_client(name: str, api_key: str, base_url: str) -> AsyncOpenAI:
    if name not in _clients:
        # Placeholder key allows app to start; real calls fail until .env is set
        key = api_key or "not-configured"
        _clients[name] = AsyncOpenAI(api_key=key, base_url=base_url)
    return _clients[name]


def _openrouter() -> AsyncOpenAI:
    return _get_client("openrouter", OPENROUTER_API_KEY, "https://openrouter.ai/api/v1")


def _moonshot() -> AsyncOpenAI:
    return _get_client("moonshot", MOONSHOT_API_KEY, "https://api.moonshot.cn/v1")


def _deepinfra() -> AsyncOpenAI:
    return _get_client(
        "deepinfra", DEEPINFRA_API_KEY, "https://api.deepinfra.com/v1/openai"
    )


PROVIDER_CLIENTS = {
    "OpenRouter / DeepInfra": _openrouter,
    "OpenRouter": _openrouter,
    "Mistral AI / OpenRouter": _openrouter,
    "Z.ai / OpenRouter": _openrouter,
    "Alibaba / DeepInfra": _deepinfra,
    "Moonshot AI / OpenRouter": _moonshot,
}


def _client_for(model_id: str) -> tuple[AsyncOpenAI, dict]:
    meta = REGISTRY[model_id]
    provider = meta.get("provider", "")
    factory = PROVIDER_CLIENTS.get(provider, _openrouter)
    client = factory()
    style = meta.get("response_style", {})
    return client, {
        "model": meta["api_model_string"],
        "max_tokens": meta.get("max_tokens", 4096),
        "temperature": style.get("avg_temperature_used", 0.5),
    }


def _ensure_provider_key(model_id: str) -> None:
    meta = REGISTRY[model_id]
    provider = meta.get("provider", "")
    if "DeepInfra" in provider and not DEEPINFRA_API_KEY:
        raise RuntimeError("DEEPINFRA_API_KEY not set in environment")
    if "Moonshot" in provider and not MOONSHOT_API_KEY:
        raise RuntimeError("MOONSHOT_API_KEY not set in environment")
    if "OpenRouter" in provider or "Mistral" in provider or "Z.ai" in provider:
        if not OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY not set in environment")


def _provider_key(model_id: str) -> str:
    return REGISTRY[model_id].get("provider", model_id)


async def call_model(
    query: str,
    model_id: str,
    system_prompt: str | None = None,
    retry: int = 0,
) -> dict:
    if model_id not in REGISTRY:
        raise ValueError(f"unknown model_id: {model_id}")

    if retry > MAX_RETRIES:
        raise RuntimeError(f"Model {model_id} failed after {MAX_RETRIES} retries")

    if retry == 0:
        _ensure_provider_key(model_id)
        pk = _provider_key(model_id)
        if not balancer.is_available(pk):
            fallback = "qwen" if model_id != "qwen" else "mistral"
            return await call_model(query, fallback, system_prompt, retry + 1)

    client, gen = _client_for(model_id)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": query})

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=gen["model"],
                messages=messages,
                max_tokens=gen["max_tokens"],
                temperature=gen["temperature"],
            ),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        content = response.choices[0].message.content or ""
        usage = response.usage

        if len(content.strip()) < 10:
            balancer.record_failure(_provider_key(model_id))
            fallback = "qwen" if model_id != "qwen" else "mistral"
            logger.warning("Short response from %s, fallback to %s", model_id, fallback)
            return await call_model(query, fallback, system_prompt, retry + 1)

        balancer.record_success(_provider_key(model_id))
        return {
            "content": content,
            "model_used": model_id,
            "tokens": usage.total_tokens if usage else None,
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
        }

    except asyncio.TimeoutError:
        balancer.record_failure(_provider_key(model_id))
        fallback = "qwen" if model_id != "qwen" else "mistral"
        logger.warning("Timeout on %s, fallback to %s", model_id, fallback)
        return await call_model(query, fallback, system_prompt, retry + 1)
    except Exception:
        balancer.record_failure(_provider_key(model_id))
        logger.exception("API error model=%s retry=%s", model_id, retry)
        if retry >= MAX_RETRIES:
            raise
        fallback = "qwen" if model_id != "qwen" else "mistral"
        return await call_model(query, fallback, system_prompt, retry + 1)

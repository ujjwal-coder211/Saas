"""Central configuration — all secrets from environment only."""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SARVA_TRAINING_DIR = ROOT_DIR / "sarva_training"
REGISTRY_DIR = SARVA_TRAINING_DIR / "models_registry"

# API provider keys (never commit real values)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MOONSHOT_API_KEY = os.environ.get("MOONSHOT_API_KEY", "")
DEEPINFRA_API_KEY = os.environ.get("DEEPINFRA_API_KEY", "")

# First-party host (paper §13): NVIDIA NIM speaks the OpenAI-compatible interface.
# Aggregator (OpenRouter) + first-party host (NIM) is the multi-provider claim.
NVIDIA_NIM_API_KEY = os.environ.get("NVIDIA_NIM_API_KEY", "")
NVIDIA_NIM_BASE_URL = os.environ.get(
    "NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"
)

# Your product API keys — comma-separated for multiple clients
_raw_keys = os.environ.get("NEURALROUTER_API_KEYS", "")
NEURALROUTER_API_KEYS: set[str] = {
    k.strip() for k in _raw_keys.split(",") if k.strip()
}

# Dev mode: allow unauthenticated local requests (NEVER in production)
ALLOW_UNAUTHENTICATED = os.environ.get("NEURALROUTER_ALLOW_UNAUTH", "").lower() in (
    "1",
    "true",
    "yes",
)

# Limits
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("NEURALROUTER_TIMEOUT_S", "30"))
MAX_RETRIES = int(os.environ.get("NEURALROUTER_MAX_RETRIES", "2"))
MAX_COLLABORATIVE_EXPERTS = int(os.environ.get("NEURALROUTER_MAX_EXPERTS", "1"))
MAX_MESSAGE_CHARS = int(os.environ.get("NEURALROUTER_MAX_MESSAGE_CHARS", "32000"))
RATE_LIMIT_PER_MINUTE = int(os.environ.get("NEURALROUTER_RATE_LIMIT", "60"))
MAX_CONCURRENT_PER_CLIENT = int(os.environ.get("NEURALROUTER_MAX_CONCURRENT_PER_CLIENT", "5"))
MAX_GLOBAL_CONCURRENT = int(os.environ.get("NEURALROUTER_MAX_GLOBAL_CONCURRENT", "50"))

# Sarva vault security (training data — separate from client API keys)
SARVA_VAULT_HMAC_KEY = os.environ.get("SARVA_VAULT_HMAC_KEY", "")
SARVA_VAULT_ENCRYPTION_KEY = os.environ.get("SARVA_VAULT_ENCRYPTION_KEY", "")
SARVA_ADMIN_KEY = os.environ.get("SARVA_ADMIN_KEY", "")

# CORS — comma-separated origins; empty = no browser CORS (API clients only)
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get("NEURALROUTER_CORS_ORIGINS", "").split(",")
    if o.strip()
]

APP_NAME = os.environ.get("NEURALROUTER_APP_NAME", "Sarva API")
APP_VERSION = os.environ.get("NEURALROUTER_APP_VERSION", "0.1.0-sarva")

# SaaS infrastructure
DATABASE_URL = os.environ.get("DATABASE_URL", "")
REDIS_URL = os.environ.get("REDIS_URL", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO", "")
SAAS_PUBLIC_URL = os.environ.get("SAAS_PUBLIC_URL", "http://localhost:8000")
SAAS_ALLOW_PUBLIC_SIGNUP = os.environ.get("SAAS_ALLOW_PUBLIC_SIGNUP", "").lower() in (
    "1",
    "true",
    "yes",
)

# Website / agents proxy — POST /public/chat (no Bearer key; rate-limited)
PUBLIC_DEMO_ENABLED = os.environ.get("PUBLIC_DEMO_ENABLED", "").lower() in (
    "1",
    "true",
    "yes",
)
PUBLIC_DEMO_RATE_LIMIT = int(os.environ.get("PUBLIC_DEMO_RATE_LIMIT", "20"))
AGENTS_API_KEY = os.environ.get("AGENTS_API_KEY", "")

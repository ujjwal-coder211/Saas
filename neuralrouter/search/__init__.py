"""Aksh Search module."""

from neuralrouter.search.web_search import (
    AKSH_SEARCH_API_KEY,
    AKSH_SEARCH_ENABLED,
    AKSH_SEARCH_PROVIDER,
    SearchResult,
    aksh_search,
    needs_web_search,
)


def search_status() -> dict:
    """Public-safe search configuration snapshot for /health and dashboard."""
    return {
        "enabled": AKSH_SEARCH_ENABLED,
        "provider": AKSH_SEARCH_PROVIDER,
        "api_key_configured": bool(AKSH_SEARCH_API_KEY),
        "ready": AKSH_SEARCH_ENABLED and bool(AKSH_SEARCH_API_KEY),
    }

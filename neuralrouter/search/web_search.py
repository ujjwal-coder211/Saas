"""
Aksh Search — fetch latest information from the internet.

Set AKSH_SEARCH_API_KEY + AKSH_SEARCH_PROVIDER (tavily|serper|brave).
Omni Controller calls this when query needs fresh data.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

AKSH_SEARCH_ENABLED = os.environ.get("AKSH_SEARCH_ENABLED", "true").lower() in ("1", "true", "yes")
AKSH_SEARCH_API_KEY = os.environ.get("AKSH_SEARCH_API_KEY", "")
AKSH_SEARCH_PROVIDER = os.environ.get("AKSH_SEARCH_PROVIDER", "tavily").lower()
AKSH_SEARCH_MAX_RESULTS = int(os.environ.get("AKSH_SEARCH_MAX_RESULTS", "5"))

_FRESHNESS_PATTERNS = re.compile(
    r"\b("
    r"latest|today|current|now|202[4-9]|recent|update|news|"
    r"abhi|aaj|latest|nayi|naya|current price|stock|weather|"
    r"kaun jeeta|result|launch"
    r")\b",
    re.I,
)


@dataclass
class SearchResult:
    query: str
    snippets: list[str]
    sources: list[str]
    provider: str

    def as_context_block(self) -> str:
        if not self.snippets:
            return ""
        lines = ["## Aksh Search (latest web context)", ""]
        for i, (snip, src) in enumerate(zip(self.snippets, self.sources), 1):
            lines.append(f"{i}. {snip}")
            if src:
                lines.append(f"   Source: {src}")
        lines.append("")
        lines.append("Use the above for up-to-date facts. Cite uncertainty if sources conflict.")
        return "\n".join(lines)


def needs_web_search(query: str, mode: str = "auto") -> bool:
    """
    mode: auto | on | off
    Omni Controller uses this; 'auto' detects freshness intent.
    """
    if not AKSH_SEARCH_ENABLED or mode == "off":
        return False
    if mode == "on":
        return True
    return bool(_FRESHNESS_PATTERNS.search(query))


async def aksh_search(query: str) -> SearchResult:
    if not AKSH_SEARCH_API_KEY:
        logger.warning("AKSH_SEARCH_API_KEY not set — search skipped")
        return SearchResult(query=query, snippets=[], sources=[], provider="none")

    if AKSH_SEARCH_PROVIDER == "tavily":
        return await _search_tavily(query)
    if AKSH_SEARCH_PROVIDER == "serper":
        return await _search_serper(query)
    logger.warning("Unknown AKSH_SEARCH_PROVIDER=%s", AKSH_SEARCH_PROVIDER)
    return SearchResult(query=query, snippets=[], sources=[], provider=AKSH_SEARCH_PROVIDER)


async def _search_tavily(query: str) -> SearchResult:
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": AKSH_SEARCH_API_KEY,
        "query": query,
        "max_results": AKSH_SEARCH_MAX_RESULTS,
        "include_answer": True,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()

    snippets: list[str] = []
    sources: list[str] = []
    if data.get("answer"):
        snippets.append(str(data["answer"]))
        sources.append("tavily:answer")
    for hit in data.get("results", [])[:AKSH_SEARCH_MAX_RESULTS]:
        snippets.append(str(hit.get("content", hit.get("title", "")))[:800])
        sources.append(str(hit.get("url", "")))

    return SearchResult(query=query, snippets=snippets, sources=sources, provider="tavily")


async def _search_serper(query: str) -> SearchResult:
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": AKSH_SEARCH_API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, headers=headers, json={"q": query, "num": AKSH_SEARCH_MAX_RESULTS})
        r.raise_for_status()
        data = r.json()

    snippets = []
    sources = []
    for hit in data.get("organic", [])[:AKSH_SEARCH_MAX_RESULTS]:
        snippets.append(f"{hit.get('title', '')}: {hit.get('snippet', '')}")
        sources.append(str(hit.get("link", "")))

    return SearchResult(query=query, snippets=snippets, sources=sources, provider="serper")

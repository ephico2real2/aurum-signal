"""
web_search.py — On-Demand Web Search for AURUM Context
=======================================================
Build order: none — standalone utility, no internal deps.
Reusable search module: Google Custom Search API (extensible to Brave/SerpAPI).

Called by AURUM when a user query triggers live-search keywords
("speaking", "news", "happening", "live", etc.).  Results are
injected into the system prompt so Claude can answer with fresh data.

Also exposed via ATHENA GET /api/search?q=...

Env vars:
    GOOGLE_SEARCH_API_KEY  — Google Cloud API key with Custom Search enabled
    GOOGLE_SEARCH_CX       — Custom Search Engine ID (programmablesearchengine.google.com)
    WEB_SEARCH_CACHE_SEC   — Result cache TTL (default 120s)
    WEB_SEARCH_MAX_RESULTS — Max results per query (default 5, max 10)
    WEB_SEARCH_TIMEOUT     — HTTP timeout seconds (default 8)

Setup (one-time):
    1. https://console.cloud.google.com → Enable "Custom Search API"
    2. Create API key → paste as GOOGLE_SEARCH_API_KEY in .env
    3. https://programmablesearchengine.google.com → Create engine
       - Search the entire web
       - Copy Search Engine ID → paste as GOOGLE_SEARCH_CX in .env
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger("web_search")

# ── Config ──────────────────────────────────────────────────────────
GOOGLE_API_KEY   = os.environ.get("GOOGLE_SEARCH_API_KEY", "").strip()
GOOGLE_CX        = os.environ.get("GOOGLE_SEARCH_CX", "").strip()
CACHE_TTL        = int(os.environ.get("WEB_SEARCH_CACHE_SEC", "120"))
MAX_RESULTS      = min(int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "5")), 10)
TIMEOUT          = float(os.environ.get("WEB_SEARCH_TIMEOUT", "8"))

# Trigger keywords — AURUM checks the user query against these
SEARCH_TRIGGERS = frozenset({
    "news", "speaking", "speaks", "speech", "press conference",
    "happening", "happening now", "live", "right now", "still on",
    "conference", "announcement", "breaking", "latest",
    "trump", "powell", "fed chair", "lagarde", "boj", "ecb",
    "fomc", "nfp result", "cpi result", "gdp result",
})

# ── In-memory cache ─────────────────────────────────────────────────
_cache: dict[str, tuple[dict, float]] = {}


def _cache_key(query: str) -> str:
    return query.strip().lower()


# ── Public API ──────────────────────────────────────────────────────
def is_configured() -> bool:
    """True if API credentials are set."""
    return bool(GOOGLE_API_KEY and GOOGLE_CX)


def needs_search(query: str) -> bool:
    """Return True if the user query contains a live-search trigger keyword."""
    q = query.lower()
    return any(kw in q for kw in SEARCH_TRIGGERS)


def search(query: str, num_results: int | None = None, use_cache: bool = True) -> dict:
    """
    Search Google Custom Search API.  Returns dict with keys:
      query, fetched_at, results[], cached, error (optional)
    Each result: {title, snippet, link, published}
    """
    if not is_configured():
        return {"error": "GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_CX not set in .env",
                "query": query, "results": []}

    # Check cache
    key = _cache_key(query)
    if use_cache and key in _cache:
        result, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return {**result, "cached": True}

    n = min(num_results or MAX_RESULTS, 10)
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CX,
        "q": query,
        "num": n,
        "dateRestrict": "d1",   # last 24 hours
        "sort": "date",
    }

    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        err = f"HTTP {e.response.status_code}: {e.response.text[:200]}" if e.response else str(e)
        log.warning("web_search HTTP error: %s", err)
        return {"error": err, "query": query, "results": []}
    except Exception as e:
        log.warning("web_search error: %s", e)
        return {"error": str(e)[:200], "query": query, "results": []}

    items = data.get("items", [])
    results = []
    for item in items:
        # Try to extract publish time from metatags
        metatags = (item.get("pagemap") or {}).get("metatags") or [{}]
        published = metatags[0].get("article:published_time") if metatags else None
        results.append({
            "title":     item.get("title", "").strip(),
            "snippet":   item.get("snippet", "").strip(),
            "link":      item.get("link", ""),
            "published": published,
        })

    result = {
        "query":      query,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "results":    results,
        "cached":     False,
    }

    # Store in cache
    _cache[key] = (result, time.time())
    log.info("web_search: %d results for %r", len(results), query)
    return result


def format_for_context(search_result: dict) -> str:
    """Format search results as a context block for AURUM prompt injection."""
    if "error" in search_result:
        return f"[WEB SEARCH ERROR] {search_result['error']}"

    results = search_result.get("results", [])
    if not results:
        return f"[WEB SEARCH] No results for: {search_result.get('query', '?')}"

    lines = [
        f"WEB SEARCH: \"{search_result['query']}\" "
        f"(fetched {search_result.get('fetched_at', '?')}"
        f"{', cached' if search_result.get('cached') else ''}):"
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"  {i}. {r['title']}")
        lines.append(f"     {r['snippet']}")
        if r.get("published"):
            lines.append(f"     Published: {r['published']}")
    return "\n".join(lines)


def search_and_format(query: str, num_results: int | None = None) -> str:
    """Convenience: search + format in one call."""
    return format_for_context(search(query, num_results))


def clear_cache():
    """Clear all cached results."""
    _cache.clear()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if not is_configured():
        print("Set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX in .env")
        print("See docstring for setup instructions.")
    else:
        import sys
        q = " ".join(sys.argv[1:]) or "Trump speaking gold XAUUSD"
        print(search_and_format(q))

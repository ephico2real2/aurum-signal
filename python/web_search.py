"""
web_search.py — On-Demand Web Search for AURUM Context
=======================================================
Build order: none — standalone utility, no internal deps.
Reusable search module using Google News RSS (free, no API key).

Called by AURUM when a user query triggers live-search keywords
("speaking", "news", "happening", "live", etc.).  Results are
injected into the system prompt so Claude can answer with fresh data.

Also exposed via ATHENA GET /api/search?q=...

Env vars:
    WEB_SEARCH_CACHE_SEC   — Result cache TTL (default 120s)
    WEB_SEARCH_MAX_RESULTS — Max results per query (default 5, max 10)
    WEB_SEARCH_TIMEOUT     — HTTP timeout seconds (default 8)
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests

log = logging.getLogger("web_search")

# ── Config ──────────────────────────────────────────────────────────
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

_RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# ── In-memory cache ─────────────────────────────────────────────────
_cache: dict[str, tuple[dict, float]] = {}


def _cache_key(query: str) -> str:
    return query.strip().lower()


# ── Public API ──────────────────────────────────────────────────────
def is_available() -> bool:
    """True if web search can work. Always available (Google News RSS is free)."""
    return True


def needs_search(query: str) -> bool:
    """Return True if the user query contains a live-search trigger keyword."""
    q = query.lower()
    return any(kw in q for kw in SEARCH_TRIGGERS)


def search(query: str, num_results: int | None = None, use_cache: bool = True) -> dict:
    """
    Search Google News RSS for recent results.  Free, no API key.
    Returns dict with keys: query, fetched_at, results[], cached, source
    Each result: {title, snippet, link, published}
    """
    n = min(num_results or MAX_RESULTS, 10)

    key = _cache_key(query)
    if use_cache and key in _cache:
        result, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return {**result, "cached": True}

    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en&gl=US&ceid=US:en"
    )
    try:
        resp = requests.get(url, headers=_RSS_HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        log.warning("web_search error: %s", e)
        return {"error": str(e)[:200], "query": query, "results": [],
                "source": "google_news_rss"}

    results = []
    try:
        root = ET.fromstring(resp.text)
        channel = root.find("channel")
        items = (channel.findall("item") if channel is not None
                 else root.findall(".//item"))
        for item in items[:n]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if title:
                results.append({
                    "title": title,
                    "snippet": desc[:200] if desc else "",
                    "link": link,
                    "published": pub or None,
                })
    except ET.ParseError as e:
        log.debug("web_search RSS XML parse error: %s", e)

    result = {
        "query": query,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "cached": False,
        "source": "google_news_rss",
    }
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
    import sys
    q = " ".join(sys.argv[1:]) or "Trump speaking gold XAUUSD"
    print(search_and_format(q))

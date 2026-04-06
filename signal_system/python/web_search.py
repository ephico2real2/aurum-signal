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
    """True if Google CSE API credentials are set.  Web search still works
    without them via Google News RSS fallback (free, no key)."""
    return bool(GOOGLE_API_KEY and GOOGLE_CX)


def is_available() -> bool:
    """True if web search can work (CSE configured OR RSS fallback)."""
    return True  # RSS fallback always available


def needs_search(query: str) -> bool:
    """Return True if the user query contains a live-search trigger keyword."""
    q = query.lower()
    return any(kw in q for kw in SEARCH_TRIGGERS)


def search(query: str, num_results: int | None = None, use_cache: bool = True) -> dict:
    """
    Search for recent results.  Tries Google CSE first; falls back to
    Google News RSS (free, no API key) if CSE is not configured.
    Returns dict with keys: query, fetched_at, results[], cached, error (optional)
    Each result: {title, snippet, link, published}
    """
    if not is_configured():
        return _search_google_news_rss(query, num_results or MAX_RESULTS, use_cache)

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
        code = e.response.status_code if e.response else 0
        err = f"HTTP {code}: {e.response.text[:200]}" if e.response else str(e)
        log.warning("web_search CSE error (HTTP %s) — falling back to RSS: %s", code, err[:100])
        return _search_google_news_rss(query, n, use_cache)
    except Exception as e:
        log.warning("web_search CSE error — falling back to RSS: %s", e)
        return _search_google_news_rss(query, n, use_cache)

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


# ── Google News RSS fallback (free, no API key) ───────────────────
def _search_google_news_rss(query: str, num_results: int, use_cache: bool) -> dict:
    """
    Free fallback: Google News RSS search.  No API key needed.
    Returns same shape as CSE search() for interchangeability.
    """
    from urllib.parse import quote_plus
    import xml.etree.ElementTree as ET

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
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        log.warning("web_search RSS fallback error: %s", e)
        return {"error": str(e)[:200], "query": query, "results": [], "source": "google_news_rss"}

    results = []
    try:
        root = ET.fromstring(resp.text)
        channel = root.find("channel")
        items = (channel.findall("item") if channel is not None
                 else root.findall(".//item"))
        for item in items[:num_results]:
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
    log.info("web_search (RSS fallback): %d results for %r", len(results), query)
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
